<h1 align="center">📤 ViberPC-Export</h1>

<p align="center">
    Read and export <strong>your own</strong> Viber Desktop (ViberPC) message history on
    <strong>your own</strong> Windows computer — into a clean, readable chronological log.
    No key required; it uses the running Viber's already-unlocked SQLCipher engine.
</p>

<p align="center">
    <a href="https://github.com/r0073rr0r/ViberPC-Export/actions/workflows/pylint.yml"><img src="https://github.com/r0073rr0r/ViberPC-Export/actions/workflows/pylint.yml/badge.svg" alt="Pylint"></a>
    <a href="LICENSE"><img src="https://img.shields.io/github/license/r0073rr0r/ViberPC-Export" alt="License: GPL-3.0"></a>
    <img src="https://img.shields.io/badge/python-3.10%2B-blue?logo=python&logoColor=white" alt="Python 3.10+">
    <img src="https://img.shields.io/badge/platform-Windows-0078D6?logo=windows&logoColor=white" alt="Platform: Windows">
    <a href="https://github.com/r0073rr0r/ViberPC-Export/commits/main"><img src="https://img.shields.io/github/last-commit/r0073rr0r/ViberPC-Export" alt="Last commit"></a>
    <a href="https://github.com/r0073rr0r/ViberPC-Export/issues"><img src="https://img.shields.io/github/issues/r0073rr0r/ViberPC-Export" alt="Issues"></a>
    <a href="https://github.com/r0073rr0r/ViberPC-Export/stargazers"><img src="https://img.shields.io/github/stars/r0073rr0r/ViberPC-Export?style=social" alt="GitHub Stars"></a>
</p>

> [!IMPORTANT]
> **Purpose and boundaries.** Strictly for accessing **your own** data on **your own**
> machine (backup, migration, personal archive). Not for other people's devices or
> accounts. Everything runs locally; nothing is sent anywhere.

---

## 📑 Table of Contents

