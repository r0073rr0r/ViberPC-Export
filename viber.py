#!/usr/bin/env python3
"""viber.py - a tool to read YOUR OWN Viber Desktop database on YOUR OWN computer.

Methods (from recommended to auxiliary):

  export   Export the decrypted tables from the LIVE Viber connection to a clean file.  [RECOMMENDED]
           No key needed; uses Viber's already-unlocked engine. Viber must be running.
  log      Build a readable chronological log from the export (names, numbers, direction).
  all      = export + log

  carve    Fallback: carve messages out of Viber's RAM without the key (partial names).
  hookkey  Capture the SQLCipher key/salt that Viber sets (for the offline 'open').
  open     Offline: open a COPY of the DB with SQLCipher (works on older versions).
  schema   Print the schema (CREATE TABLE) from memory - useful if the version changes.
  doctor   Environment check (Viber, .env, dependencies).

All outputs go to  export/  (which is NOT committed). Examples:
  python viber.py all
  python viber.py export && python viber.py log
  python viber.py open --method all
  python viber.py hookkey --write-env
"""
import argparse
import os
import sys


def cmd_export(a):
    from viberkit import frida_export, build_log
    if frida_export.run(timeout=a.timeout) and a.then_log:
        build_log.run()


def cmd_log(a):
    from viberkit import build_log
    build_log.run(db=a.db)


def cmd_all(a):
    from viberkit import frida_export, build_log
    if frida_export.run(timeout=a.timeout):
        build_log.run()


def cmd_carve(a):
    from viberkit import frida_carve
    frida_carve.run(timeout=a.timeout)


def cmd_hookkey(a):
    from viberkit import frida_hookkey
    frida_hookkey.run(timeout=a.timeout, write_env=a.write_env)


def cmd_open(a):
    from viberkit import sqlcipher_open, build_log
    plain = sqlcipher_open.run(method=a.method)
    if plain and a.then_log:
        build_log.run(db=plain)


def cmd_schema(a):
    from viberkit import frida_schema
    frida_schema.run()


def cmd_doctor(a):
    from viberkit import config
    from viberkit.frida_common import get_viber_pid
    print("== doctor ==")
    pid = get_viber_pid()
    print(f"  Viber running  : {'yes (pid=%d)' % pid if pid else 'NO'}")
    db = config.viber_db()
    print(f"  viber.db       : {db}  {'(exists)' if db and os.path.exists(db) else '(NOT found)'}")
    print(f"  self number    : {config.self_number() or '(unknown)'}")
    print(f"  VIBER_HEXKEY   : {'set' if config.hexkey() else '(empty)'}")
    print(f"  export dir     : {config.EXPORT_DIR}")
    for mod in ("frida", "sqlcipher3"):
        try:
            __import__(mod); print(f"  dep {mod:11s}: ok")
        except Exception:
            print(f"  dep {mod:11s}: MISSING")


def main():
    p = argparse.ArgumentParser(
        description="Read your own Viber Desktop database (see README.md).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("export", help="export from the live connection [recommended]")
    s.add_argument("--timeout", type=int, default=90)
    s.add_argument("--no-log", dest="then_log", action="store_false", help="do not build the log afterwards")
    s.set_defaults(func=cmd_export, then_log=True)

    s = sub.add_parser("log", help="build the log from the export")
    s.add_argument("--db", default=None, help="path to a clean .db (default export/viber_export.db)")
    s.set_defaults(func=cmd_log)

    s = sub.add_parser("all", help="export + log")
    s.add_argument("--timeout", type=int, default=90)
    s.set_defaults(func=cmd_all)

    s = sub.add_parser("carve", help="fallback: carve from RAM")
    s.add_argument("--timeout", type=int, default=120)
    s.set_defaults(func=cmd_carve)

    s = sub.add_parser("hookkey", help="capture the SQLCipher key/salt")
    s.add_argument("--timeout", type=int, default=120)
    s.add_argument("--write-env", action="store_true", help="write to .env")
    s.set_defaults(func=cmd_hookkey)

    s = sub.add_parser("open", help="offline SQLCipher open of a copy")
    s.add_argument("--method", choices=("raw", "salt", "kdf", "all"), default="all")
    s.add_argument("--no-log", dest="then_log", action="store_false")
    s.set_defaults(func=cmd_open, then_log=True)

    s = sub.add_parser("schema", help="print the schema from memory")
    s.set_defaults(func=cmd_schema)

    s = sub.add_parser("doctor", help="environment check")
    s.set_defaults(func=cmd_doctor)

    args = p.parse_args()
    # UTF-8 output on the Windows console
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    args.func(args)


if __name__ == "__main__":
    main()
