"""Shared read model over the clean (decrypted) export.

Loads Contact / ChatInfo / ChatRelation and resolves, for any event, who the
peer is (1:1 name or group name) plus IN/OUT direction. Used by build_log.py
and export_media.py so the two stay consistent.

Semantics (established from real data):
  - Direction: 0 = IN (received), 1 = OUT (sent)
  - Events.ContactID = the message AUTHOR; the peer is computed from members.
"""
import os
import sqlite3
import unicodedata
from datetime import datetime

from . import config


def clean(s):
    """Strip Unicode format/bidi control chars (U+2066-2069, ZWJ, ...) that
    Viber embeds in contact names - they clutter the log and file names."""
    if not s:
        return s
    return "".join(ch for ch in s if unicodedata.category(ch) != "Cf").strip()

# All Messages columns the enrich helpers may look at.
MESSAGE_COLS = (
    "EventID", "Type", "Body", "PayloadPath", "ThumbnailPath", "StickerID",
    "Duration", "Info", "PGIsLiked", "PGLikeCount", "SelfReaction",
    "MembersReactions", "AdminsReactions",
)


class Model:
    """Contact/chat resolution over one export database."""

    def __init__(self, db):
        self.con = sqlite3.connect(db)
        self.con.row_factory = sqlite3.Row
        cur = self.con.cursor()
        self.contacts, self.chatinfo, self.chatrel = {}, {}, {}
        for r in cur.execute("SELECT ContactID,Name,Number,ClientName FROM Contact"):
            self.contacts[r["ContactID"]] = (r["Name"], r["Number"], r["ClientName"])
        for r in cur.execute("SELECT ChatID,Name FROM ChatInfo"):
            self.chatinfo[r["ChatID"]] = r["Name"]
        for r in cur.execute("SELECT ChatID,ContactID FROM ChatRelation"):
            self.chatrel.setdefault(r["ChatID"], []).append(r["ContactID"])
        self_num = config.self_number()
        self.selfids = {cid for cid, (nm, num, cl) in self.contacts.items()
                        if num and self_num and self_num in num}

    def clabel(self, cid):
        ct = self.contacts.get(cid)
        if not ct:
            return None
        nm = clean(ct[0] or ct[2] or "")
        num = clean(ct[1] or "")
        if nm and num:
            return f"{nm} ({num})"
        return nm or num or None

    @staticmethod
    def fmt(ms):
        try:
            return datetime.fromtimestamp(ms / 1000).strftime("%Y-%m-%d %H:%M:%S")
        except Exception:
            return str(ms)

    @staticmethod
    def iso(ms):
        try:
            return datetime.fromtimestamp(ms / 1000).isoformat(sep=" ", timespec="seconds")
        except Exception:
            return str(ms)

    def resolve(self, chat, author, direction):
        """Return (is_group, peer_label) for an event."""
        members = [m for m in self.chatrel.get(chat, []) if m]
        non_self = [m for m in members if m not in self.selfids]
        chatname = clean(self.chatinfo.get(chat) or "")
        if len(non_self) > 1:
            return True, chatname or "group"
        if len(non_self) == 1:
            peer = self.clabel(non_self[0])
        elif direction == 0:
            peer = self.clabel(author)
        else:
            peer = self.clabel(non_self[0]) if non_self else None
        return False, (peer or chatname or f"ChatID={chat}")

    def events(self):
        """Yield joined Events + Messages rows in chronological order."""
        cols = ",".join(f"m.{c} {c}" for c in MESSAGE_COLS)
        q = (f"SELECT e.TimeStamp ts, e.Direction dir, e.ChatID chat, "
             f"e.ContactID cid, {cols} "
             "FROM Events e JOIN Messages m ON m.EventID=e.EventID "
             "ORDER BY e.TimeStamp")
        return self.con.execute(q)

    def close(self):
        self.con.close()


def require_db(db=None):
    db = db or config.export_db_path()
    if not os.path.exists(db):
        raise SystemExit(f"[X] No export found: {db}\n"
                         "    Run first:  python viber.py export")
    return db
