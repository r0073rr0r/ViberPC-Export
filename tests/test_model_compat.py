"""Model must read both the pre-29.5 (Messages table) and 29.5+ (merged Events) schemas."""
import json
import sqlite3

from viberkit import config, enrich
from viberkit.model import Model

COMMON = """
CREATE TABLE Contact (ContactID INTEGER PRIMARY KEY, Name TEXT, Number TEXT, ClientName TEXT);
CREATE TABLE ChatInfo (ChatID INTEGER PRIMARY KEY, Name TEXT);
CREATE TABLE ChatRelation (ChatID INTEGER, ContactID INTEGER);
INSERT INTO Contact VALUES (1, 'Me', '+381600000001', NULL), (2, 'Ana', '+381600000002', NULL);
INSERT INTO ChatInfo VALUES (10, NULL);
INSERT INTO ChatRelation VALUES (10, 1), (10, 2);
"""

NEW_SCHEMA = COMMON + """
CREATE TABLE Events (EventID INTEGER PRIMARY KEY, TimeStamp INTEGER, Direction INTEGER,
  Type INTEGER, ChatID INTEGER, ContactID INTEGER, Token INTEGER, MessageType INTEGER,
  Body TEXT, PayloadPath TEXT, ThumbnailPath TEXT, Duration INTEGER, Info TEXT,
  PGIsLiked INTEGER, PGLikeCount INTEGER, SelfReaction TEXT, MembersReactions TEXT,
  AdminsReactions TEXT, CallType INTEGER);
CREATE TABLE Reactions (ReactionID INTEGER PRIMARY KEY, ChatID INTEGER, MessageToken INTEGER,
  ContactID INTEGER, ReactionType TEXT, TimeStamp INTEGER);
INSERT INTO Events (EventID, TimeStamp, Direction, Type, ChatID, ContactID, Token, MessageType, Body)
  VALUES (1, 1000, 0, 0, 10, 2, 555, 1, 'hello'),
         (2, 2000, 1, 0, 10, 1, 556, 4, '40103'),
         (3, 2500, 0, 1, 10, 2, 557, NULL, NULL);
INSERT INTO Reactions VALUES (7, 10, 555, 1, '2', 3000), (8, 10, 556, 2, '🥳', 4000);
"""

OLD_SCHEMA = COMMON + """
CREATE TABLE Events (EventID INTEGER PRIMARY KEY, TimeStamp INTEGER, Direction INTEGER,
  ChatID INTEGER, ContactID INTEGER);
CREATE TABLE Messages (EventID INTEGER PRIMARY KEY, Type INTEGER, Subject TEXT, Body TEXT,
  PayloadPath TEXT, ThumbnailPath TEXT, StickerID INTEGER, Duration INTEGER, Info TEXT,
  PGIsLiked INTEGER, PGLikeCount INTEGER, SelfReaction TEXT, MembersReactions TEXT,
  AdminsReactions TEXT);
INSERT INTO Events VALUES (1, 1000, 0, 10, 2), (2, 2000, 1, 10, 1);
INSERT INTO Messages (EventID, Type, Body, StickerID) VALUES (1, 1, 'hello', 0), (2, 4, '', 40103);
"""


def _model(tmp_path, monkeypatch, schema):
    monkeypatch.setattr(config, "self_number", lambda: "381600000001")
    db = tmp_path / "export.db"
    con = sqlite3.connect(db)
    con.executescript(schema)
    con.close()
    return Model(str(db))


def test_text_and_sticker_both_schemas(tmp_path, monkeypatch):
    for name, schema in (("old", OLD_SCHEMA), ("new", NEW_SCHEMA)):
        sub = tmp_path / name
        sub.mkdir()
        model = _model(sub, monkeypatch, schema)
        rows = [dict(r) for r in model.events() if r["EventID"] > 0]
        model.close()
        assert [enrich.describe(r)["kind"] for r in rows] == ["text", "sticker"], name
        assert enrich.describe(rows[1])["text"] == "[Sticker #40103]", name


def test_new_schema_skips_calls_and_adds_reactions(tmp_path, monkeypatch):
    model = _model(tmp_path, monkeypatch, NEW_SCHEMA)
    rows = [dict(r) for r in model.events()]
    model.close()
    assert [r["EventID"] for r in rows] == [1, 2, -7, -8]       # call (MessageType NULL) skipped
    mine, theirs = rows[2], rows[3]
    assert mine["dir"] == 1 and theirs["dir"] == 0              # direction from who reacted
    assert json.loads(mine["Info"]) == {"1on1reactions": {"reaction": "2"}}
    assert enrich.describe(mine)["text"] == "[reacted ❤️]"
    assert enrich.describe(theirs)["text"] == "[reacted 🥳]"     # 29.5 stores raw emoji


def test_reaction_emoji_mapping():
    # pylint: disable=protected-access
    assert enrich._reaction_emoji("1") == enrich.REACTION_EMOJI["1"]
    assert enrich._reaction_emoji("🫡") == "🫡"
    assert enrich._reaction_emoji("") is None
    assert enrich._reaction_emoji("0") is None
    assert enrich._reaction_emoji(None) is None
