"""Generate self-contained HTML D3.js force-directed graph from graph data."""

from __future__ import annotations
import json
from pathlib import Path
from deepgraph.core.graph import TypedMultiGraph


def export_html(graph: TypedMultiGraph,
                output: Path,
                title: str = "DeepGraph",
                *,
                show_all_nodes: bool = False) -> Path:
    """Export a graph as a self-contained HTML file with D3.js force-directed graph.

    By default only class/interface/enum/record/module nodes are shown (structural view).
    Set show_all_nodes=True to include fields, methods, functions, constructors.
    """
    data = graph.to_json_dict()

    deg: dict[str, int] = {}
    for e in data["edges"]:
        deg[e["source_id"]] = deg.get(e["source_id"], 0) + 1
        deg[e["target_id"]] = deg.get(e["target_id"], 0) + 1
    for n in data["nodes"]:
        n["degree"] = deg.get(n["id"], 0)

    json_data = json.dumps(data)

    initial_filter = '"class","interface","enum","record","module"' if not show_all_nodes else \
        '"class","interface","enum","record","module","method","function","field","constructor"'

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title}</title>
<script src="https://d3js.org/d3.v7.min.js"></script>
<style>
:root {{
  --canvas: #1a1a1a;
  --canvas-soft: #252525;
  --canvas-card: #2a2a2a;
  --hairline: #3a3a3a;
  --ink: #e0e0e0;
  --ink-hover: #ffffff;
  --body: #aaaaaa;
  --body-mid: #777777;
  --text-input-bg: #252525;
  --svg-stroke: #1a1a1a;
}}
[data-theme="light"] {{
  --canvas: #e4e0da;
  --canvas-soft: #d4d0ca;
  --canvas-card: #eeebe6;
  --hairline: #b8b4ae;
  --ink: #1e1e1e;
  --ink-hover: #000000;
  --body: #555555;
  --body-mid: #888888;
  --text-input-bg: #eeebe6;
  --svg-stroke: #e4e0da;
}}

* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{ font-family: Inter, system-ui, -apple-system, sans-serif; background: var(--canvas); color: var(--body); overflow: hidden; height: 100vh; transition: background .2s, color .2s; }}
#container {{ display: flex; height: 100vh; }}
#sidebar {{ width: 220px; background: var(--canvas); padding: 16px; overflow-y: auto; border-right: 1px solid var(--hairline); flex-shrink: 0; transition: background .2s, border-color .2s; }}
#sidebar h2 {{ font-family: Inter, sans-serif; font-size: 13px; font-weight: 400; color: var(--ink); margin-bottom: 8px; letter-spacing: -0.3px; text-transform: uppercase; transition: color .2s; }}
#sidebar h3 {{ font-family: GeistMono, ui-monospace, SFMono-Regular, monospace; font-size: 11px; font-weight: 400; color: var(--body-mid); margin: 14px 0 6px; letter-spacing: 1.2px; text-transform: uppercase; transition: color .2s; }}
#graph {{ flex: 1; position: relative; }}
.control-group {{ margin-bottom: 8px; }}
.control-group label {{ display: flex; align-items: center; gap: 6px; font-size: 12px; font-weight: 400; color: var(--body); padding: 3px 0; cursor: pointer; transition: color .2s; }}
.control-group label:hover {{ color: var(--ink-hover); }}
.control-group input[type="checkbox"] {{ appearance: none; width: 14px; height: 14px; border: 1px solid var(--hairline); border-radius: 6px; background: transparent; cursor: pointer; flex-shrink: 0; transition: background .15s, border-color .15s; }}
.control-group input[type="checkbox"]:checked {{ background: var(--ink); border-color: var(--ink); }}
.control-group input[type="text"] {{ width: 100%; padding: 7px 10px; border: 1px solid var(--hairline); background: var(--text-input-bg); color: var(--ink); border-radius: 8px; font-size: 12px; font-family: Inter, sans-serif; outline: none; transition: background .2s, color .2s, border-color .2s; }}
.control-group input[type="text"]:focus {{ border-color: var(--ink); }}
.stats {{ font-family: GeistMono, ui-monospace, SFMono-Regular, monospace; font-size: 10px; color: var(--body-mid); margin-top: 8px; letter-spacing: 0.5px; line-height: 1.5; text-transform: uppercase; transition: color .2s; }}
.node-label {{ font-family: Inter, sans-serif; font-size: 9px; letter-spacing: -0.2px; font-weight: 400; pointer-events: none; }}
.edge-label {{ font-family: GeistMono, ui-monospace, monospace; font-size: 7px; letter-spacing: 0.8px; text-transform: uppercase; fill: var(--body-mid); pointer-events: none; transition: fill .2s; }}
#tooltip {{ position: absolute; display: none; background: var(--canvas-card); border: 1px solid var(--hairline); border-radius: 8px; padding: 10px 14px; font-size: 12px; max-width: 260px; pointer-events: none; z-index: 100; transition: background .2s, border-color .2s; }}
#tooltip .name {{ font-family: Inter, sans-serif; color: var(--ink); font-size: 13px; letter-spacing: -0.3px; transition: color .2s; }}
#tooltip .meta {{ font-family: GeistMono, ui-monospace, monospace; color: var(--body-mid); font-size: 10px; margin-top: 4px; letter-spacing: 0.3px; text-transform: uppercase; transition: color .2s; }}
#tooltip .prop {{ color: var(--body); font-size: 11px; margin-top: 2px; transition: color .2s; }}
.legend {{ margin-top: 14px; }}
.legend-item {{ display: flex; align-items: center; gap: 6px; font-size: 10px; font-weight: 400; color: var(--body-mid); padding: 2px 0; letter-spacing: 0.2px; text-transform: uppercase; font-family: GeistMono, ui-monospace, monospace; transition: color .2s; }}
.legend-color {{ width: 7px; height: 7px; border-radius: 50%; flex-shrink: 0; }}

