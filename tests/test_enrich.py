"""Unit tests for the pure enrichment helpers (no database needed)."""
from viberkit import enrich
from viberkit.model import clean


def _row(**kw):
    base = {"Type": 1, "Subject": None, "Body": None, "PayloadPath": None,
            "ThumbnailPath": None, "StickerID": 0, "Duration": 0, "Info": None,
            "PGIsLiked": 0, "PGLikeCount": 0, "SelfReaction": None,
            "MembersReactions": None, "AdminsReactions": None}
    base.update(kw)
    return base


def test_text():
    d = enrich.describe(_row(Type=1, Body="hello"))
    assert d["kind"] == "text" and d["text"] == "hello"


def test_image_with_payload():
    d = enrich.describe(_row(Type=2, PayloadPath="C:/x/photo.jpg"))
    assert d["kind"] == "image"
    assert "photo.jpg" in d["text"] and d["media_path"].endswith("photo.jpg")


def test_image_missing_uses_thumbnail_note():
    d = enrich.describe(_row(Type=2, PayloadPath="", ThumbnailPath="C:/t/thumb.jpg"))
    assert d["kind"] == "image" and "thumbnail only" in d["text"]


def test_video_duration_is_milliseconds():
    d = enrich.describe(_row(Type=3, PayloadPath="C:/x/clip.mp4", Duration=22431))
    assert "0:22" in d["text"]          # 22431 ms -> 22 s


def test_file():
    d = enrich.describe(_row(Type=11, PayloadPath="C:/x/sheet.xlsx"))
    assert d["kind"] == "file" and "sheet.xlsx" in d["text"]


def test_link_uses_title():
    info = '{"URL":"https://e.com","Title":"Example"}'
    d = enrich.describe(_row(Type=9, Body="https://e.com", Info=info))
    assert d["kind"] == "link" and "Example" in d["text"] and d["url"] == "https://e.com"


def test_sticker():
    d = enrich.describe(_row(Type=4, StickerID=40103))
    assert d["kind"] == "sticker" and "40103" in d["text"]


def test_subject_fallback_when_no_body():
    d = enrich.describe(_row(Type=15, Body=None, Subject="Promo text"))
    assert d["kind"] == "post" and d["text"] == "Promo text"


def test_reaction_token_row_renders_emoji():
    info = '{"1on1reactions":{"reaction":2,"reaction_v1":2}}'
    d = enrich.describe(_row(Type=0, Body="6253459179658317583", Info=info))
    assert d["kind"] == "reaction" and d["text"] == "[reacted ❤️]"


def test_reaction_token_row_without_info():
    d = enrich.describe(_row(Type=0, Body="6253455409851423095"))
    assert d["kind"] == "reaction" and d["text"] == "[reaction]"


def test_system_fallback():
    d = enrich.describe(_row(Type=72))
    assert d["kind"] == "system" and d["text"] == "[system message]"


def test_pin_created():
    info = '{"pin":{"action":"create","text":"read this"}}'
    d = enrich.describe(_row(Type=15, Info=info))
    assert d["kind"] == "system" and "pinned a message" in d["text"] and "read this" in d["text"]


def test_pin_removed():
    info = '{"pin":{"action":"delete","text":"old"}}'
    d = enrich.describe(_row(Type=15, Info=info))
    assert d["kind"] == "system" and d["text"] == "\U0001F4CC unpinned a message"


def test_reactions_members_aggregate():
    summary, detail = enrich.reactions(_row(MembersReactions='{"1":2,"2":1}'))
    assert "×2" in summary and detail["others"] == {"1": 2, "2": 1}


def test_reactions_self_and_like_count():
    summary, _ = enrich.reactions(_row(SelfReaction="🥳", PGLikeCount=3))
    assert "you:🥳" in summary


def test_reactions_empty():
    summary, _ = enrich.reactions(_row())
    assert summary == ""


def test_context_reply_and_edit():
    info = '{"quote":{"text":"earlier msg"},"edit":{"token":1}}'
    ctx = enrich.context(_row(Info=info))
    assert ctx["reply_to"] == "earlier msg" and ctx["edited"] is True


def test_context_none():
    ctx = enrich.context(_row(Info="{}"))
    assert ctx["reply_to"] == "" and ctx["edited"] is False


def test_clean_strips_bidi_controls():
    assert clean(chr(0x2068) + "Ilija" + chr(0x2069)) == "Ilija"   # FSI ... PDI
    assert clean("plain") == "plain"
