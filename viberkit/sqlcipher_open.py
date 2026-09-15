"""Offline method: open a COPY of the DB with SQLCipher using the captured key.

Does NOT require Viber running. Works on older Viber versions where the 'hexkey' is a
directly-usable SQLCipher key. On newer versions (like this one) Viber transforms the key
internally, so this FAILS - use 'export' or 'carve' instead.

Methods (--method):
  raw   : PRAGMA key = x'KEY'                       (key = captured hexkey)
  salt  : PRAGMA key = x'KEY+SALT' and cipher_salt   (explicit salt)
  kdf   : PBKDF2 over the key bytes + salt           (various iterations/hmac)
  all   : try everything in order (default)

On success it exports a clean file (viber_plain.db) via sqlcipher_export.
"""
import os, shutil, itertools, hashlib
from . import config


def _need_sqlcipher():
    try:
        import sqlcipher3
        return sqlcipher3
    except Exception:
        raise SystemExit("[X] Missing 'sqlcipher3-wheels'.  pip install sqlcipher3-wheels")


def _fresh_copy():
    src = config.viber_db()
    if not src or not os.path.exists(src):
        raise SystemExit(f"[X] Cannot find viber.db (VIBER_DB in .env?). Looked for: {src}")
    enc = config.enc_db_path()
    shutil.copy2(src, enc)
    for ext in ("-wal", "-shm", "-journal"):
        if os.path.exists(enc + ext):
            os.remove(enc + ext)
    return enc


def _variants(method, key, salt):
    """Generate (label, [pragmas]) combinations for the given method."""
    if method in ("raw", "all"):
        for compat in (4, 3):
            yield (f"raw compat{compat}",
                   [f"PRAGMA key = \"x'{key}'\";", f"PRAGMA cipher_compatibility = {compat};"])
    if method in ("salt", "all") and salt:
        for compat in (4, 3):
            yield (f"key+salt(96) compat{compat}",
                   [f"PRAGMA key = \"x'{key}{salt}'\";", f"PRAGMA cipher_compatibility = {compat};"])
            yield (f"key + cipher_salt compat{compat}",
                   [f"PRAGMA key = \"x'{key}'\";", f"PRAGMA cipher_salt = \"x'{salt}'\";",
                    f"PRAGMA cipher_compatibility = {compat};"])
    if method in ("kdf", "all") and salt:
        kb = bytes.fromhex(key)
        sb = bytes.fromhex(salt)
        hmac_kdf = {"HMAC_SHA512": "PBKDF2_HMAC_SHA512",
                    "HMAC_SHA256": "PBKDF2_HMAC_SHA256",
                    "HMAC_SHA1": "PBKDF2_HMAC_SHA1"}
        for algo, kiter, page, hm in itertools.product(
                ("sha512", "sha256", "sha1"),
                (256000, 64000, 12000, 4000, 1000, 1),
                (4096, 1024),
                ("HMAC_SHA512", "HMAC_SHA256", "HMAC_SHA1")):
            mk = hashlib.pbkdf2_hmac(algo, kb, sb, kiter, dklen=32).hex()
            yield (f"kdf {algo} iter={kiter} page={page} {hm}",
                   [f"PRAGMA key = \"x'{mk}'\";", "PRAGMA cipher = 'aes-256-cbc';",
                    f"PRAGMA cipher_page_size = {page};",
                    f"PRAGMA cipher_hmac_algorithm = {hm};",
                    f"PRAGMA cipher_kdf_algorithm = {hmac_kdf[hm]};"])


def run(method="all"):
    m = _need_sqlcipher()
    key, salt = config.hexkey(), config.salt()
    if not key:
        raise SystemExit("[X] No VIBER_HEXKEY in .env. Capture it:  python viber.py hookkey --write-env")
    enc = _fresh_copy()
    print(f"[i] copy: {enc}")

    tried = 0
    for label, pragmas in _variants(method, key, salt):
        tried += 1
        try:
            con = m.connect(enc); c = con.cursor()
            for stmt in pragmas:
                c.execute(stmt)
            c.execute("SELECT count(*) FROM sqlite_master;")
            n = c.fetchone()[0]
            print(f"[+] SUCCESS [{label}] tables in master={n}")
            plain = config.plain_db_path()
            if os.path.exists(plain):
                os.remove(plain)
            c.execute(f"ATTACH DATABASE '{plain}' AS plaintext KEY '';")
            c.execute("SELECT sqlcipher_export('plaintext');")
            c.execute("DETACH DATABASE plaintext;")
            con.close()
            print(f"[OK] clean file -> {plain}")
            print("    Now:  python viber.py log --db export/viber_plain.db")
            return plain
        except Exception as e:
            print(f"[-] [{label}] {str(e)[:70]}")
            try:
                con.close()
            except Exception:
                pass
    print(f"\n[X] None of the {tried} variants opened the database.")
    print("    The key is probably transformed internally (newer versions) - use 'export' or 'carve'.")
    return None