#theme-toggle {{ font-family: GeistMono, ui-monospace, monospace; font-size: 10px; letter-spacing: 1px; text-transform: uppercase; border: 1px solid var(--hairline); border-radius: 9999px; padding: 4px 10px; background: transparent; color: var(--body-mid); cursor: pointer; transition: color .2s, border-color .2s; margin-top: 12px; width: 100%; }}
#theme-toggle:hover {{ color: var(--ink); border-color: var(--ink); }}
</style>
</head>
<body>
<div id="container">
<div id="sidebar">
  <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px">
    <h2 style="margin-bottom:0">{title}</h2>
    <button id="theme-toggle" onclick="toggleTheme()">Dark</button>
  </div>
  <div class="control-group">
    <input type="text" id="search" placeholder="Filter nodes..." oninput="filterGraph()">
  </div>
  <h3>Node Types</h3>
  <div class="control-group" id="node-filters"></div>
  <h3>Edge Types</h3>
  <div class="control-group" id="edge-filters"></div>
  <h3>Display</h3>
  <div class="control-group">
    <label><input type="checkbox" id="chk-edge-labels" checked onchange="filterGraph()"> Edge labels</label>
    <label><input type="checkbox" id="chk-node-labels" checked onchange="filterGraph()"> Node labels</label>
  </div>
  <div class="stats" id="stats"></div>
  <div class="legend" id="legend"></div>
</div>
<div id="graph"><div id="tooltip"></div></div>
</div>
<script>
const DATA = {json_data};

const DARK_NODES = {{class:"#ff7a17",interface:"#7c3aed",enum:"#c4b5fd",record:"#a0c3ec",
  module:"#a0c3ec",method:"#c0c0c0",function:"#c0c0c0",field:"#888888",constructor:"#888888",unknown:"#4a4a4a"}};
const DARK_EDGES = {{extends:"#ff7a17",implements:"#7c3aed",contains:"#3a3a3a",depends_on:"#4a4a4a",references:"#a0c3ec",unknown:"#3a3a3a"}};
const LIGHT_NODES = {{class:"#ff7a17",interface:"#7c3aed",enum:"#9a7ce0",record:"#7ba9d4",
  module:"#7ba9d4",method:"#444444",function:"#444444",field:"#777777",constructor:"#777777",unknown:"#b0b0b0"}};
