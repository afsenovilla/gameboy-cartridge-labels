# screenscraper_review: a page to look through what screenscraper_match found, for checking it by eye.
#   python run.py py src/screenscraper_review.py      ->  screenscraper-labels/review.html (open it in the browser)
# A grid of ScreenScraper's label images, filtered by how each was matched (unmatched, by title, unknown serial, near,
# by serial), by system and by text (title, serial, game id). Clicking one shows it beside our restored label of the
# same print, with the serial, the text read and what to check for that kind of match. Each can be marked good (B) or
# bad (M), moving on to the next; the marks stay in this browser, filterable (unreviewed, good, bad), and "Copy bad
# ones for ignore.txt" gives the lines to paste into screenscraper-labels/ignore.txt (then --dedupe removes them).
import html
import json
import os

OUT = "screenscraper-labels"
LABELS = os.path.join("published-labels", "labels.json")


def items(matches, labels):
    """One entry per image, as the page wants it: shared images (same_as) once, with every region's name."""
    files = {e["id"]: e.get("file") for e in labels}
    regions = {}
    for name, e in matches.items():
        if e.get("same_as"):
            regions.setdefault(e["same_as"], []).append(name)
    out = []
    for name, e in matches.items():
        if e.get("same_as"):
            continue
        ours = next((p for p in e.get("labels", []) if files.get(p)), None)
        out.append({"img": name, "also": regions.get(name, []), "how": e["how"], "system": e["system"],
                    "game": e["game"], "name": (e.get("names") or [""])[0], "serial": e.get("serial") or "",
                    "title": e.get("title") or "", "guess": [f'{g["release"]} {g.get("title") or ""}' for g in e.get("guesses", [])],
                    "ours": ours and "../published-labels/" + files[ours], "ours_id": ours or "",
                    "wanted": e.get("wanted", []), "text": " | ".join(e.get("text", []))})
    order = {"none": 0, "title": 1, "unknown": 2, "near": 3, "serial": 4}
    return sorted(out, key=lambda x: (order.get(x["how"], 9), x["system"], x["name"].lower()))