- [🧠 How it works](#-how-it-works-short-version)
- [📦 Requirements](#-requirements)
- [⚙️ Setup](#️-setup)
- [🚀 Usage](#-usage)
- [🧰 All methods](#-all-methods)
- [🔄 What if I close or update Viber?](#-what-if-i-close-or-update-viber)
- [🗂️ Structure](#️-structure)
- [🩺 Troubleshooting](#-troubleshooting)
- [🤝 Contributing](#-contributing)
- [🔐 Security](#-security)
- [⚖️ Legal & License](#️-legal--license)

## 🧠 How it works (short version)

Newer Viber versions **internally transform** the key, so `viber.db` cannot be opened with
plain SQLCipher even when you capture the "hexkey" Viber uses. That is why the main method
is different: while Viber runs, its **own engine already holds the DB unlocked**. The tool
attaches (via frida) to Viber's live Qt SQL connection and makes it export the decrypted
tables into an unencrypted file (`ATTACH DATABASE … KEY ''` + `CREATE TABLE AS SELECT`).
The readable log is then built from that clean file.

## 📦 Requirements

- Windows, **Python 3.10+**
- **Viber Desktop running and logged in** (for all "live" methods)
- `pip install -r requirements.txt`
  - `frida`, `frida-tools` — required
  - `sqlcipher3-wheels` — only for the offline `open` method

## ⚙️ Setup

1. `pip install -r requirements.txt`
2. Copy `.env.example` to `.env` and fill in if needed (usually you need **nothing** — the
   path and account number are auto-detected):
   ```
   VIBER_DB=              # empty = auto-detect %APPDATA%\ViberPC\<number>\viber.db
   VIBER_SELF_NUMBER=     # empty = derived from the path
   ```
3. Check: `python viber.py doctor`

> [!NOTE]
> `.env` and everything under `export/` are in `.gitignore` — **your data never goes to GitHub.**

## 🚀 Usage

```bash
python viber.py all            # RECOMMENDED: export from the live Viber + build log
# or in two steps:
python viber.py export
python viber.py log
```

Output:
- `export/viber_export.db` — the whole decrypted Viber (Contact, Messages, Events, …)
- `export/viber_messages.txt` — a readable chronological log

If `export` says there was no activity, **open a chat in Viber** while the script is
waiting (this triggers a read from the DB) and run it again.

## 🧰 All methods

| Command | What it does | Needs Viber? | Needs the key? |
|---|---|:---:|:---:|
| `export` | export from the live connection **(recommended)** | ✅ | ❌ |
| `log` | log from the export | ❌ | ❌ |
| `all` | `export` + `log` | ✅ | ❌ |
| `carve` | pull messages from RAM (partial names) | ✅ | ❌ |
| `hookkey` | capture the SQLCipher key/salt | ✅ | — |
| `open` | offline SQLCipher open of a copy | ❌ | ✅ |
| `schema` | print the schema from memory | ✅ | ❌ |
| `doctor` | environment check | — | — |

Examples of the auxiliary methods:
```bash
python viber.py carve                 # if Qt injection doesn't work on your version
python viber.py hookkey --write-env    # write the captured key into .env
python viber.py open --method all      # older versions: open a copy with the key
python viber.py schema                 # if the schema changed in a new version
```

## 🔄 What if I close or update Viber?

- **Viber closed:** the "live" methods (`export`, `carve`, `hookkey`, `schema`) will not
  work — only a running Viber keeps the DB unlocked. Start it and sign in, then run again.
  An already-created `viber_export.db` stays readable (it is unencrypted).
- **Viber update:** the export relies on Qt6 symbols and the `viber.db` connection name.
  A major update may change those. Order of resilience:
  1. `python viber.py export` (usually still works),
  2. `python viber.py carve` (does not depend on Qt symbols),
  3. `python viber.py schema` to check whether the schema/columns differ,
  4. `hookkey` + `open` if that version uses a directly-usable key.
- The export is a **point-in-time snapshot**. For the latest messages, run `export` again.

## 🗂️ Structure

```
viber.py            # CLI (all commands)
viberkit/           # per-method logic
  config.py           .env + paths (outputs to export/)
  frida_export.py     live export  [main]
  build_log.py        log from the export
  frida_carve.py      carving from RAM
  frida_hookkey.py    key capture
  sqlcipher_open.py   offline opening
  frida_schema.py     schema from memory
export/             # your data (gitignored, empty in the repo)
attic/              # research notes + a probe tool (reference)
.env / .env.example # secrets (ignored) / template
```

`attic/NOTES.md` records the whole research journey (brute-forcing the key, the bcrypt
hook, keyhunt, various probes) and the conclusions; `attic/probe_qt.py` helps diagnose a
new Viber version. Not needed for normal use.

## 🩺 Troubleshooting

- **"Viber is not running"** — start and sign in to Viber Desktop.
- **`export` doesn't trigger** — open a chat while the script waits; it watches for a read
  on `viber.db`.
- **Viber freezes** — don't use experimental in-process result iteration; the main
  `export` only runs quick `exec()` calls and does not block.
- **`open` fails on every variant** — the key is probably transformed internally (newer
  versions). Use `export` or `carve`.
- **Empty/odd log** — check `VIBER_SELF_NUMBER` (it affects IN/OUT) and run `schema` to
  confirm the columns match what is expected.

## 🤝 Contributing

Contributions are welcome! Please read the [Contributing Guide](CONTRIBUTING.md) and the
[Code of Conduct](CODE_OF_CONDUCT.md) first. CI lints on Python 3.10–3.13 and requires a
clean `pylint` run (10/10) with the repo's [`.pylintrc`](.pylintrc).

## 🔐 Security

Found a vulnerability? Please **do not** open a public issue — follow the
[Security Policy](SECURITY.md) to report it privately.

## ⚖️ Legal & License

This tool only accesses a local database that belongs to you, on your own machine. You are
responsible for using it in accordance with local laws and Viber's terms. Do not use it on
data that is not yours.

Licensed under the **GNU General Public License v3.0** — see [LICENSE](LICENSE).

<p align="center"><sub>Made with ❤️ by <a href="https://github.com/r0073rr0r">r0073rr0r</a></sub></p>