const LIGHT_EDGES = {{extends:"#ff7a17",implements:"#7c3aed",contains:"#b8b4ae",depends_on:"#9a9690",references:"#7ba9d4",unknown:"#b8b4ae"}};

const INITIAL_TYPES = [{initial_filter}];

let svg, g, simulation, linkG, nodeG, labelG, edgeLabelG, tooltip;
let nodeEls = {{}}, linkEls = {{}}, labelEls = {{}}, edgeLabelEls = {{}};
let nodeById = {{}}, edgeByKey = {{}};
let nodeFilter = {{}}, edgeFilter = {{}};
let width, height;
let currentTheme = 'dark', visibleNodeIds = new Set(), visibleEdgeKeys = new Set();
let nodePalette = DARK_NODES, edgePalette = DARK_EDGES;

function toggleTheme() {{
  const html = document.documentElement;
  const btn = document.getElementById('theme-toggle');
  if (currentTheme === 'dark') {{
    html.setAttribute('data-theme', 'light');
    btn.textContent = 'Light';
    currentTheme = 'light';
    nodePalette = LIGHT_NODES;
    edgePalette = LIGHT_EDGES;
  }} else {{
    html.removeAttribute('data-theme');
    btn.textContent = 'Dark';
    currentTheme = 'dark';
    nodePalette = DARK_NODES;
    edgePalette = DARK_EDGES;
  }}
  repaintGraph();
  updateLegend();
}}

function updateLegend() {{
  const lg = document.getElementById('legend');
  lg.innerHTML = '<h3>Legend</h3>';
  Object.entries(nodePalette).filter(([k])=>k!=='unknown').forEach(([k,v])=> {{
    lg.innerHTML += '<div class=legend-item><span class=legend-color style=background:'+v+'></span>'+k+'</div>';
  }});
}}

function repaintGraph() {{
  DATA.nodes.forEach(n => {{
    const c = nodeEls[n.id];
    if (c) c.attr('fill', nodePalette[n.type]||nodePalette.unknown);
    const l = labelEls[n.id];
    if (l) l.attr('fill', nodePalette[n.type]||nodePalette.unknown);
  }});
  DATA.edges.forEach(e => {{
    const key = e.source_id+'|'+e.target_id+'|'+(e.key||'');
    const l = linkEls[key];
    if (l) l.attr('stroke', edgePalette[e.type]||edgePalette.unknown);
  }});
}}

