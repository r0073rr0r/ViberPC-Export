"""Diagnostics for a new/changed Viber version.

Reads no secrets. It lists:
  - the relevant Qt6Sql/Qt6Core exported symbols (for NativeFunction addresses),
  - the live SQL connection names (which one is 'viber.db'),
  - optionally: the SQL Viber executes (--sniff), to see which thread the viber tables
    are on.

Usage:
  python attic/probe_qt.py            # symbols + connections
  python attic/probe_qt.py --sniff    # + follow SQL for 30s (click around Viber)
"""
import sys, time
import frida

NEEDLES_SQL = ['database@QSqlDatabase', 'exec@QSqlQuery', 'next@QSqlQuery',
               'value@QSqlQuery', '0QSqlQuery@@QEAA@AEBVQSqlDatabase',
               'prepare@QSqlQuery', 'connectionNames@QSqlDatabase',
               '1QSqlQuery@@QEAA@XZ', '1QSqlDatabase@@QEAA@XZ']
NEEDLES_CORE = ['fromUtf16@QString', 'toString@QVariant', '1QString@@QEAA@XZ',
                '1QVariant@@QEAA@XZ']


def get_pid():
    procs = [p for p in frida.get_local_device().enumerate_processes()
             if "viber" in p.name.lower()]
    if not procs:
        raise SystemExit("[X] Viber is not running.")
    return procs[0].pid


JS = r"""
var SNIFF = %%SNIFF%%;
function expMap(n){var m=Process.findModuleByName(n),o={};if(!m)return o;m.enumerateExports().forEach(function(e){o[e.name]=e.address;});return o;}
function findSyms(modName, needles){
  var map=expMap(modName), out={};
  needles.forEach(function(nd){ for(var k in map){ if(k.indexOf(nd)>=0){ out[nd]=k; break; } } });
  return out;
}
var a_connNames=null; var Smap=expMap('Qt6Sql.dll');
for(var k in Smap){ if(k.indexOf('connectionNames@QSqlDatabase')>=0){ a_connNames=Smap[k]; break; } }
function readQString(p){try{var d=p.add(8).readPointer();var s=p.add(16).readLong();if(d.isNull()||s<=0||s>1e6)return "";return d.readUtf16String(s);}catch(e){return "";}}
function conns(){
  if(!a_connNames) return [];
  try{
    var f=new NativeFunction(a_connNames,'void',['pointer']);
    var b=Memory.alloc(32); f(b);
    var sz=b.add(16).readLong(), pt=b.add(8).readPointer(), out=[];
    for(var i=0;i<sz&&i<500;i++) out.push(readQString(pt.add(i*24)));
    return out;
  }catch(e){ return []; }
}
send({t:'syms', sql:findSyms('Qt6Sql.dll',%%NSQL%%), core:findSyms('Qt6Core.dll',%%NCORE%%)});
send({t:'conns', list:conns()});

if(SNIFF){
  var a_execS=null, a_prep=null;
  for(var k in Smap){ if(k.indexOf('exec@QSqlQuery@@QEAA_NAEBVQString')>=0) a_execS=Smap[k];
                      if(k.indexOf('prepare@QSqlQuery')>=0) a_prep=Smap[k]; }
  var n=0;
  function hook(a,label){ if(!a)return; Interceptor.attach(a,{onEnter:function(args){
    if(n>=20)return; var s=readQString(args[1]); if(s){ n++; send({t:'sql', tid:Process.getCurrentThreadId().toString(16), label:label, sql:s.slice(0,90)}); }
  }}); }
  hook(a_execS,'exec'); hook(a_prep,'prepare');
  send({t:'sniffing'});
}
"""


def main():
    sniff = "--sniff" in sys.argv
    pid = get_pid()
    print(f"[i] Viber pid={pid}")
    import json
    js = (JS.replace("%%SNIFF%%", "true" if sniff else "false")
            .replace("%%NSQL%%", json.dumps(NEEDLES_SQL))
            .replace("%%NCORE%%", json.dumps(NEEDLES_CORE)))

    def on_msg(m, d):
        if m.get("type") != "send":
            print("ERR", m.get("stack")); return
        p = m["payload"]; t = p.get("t")
        if t == "syms":
            print("\n=== Qt6Sql symbols ===")
            for k, v in p["sql"].items():
                print(f"  {k:40s} -> {v or '(MISSING)'}")
            print("=== Qt6Core symbols ===")
            for k, v in p["core"].items():
                print(f"  {k:40s} -> {v or '(MISSING)'}")
        elif t == "conns":
            print("\n=== live connections ===")
            for c in p["list"]:
                print("  ", c)
        elif t == "sql":
            print(f"  [tid={p['tid']}] {p['label']}: {p['sql']}")
        elif t == "sniffing":
            print("\n[i] following SQL for 30s - click around Viber...")

    s = frida.attach(pid)
    sc = s.create_script(js)
    sc.on("message", on_msg)
    sc.load()
    time.sleep(30 if sniff else 1.5)
    s.detach()


if __name__ == "__main__":
    main()
