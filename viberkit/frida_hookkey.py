"""Method: capture the SQLCipher key/salt that Viber sets through the Qt SQL layer.

Hooks QSqlQuery::prepare/exec and QSqlDatabase::setPassword/open/setConnectOptions and
reads the QString argument. Looks for 'PRAGMA key/hexkey/rekey/cipher_salt ...' and
extracts the hex.

NOTE: on newer Viber versions the hexkey is INTERNALLY transformed, so stock SQLCipher
does not accept it directly (use 'export' or 'carve' instead). On older versions the
captured key works in 'viber.py open'.

Requires Viber running. The key is usually set at startup / when the DB is unlocked, so
you may need to restart Viber while this is listening (or wait for a reconnect).
"""
import re, time
import frida
from .frida_common import require_viber
from . import config

JS = r"""
var mod=null;
Process.enumerateModules().forEach(function(m){ if(/Qt6Sql/i.test(m.name)) mod=m; });
if(!mod){ send({t:'err',msg:'Qt6Sql.dll not loaded'}); }
var PTR=Process.pointerSize;
function readQString(p){try{if(p.isNull())return null;var d=p.add(PTR).readPointer();var s=p.add(2*PTR).readLong();if(d.isNull()||s<=0||s>200000)return null;return d.readUtf16String(s);}catch(e){return null;}}
function interesting(s){return s && /key|rekey|cipher|pragma|pass/i.test(s);}
var exps=mod?mod.enumerateExports():[];
var n=0;
exps.forEach(function(e){
  if(!/QString/.test(e.name)) return;
  var label=null;
  if(/prepare@QSqlQuery/.test(e.name)) label='prepare';
  else if(/exec@QSqlQuery/.test(e.name)) label='exec';
  else if(/setPassword@QSqlDatabase/.test(e.name)) label='setPassword';
  else if(/open@QSqlDatabase/.test(e.name)) label='open';
  else if(/setConnectOptions@QSqlDatabase/.test(e.name)) label='setConnectOptions';
  if(!label) return;
  try{
    Interceptor.attach(e.address,{onEnter:function(a){
      for(var i=1;i<=2;i++){ var s=readQString(a[i]); if(s && interesting(s)) send({t:'hit',label:label,sql:s}); }
    }});
    n++;
  }catch(err){}
});
send({t:'armed',hooks:n});
"""


def run(timeout=120, write_env=False):
    pid = require_viber()
    print(f"[i] Viber pid={pid}")
    hits = []

    def on_msg(m, d):
        if m.get("type") == "send":
            p = m["payload"]
            if p.get("t") == "armed":
                print(f"[i] hooks: {p.get('hooks')}. Listening {timeout}s.")
                print("    If nothing shows up: close and reopen Viber (the key is set when the DB is unlocked).")
            elif p.get("t") == "hit":
                print(f"\n[{p['label']}] {p['sql'][:200]}")
                hits.append(p["sql"])
            elif p.get("t") == "err":
                print("[JS ERR]", p.get("msg"))
        elif m.get("type") == "error":
            print("[ERR]", m.get("stack"))

    s = frida.attach(pid)
    sc = s.create_script(JS)
    sc.on("message", on_msg)
    sc.load()
    t0 = time.time()
    while time.time() - t0 < timeout and len(hits) < 5:
        time.sleep(0.2)
    s.detach()

    key = salt = None
    for sql in hits:
        mk = re.search(r"(?:hex)?key\s*=\s*['\"]?x?'?([0-9a-fA-F]{32,})'?", sql)
        ms = re.search(r"cipher_salt\s*=\s*['\"]?x?'?([0-9a-fA-F]{32})'?", sql)
        if mk and not key:
            key = mk.group(1)
        if ms and not salt:
            salt = ms.group(1)
    print("\n=== SUMMARY ===")
    print(f"  VIBER_HEXKEY = {key or '(not captured)'}")
    print(f"  VIBER_SALT   = {salt or '(not captured; salt is usually the first 16 bytes of the DB)'}")
    if key and write_env:
        _write_env(key, salt)
    elif key:
        print("\n  (Add to .env manually, or run with  --write-env  to write it.)")
    return key, salt


def _write_env(key, salt):
    import os
    p = os.path.join(config.ROOT, ".env")
    lines = []
    if os.path.exists(p):
        lines = open(p, encoding="utf-8").read().splitlines()

    def setk(name, val):
        for i, ln in enumerate(lines):
            if ln.strip().startswith(name + "="):
                lines[i] = f"{name}={val}"
                return
        lines.append(f"{name}={val}")

    setk("VIBER_HEXKEY", key)
    if salt:
        setk("VIBER_SALT", salt)
    open(p, "w", encoding="utf-8").write("\n".join(lines) + "\n")
    print(f"[OK] Written to {p}")
