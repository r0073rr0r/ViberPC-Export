"""Message enrichment: turn a raw Messages row into a human/AI-friendly summary.

Pure helpers (no DB) shared by build_log.py and export_media.py.

Message Type codes (established from real data):
  0, 1        text
  2           image (photo)         -> PayloadPath / ThumbnailPath
  3           video                 -> PayloadPath (+ Duration)
  9           link/URL preview      -> Info.Title / Info.Description / Info.URL
  11          file                  -> PayloadPath
  4           sticker               -> StickerID
  other       system / rich / bot   -> Body when present, else a type tag
"""
import json
import os
from collections import Counter

# Viber reaction id -> emoji (order matches the Viber reaction bar).
REACTION_EMOJI = {
    "1": "\U0001F44D",  # 👍 like
    "2": "❤️",  # ❤️ love
    "3": "\U0001F602",  # 😂 laugh
    "4": "\U0001F62E",  # 😮 wow
    "5": "\U0001F622",  # 😢 sad
    "6": "\U0001F621",  # 😡 angry
    "7": "\U0001F44E",  # 👎 dislike
}

MEDIA_KIND = {2: "image", 3: "video", 11: "file"}
TEXT_TYPES = {0, 1}


def parse_info(raw):
    """Info is a JSON string (or None). Return a dict, never raise."""
    if not raw:
        return {}
    try:
        val = json.loads(raw)
        return val if isinstance(val, dict) else {}
    except Exception:
        return {}


def _fmt_duration(millis):
    """Duration is stored in milliseconds. Render as m:ss."""
    try:
        seconds = int(millis) // 1000
    except (TypeError, ValueError):
        return None
    if seconds <= 0:
        return None
    return f"{seconds // 60}:{seconds % 60:02d}"


def describe(row):
    """Summarize one message row (a plain dict).

    Returns a dict:
      kind       : text | image | video | file | link | sticker | system
      text       : one-line human summary (already includes filename/caption)
      caption    : optional text that accompanied a media item ('' if none)
      media_path : original on-disk path for media, or ''
      thumb_path : original thumbnail path, or ''
      url        : link URL for link messages, or ''
    """
    mtype = row.get("Type")
    body = (row.get("Body") or "").strip()
    info = parse_info(row.get("Info"))
    sticker = row.get("StickerID")
    payload = (row.get("PayloadPath") or "").strip()
    thumb = (row.get("ThumbnailPath") or "").strip()

    if sticker and str(sticker) not in ("0", ""):
        return {"kind": "sticker", "text": f"[Sticker #{sticker}]",
                "caption": body, "media_path": "", "thumb_path": thumb, "url": ""}

    if mtype == 9:
        url = (info.get("URL") or body).strip()
        title = (info.get("Title") or "").strip()
        summary = f"[Link] {url}"
        if title:
            summary += f" — {title}"
        return {"kind": "link", "text": summary, "caption": "",
                "media_path": "", "thumb_path": thumb, "url": url}

    if payload or mtype in MEDIA_KIND:
        kind = MEDIA_KIND.get(mtype, "file")
        name = os.path.basename(payload) if payload else "(not downloaded)"
        label = {"image": "Image", "video": "Video", "file": "File"}[kind]
        dur = _fmt_duration(row.get("Duration"))
        tag = f"[{label}" + (f" {dur}" if dur else "") + f": {name}]"
        if not payload:
            tag += " (thumbnail only)" if thumb else " (missing on disk)"
        text = f"{tag} {body}".strip() if body else tag
        return {"kind": kind, "text": text, "caption": body,
                "media_path": payload, "thumb_path": thumb, "url": ""}

    if body:
        return {"kind": "text", "text": body, "caption": "",
                "media_path": "", "thumb_path": "", "url": ""}

    subject = (row.get("Subject") or "").strip()
    if subject:
        return {"kind": "post", "text": subject, "caption": "",
                "media_path": "", "thumb_path": "", "url": ""}

    return {"kind": "system", "text": f"[event type {mtype}]", "caption": "",
            "media_path": "", "thumb_path": "", "url": ""}


def context(row):
    """Reply/quote and edit context for a message.

    Returns {"reply_to": <quoted text or ''>, "edited": <bool>}.
    """
    info = parse_info(row.get("Info"))
    quote = info.get("quote")
    reply_to = ""
    if isinstance(quote, dict):
        reply_to = (quote.get("text") or "").strip()
    return {"reply_to": reply_to, "edited": "edit" in info}


def reactions(row):
    """Aggregate reactions/likes on a message.

    Returns (summary_str, detail_dict). summary_str is '' when there are none.
    """
    others = Counter()
    for col in ("MembersReactions", "AdminsReactions"):
        raw = row.get(col)
        if not raw:
            continue
        try:
            for rid, cnt in json.loads(raw).items():
                others[str(rid)] += int(cnt)
        except Exception:
            pass

    parts = []
    if others:
        parts.append(" ".join(
            f"{REACTION_EMOJI.get(rid, '#' + rid)}×{cnt}"
            for rid, cnt in sorted(others.items(), key=lambda kv: -kv[1])))

    self_reaction = (row.get("SelfReaction") or "").strip()
    if self_reaction:
        parts.append(f"you:{self_reaction}")
    elif row.get("PGIsLiked"):
        parts.append(f"you:{REACTION_EMOJI.get(str(row.get('PGIsLiked')), REACTION_EMOJI['1'])}")

    like_count = row.get("PGLikeCount") or 0
    if not others and like_count:
        parts.append(f"{REACTION_EMOJI['1']}×{like_count}")

    summary = "  ".join(p for p in parts if p)
    detail = {"others": dict(others), "self": self_reaction,
              "like_count": like_count}
    return summary, detail