PAGE = r"""<!doctype html><html lang="es"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>ScreenScraper review</title>
<style>
:root{--bg:#16181c;--panel:#20232a;--line:#33373f;--text:#e8e6e1;--dim:#9a9ea6;--none:#e05a4f;--title:#e0a23c;--unknown:#c8a0ff;--near:#5aa9e6;--serial:#6cc070}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--text);font:14px/1.4 system-ui,sans-serif}
header{position:sticky;top:0;z-index:2;background:var(--bg);border-bottom:1px solid var(--line);padding:12px 16px;display:flex;flex-wrap:wrap;gap:8px;align-items:center}
h1{font-size:16px;margin:0 12px 0 0}button,input{font:inherit;color:var(--text);background:var(--panel);border:1px solid var(--line);border-radius:6px;padding:5px 10px}
button{cursor:pointer}button.on{border-color:var(--text)}button .n{color:var(--dim);margin-left:4px}input{min-width:200px}
.how-none{color:var(--none)}.how-title{color:var(--title)}.how-unknown{color:var(--unknown)}.how-near{color:var(--near)}.how-serial{color:var(--serial)}
main{display:grid;grid-template-columns:repeat(auto-fill,minmax(190px,1fr));gap:12px;padding:16px}
.card{background:var(--panel);border:1px solid var(--line);border-radius:8px;padding:8px;cursor:pointer;display:flex;flex-direction:column;gap:4px}
.card:focus-visible,.card:hover{border-color:var(--dim)}.card.bad{opacity:.35;border-style:dashed}.card.good{border-color:var(--serial)}
.hint{color:var(--dim);font-size:13px;margin:8px 0 0}kbd{border:1px solid var(--line);border-radius:4px;padding:0 4px;font:12px system-ui}
.card img{width:100%;height:120px;object-fit:contain;background:#0d0e10;border-radius:4px}
.card .t{font-weight:600;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.card .s{font-size:12px;color:var(--dim)}
.more{grid-column:1/-1;justify-self:center}
dialog{background:var(--panel);color:var(--text);border:1px solid var(--line);border-radius:10px;max-width:min(1000px,95vw);width:100%}
dialog::backdrop{background:#000a}.pair{display:grid;grid-template-columns:1fr 1fr;gap:12px}.pair figure{margin:0}
.pair img{width:100%;max-height:50vh;object-fit:contain;background:#0d0e10;border-radius:6px}.pair figcaption{color:var(--dim);font-size:12px;margin-top:4px}
dl{display:grid;grid-template-columns:auto 1fr;gap:4px 12px;margin:12px 0}dt{color:var(--dim)}dd{margin:0;word-break:break-word}
.row{display:flex;gap:8px;justify-content:flex-end;flex-wrap:wrap}
@media (max-width:600px){.pair{grid-template-columns:1fr}}
</style>
<header>
<h1>ScreenScraper</h1>
<span id="hows"></span><span id="systems"></span>
<span id="states"></span>
<input id="q" type="search" placeholder="Título, serial o id">
<button id="copy">Copiar malas para ignore.txt <span class="n" id="nbad"></span></button>
</header>
<main id="grid"></main>
<dialog id="dlg"><div class="pair"><figure><img id="d-ss" alt=""><figcaption id="d-ssc"></figcaption></figure>
<figure><img id="d-ours" alt=""><figcaption id="d-oursc"></figcaption></figure></div>
<dl id="d-info"></dl><p class="hint" id="d-hint"></p>
<div class="row"><button id="d-good">Bien <kbd>B</kbd></button><button id="d-bad">Mala <kbd>M</kbd></button><button id="d-prev">← Anterior</button><button id="d-next">Siguiente →</button><button id="d-close">Cerrar</button></div></dialog>
<script id="data" type="application/json">__DATA__</script>
<script>
const ITEMS=JSON.parse(document.getElementById("data").textContent);
const HOWS=[["none","Sin nada"],["title","Por título"],["unknown","Serial desconocido"],["near","Aproximado"],["serial","Por serial"]];
const SYS=[["gb","GB"],["gbc","GBC"],["gba","GBA"]];
const $=id=>document.getElementById(id);
let mark={};try{mark=JSON.parse(localStorage.getItem("ss-mark")||"{}")}catch(e){}
const bad={has:k=>mark[k]==="bad"};
const saveBad=()=>{try{localStorage.setItem("ss-mark",JSON.stringify(mark))}catch(e){};$("nbad").textContent=Object.values(mark).filter(v=>v==="bad").length||"";
 const n=k=>ITEMS.filter(x=>(mark[x.img]||"todo")===k).length;document.querySelectorAll("#states .n").forEach(e=>e.textContent=n(e.dataset.k))};
const STATES=[["todo","Sin revisar"],["good","Bien"],["bad","Malas"]];
let how=new Set(["none","title","unknown","near"]),sys=new Set(["gb","gbc","gba"]),st=new Set(["todo","good","bad"]),shown=[],limit=120,cur=-1;
function chips(el,list,set,key){el.innerHTML="";for(const [k,label] of list){const b=document.createElement("button");
 const n=ITEMS.filter(x=>x[key]===k).length;b.innerHTML=`<span class="${key==="how"?"how-"+k:""}">${label}</span><span class="n">${n}</span>`;
 b.className=set.has(k)?"on":"";b.onclick=()=>{set.has(k)?set.delete(k):set.add(k);b.className=set.has(k)?"on":"";limit=120;render()};el.append(b)}}
function render(){const q=$("q").value.trim().toLowerCase();
 shown=ITEMS.filter(x=>how.has(x.how)&&sys.has(x.system)&&st.has(mark[x.img]||"todo")&&(!q||(x.name+" "+x.serial+" "+x.title+" "+x.game+" "+x.img).toLowerCase().includes(q)));
 const g=$("grid");g.innerHTML="";shown.slice(0,limit).forEach((x,i)=>{const c=document.createElement("div");c.className="card"+(mark[x.img]?" "+mark[x.img]:"");c.tabIndex=0;
  c.innerHTML=`<img loading="lazy" src="${x.img}" alt=""><div class="t" title="${esc(x.name)}">${esc(x.name)||"?"}</div><div class="s"><span class="how-${x.how}">●</span> ${esc(x.serial||x.guess[0]||"—")}</div><div class="s">${esc(x.img)}</div>`;
  c.onclick=()=>open(i);c.onkeydown=e=>{if(e.key==="Enter")open(i)};g.append(c)});
 if(shown.length>limit){const b=document.createElement("button");b.className="more";b.textContent=`Mostrar más (${shown.length-limit} restantes)`;b.onclick=()=>{limit+=240;render()};g.append(b)}}
const esc=s=>String(s).replace(/[&<>"]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
function open(i){cur=i;const x=shown[i];$("d-ss").src=x.img;$("d-ssc").textContent="ScreenScraper: "+[x.img,...x.also].join(", ");
 $("d-ours").src=x.ours||"";$("d-ours").style.display=x.ours?"":"none";$("d-oursc").textContent=x.ours?"Nuestra: "+x.ours_id:"Sin etiqueta restaurada de este print";
 const rows=[["Juego",`${x.name} (ScreenScraper ${x.game}, ${x.system})`],["Cómo",HOWS.find(h=>h[0]===x.how)[1]],["Serial",x.serial||"—"],["Lanzamiento",x.title||"—"],
  ["Por título",x.guess.join(" · ")||"—"],["En wanted",x.wanted.join(", ")||"—"],["Texto leído",x.text||"—"]];
 $("d-info").innerHTML=rows.map(([k,v])=>`<dt>${k}</dt><dd>${esc(v)}</dd>`).join("");badLabel();if(!$("dlg").open)$("dlg").showModal()}
const HINT={none:"No se leyó serial ni se adivinó el juego. Mira si es una etiqueta de cartucho de verdad (no una caja, una tarjeta o un juego de fans) y de qué juego es.",
 title:"Sin serial legible: solo se adivinó por el título. Bien si la etiqueta es de ese juego y esa consola; mala si no es una etiqueta de cartucho.",
 unknown:"Se leyó un serial que no está en la base. Compáralo con el que se ve impreso en la etiqueta: bien si coinciden y es una etiqueta de cartucho.",
 near:"Se leyó un serial con algún error y se corrigió al más parecido. Compara el serial con el impreso en la etiqueta.",
 serial:"Casó por serial. Si hay etiqueta nuestra al lado, deberían ser el mismo cartucho (puede cambiar el escaneo, no el diseño)."};
function badLabel(){const m=mark[shown[cur].img];$("d-good").className=m==="good"?"on":"";$("d-bad").className=m==="bad"?"on":"";
 $("d-hint").textContent=HINT[shown[cur].how]||""}
function setMark(v){const x=shown[cur];mark[x.img]===v?delete mark[x.img]:mark[x.img]=v;saveBad();const i=cur;render();
 if(mark[x.img]&&i<shown.length)open(Math.min(i+(shown[i]===x?1:0),shown.length-1));else if(shown.length)open(Math.min(i,shown.length-1));else $("dlg").close()}
$("d-good").onclick=()=>setMark("good");$("d-bad").onclick=()=>setMark("bad");
$("d-prev").onclick=()=>cur>0&&open(cur-1);$("d-next").onclick=()=>cur<shown.length-1&&open(cur+1);$("d-close").onclick=()=>$("dlg").close();
$("dlg").addEventListener("keydown",e=>{if(e.key==="ArrowRight")$("d-next").click();if(e.key==="ArrowLeft")$("d-prev").click();
 if(e.key==="b"||e.key==="B")setMark("good");if(e.key==="m"||e.key==="M")setMark("bad")});
$("q").oninput=()=>{limit=120;render()};
$("copy").onclick=async()=>{const lines=Object.keys(mark).filter(k=>mark[k]==="bad").map(p=>{const x=ITEMS.find(i=>i.img===p);return `${p}  # ${x?x.name:""}`}).join("\n");
 try{await navigator.clipboard.writeText(lines);$("copy").firstChild.textContent="Copiado "}catch(e){prompt("Copia estas líneas:",lines)}};
chips($("hows"),HOWS,how,"how");chips($("systems"),SYS,sys,"system");
for(const [k,label] of STATES){const b=document.createElement("button");b.innerHTML=`${label}<span class="n" data-k="${k}"></span>`;b.className="on";
 b.onclick=()=>{st.has(k)?st.delete(k):st.add(k);b.className=st.has(k)?"on":"";limit=120;render()};$("states").append(b)}
saveBad();render();
</script></html>"""


def main():
    with open(os.path.join(OUT, "matches.json"), encoding="utf-8") as f:
        matches = json.load(f)
    labels = json.load(open(LABELS, encoding="utf-8")) if os.path.exists(LABELS) else []
    data = json.dumps(items(matches, labels), ensure_ascii=False).replace("</", "<\\/")
    path = os.path.join(OUT, "review.html")
    with open(path, "w", encoding="utf-8") as f:
        f.write(PAGE.replace("__DATA__", data))
    print("Open", path)


if __name__ == "__main__":
    main()
