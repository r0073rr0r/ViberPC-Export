"""Builds a browsable HTML view of the conversations (export/viber_chats.html).

A single self-contained page: a sidebar of contacts/chats on the left, chat
bubbles on the right, with images, videos, stickers and files embedded via
their relative paths under export/media/ (so open the file from export/).
Run `python viber.py media` first so the media files exist.
"""
import csv
import html
import os

from . import config
from . import enrich
from .model import Model, require_db

_IMG_EXT = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"}
_VID_EXT = {".mp4", ".webm", ".mov", ".m4v", ".3gp"}

_CSS = """
:root{--bg:#0b141a;--panel:#111b21;--in:#202c33;--out:#005c4b;--txt:#e9edef;
--muted:#8696a0;--line:#222d34;--accent:#00a884}
*{box-sizing:border-box}
body{margin:0;font:14px/1.5 -apple-system,Segoe UI,Roboto,sans-serif;
background:var(--bg);color:var(--txt);display:flex;height:100vh;overflow:hidden}
#side{width:320px;flex:none;background:var(--panel);border-right:1px solid var(--line);
overflow-y:auto}
#side h1{font-size:15px;padding:16px;margin:0;position:sticky;top:0;background:var(--panel);
border-bottom:1px solid var(--line)}
.peer{padding:10px 16px;cursor:pointer;border-bottom:1px solid var(--line);display:flex;
justify-content:space-between;gap:8px}
.peer:hover{background:var(--in)}.peer.active{background:var(--in)}
.peer .n{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.peer .c{color:var(--muted);font-size:12px;flex:none}
#main{flex:1;overflow-y:auto;padding:24px;background-image:linear-gradient(#0b141a,#0b141a)}
.chat{display:none;max-width:900px;margin:0 auto}.chat.show{display:block}
.chat h2{position:sticky;top:-24px;background:var(--bg);padding:8px 0;margin:0 0 12px}
.msg{max-width:70%;margin:6px 0;padding:6px 10px;border-radius:10px;background:var(--in);
clear:both;float:left;white-space:pre-wrap;word-wrap:break-word}
.msg.out{float:right;background:var(--out)}
.msg .who{font-size:12px;color:var(--accent);font-weight:600;margin-bottom:2px}
.msg .meta{font-size:11px;color:var(--muted);margin-top:3px;text-align:right}
.msg .quote{border-left:3px solid var(--accent);padding:2px 8px;margin:2px 0 4px;
background:rgba(0,0,0,.2);color:var(--muted);font-size:13px;border-radius:4px}
.msg img{max-width:260px;max-height:260px;border-radius:6px;display:block;margin:3px 0}
.msg img.stk{max-width:120px}
.msg video{max-width:280px;border-radius:6px;display:block;margin:3px 0}
.msg a{color:#53bdeb}.react{font-size:12px;margin-top:2px}
.edited{color:var(--muted);font-size:11px}
"""

_JS = """
function show(i){
 document.querySelectorAll('.chat').forEach(c=>c.classList.remove('show'));
 document.querySelectorAll('.peer').forEach(p=>p.classList.remove('active'));
 document.getElementById('chat'+i).classList.add('show');
 document.getElementById('peer'+i).classList.add('active');
 document.getElementById('main').scrollTop=0;
}
window.onload=()=>show(0);
"""


def _media_index():
    path = os.path.join(config.EXPORT_DIR, "media_index.csv")
    index = {}
    if os.path.exists(path):
        with open(path, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                if row.get("saved_path"):
                    index[row["EventID"]] = row["saved_path"]
    return index


def _media_html(rel):
    ext = os.path.splitext(rel)[1].lower()
    src = html.escape(rel)
    if ext in _VID_EXT:
        return f'<video controls src="{src}"></video>'
    if ext in _IMG_EXT:
        cls = " class=stk" if "/stickers/" in rel else ""
        return f'<a href="{src}" target=_blank><img{cls} src="{src}" loading=lazy></a>'
    name = html.escape(os.path.basename(rel))
    return f'<a href="{src}" target=_blank>\U0001F4CE {name}</a>'


def run(db=None, out=None):
    db = require_db(db)
    out = out or os.path.join(config.EXPORT_DIR, "viber_chats.html")
    model = Model(db)
    media_index = _media_index()

    chats = {}   # peer -> list of msg dicts;  order -> last ts
    last_ts = {}
    for r in model.events():
        row = dict(r)
        is_group, peer = model.resolve(row["chat"], row["cid"], row["dir"])
        desc = enrich.describe(row)
        ctx = enrich.context(row)
        react, _ = enrich.reactions(row)
        chats.setdefault(peer, []).append({
            "ts": row["ts"], "time": model.fmt(row["ts"]),
            "out": row["dir"] == 1, "is_group": is_group,
            "author": model.clabel(row["cid"]) or "",
            "kind": desc["kind"], "text": desc["text"], "caption": desc["caption"],
            "media": media_index.get(str(row["EventID"]), ""),
            "reply": ctx["reply_to"], "edited": ctx["edited"], "react": react,
        })
        last_ts[peer] = max(last_ts.get(peer, 0), row["ts"])
    model.close()

    peers = sorted(chats, key=lambda p: last_ts[p], reverse=True)

    parts = ['<meta charset="utf-8"><meta name="viewport" '
             'content="width=device-width,initial-scale=1">'
             f"<style>{_CSS}</style><title>Viber chats</title>",
             '<div id="side"><h1>\U0001F4AC Viber chats</h1>']
    for i, peer in enumerate(peers):
        parts.append(f'<div class="peer" id="peer{i}" onclick="show({i})">'
                     f'<span class="n">{html.escape(peer)}</span>'
                     f'<span class="c">{len(chats[peer])}</span></div>')
    parts.append('</div><div id="main">')

    for i, peer in enumerate(peers):
        parts.append(f'<div class="chat" id="chat{i}"><h2>{html.escape(peer)}</h2>')
        for m in chats[peer]:
            cls = "msg out" if m["out"] else "msg"
            parts.append(f'<div class="{cls}">')
            if m["is_group"] and not m["out"] and m["author"]:
                parts.append(f'<div class="who">{html.escape(m["author"])}</div>')
            if m["reply"]:
                parts.append(f'<div class="quote">{html.escape(m["reply"][:140])}</div>')
            if m["media"]:
                parts.append(_media_html(m["media"]))
                body = m["caption"]
            else:
                body = m["text"]
            if body:
                parts.append(html.escape(body))
            if m["react"]:
                parts.append(f'<div class="react">{html.escape(m["react"])}</div>')
            edited = ' <span class="edited">(edited)</span>' if m["edited"] else ""
            parts.append(f'<div class="meta">{html.escape(m["time"])}{edited}</div>')
            parts.append("</div>")
        parts.append("</div>")

    parts.append(f"</div><script>{_JS}</script>")
    with open(out, "w", encoding="utf-8") as f:
        f.write("".join(parts))

    print(f"[OK] {len(peers)} chats -> {out}")
    return out
