// panel_sectors.js: the by-sector panel. Needs echarts, common.js and data/index.js,
// and the markup of panel_sectors.html (ids of the controls and charts).

const state = { sp: "CO", sub: "anthro-surf", ds: "CMIP7-historical", view: "stack", res: "auto", scmode: "abs",
                hidden: new Set(), range: null, full: null };
const eTS = echarts.init(document.getElementById("e-ts"));
const eSH = echarts.init(document.getElementById("e-sh"));
const eSC = echarts.init(document.getElementById("e-sc"));
const status = (t, err) => { const s = document.getElementById("status"); s.textContent = t || ""; s.classList.toggle("err", !!err); };
const effRes = () => state.res !== "auto" ? state.res : (state.range[1] - state.range[0] < 50 ? "month" : "year");
const unit = () => effRes() === "month" ? "Tg/month" : "Tg/yr";
const fmtRange = () => `${Math.ceil(state.range[0] - 0.5)}–${Math.floor(state.range[1] - 0.5)}`;
const SECTOR_ORDER = Object.keys(SECTORS);
let SD = null, L = null, lastRes = null;   // L: {years, layers: [{key, label, color, rows}], total, note}

// Layers of one subset: its sectors without ALL/bbALL; if they do not add up to the
// total (e.g. historical bburning: only bbPEAT for CO2), the difference is a "rest" layer
function layers() {
  const d = SD.datasets[state.ds], secs = d.subsets[state.sub], years = d.years;
  const totKey = TOTAL_SECTORS.find(k => secs[k]);
  const parts = Object.keys(secs).filter(k => !TOTAL_SECTORS.includes(k))
                     .sort((a, b) => SECTOR_ORDER.indexOf(a) - SECTOR_ORDER.indexOf(b));
  const mk = k => ({ key: k, label: (SECTORS[k] || [k])[0] + ` (${k})`, color: css("--s" + ((SECTORS[k] || [0, 1])[1])), rows: secs[k] });
  if (!parts.length)
    return { years, layers: [Object.assign(mk(totKey), { label: `${(SECTORS[totKey] || [totKey])[0]} (${totKey}, no sector split)` })],
             note: `${dsLabel(state.ds)} gives ${state.sub} of ${state.sp} only as a total (${totKey}): no sector split.` };
  const out = parts.map(mk);
  let note = "";
  if (totKey) {
    const rest = years.map((_, i) => {
      const t = secs[totKey][i];
      return t == null || parts.some(k => secs[k][i] == null) ? null
        : MONTHS.map((_, m) => Math.max(0, t[m] - parts.reduce((a, k) => a + secs[k][i][m], 0)));
    });
    const restSum = rest.reduce((a, r) => a + (sum12(r) || 0), 0), totSum = secs[totKey].reduce((a, r) => a + (sum12(r) || 0), 0);
    if (totSum > 0 && restSum / totSum > 0.005) {
      out.push({ key: "rest", label: `Rest of ${totKey} (not split)`, color: css("--rest"), rows: rest });
      note = `The sectors given (${parts.join(", ")}) do not add up to ${totKey}: the difference is shown as "rest".`;
    }
  }
  return { years, layers: out, note };
}
const shown = () => L.layers.filter(l => !state.hidden.has(l.key));

function setFull() { state.full = [L.years[0], L.years[L.years.length - 1] + 1]; state.range = state.full.slice(); }