function init() {{
  const el = document.getElementById('graph');
  width = el.clientWidth; height = el.clientHeight;
  tooltip = document.getElementById('tooltip');
  svg = d3.select(el).insert('svg','#tooltip').attr('width',width).attr('height',height);
  svg.call(d3.zoom().scaleExtent([0.05,10]).on('zoom',e=>g.attr('transform',e.transform)));
  g = svg.append('g');

  DATA.nodes.forEach(n => nodeById[n.id] = n);
  DATA.edges.forEach(e => {{
    const k = e.source_id+'|'+e.target_id+'|'+(e.key||'');
    edgeByKey[k] = e;
  }});

  const deg = {{}};
  DATA.nodes.forEach(n => deg[n.id]=0);
  DATA.edges.forEach(e => {{ deg[e.source_id]=(deg[e.source_id]||0)+1; deg[e.target_id]=(deg[e.target_id]||0)+1; }});
  DATA.nodes.forEach(n => n.degree=deg[n.id]||0);

  linkG = g.append('g');
  edgeLabelG = g.append('g');
  nodeG = g.append('g');
  labelG = g.append('g');

  DATA.nodes.forEach(n => {{
    const r = Math.max(3, Math.min(14, 3 + Math.sqrt(n.degree||1)*2));
    const circle = nodeG.append('circle').attr('r',r).attr('fill',nodePalette[n.type]||nodePalette.unknown)
      .attr('stroke','var(--svg-stroke)').attr('stroke-width',1.5)
      .on('mouseover',e=>showTooltip(n,e)).on('mouseout',hideTooltip)
      .call(d3.drag().on('start',(e,d)=>{{if(!e.active)simulation.alphaTarget(0.02).restart();d.fx=d.x;d.fy=d.y;}})
        .on('drag',(e,d)=>{{d.fx=+e.x;d.fy=+e.y;}}).on('end',(e,d)=>{{if(!e.active)simulation.alphaTarget(0);d.fx=null;d.fy=null;}}));
    nodeEls[n.id] = circle;
    const lbl = labelG.append('text').text(n.label||n.id).attr('font-size','9px')
      .attr('fill',nodePalette[n.type]||nodePalette.unknown).attr('dy','0.35em').attr('dx','5');
    labelEls[n.id] = lbl;
  }});

  DATA.edges.forEach(e => {{
    const c = edgePalette[e.type]||edgePalette.unknown;
    const w = Math.max(0.5, Math.min(3, (e.weight||1)*0.5));
    const dash = e.type==='references'?'4,3':e.type==='depends_on'?'2,2':'';
    const key = e.source_id+'|'+e.target_id+'|'+(e.key||'');
    const line = linkG.append('line').attr('stroke',c).attr('stroke-width',w)
      .attr('stroke-opacity',0.6).attr('stroke-dasharray',dash)
      .on('mouseover',ev=>showEdgeTooltip(e,ev)).on('mouseout',hideTooltip);
    linkEls[key] = line;
    const lbl = edgeLabelG.append('text').attr('font-size','7px').attr('fill','var(--body-mid)')
      .attr('text-anchor','middle').attr('dy','-4').attr('font-family','GeistMono,ui-monospace,monospace');
    edgeLabelEls[key] = lbl;
  }});

  const allTypes = [...new Set(DATA.nodes.map(n=>n.type))].sort();
  const allEdgeTypes = [...new Set(DATA.edges.map(e=>e.type))].sort();
  const nf = document.getElementById('node-filters');
  allTypes.forEach(t => {{
    nodeFilter[t] = INITIAL_TYPES.includes(t);
    const lb = document.createElement('label');
    lb.innerHTML = '<input type=checkbox'+(nodeFilter[t]?' checked':'')+' onchange="nodeFilter[\\''+t+'\\']=this.checked;filterGraph()">'+t;
    nf.appendChild(lb);
  }});
  const ef = document.getElementById('edge-filters');
  allEdgeTypes.forEach(t => {{
    edgeFilter[t] = true;
    const lb = document.createElement('label');
    lb.innerHTML = '<input type=checkbox checked onchange="edgeFilter[\\''+t+'\\']=this.checked;filterGraph()">'+t;
    ef.appendChild(lb);
  }});

  const lg = document.getElementById('legend');
  lg.innerHTML = '<h3>Legend</h3>';
  Object.entries(nodePalette).filter(([k])=>k!=='unknown').forEach(([k,v])=> {{
    lg.innerHTML += '<div class=legend-item><span class=legend-color style=background:'+v+'></span>'+k+'</div>';
  }});

  updateStats();
  filterGraph();

  const linkedEdges = DATA.edges.map(e => ({{...e, source: e.source_id, target: e.target_id}}));

  simulation = d3.forceSimulation(DATA.nodes)
    .alphaDecay(0.08).alphaMin(0.001).velocityDecay(0.4)
    .force('link', d3.forceLink(linkedEdges).id(d=>d.id).distance(e=>e.type==='contains'?30:100))
    .force('charge', d3.forceManyBody().strength(-80))
    .force('center', d3.forceCenter(width/2, height/2))
    .force('collision', d3.forceCollide().radius(d=>4+Math.sqrt(d.degree||1)*2))
    .on('tick', ticked);
}}

