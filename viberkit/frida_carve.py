"""Fallback method: carve decrypted SQLite pages out of Viber's RAM.

Uses neither the key nor Qt injection. Reads all rw- regions, extracts table-leaf pages
(0x0D, page 4096), parses records and classifies them by structural signature, then joins
Messages+Events+Contact+ChatInfo+ChatRelation into a chronological log.

Downside vs 'export': it only sees what Viber has loaded into the page cache (e.g. the
full address book is often NOT resident), and long messages on overflow pages are
truncated. Upside: works even when Qt symbols/connections differ (other version).
Requires Viber running.
"""
import time, struct, hashlib
from datetime import datetime
import frida
from .frida_common import require_viber
from . import config

PAGE = 4096
CHUNK = 4 * 1024 * 1024
MAX_REGION = 1024 * 1024 * 1024

JS = r"""
rpc.exports = {
  ranges: function () {
    return Process.enumerateRanges('rw-').map(function (r) { return { base: r.base.toString(), size: r.size }; });
  },
  read: function (baseStr, off, size) {
    try { return ptr(baseStr).add(off).readByteArray(size); } catch (e) { return null; }
  }
};
"""

_MAXLOCAL = PAGE - 35
_MINLOCAL = (PAGE - 12) * 32 // 255 - 23


def _varint(buf, p):
    val = 0
    for i in range(9):
        b = buf[p + i]
        if i == 8:
            return (val << 8) | b, 9
        val = (val << 7) | (b & 0x7F)
        if not (b & 0x80):
            return val, i + 1
    return val, 9


def _ssize(t):
    if t < 5:  return t
    if t == 5: return 6
    if t in (6, 7): return 8
    if t in (8, 9): return 0
    if t >= 12: return (t - 12) // 2 if t % 2 == 0 else (t - 13) // 2
    return 0


def _dec(t, raw):
    if t == 0: return None
    if 1 <= t <= 6: return int.from_bytes(raw, "big", signed=True)
    if t == 7: return struct.unpack(">d", raw)[0] if len(raw) == 8 else None
    if t == 8: return 0
    if t == 9: return 1
    if t >= 12 and t % 2 == 1: return raw.decode("utf-8", "replace")
    return bytes(raw)


def _cell(buf, cell_abs, page_end):
    p = cell_abs
    P, n1 = _varint(buf, p)
    rowid, n2 = _varint(buf, p + n1)
    cs = p + n1 + n2
    if P < 2:
        return None
    if P <= _MAXLOCAL:
        avail = P; need = cs + avail
    else:
        K = _MINLOCAL + (P - _MINLOCAL) % (PAGE - 4)
        avail = K if K <= _MAXLOCAL else _MINLOCAL
        need = cs + avail + 4
    if need > page_end:
        return None
    lim = cs + avail
    hlen, hn = _varint(buf, cs)
    hend = cs + hlen
    if hn > hlen or hend > lim:
        return None
    types = []
    q = cs + hn
    while q < hend:
        t, tn = _varint(buf, q); types.append(t); q += tn
    if q != hend:
        return None
    vals = []
    b = hend
    for t in types:
        sz = _ssize(t)
        if b + sz > lim:
            if t >= 13 and t % 2 == 1:
                vals.append(buf[b:lim].decode("utf-8", "replace"))
            else:
                vals.append(None)
            vals += [None] * (len(types) - len(vals))
            break
        vals.append(_dec(t, buf[b:b + sz])); b += sz
    else:
        if avail == P and b - cs != P:
            return None
    return rowid, vals


def _leaf(buf, i):
    if buf[i] != 0x0D:
        return None
    ncell = (buf[i + 3] << 8) | buf[i + 4]
    if ncell < 1 or ncell > 1000:
        return None
    if i + 8 + 2 * ncell > i + PAGE:
        return None
    page_end = i + PAGE
    recs = []
    last = -1
    for k in range(ncell):
        po = i + 8 + 2 * k
        off = (buf[po] << 8) | buf[po + 1]
        if off < 8 + 2 * ncell or off >= PAGE:
            return None
        rec = _cell(buf, i + off, page_end)
        if rec is None or rec[0] <= last:
            return None
        last = rec[0]
        recs.append(rec)
    return recs


