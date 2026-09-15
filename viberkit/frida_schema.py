"""Helper method: print the full CREATE TABLE (schema) of viber.db from live memory.

Scans decrypted SQLite 'page 1' pages in Viber's RAM and extracts the CREATE TABLE text.
Useful for understanding the columns (e.g. if the schema changes in a new Viber version).
Requires Viber running.
"""
import time, re
import frida
from .frida_common import require_viber

JS = r"""
var MAGIC='53 51 4c 69 74 65 20 66 6f 72 6d 61 74 20 33 00';
var ranges=Process.enumerateRanges('rw-');
for (var i=0;i<ranges.length;i++){
  var r=ranges[i];
  if (r.size>1024*1024*1024) continue;
  var hits; try{hits=Memory.scanSync(r.base,r.size,MAGIC);}catch(e){continue;}
  for (var j=0;j<hits.length;j++){
    var a=hits[j].address; var end=r.base.add(r.size);
    var maxl=end.sub(a); var ln=16384; if(maxl.compare(ptr(16384))<0) ln=maxl.toInt32();
    var buf=null; var sizes=[ln,8192,4096,2048];
    for (var s=0;s<sizes.length;s++){ if(sizes[s]>ln) continue; try{buf=a.readByteArray(sizes[s]);}catch(e){buf=null;} if(buf) break; }
    if(buf) send({t:'pg'},buf);
  }
}
send({t:'done'});
"""


def run():
    pid = require_viber()
    print(f"[i] Viber pid={pid}")
    blobs = []
    done = {"v": False}

    def on_msg(m, d):
        if m.get("type") == "send":
            if m["payload"].get("t") == "pg" and d:
                blobs.append(bytes(d))
            elif m["payload"].get("t") == "done":
                done["v"] = True
        elif m.get("type") == "error":
            print("ERR", m.get("stack"))

    s = frida.attach(pid)
    sc = s.create_script(JS)
    sc.on("message", on_msg)
    sc.load()
    t0 = time.time()
    while not done["v"] and time.time() - t0 < 120:
        time.sleep(0.2)
    s.detach()

    for b in blobs:
        txt = b.decode("latin-1", "replace")
        if "Messages" in txt and "Events" in txt:
            psize = (b[16] << 8) | b[17]
            print(f"\n########## viber.db (page_size={psize}) ##########")
            for m in re.finditer(r"CREATE TABLE [\"']?(\w+)[\"']?\s*\(", txt):
                name = m.group(1); start = m.end() - 1
                depth = 0; end = start
                for k in range(start, min(len(txt), start + 2000)):
                    ch = txt[k]
                    if ch == "(":
                        depth += 1
                    elif ch == ")":
                        depth -= 1
                        if depth == 0:
                            end = k + 1; break
                    elif ch == "\x00":
                        end = k; break
                body = txt[m.start():end]
                body = re.sub(r"[^\x20-\x7e]", " ", body)
                body = re.sub(r"\s+", " ", body).strip()
                print(f"\n-- {name}:\n{body[:900]}")
            return True
    print("[X] Could not find the viber.db schema in memory (is Viber unlocked?).")
    return False
