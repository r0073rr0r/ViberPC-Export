"""Builds a readable chronological log from the clean (decrypted) export.

Works with both viber_export.db (live export) and viber_plain.db (offline 'open').

Produces two files in export/:
  - viber_messages.txt : human-readable log with text, media, stickers, likes
  - viber_log.jsonl    : one JSON object per event (for feeding to an AI)

If media was exported first (python viber.py media), the copied file paths are
linked into both outputs via export/media_index.csv.
"""
import csv
import json
import os

from . import config
from . import enrich
from .model import Model, require_db


def _media_index():
    """EventID -> saved relative media path, from export/media_index.csv."""
    path = os.path.join(config.EXPORT_DIR, "media_index.csv")
    index = {}
    if not os.path.exists(path):
        return index
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if row.get("saved_path"):
                index[row["EventID"]] = row["saved_path"]
    return index


def run(db=None, out=None):
    db = require_db(db)
    out = out or config.log_path()
    jsonl_out = os.path.splitext(out)[0].replace("_messages", "_log") + ".jsonl"
    if jsonl_out == out:
        jsonl_out = out + ".jsonl"

    model = Model(db)
    media_index = _media_index()

    entries = []
    for r in model.events():
        row = dict(r)
        is_group, peer = model.resolve(row["chat"], row["cid"], row["dir"])
        desc = enrich.describe(row)
        react_str, react_detail = enrich.reactions(row)
        saved = media_index.get(str(row["EventID"]))
        entries.append({
            "ts": row["ts"],
            "time": model.iso(row["ts"]),
            "direction": "OUT" if row["dir"] == 1 else "IN",
            "is_group": is_group,
            "peer": peer,
            "author": model.clabel(row["cid"]) or f"ContactID={row['cid']}",
            "kind": desc["kind"],
            "text": desc["text"].replace("\r", " ").replace("\n", " "),
            "caption": desc["caption"],
            "url": desc["url"],
            "media_file": saved or desc["media_path"] or desc["thumb_path"],
            "reactions": react_str,
            "reactions_detail": react_detail,
        })

    entries.sort(key=lambda e: e["ts"])

    with open(out, "w", encoding="utf-8") as f:
        f.write(f"# Viber log - {len(entries)} events "
                "(text, images, videos, files, stickers, links, reactions)\n")
        f.write("# DIR: IN=received, OUT=sent. In groups the message author is shown.\n\n")
        for e in entries:
            head = f"[{e['time']}] {e['direction']:<3}"
            who = f"[{e['peer']}] {e['author']}" if e["is_group"] else e["peer"]
            line = f"{head} {who}: {e['text']}"
            if e["reactions"]:
                line += f"   {{reactions: {e['reactions']}}}"
            f.write(line + "\n")

    with open(jsonl_out, "w", encoding="utf-8") as f:
        for e in entries:
            slim = {k: v for k, v in e.items() if k != "ts"}
            f.write(json.dumps(slim, ensure_ascii=False) + "\n")

    model.close()
    media_note = f"  (linked {len(media_index)} media files)" if media_index else ""
    print(f"[OK] {len(entries)} events -> {out}")
    print(f"[OK] {len(entries)} events -> {jsonl_out}{media_note}")
    return out