def run(timeout=120):
    pid = require_viber()
    print(f"[i] Viber pid={pid}")
    s = frida.attach(pid)
    sc = s.create_script(JS)
    sc.load()
    api = getattr(sc, "exports_sync", None) or sc.exports

    events, messages, contacts, chatinfo, chatrel = {}, {}, {}, {}, {}

    def is_int(x): return isinstance(x, int)
    def is_str(x): return isinstance(x, str)

    def classify(rowid, v):
        # In this Viber build EventID/ContactID are rowid aliases -> column 0 is NULL and
        # the real key is the cell rowid. SQLite also omits trailing NULL columns, so we
        # classify by STABLE LEADING columns, not by the exact count.
        n = len(v)
        if v[0] is not None:
            if n in (2, 3) and is_int(v[0]) and is_int(v[1]) and 0 < v[0] < 10**9 and 0 < v[1] < 10**12:
                chatrel.setdefault(v[0], set()).add(v[1])
            return
        if n >= 12 and is_int(v[1]) and 1_000_000_000_000 <= v[1] <= 20_000_000_000_000 and v[2] in (0, 1):
            events.setdefault(rowid, {"ts": v[1], "dir": v[2], "chat": v[6], "contact": v[7]})
            return
        if n >= 15 and is_int(v[1]) and is_int(v[2]):
            body = v[4] if is_str(v[4]) else None
            prev = messages.get(rowid)
            if prev is None or (prev.get("body") is None and body is not None):
                messages[rowid] = {"body": body}
            return
        if is_str(v[1]) and is_str(v[2]):
            chatinfo.setdefault(rowid, v[1]); return
        if n >= 7 and (is_str(v[1]) or is_str(v[3]) or is_str(v[6])):
            c = contacts.setdefault(rowid, {"name": None, "number": None, "client": None})
            if c["name"] is None and is_str(v[1]):   c["name"] = v[1]
            if c["number"] is None and is_str(v[3]): c["number"] = v[3]
            if c["client"] is None and is_str(v[6]): c["client"] = v[6]

    seen = set()
    ranges = api.ranges()
    print(f"[i] rw- regions: {len(ranges)}")
    for r in ranges:
        size = r["size"]
        if size > MAX_REGION or size < PAGE:
            continue
        buf = bytearray()
        off = 0
        while off < size:
            nb = min(CHUNK, size - off)
            data = api.read(r["base"], off, nb)
            if data is not None:
                buf += data
            else:
                sub = 0
                while sub < nb:
                    mb = min(65536, nb - sub)
                    d2 = api.read(r["base"], off + sub, mb)
                    buf += d2 if d2 is not None else (b"\x00" * mb)
                    sub += mb
            off += nb
        idx = 0
        limit = len(buf) - PAGE
        while idx <= limit:
            j = buf.find(b"\x0d", idx)
            if j < 0 or j > limit:
                break
            recs = _leaf(buf, j)
            if recs:
                h = hashlib.blake2b(buf[j:j + PAGE], digest_size=16).digest()
                if h not in seen:
                    seen.add(h)
                    for rowid, vals in recs:
                        classify(rowid, vals)
            idx = j + 1
    s.detach()
    print(f"[i] Events={len(events)} Messages={len(messages)} Contacts={len(contacts)} "
          f"ChatInfo={len(chatinfo)} ChatRel={len(chatrel)} pages={len(seen)}")

    self_num = config.self_number()
    selfids = {cid for cid, c in contacts.items() if c["number"] and self_num and self_num in c["number"]}

    def clabel(cid):
        c = contacts.get(cid)
        if not c:
            return None
        nm = (c["name"] or c["client"] or "").strip()
        num = c["number"] or ""
        if nm and num: return f"{nm} ({num})"
        return nm or num or None

    def fmt(ms):
        try:    return datetime.fromtimestamp(ms / 1000).strftime("%Y-%m-%d %H:%M:%S")
        except: return str(ms)

    rows = []
    for eid, msg in messages.items():
        ev = events.get(eid)
        if not ev or not msg.get("body"):
            continue
        members = [m for m in chatrel.get(ev["chat"], set()) if m]
        non_self = [m for m in members if m not in selfids]
        if len(non_self) > 1:
            peer = (chatinfo.get(ev["chat"]) or "group").strip()
        elif len(non_self) == 1:
            peer = clabel(non_self[0])
        elif ev["dir"] == 0:
            peer = clabel(ev["contact"])
        else:
            peer = None
        peer = peer or (chatinfo.get(ev["chat"]) or "").strip() or f"ContactID={ev['contact']}"
        rows.append((ev["ts"], ev["dir"], peer, msg["body"].replace("\r", " ").replace("\n", " ")))

    rows.sort(key=lambda x: x[0])
    out = config.log_path()
    with open(out, "w", encoding="utf-8") as f:
        f.write(f"# Viber log (carved from memory) - {len(rows)} messages\n")
        f.write("# DIR: IN=received, OUT=sent. Names are partial (only what was resident in RAM).\n\n")
        for ts, d, peer, body in rows:
            f.write(f"[{fmt(ts)}] {'OUT' if d == 1 else 'IN '} {peer}: {body}\n")
    print(f"[OK] {len(rows)} messages -> {out}")
    return out