function ticked() {{
  // Only update visible elements — invisible ones don't move on screen
  visibleEdgeKeys.forEach(k => {{
    const e = edgeByKey[k];
    const s = nodeById[e.source_id];
    const t = nodeById[e.target_id];
    if (!s||!t) return;
    linkEls[k].attr('x1',s.x).attr('y1',s.y).attr('x2',t.x).attr('y2',t.y);
    const elbl = edgeLabelEls[k];
    if (elbl) elbl.attr('x',(s.x+t.x)/2).attr('y',(s.y+t.y)/2);
  }});
  visibleNodeIds.forEach(id => {{
    const n = nodeById[id];
    nodeEls[id].attr('cx',n.x).attr('cy',n.y);
    const lbl = labelEls[id];
    if (lbl) lbl.attr('x',n.x+5).attr('y',n.y);
  }});
}}

function filterGraph() {{
  const search = document.getElementById('search').value.toLowerCase();
  const showEdgeLabels = document.getElementById('chk-edge-labels').checked;
  const showNodeLabels = document.getElementById('chk-node-labels').checked;

  visibleNodeIds = new Set();
  DATA.nodes.forEach(n => {{
    const ok = nodeFilter[n.type] !== false && (n.label||'').toLowerCase().includes(search);
    nodeEls[n.id].attr('display', ok ? null : 'none');
    labelEls[n.id].attr('display', (ok && showNodeLabels) ? null : 'none');
    if (ok) visibleNodeIds.add(n.id);
  }});

  visibleEdgeKeys = new Set();
  DATA.edges.forEach(e => {{
    const key = e.source_id+'|'+e.target_id+'|'+(e.key||'');
    const ok = edgeFilter[e.type] !== false && visibleNodeIds.has(e.source_id) && visibleNodeIds.has(e.target_id);
    const l = linkEls[key];
    if (l) l.attr('display', ok ? null : 'none');
    const lbl = edgeLabelEls[key];
    if (lbl) lbl.attr('display', (ok && showEdgeLabels) ? null : 'none')
      .text(ok ? (e.cardinality ? e.type+' '+e.cardinality : e.type) : '');
    if (ok) visibleEdgeKeys.add(key);
  }});

  updateStats(visibleNodeIds.size);
}}

function updateStats(visibleCount) {{
  const vis = visibleCount !== undefined ? visibleCount : DATA.nodes.length;
  document.getElementById('stats').innerHTML = 'Nodes: '+vis+'/'+DATA.nodes.length+'<br>Edges: '+DATA.edges.length;
}}

function showTooltip(n, e) {{
  let html = '<div class=name>'+(n.label||n.id)+'</div><div class=meta>'+n.type+'</div>';
  if (n.source_location) html += '<div class=meta>'+n.source_location+'</div>';
  if (n.degree!==undefined) html += '<div class=prop>Degree: '+n.degree+'</div>';
  tooltip.innerHTML = html; tooltip.style.display='block';
  const rect = document.getElementById('graph').getBoundingClientRect();
  tooltip.style.left=(e.clientX-rect.left+12)+'px'; tooltip.style.top=(e.clientY-rect.top-10)+'px';
}}

function showEdgeTooltip(e, ev) {{
  const src = nodeById[e.source_id];
  const tgt = nodeById[e.target_id];
  const sn = src?src.label||src.id:e.source_id;
  const tn = tgt?tgt.label||tgt.id:e.target_id;
  tooltip.innerHTML = '<div class=name>'+(e.cardinality?e.type+' '+e.cardinality:e.type)+'</div><div class=meta>'+sn+' -> '+tn+'</div>';
  tooltip.style.display='block';
  const rect = document.getElementById('graph').getBoundingClientRect();
  tooltip.style.left=(ev.clientX-rect.left+12)+'px'; tooltip.style.top=(ev.clientY-rect.top-10)+'px';
}}

function hideTooltip() {{ tooltip.style.display='none'; }}

window.addEventListener('load', init);
window.addEventListener('resize', () => {{
  width = document.getElementById('graph').clientWidth;
  height = document.getElementById('graph').clientHeight;
  svg.attr('width',width).attr('height',height);
  simulation.force('center', d3.forceCenter(width/2, height/2));
}});
</script>
</body>
</html>"""

    output.write_text(html, encoding="utf-8")
    return output