function drawTS() {
  lastRes = effRes();
  const res = effRes(), pct = state.view === "pct", stack = state.view !== "lines";
  const pts = L.layers.map(l => points(L.years, l.rows, res));
  const vis = L.layers.map(l => !state.hidden.has(l.key));
  const n = pts[0].length;
  const tot = [...Array(n).keys()].map(i => pts.some((p, j) => vis[j] && p[i][1] == null) ? null
                                                 : pts.reduce((a, p, j) => a + (vis[j] ? p[i][1] : 0), 0));
  const val = (j, i) => { const v = pts[j][i][1]; return v == null ? null : pct ? (tot[i] ? 100 * v / tot[i] : 0) : v; };
  // cumulative sums done here (ECharts stack on a value x axis drew only the first layer)
  let acc = null; const cum = [];
  L.layers.forEach((l, j) => {
    const v = [...Array(n).keys()].map(i => vis[j] ? val(j, i) : (val(j, i) == null ? null : 0));
    acc = stack ? (acc ? acc.map((a, i) => a == null || v[i] == null ? null : a + v[i]) : v.slice()) : v;
    cum.push(acc.map((y, i) => [pts[j][i][0], y]));
  });
  const order = stack ? [...L.layers.keys()].reverse() : [...L.layers.keys()];
  const gs = gaps(L.years);
  const series = order.map((j, k) => ({
    name: L.layers[j].label, type: "line", showSymbol: false, data: cum[j],
    lineStyle: stack ? { width: 0.8, color: css("--bg") } : { width: 1.8, color: L.layers[j].color },
    areaStyle: stack ? { color: L.layers[j].color, opacity: 1 } : null, itemStyle: { color: L.layers[j].color },
    markArea: k === 0 && gs.length ? gapArea(gs) : undefined }));
  if (res === "year") {   // years in runs of 1-2: dots, so they are not lost
    const iso = new Set(isolated(L.years, L.layers[0].rows).map(p => p[0]));
    L.layers.forEach((l, j) => {
      const d = cum[j].filter(p => iso.has(p[0]) && p[1] != null);
      if (d.length) series.push({ name: l.label, type: "scatter", data: d, symbolSize: 7, tooltip: { show: false },
        itemStyle: { color: l.color, borderColor: css("--bg"), borderWidth: 1.5 } });
    });
  }
  eTS.setOption({
    animation: false, textStyle: { fontFamily: "Lato, Arial, sans-serif", color: css("--fg") },
    title: titleOpt(`${state.sp} · ${state.sub} · ${dsLabel(state.ds)}`, `global, ${pct ? "% of total" : unit()}`),
    legend: { data: L.layers.map(l => l.label), top: 44, left: 0, right: 0, textStyle: { color: css("--muted") }, icon: "roundRect",
      itemWidth: 12, itemHeight: 8, inactiveColor: css("--line"),
      selected: Object.fromEntries(L.layers.map(l => [l.label, !state.hidden.has(l.key)])) },
    grid: { left: 60, right: 44, top: 112, bottom: 76 },
    tooltip: Object.assign(tipStyle(), { trigger: "axis", axisPointer: { type: "line", label: { formatter: p => decLabel(+p.value, effRes()) } },
      formatter: ps => {
        ps = ps.filter(p => p.seriesType === "line");
        if (!ps.length) return "";
        const i = ps[0].dataIndex, t = tot[i];
        if (t == null) return `<b>${decLabel(ps[0].value[0], res)}</b><br>no data`;
        const rows = L.layers.map((l, j) => ({ l, v: pts[j][i][1], j })).filter(o => vis[o.j]).reverse().map(o =>
          `<span style="color:${o.l.color}">●</span> ${o.l.label}<span style="float:right;margin-left:16px">${fmt(o.v)} (${t ? (100 * o.v / t).toFixed(1) : 0} %)</span>`);
        return `<b>${decLabel(ps[0].value[0], res)}</b><br>${rows.join("<br>")}<br><b>Total<span style="float:right">${fmt(t)} ${unit()}</span></b>`;
      } }),
    toolbox: toolbox(),
    graphic: [attribution()],
    xAxis: { type: "value", min: state.full[0], max: state.full[1], axisLine: axisStyle().axisLine, splitLine: { show: false },
      axisLabel: { color: css("--muted"), formatter: v => Math.round(v) } },
    yAxis: Object.assign({ type: "value", min: 0, max: pct ? 100 : null }, axisStyle()),
    dataZoom: [
      { type: "inside", xAxisIndex: 0, startValue: state.range[0], endValue: state.range[1], filterMode: "none" },
      { type: "slider", xAxisIndex: 0, height: 26, bottom: 20, borderColor: css("--line"), fillerColor: "rgba(41,128,185,.18)",
        textStyle: { color: css("--muted") }, labelFormatter: v => Math.round(v), filterMode: "none", showDataShadow: false },
      { type: "slider", yAxisIndex: 0, width: 16, right: 8, top: 112, bottom: 76, borderColor: css("--line"),
        fillerColor: "rgba(41,128,185,.18)", showDataShadow: false, labelFormatter: "", filterMode: "none" },
    ],
    series,
  }, { replaceMerge: ["series", "legend"] });
}
const inRange = (y) => y + 1 > state.range[0] && y < state.range[1];

