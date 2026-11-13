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
    "EventID", "Type", "Subject", "Body", "PayloadPath", "ThumbnailPath",
    "StickerID", "Duration", "Info", "PGIsLiked", "PGLikeCount",
    "SelfReaction", "MembersReactions", "AdminsReactions",
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
        self.has_reactions_table = self._install_compat()

    def _install_compat(self):
        """Expose Viber 29.5+ data through the pre-29.5 shape the readers expect.

        29.5 dropped the Messages table (its columns now live in Events, with
        Type->MessageType and the sticker id in Body) and moved 1:1 reactions
        out of message rows into a separate Reactions table. A TEMP view keeps
        the export file untouched. Returns True when a Reactions table exists.
        """
        cur = self.con.cursor()
        have = {r[0] for r in cur.execute(
            "SELECT name FROM sqlite_master WHERE type IN ('table','view')")}
        if "Messages" in have:
            return False
        ev_cols = {r[1] for r in cur.execute("PRAGMA table_info(Events)")}
        if "MessageType" not in ev_cols:
            return False
        cur.execute(
            "CREATE TEMP VIEW Messages AS SELECT EventID, MessageType AS Type, "
            "NULL AS Subject, "
            "CASE WHEN MessageType=4 THEN '' ELSE Body END AS Body, "
            "PayloadPath, ThumbnailPath, "
            "CASE WHEN MessageType=4 THEN Body ELSE 0 END AS StickerID, "
            "Duration, Info, PGIsLiked, PGLikeCount, "
            "SelfReaction, MembersReactions, AdminsReactions "
            "FROM main.Events WHERE MessageType IS NOT NULL")
        if "Reactions" not in have:
            return False
        # Reactions used to be their own message rows (Type=0); keep showing
        # them as timeline events, with IN/OUT taken from who reacted.
        cur.execute("CREATE TEMP TABLE compat_self(ContactID INTEGER PRIMARY KEY)")
        cur.executemany("INSERT INTO compat_self VALUES (?)", [(c,) for c in self.selfids])
        return True

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
             "FROM Events e JOIN Messages m ON m.EventID=e.EventID")
        if self.has_reactions_table:
            # Synthetic rows shaped like the old 1:1 reaction messages. Negative
            # EventIDs so they never collide with real events (media index).
            special = {
                "EventID": "-r.ReactionID",
                "Type": "0",
                "Info": "json_object('1on1reactions', json_object('reaction', r.ReactionType))",
            }
            rcols = ",".join(f"{special.get(c, 'NULL')} {c}" for c in MESSAGE_COLS)
            q += (" UNION ALL SELECT r.TimeStamp ts, "
                  "CASE WHEN r.ContactID IN (SELECT ContactID FROM compat_self) "
                  "THEN 1 ELSE 0 END dir, "
                  f"r.ChatID chat, r.ContactID cid, {rcols} "
                  "FROM Reactions r")
        return self.con.execute(q + " ORDER BY ts")

    def close(self):
        self.con.close()


def require_db(db=None):
    db = db or config.export_db_path()
    if not os.path.exists(db):
        raise SystemExit(f"[X] No export found: {db}\n"
                         "    Run first:  python viber.py export")
    return db
