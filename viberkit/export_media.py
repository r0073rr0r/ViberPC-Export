"""Copies media referenced by the export into a self-contained export/media/ tree.

Viber does not store image bytes in viber.db - the database only keeps the
on-disk paths (PayloadPath = original, ThumbnailPath = thumbnail). This module
resolves those paths and copies whatever still exists into:

    export/media/<peer>/<date>_<eventid>_<name>

For received items that were never downloaded (only a thumbnail exists locally)
it saves the thumbnail instead. It also writes export/media_index.csv so
build_log.py can link each copied file back to its message.
"""
import csv
import os
import re
import shutil

from . import config
from . import enrich
from .model import Model, require_db

MEDIA_KINDS = ("image", "video", "file")
_SAFE = re.compile(r'[<>:"/\\|?*\x00-\x1f]+')


def _safe(name, fallback="unknown"):
    name = _SAFE.sub("_", (name or "").strip()).strip(". ")
    return (name or fallback)[:80]


def run(db=None, include_thumbs=True):
    db = require_db(db)
    model = Model(db)
    media_root = os.path.join(config.EXPORT_DIR, "media")
    os.makedirs(media_root, exist_ok=True)

    index_path = os.path.join(config.EXPORT_DIR, "media_index.csv")
    saved = copied_orig = copied_thumb = missing = 0

    with open(index_path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(["EventID", "time", "direction", "peer", "kind",
                         "status", "orig_path", "saved_path"])

        for r in model.events():
            row = dict(r)
            desc = enrich.describe(row)
            if desc["kind"] not in MEDIA_KINDS:
                continue

            _, peer = model.resolve(row["chat"], row["cid"], row["dir"])
            direction = "OUT" if row["dir"] == 1 else "IN"
            src, status = desc["media_path"], "original"
            if not (src and os.path.exists(src)):
                if include_thumbs and desc["thumb_path"] and os.path.exists(desc["thumb_path"]):
                    src, status = desc["thumb_path"], "thumbnail"
                else:
                    missing += 1
                    writer.writerow([row["EventID"], model.iso(row["ts"]), direction,
                                     peer, desc["kind"], "missing",
                                     desc["media_path"] or desc["thumb_path"], ""])
                    continue

            peer_dir = os.path.join(media_root, _safe(peer, "unknown"))
            os.makedirs(peer_dir, exist_ok=True)
            date = model.fmt(row["ts"])[:10]
            base = _safe(os.path.basename(src), f"file_{row['EventID']}")
            dest_name = f"{date}_{row['EventID']}_{base}"
            if status == "thumbnail":
                dest_name = "thumb_" + dest_name
            dest = os.path.join(peer_dir, dest_name)
            try:
                shutil.copy2(src, dest)
            except Exception as exc:
                missing += 1
                writer.writerow([row["EventID"], model.iso(row["ts"]), direction,
                                 peer, desc["kind"], f"error:{exc}", src, ""])
                continue

            rel = os.path.relpath(dest, config.EXPORT_DIR).replace(os.sep, "/")
            writer.writerow([row["EventID"], model.iso(row["ts"]), direction,
                             peer, desc["kind"], status, src, rel])
            saved += 1
            if status == "original":
                copied_orig += 1
            else:
                copied_thumb += 1

    model.close()
    print(f"[OK] media -> {media_root}")
    print(f"     originals: {copied_orig}   thumbnails: {copied_thumb}   "
          f"missing: {missing}   (index: {os.path.basename(index_path)})")
    return media_root