function drawSH() {
  const items = shown().map(l => {
    const rows = l.rows.filter((m, i) => m && inRange(L.years[i]));
    return { l, n: rows.length, v: rows.reduce((a, m) => a + sum12(m), 0) / Math.max(1, rows.length) };
  }).sort((a, b) => a.v - b.v);
  const tot = items.reduce((a, o) => a + o.v, 0), n = Math.max(0, ...items.map(o => o.n));
  eSH.setOption({
    animation: false, textStyle: { fontFamily: "Lato, Arial, sans-serif", color: css("--fg") },
    grid: { left: 8, right: 60, top: 8, bottom: 24, containLabel: true },
    tooltip: Object.assign(tipStyle(), { trigger: "item", formatter: p => `${p.marker}${p.name}<br>${fmt(p.value)} Tg/yr · ${(100 * p.value / tot).toFixed(1)} %` }),
    xAxis: Object.assign({ type: "value", splitNumber: 2 }, axisStyle(), { axisLabel: { color: css("--muted"), formatter: v => fmt(v), hideOverlap: true } }),
    yAxis: { type: "category", data: items.map(o => o.l.label), axisLine: axisStyle().axisLine, axisTick: { show: false },
      axisLabel: { color: css("--fg"), width: 150, overflow: "break" } },
    series: [{ type: "bar", barMaxWidth: 26, data: items.map(o => ({ value: o.v, itemStyle: { color: o.l.color, borderRadius: [0, 4, 4, 0] } })),
      label: { show: true, position: "right", color: css("--muted"), fontSize: 11, formatter: p => tot ? `${(100 * p.value / tot).toFixed(1)} %` : "" } }],
  }, { replaceMerge: ["series"] });
  document.getElementById("cap-sh").textContent = n ? `Mean share, ${n} years with data in ${fmtRange()} (Tg/yr)` : `No data in ${fmtRange()}`;
}
function drawSC() {
  const rel = state.scmode === "rel";
  const series = shown().map(l => {
    const rows = l.rows.filter((m, i) => m && inRange(L.years[i]));
    if (!rows.length) return null;
    let v = MONTHS.map((_, i) => rows.reduce((a, m) => a + m[i], 0) / rows.length);
    if (rel) { const mean = v.reduce((a, b) => a + b, 0) / 12; v = v.map(x => mean ? x / mean : 0); }
    return { name: l.label, type: "line", data: v, symbol: "circle", symbolSize: 7, emphasis: { focus: "series" },
      lineStyle: { width: 2, color: l.color }, itemStyle: { color: l.color, borderColor: css("--bg"), borderWidth: 2 } };
  }).filter(Boolean);
  eSC.setOption({
    animation: false, textStyle: { fontFamily: "Lato, Arial, sans-serif", color: css("--fg") },
    grid: { left: 56, right: 16, top: 16, bottom: 30 },
    tooltip: Object.assign(tipStyle(), { trigger: "axis", order: "valueDesc",
      valueFormatter: v => v == null ? "" : rel ? (+v).toFixed(2) + " × mean" : fmt(+v) + " Tg/month" }),
    xAxis: Object.assign({ type: "category", data: MONTHS, boundaryGap: false }, axisStyle(), { splitLine: { show: false } }),
    yAxis: Object.assign({ type: "value", min: rel ? null : 0, scale: rel }, axisStyle()),
    series,
  }, { replaceMerge: ["series"] });
  document.getElementById("cap-sc").textContent = `Mean seasonal cycle per sector, years with data in ${fmtRange()}`;
}
function draw() {
  if (!SD) return;
  drawTS(); drawSH(); drawSC();
  document.getElementById("splitnote").textContent = L.note;
  eTS.resize(); eSH.resize(); eSC.resize();
}

