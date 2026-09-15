"""Builds a readable chronological log from the clean (decrypted) export.

Works with both viber_export.db (live export) and viber_plain.db (offline 'open').
Joins Events + Messages + Contact + ChatInfo + ChatRelation.

Semantics (established from real data):
  - Direction: 0 = IN (received), 1 = OUT (sent)
  - Events.ContactID = the message AUTHOR; the peer is computed from chat members.
"""
import os, sqlite3
from datetime import datetime
from . import config


def _load(db):
    con = sqlite3.connect(db); con.row_factory = sqlite3.Row; c = con.cursor()
    contacts, chatinfo, chatrel = {}, {}, {}
    for r in c.execute("SELECT ContactID,Name,Number,ClientName FROM Contact"):
        contacts[r["ContactID"]] = (r["Name"], r["Number"], r["ClientName"])
    for r in c.execute("SELECT ChatID,Name FROM ChatInfo"):
        chatinfo[r["ChatID"]] = r["Name"]
    for r in c.execute("SELECT ChatID,ContactID FROM ChatRelation"):
        chatrel.setdefault(r["ChatID"], []).append(r["ContactID"])
    return con, c, contacts, chatinfo, chatrel


def run(db=None, out=None):
    db = db or config.export_db_path()
    out = out or config.log_path()
    if not os.path.exists(db):
        raise SystemExit(f"[X] No export found: {db}\n    Run first:  python viber.py export")

    self_num = config.self_number()
    con, c, contacts, chatinfo, chatrel = _load(db)
    selfids = {cid for cid, (nm, num, cl) in contacts.items()
               if num and self_num and self_num in num}

    def clabel(cid):
        ct = contacts.get(cid)
        if not ct:
            return None
        nm = (ct[0] or ct[2] or "").strip()
        num = ct[1] or ""
        if nm and num:
            return f"{nm} ({num})"
        return nm or num or None

    def fmt(ms):
        try:
            return datetime.fromtimestamp(ms / 1000).strftime("%Y-%m-%d %H:%M:%S")
        except Exception:
            return str(ms)

    def resolve(chat, author, direction):
        members = [m for m in chatrel.get(chat, []) if m]
        non_self = [m for m in members if m not in selfids]
        chatname = (chatinfo.get(chat) or "").strip()
        if len(non_self) > 1:                       # group
            return True, chatname or "group"
        if len(non_self) == 1:                      # 1:1
            peer = clabel(non_self[0])
        elif direction == 0:
            peer = clabel(author)                   # incoming -> author is the peer
        else:
            peer = clabel(non_self[0]) if non_self else None
        return False, (peer or chatname or f"ChatID={chat}")

    rows = []
    q = """SELECT e.TimeStamp ts, e.Direction dir, e.ChatID chat, e.ContactID cid, m.Body body
           FROM Events e JOIN Messages m ON m.EventID=e.EventID
           WHERE m.Body IS NOT NULL AND m.Body<>''"""
    for r in c.execute(q):
        is_group, peer = resolve(r["chat"], r["cid"], r["dir"])
        author = clabel(r["cid"]) or f"ContactID={r['cid']}"
        body = r["body"].replace("\r", " ").replace("\n", " ")
        rows.append((r["ts"], r["dir"], is_group, peer, author, body))
    con.close()

    rows.sort(key=lambda x: x[0])
    with open(out, "w", encoding="utf-8") as f:
        f.write(f"# Viber log - {len(rows)} messages\n")
        f.write("# DIR: IN=received, OUT=sent. In groups the message author is also shown.\n\n")
        for ts, d, grp, peer, author, body in rows:
            dl = "OUT" if d == 1 else "IN "
            if grp:
                f.write(f"[{fmt(ts)}] {dl} [{peer}] {author}: {body}\n")
            else:
                f.write(f"[{fmt(ts)}] {dl} {peer}: {body}\n")

    print(f"[OK] {len(rows)} messages -> {out}")
    return out
