"""Animated replay of a recorded run (self-contained HTML/CSS/JS for an isolated iframe).

The animation only plays frames built from REAL events (see demo_frames). It compresses the real
waiting time (each step is shown for a few seconds) but prints the real elapsed time of every step.
All text is inserted with textContent, never as HTML. `prefers-reduced-motion` disables autoplay and
movement.
"""

from __future__ import annotations

import json
from typing import Any

from datapilot.ui.demo_frames import Frame

HEIGHT = 780

_TEMPLATE = r"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Agent workflow</title>
<style>
:root{--ink:#14202b;--muted:#5b6773;--line:#e4e8ec;--card:#fff;--bg:transparent;
--plan:#4f5bd5;--code:#0b7f8a;--exec:#c98a12;--rev:#1f8a5b;--bad:#c7402f;--ok:#1f8a5b;--warn:#b7791f;
--font:Inter,'Segoe UI',system-ui,-apple-system,sans-serif}
*{box-sizing:border-box}html,body{margin:0;background:var(--bg);color:var(--ink);font-family:var(--font)}
.wrap{max-width:none;margin:0;padding:4px 0 12px}
.stage{background:linear-gradient(180deg,#fff,#f6f9fb);border:1px solid var(--line);border-radius:18px;
box-shadow:0 10px 30px rgba(20,32,43,.06);padding:12px 10px 4px;position:relative}
svg{width:100%;height:auto;display:block;overflow:visible}
.edge{stroke:#cfd7de;stroke-width:3;fill:none;stroke-linecap:round}
.edge.on{stroke:#8fa3b3}.edge.loop{stroke:var(--bad);stroke-dasharray:7 7}
.node rect{fill:#fff;stroke:#d9e0e6;stroke-width:2;rx:16;transition:all .35s}
.node text{font-family:var(--font)}
.node .nm{font-size:17px;font-weight:700;fill:var(--ink)}.node .rl{font-size:12px;fill:var(--muted)}
.node .st{font-size:12px;font-weight:700;letter-spacing:.04em;fill:var(--muted);text-transform:uppercase}
.node.done rect{stroke:#bfe3d0;fill:#f4fbf7}.node.done .st{fill:var(--ok)}
.node.active rect{stroke-width:3;filter:drop-shadow(0 8px 16px rgba(20,32,43,.18))}
.node.active.planner rect{stroke:var(--plan)}.node.active.coder rect{stroke:var(--code)}
.node.active.executor rect{stroke:var(--exec)}.node.active.reviewer rect{stroke:var(--rev)}
.node.error rect,.node.active.error rect{stroke:var(--bad)!important;fill:#fdf1ef}.node.error .st{fill:var(--bad)}
.node.approved rect{stroke:var(--ok);fill:#eefaf3}.node.approved .st{fill:var(--ok)}
.node.shake{animation:shake .5s}
@keyframes shake{20%{transform:translate(-4px,0)}40%{transform:translate(4px,0)}60%{transform:translate(-3px,0)}80%{transform:translate(3px,0)}}
.icon{fill:none;stroke:#fff;stroke-width:2.2;stroke-linecap:round;stroke-linejoin:round}
.packet{transition:transform .9s cubic-bezier(.4,.1,.2,1),opacity .3s}
.pulse{animation:pulse 1.6s infinite}
@keyframes pulse{0%{opacity:.35;r:20}100%{opacity:0;r:34}}
.card{margin-top:14px;background:var(--card);border:1px solid var(--line);border-radius:18px;padding:18px 20px;
box-shadow:0 10px 30px rgba(20,32,43,.06);height:288px;overflow:auto;border-left:6px solid #cfd7de;transition:border-color .3s}
.card.neutral{border-left-color:var(--code)}.card.ok{border-left-color:var(--ok)}
.card.bad{border-left-color:var(--bad)}.card.warn{border-left-color:var(--warn)}
.card .top{display:flex;gap:10px;align-items:center;flex-wrap:wrap;margin-bottom:6px}
.pill{font-size:11px;font-weight:700;letter-spacing:.07em;text-transform:uppercase;color:#fff;border-radius:999px;padding:4px 10px}
.pill.You,.pill.Result{background:#14202b}.pill.Planner{background:var(--plan)}.pill.Coder{background:var(--code)}
.pill.Executor{background:var(--exec)}.pill.Reviewer{background:var(--rev)}
.real{font-size:12px;color:var(--muted)}
.card h3{margin:2px 0 6px;font-size:21px;line-height:1.25}
.card p{margin:0;color:#2c3a47;font-size:15px;line-height:1.55;white-space:pre-wrap;word-break:break-word;max-height:96px;overflow:auto}
.badge{margin-top:10px;display:inline-block;background:#fff4de;border:1px solid #f0d28f;color:#7a5200;
font-size:12.5px;font-weight:600;border-radius:10px;padding:6px 10px}
pre{margin:12px 0 0;background:#0f1d2b;color:#d8e6f3;border-radius:12px;padding:12px 14px;font-size:12.5px;
line-height:1.5;overflow:auto;max-height:118px;font-family:ui-monospace,SFMono-Regular,Consolas,monospace}
.card.bad p{color:#8f2c1f;font-family:ui-monospace,Consolas,monospace;font-size:14px}
.enter{animation:enter .45s ease both}@keyframes enter{from{opacity:0;transform:translateY(8px)}to{opacity:1;transform:none}}
.controls{margin-top:14px;display:flex;gap:10px;align-items:center;flex-wrap:wrap}
button{font:inherit;font-weight:600;border:1px solid var(--line);background:#fff;color:var(--ink);border-radius:12px;
padding:9px 14px;cursor:pointer;box-shadow:0 2px 6px rgba(20,32,43,.05)}
button:hover{border-color:#b9c4cd}button:focus-visible,input:focus-visible{outline:3px solid #7cc4cc;outline-offset:2px}
button.primary{background:#0b7f8a;border-color:#0b7f8a;color:#fff}
input[type=range]{flex:1;min-width:140px;accent-color:#0b7f8a}
.counter{margin-left:auto;font-size:13px;color:var(--muted)}.counter b{color:var(--ink);font-size:15px}
.bar{height:6px;border-radius:99px;background:#e9eef2;overflow:hidden;margin-top:12px}
.bar i{display:block;height:100%;width:0;background:linear-gradient(90deg,#0b7f8a,#1f8a5b);transition:width .5s}
.more{margin-top:12px}.more summary{cursor:pointer;font-weight:700;color:var(--teal);padding:6px 2px}.feed{list-style:none;margin:8px 0 0;padding:0;display:grid;gap:8px;max-height:220px;overflow:auto}
.feed li{display:flex;gap:10px;align-items:center;background:#fff;border:1px solid var(--line);border-radius:12px;
padding:9px 12px;font-size:14px;cursor:pointer;opacity:.5;transition:opacity .3s}
.feed li.seen{opacity:1}.feed li.cur{border-color:#0b7f8a;box-shadow:0 0 0 3px rgba(11,127,138,.12)}
.feed .dot{width:10px;height:10px;border-radius:50%;flex:none}
.feed .ts{margin-left:auto;color:var(--muted);font-size:12px;white-space:nowrap}
@media (max-width:640px){.card h3{font-size:18px}.card{padding:14px;height:250px}.feed .ts{display:none}}
@media (prefers-reduced-motion:reduce){*{animation:none!important;transition:none!important}}
</style></head><body><div class="wrap">
<div class="stage"><svg id="svg" viewBox="0 0 960 250" role="img" aria-label="The four AI agents and how work moves between them">
<defs><marker id="arr" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="7" markerHeight="7" orient="auto">
<path d="M0 0L10 5L0 10z" fill="#9fb0bf"/></marker></defs>
<path id="e01" class="edge" d="M212 98H262" marker-end="url(#arr)"/>
<path id="e12" class="edge" d="M452 98H502" marker-end="url(#arr)"/>
<path id="e23" class="edge" d="M692 98H742" marker-end="url(#arr)"/>
<path id="loop" class="edge" d="M597 150C597 232 357 232 357 150" marker-end="url(#arr)"/>
<g id="nodes"></g>
<g id="pk" class="packet" opacity="0"><circle r="11" fill="#14202b"/><circle class="pulse" r="20" fill="#14202b"/></g>
<text x="480" y="244" text-anchor="middle" font-size="12" fill="#8a97a3" id="looplabel"></text>
</svg></div>
<div class="card neutral" id="card" aria-live="polite"><div class="top"><span class="pill You" id="who">Ready</span>
<span class="real" id="real"></span></div><h3 id="ttl">Press play to watch the team work</h3><p id="det"></p>
<div id="bdg"></div><pre id="code" hidden></pre></div>
<div class="bar"><i id="prog"></i></div>
<div class="controls"><button class="primary" id="play" aria-label="Play or pause">Play</button>
<button id="back" aria-label="Previous step">&larr; Back</button><button id="next" aria-label="Next step">Next &rarr;</button>
<button id="again" aria-label="Replay from the start">Replay</button><button id="speed" aria-label="Change speed">1&times;</button>
<input id="scrub" type="range" min="0" max="0" value="0" aria-label="Jump to a step">
<span class="counter">Agent messages <b id="cnt">0</b> of 12 · <span id="elapsed">0.0</span>s real time</span></div>
<details class="more"><summary>All steps — click one to jump to it</summary><ol class="feed" id="feed"></ol></details></div>
<script>
const FRAMES=__FRAMES__;const META=__META__;
const NODES=[{k:"Planner",c:"planner",role:"Makes the plan",col:"#4f5bd5"},
{k:"Coder",c:"coder",role:"Writes the Python code",col:"#0b7f8a"},
{k:"Executor",c:"executor",role:"Runs it in a sandbox",col:"#c98a12"},
{k:"Reviewer",c:"reviewer",role:"Checks and approves",col:"#1f8a5b"}];
const LAYOUT={wide:{vb:"0 0 960 250",w:192,h:116,p:{Planner:[20,40],Coder:[260,40],Executor:[500,40],Reviewer:[740,40]},
 e01:"M212 98H262",e12:"M452 98H502",e23:"M692 98H742",loop:"M597 150C597 232 357 232 357 150"},
 narrow:{vb:"0 0 380 322",w:160,h:108,p:{Planner:[10,20],Coder:[210,20],Executor:[210,190],Reviewer:[10,190]},
 e01:"M172 74H208",e12:"M290 130V188",e23:"M208 244H172",loop:"M240 190C196 172 196 146 240 128"}};
let L=LAYOUT.wide;
const ICON={Planner:"M9 9h14M9 15h14M9 21h9",Coder:"M13 10l-5 6 5 6M19 10l5 6-5 6",
Executor:"M10 9l13 7-13 7z",Reviewer:"M9 16l5 5 9-11"};
const $=id=>document.getElementById(id);const NS="http://www.w3.org/2000/svg";
const reduce=matchMedia("(prefers-reduced-motion: reduce)").matches;
let cur=-1,timer=null,speed=1,playing=false,started=false;
const nodeEls={};
function mk(tag,attrs,parent){const e=document.createElementNS(NS,tag);for(const k in attrs)e.setAttribute(k,attrs[k]);
 if(parent)parent.appendChild(e);return e}
NODES.forEach(n=>{const g=mk("g",{class:"node "+n.c},$("nodes"));
 const rc=mk("rect",{width:192,height:116,x:0,y:0,rx:16},g);
 const ic=mk("circle",{cx:34,cy:34,r:20,fill:n.col},g);
 const p=mk("path",{d:ICON[n.k],class:"icon",transform:"translate(18,18)"},g);
 const t1=mk("text",{x:64,y:40,class:"nm"},g);t1.textContent=n.k;
 const t2=mk("text",{x:16,y:78,class:"rl"},g);t2.textContent=n.role;
 const t3=mk("text",{x:16,y:100,class:"st"},g);t3.textContent="Waiting";nodeEls[n.k]={g,st:t3,n,rc,t2,t3}});
function applyLayout(){const narrow=document.documentElement.clientWidth<560;L=narrow?LAYOUT.narrow:LAYOUT.wide;
 $("svg").setAttribute("viewBox",L.vb);
 NODES.forEach(n=>{const o=nodeEls[n.k],[x,y]=L.p[n.k];o.g.setAttribute("transform",`translate(${x},${y})`);
  o.rc.setAttribute("width",L.w);o.rc.setAttribute("height",L.h);o.t2.setAttribute("y",narrow?76:78);o.t3.setAttribute("y",narrow?96:100)});
 ["e01","e12","e23","loop"].forEach(k=>$(k).setAttribute("d",L[k]));
 $("looplabel").style.display=narrow?"none":""}
applyLayout();addEventListener("resize",()=>{applyLayout()});
const pos=k=>{const q=L.p[k];return q?{x:q[0]+L.w/2,y:q[1]+L.h/2}:{x:-30,y:98}};
const edge=k=>{const q=L.p[k];return q?{x:q[0]-4,y:q[1]+L.h/2}:{x:-30,y:98}};
function setPacket(from,to,loop){const pk=$("pk");const a=pos(from),b=pos(to);
 if(reduce||!nodeEls[to]){pk.setAttribute("opacity","0");return}
 pk.style.transition="none";pk.style.transform=`translate(${a.x}px,${a.y}px)`;pk.setAttribute("opacity","1");
 requestAnimationFrame(()=>requestAnimationFrame(()=>{pk.style.transition="";
  const e=edge(to);pk.style.transform=`translate(${e.x}px,${e.y}px)`;
  clearTimeout(window.__pkT);window.__pkT=setTimeout(()=>pk.setAttribute("opacity","0"),1100)}))}
function render(i,animate){const f=FRAMES[i];cur=i;started=true;
 Object.values(nodeEls).forEach(o=>{o.g.setAttribute("class","node "+o.n.c);o.st.textContent="Waiting"});
 let prev="You";
 for(let j=0;j<=i;j++){const fj=FRAMES[j];const o=nodeEls[fj.actor];if(!o)continue;
  const isCur=(j===i);let cls="node "+o.n.c;
  if(isCur){cls+=" active";if(fj.kind==="run_fail")cls+=" error";if(fj.kind==="approve")cls+=" approved"}
  else cls+=" done";
  o.g.setAttribute("class",cls);
  o.st.textContent=isCur?({plan:"Planning",code:"Writing code",run_ok:"Ran OK",run_fail:"Crashed",feedback:"Asked for changes",approve:"Approved"}[fj.kind]||"Working"):"Done"}
 FRAMES.slice(0,i).forEach(()=>{});
 const hist=FRAMES.slice(0,i+1);const anyLoop=hist.some(x=>x.loop);
 $("loop").setAttribute("class","edge"+(anyLoop?" loop":""));
 $("e01").setAttribute("class","edge"+(i>=1?" on":""));$("e12").setAttribute("class","edge"+(i>=2?" on":""));
 $("e23").setAttribute("class","edge"+(hist.some(x=>x.actor==="Reviewer")?" on":""));
 $("looplabel").textContent=anyLoop?"the error / feedback goes back to the Coder":"";
 const card=$("card");card.className="card "+f.tone+" enter";void card.offsetWidth;
 $("who").className="pill "+f.actor;$("who").textContent=f.actor==="You"?"Question":f.actor;
 $("real").textContent=i===0?"":`real time +${f.t.toFixed(1)} s`;
 $("ttl").textContent=f.title;$("det").textContent=f.detail;
 const b=$("bdg");b.textContent="";if(f.badge){const s=document.createElement("span");s.className="badge";s.textContent=f.badge;b.appendChild(s)}
 const c=$("code");if(f.code&&f.code.length){c.hidden=false;c.textContent=f.code.join("\n")+"\n…"}else{c.hidden=true;c.textContent=""}
 const prevActor=i>0?FRAMES[i-1].actor:"You";
 if(animate){setPacket(prevActor,f.actor,f.loop&&f.actor==="Coder");
  if(f.kind==="run_fail"){const g=nodeEls.Executor.g;g.classList.add("shake")}}
 $("cnt").textContent=f.count;$("elapsed").textContent=f.t.toFixed(1);
 $("scrub").value=i;$("prog").style.width=((i+1)/FRAMES.length*100)+"%";
 document.querySelectorAll(".feed li").forEach((li,k)=>{li.className=(k<=i?"seen ":"")+(k===i?"cur":"")});
 $("play").textContent=playing?"Pause":(i>=FRAMES.length-1?"Done":"Play")}
function step(d){const n=cur+d;if(n<0||n>=FRAMES.length)return false;render(n,true);return true}
function tick(){if(!step(1)){stop()}}
function play(){if(cur>=FRAMES.length-1)render(0,true);playing=true;clearInterval(timer);
 timer=setInterval(tick,3300/speed);$("play").textContent="Pause"}
function stop(){playing=false;clearInterval(timer);$("play").textContent=cur>=FRAMES.length-1?"Done":"Play"}
$("play").onclick=()=>playing?stop():play();
$("next").onclick=()=>{stop();step(1)};$("back").onclick=()=>{stop();step(-1)};
$("again").onclick=()=>{stop();render(0,true);play()};
$("speed").onclick=()=>{speed=speed===1?2:speed===2?0.5:1;$("speed").textContent=(speed===0.5?"½":speed)+"×";
 if(playing){clearInterval(timer);timer=setInterval(tick,3300/speed)}};
$("scrub").oninput=e=>{stop();render(+e.target.value,true)};
$("scrub").max=FRAMES.length-1;
const COL={neutral:"#8a97a3",ok:"#1f8a5b",bad:"#c7402f",warn:"#b7791f"};
FRAMES.forEach((f,k)=>{const li=document.createElement("li");const d=document.createElement("span");d.className="dot";
 d.style.background=({You:"#14202b",Planner:"#4f5bd5",Coder:"#0b7f8a",Executor:"#c98a12",Reviewer:"#1f8a5b",Result:"#1f8a5b"})[f.actor];
 const t=document.createElement("span");t.textContent=f.title;const ts=document.createElement("span");ts.className="ts";
 ts.textContent=k===0?"start":`+${f.t.toFixed(1)} s`;li.append(d,t,ts);li.onclick=()=>{stop();render(k,true)};$("feed").appendChild(li)});
render(0,false);
if(!reduce&&"IntersectionObserver" in window){new IntersectionObserver((es,ob)=>{if(es.some(e=>e.isIntersecting)&&!playing&&cur<1){ob.disconnect();setTimeout(play,500)}},{threshold:.35}).observe(document.querySelector(".stage"))}
else if(!reduce){setTimeout(play,800)}
</script></body></html>"""


def workflow_html(frames: list[Frame], meta: dict[str, Any] | None = None) -> str:
    """Full HTML document for `st.components.v1.html`. JSON is escaped so it cannot close the script."""

    def dump(value: Any) -> str:
        text = json.dumps(value, ensure_ascii=False)
        # no "<", ">" or "&" survives: the data can never close the script or open a tag
        return text.replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")

    return _TEMPLATE.replace("__FRAMES__", dump([f.to_dict() for f in frames])).replace(
        "__META__", dump(meta or {})
    )
