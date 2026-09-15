# Notes: how we arrived at the solution

Summary of the research to decrypt the ViberPC `viber.db` (SQLCipher). The working
solutions live in `viberkit/`; this documents what was tried, what works and why -
useful if Viber updates, or for a similar project. No real key/account number is in the
repo; all secrets go in `.env`.

## Problem

`viber.db` is a SQLCipher database. A frida hook on `QSqlQuery::exec` showed that Viber
sets `PRAGMA hexkey='<64 hex>'`, but that hexkey is **internally transformed** - stock
SQLCipher does not accept it as a raw key, nor with an explicit salt, nor through a KDF.
So direct offline opening does not work on newer versions.

## Methods (in the order they were tried)

1. **Offline SQLCipher with the captured key** - `raw`, `raw+salt(96)`, `cipher_salt`,
   and a full PBKDF2 sweep (sha1/256/512 x iterations x page x HMAC). Result: **does not
   work** (the key is transformed). The salt does equal the first 16 bytes of the file,
   so that was not the issue either. -> today `viberkit/sqlcipher_open.py`
   (`viber.py open`), useful for older versions where the key works directly.

2. **Capturing the key via Qt / bcrypt** - hooks on `QSqlDatabase::setPassword/open` and
   `QSqlQuery::prepare/exec`, reading the `QString` argument; also an attempt to grab the
   AES key from `bcrypt.dll`. The key is captured but unusable directly (see point 1).
   -> today `viberkit/frida_hookkey.py` (`viber.py hookkey`).

3. **Carving from memory** - the decrypted SQLite pages are in the running Viber's RAM.
   Scan the `rw-` regions, extract table-leaf pages (0x0D, page 4096), parse records and
   classify by structural signature. **Works for messages.** Downsides: the full address
   book (`Contact`) is often not resident; long messages on overflow pages are truncated.
   -> today `viberkit/frida_carve.py` (`viber.py carve`).

4. **Injecting a query on the live Qt connection** - the real solution.
   - SQLite is statically linked (no exported `sqlite3_*` symbols), but **Qt6Sql.dll
     exports** `QSqlDatabase::database`, `QSqlQuery(db)`, `exec`, `next`, `value`, and
     Qt6Core exports `QString::fromUtf16`, `QVariant::toString`.
   - The first attempt iterated the result in-process (`value()`/`next()`/`QVariant`) -
     that **froze/crashed** Viber (blocked the DB thread + fragile C++ ABI). Do not do that.
   - Final approach: instead of reading rows, let Viber's own engine copy the tables into
     an unencrypted file: `ATTACH DATABASE '<out>' AS vplain KEY ''` then
     `CREATE TABLE vplain.X AS SELECT * FROM X`. Uses **only `exec()`** (bool), does not
     block the thread, clean and complete result. -> `viberkit/frida_export.py`
     (`viber.py export`).

## Key technical findings

- In this Viber build `EventID` and `ContactID` are **rowid aliases** -> column 0 in the
  record is NULL, and the real key is the cell rowid.
- **Direction: 0 = IN (received), 1 = OUT (sent).** `Events.ContactID` = the message
  **author**; the peer is computed from `ChatRelation`/`ChatInfo`.
- Viber keeps several connections; messages are on a connection named exactly **`viber.db`**
  (one thread), while `data.db` is a separate database. That is why the export only starts
  once the hook catches a `SELECT` on a viber table (guarantees the correct thread +
  autocommit so `ATTACH` does not fail).
- Mangled symbols used (MSVC x64): `?database@QSqlDatabase@@SA...`,
  `??0QSqlQuery@@QEAA@AEBVQSqlDatabase@@@Z`, `?exec@QSqlQuery@@QEAA_NAEBVQString@@@Z`,
  `?fromUtf16@QString@@SA?AV1@PEB_S_J@Z`, `?toString@QVariant@@QEBA?AVQString@@XZ`.

## If Viber updates

Symbols/schema/connection names may change. For diagnostics use `attic/probe_qt.py`
(lists Qt symbols and live connections, and can show the SQL Viber runs), then
`viber.py schema` to compare the columns.