eTS.on("datazoom", () => {
  const dz = eTS.getOption().dataZoom[0];
  if (dz.startValue === undefined) return;
  state.range = [dz.startValue, dz.endValue];
  if (effRes() !== lastRes) drawTS();
  drawSH(); drawSC();
});
eTS.on("restore", () => { state.range = state.full.slice(); draw(); });
eTS.on("legendselectchanged", e => {
  state.hidden = new Set(L.layers.filter(l => !e.selected[l.label]).map(l => l.key));
  drawTS(); drawSH(); drawSC();
});

// ---------- controls ----------
const spSel = document.getElementById("species"), subSel = document.getElementById("subset"), dsSel = document.getElementById("dataset");
fillSpecies(spSel); spSel.value = state.sp;
SUBSETS.forEach(s => subSel.add(new Option(s.label, s.id)));
subSel.value = state.sub;
presentDatasets().forEach(d => dsSel.add(new Option(d.label, d.id)));

function syncControls() {
  const subs = EMI.index.species[state.sp].subsets;
  for (const o of subSel.options) o.disabled = !Object.values(subs).some(x => x[o.value]);
  if (subSel.selectedOptions[0].disabled) subSel.value = [...subSel.options].find(o => !o.disabled).value;
  state.sub = subSel.value;
  for (const o of dsSel.options) {
    const has = !!(subs[o.value] && subs[o.value][state.sub]);
    o.disabled = !has; o.textContent = dsLabel(o.value) + (has ? "" : " (no data)");
  }
  dsSel.value = state.ds;
  if (!dsSel.selectedOptions[0] || dsSel.selectedOptions[0].disabled) dsSel.value = [...dsSel.options].find(o => !o.disabled).value;
  state.ds = dsSel.value;
  state.hidden.clear();
  L = layers(); setFull();
}
async function loadSpecies() {
  status(`Loading ${state.sp}…`);
  try { SD = await EMI.load(state.sp); } catch (e) { status(e.message, true); return; }
  status(""); syncControls(); draw();
}
spSel.addEventListener("change", () => { state.sp = spSel.value; loadSpecies(); });
subSel.addEventListener("change", () => { state.sub = subSel.value; syncControls(); draw(); });
dsSel.addEventListener("change", () => { state.ds = dsSel.value; syncControls(); draw(); });
function seg(id, key, redraw) {
  document.querySelectorAll(`#${id} button`).forEach(b => b.addEventListener("click", () => {
    state[key] = b.dataset.v;
    document.querySelectorAll(`#${id} button`).forEach(x => x.setAttribute("aria-pressed", x === b));
    redraw();
  }));
}
seg("view", "view", drawTS); seg("res", "res", drawTS); seg("scmode", "scmode", drawSC);
document.getElementById("gen").textContent = EMI.index.generated;

window.addEventListener("resize", () => { eTS.resize(); eSH.resize(); eSC.resize(); });
matchMedia("(prefers-color-scheme: dark)").addEventListener("change", () => { if (SD) { L = layers(); draw(); } });
new MutationObserver(() => { if (SD) { L = layers(); draw(); } }).observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
loadSpecies();
