"""Loads .env and project paths. All outputs go to export/ (gitignored)."""
import os, glob

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXPORT_DIR = os.path.join(ROOT, "export")


def _load_env():
    env = {}
    p = os.path.join(ROOT, ".env")
    if os.path.exists(p):
        for line in open(p, encoding="utf-8"):
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip()
    return env


ENV = _load_env()


def hexkey():
    return ENV.get("VIBER_HEXKEY", "").strip()


def salt():
    return ENV.get("VIBER_SALT", "").strip()


def _expand(p):
    """Support ~ and environment variables (e.g. ~/AppData/... or %APPDATA%/...)."""
    return os.path.expanduser(os.path.expandvars(p)) if p else p


def viber_db():
    """Path to the live Viber DB. From .env (with ~ and env vars) or auto-detected in %APPDATA%\\ViberPC."""
    p = _expand(ENV.get("VIBER_DB", "").strip())
    if p and os.path.exists(p):
        return p
    base = os.path.join(os.environ.get("APPDATA", ""), "ViberPC")
    hits = glob.glob(os.path.join(base, "*", "viber.db"))
    return hits[0] if hits else p


def stickers_dir():
    """Viber's on-disk sticker cache: %APPDATA%\\ViberPC\\data\\stickers."""
    return os.path.join(os.environ.get("APPDATA", ""), "ViberPC", "data", "stickers")


def self_number():
    """Your own account number - used to distinguish IN/OUT. From .env or from the DB path."""
    n = ENV.get("VIBER_SELF_NUMBER", "").strip()
    if n:
        return n
    p = viber_db()
    if p:
        for seg in os.path.normpath(p).split(os.sep):
            if seg.isdigit() and len(seg) >= 9:
                return seg
    return ""


def ensure_export_dir():
    os.makedirs(EXPORT_DIR, exist_ok=True)
    return EXPORT_DIR


def _ex(name):
    ensure_export_dir()
    return os.path.join(EXPORT_DIR, name)


def export_db_path():
    return _ex("viber_export.db")


def enc_db_path():
    return _ex("viber_enc.db")


def plain_db_path():
    return _ex("viber_plain.db")


def log_path():
    return _ex("viber_messages.txt")
