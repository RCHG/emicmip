// panel_timeseries.js: the time-series panel. Needs echarts, common.js and data/index.js,
// and the markup of panel_timeseries.html (ids of the controls and charts).

const state = { sp: "CO", sub: "Total", on: new Set(presentDatasets().map(d => d.id)), res: "auto",
                gap: "break", season: true, range: null, full: null };
const eTS = echarts.init(document.getElementById("e-ts"));
const eSC = echarts.init(document.getElementById("e-sc"));
const status = (t, err) => { const s = document.getElementById("status"); s.textContent = t || ""; s.classList.toggle("err", !!err); };
const effRes = () => state.res !== "auto" ? state.res : (state.range[1] - state.range[0] < 50 ? "month" : "year");
const unit = () => effRes() === "month" ? "Tg/month" : "Tg/yr";
const fmtRange = () => `${Math.ceil(state.range[0] - 0.5)}–${Math.floor(state.range[1] - 0.5)}`;
let SD = null, lastRes = null;

// rows of the current subset for one dataset (or null)
function rowsFor(ds) { return state.sub === "Total" ? totalRows(SD, ds) : subsetRows(SD, ds, state.sub); }
const visible = () => presentDatasets().filter(d => state.on.has(d.id) && rowsFor(d.id));

function setFull() {
  const ys = visible().flatMap(d => SD.datasets[d.id].years);
  state.full = ys.length ? [Math.min(...ys), Math.max(...ys) + 1] : [1750, 2101];
  state.range = state.full.slice();
}

function drawTS() {
  lastRes = effRes();
  const res = effRes(), series = [];
  for (const d of visible()) {
    const r = rowsFor(d.id), c = dsColor(d.id);
    series.push({ name: d.label, type: "line", data: points(r.years, r.rows, res), showSymbol: false,
      connectNulls: state.gap === "connect", lineStyle: { width: 1.6, color: c }, itemStyle: { color: c },
      markArea: gaps(r.years).length ? gapArea(gaps(r.years)) : undefined });
    if (res === "year" && state.gap === "break") {
      const iso = isolated(r.years, r.rows);
      if (iso.length) series.push({ name: d.label, type: "scatter", data: iso, symbolSize: 7,
        itemStyle: { color: c, borderColor: css("--bg"), borderWidth: 1.5 }, tooltip: { show: false } });
    }
  }
  const sub = state.sub === "Total" ? "Total" : state.sub;
  eTS.setOption({
    animation: false, textStyle: { fontFamily: "Lato, Arial, sans-serif", color: css("--fg") },
    title: titleOpt(`${state.sp} · ${sub}`, `global, ${unit()}`),
    legend: { top: 44, left: 0, textStyle: { color: css("--muted") }, icon: "roundRect", itemWidth: 14, itemHeight: 4,
      data: visible().map(d => d.label) },
    grid: { left: 60, right: 44, top: 104, bottom: 76 },
    tooltip: Object.assign(tipStyle(), { trigger: "axis",
      valueFormatter: v => v == null ? "no data" : fmt(+v) + " " + unit(),
      axisPointer: { type: "line", label: { formatter: p => decLabel(+p.value, effRes()) } } }),
    toolbox: toolbox({ dataView: { title: "Table", readOnly: true, lang: ["Data", "Close", ""],
      backgroundColor: css("--bg"), textColor: css("--fg"), textareaColor: css("--panel"), textareaBorderColor: css("--line"),
      buttonColor: css("--accent"), buttonTextColor: css("--accent-ink") } }),
    graphic: [attribution()],
    xAxis: { type: "value", min: state.full[0], max: state.full[1], axisLine: axisStyle().axisLine, splitLine: { show: false },
      axisLabel: { color: css("--muted"), formatter: v => Math.round(v) } },
    yAxis: Object.assign({ type: "value", min: 0 }, axisStyle()),
    dataZoom: [
      { type: "inside", xAxisIndex: 0, startValue: state.range[0], endValue: state.range[1], filterMode: "none" },
      { type: "slider", xAxisIndex: 0, height: 26, bottom: 20, borderColor: css("--line"), fillerColor: "rgba(41,128,185,.18)",
        textStyle: { color: css("--muted") }, labelFormatter: v => Math.round(v), filterMode: "none", showDataShadow: false },
      { type: "slider", yAxisIndex: 0, width: 16, right: 8, top: 104, bottom: 76, borderColor: css("--line"),
        fillerColor: "rgba(41,128,185,.18)", showDataShadow: false, labelFormatter: "", filterMode: "none" },
    ],
    series,
  }, { replaceMerge: ["series", "legend"] });
}

function drawSC() {
  if (!state.season) return;
  let nmax = 0;
  const series = visible().map(d => {
    const r = rowsFor(d.id);
    const rows = r.rows.filter((m, i) => m && r.years[i] + 1 > state.range[0] && r.years[i] < state.range[1]);
    nmax = Math.max(nmax, rows.length);
    if (!rows.length) return null;
    const c = dsColor(d.id);
    return { name: d.label, type: "line", symbol: "circle", symbolSize: 8,
      data: MONTHS.map((_, i) => rows.reduce((a, m) => a + m[i], 0) / rows.length),
      lineStyle: { width: 2, color: c }, itemStyle: { color: c, borderColor: css("--bg"), borderWidth: 2 } };
  }).filter(Boolean);
  eSC.setOption({
    animation: false, textStyle: { fontFamily: "Lato, Arial, sans-serif", color: css("--fg") },
    grid: { left: 52, right: 12, top: 14, bottom: 30 },
    tooltip: Object.assign(tipStyle(), { trigger: "axis", valueFormatter: v => fmt(+v) + " Tg/month" }),
    xAxis: Object.assign({ type: "category", data: MONTHS, boundaryGap: false }, axisStyle(), { splitLine: { show: false } }),
    yAxis: Object.assign({ type: "value", min: 0 }, axisStyle()),
    series,
  }, { replaceMerge: ["series"] });
  document.getElementById("cap-sc").textContent =
    `Mean seasonal cycle, years with data in ${fmtRange()} (Tg/month)` + (series.length ? "" : ": no data in this range");
}

function totalNote() {
  const el = document.getElementById("totalnote");
  if (state.sub !== "Total") { el.textContent = ""; return; }
  const used = new Set(visible().flatMap(d => totalRows(SD, d.id).used));
  el.textContent = `Total = anthro-surf (ALL) + anthro-air (AVI) + bburning (bbALL); anthro-biof is part of anthro-surf and not added. `
    + `For ${state.sp}: ${[...used].join(" + ") || "none"}.`;
}

function draw() {
  document.getElementById("pane").classList.toggle("one", !state.season);
  document.getElementById("seasonbox").hidden = !state.season;
  if (!SD) return;
  if (!visible().length) status("No data for this species and subset in the selected datasets.", true); else status("");
  drawTS(); drawSC(); totalNote();
  eTS.resize(); eSC.resize();
}

eTS.on("datazoom", () => {
  const dz = eTS.getOption().dataZoom[0];
  if (dz.startValue === undefined) return;
  state.range = [dz.startValue, dz.endValue];
  if (effRes() !== lastRes) drawTS();
  drawSC();
});
eTS.on("restore", () => { state.range = state.full.slice(); drawTS(); drawSC(); });

// ---------- controls ----------
const spSel = document.getElementById("species"), subSel = document.getElementById("subset");
fillSpecies(spSel);
spSel.value = state.sp;
subSel.add(new Option("Total", "Total"));
SUBSETS.forEach(s => subSel.add(new Option(s.label, s.id)));

function syncControls() {
  // subsets: enabled when at least one dataset has it for this species
  const subs = EMI.index.species[state.sp].subsets;
  for (const o of subSel.options) {
    const ok = o.value === "Total" ? SUBSETS.some(s => s.inTotal && Object.values(subs).some(x => x[s.id]))
                                   : Object.values(subs).some(x => x[o.value]);
    o.disabled = !ok;
  }
  if (subSel.selectedOptions[0].disabled) subSel.value = [...subSel.options].find(o => !o.disabled).value;
  state.sub = subSel.value;
  // datasets: greyed when they have no data for species/subset
  for (const d of presentDatasets()) {
    const lab = document.getElementById("lab-" + d.id), has = !!rowsFor(d.id);
    lab.classList.toggle("off", !has);
    lab.querySelector("input").disabled = !has;
    lab.querySelector("small").textContent = has ? yearsText(SD.datasets[d.id].years) : "no data";
  }
}
const yearsText = ys => ys[0] + "–" + ys[ys.length - 1] + (gaps(ys).length ? " (with gaps)" : "");

const box = document.getElementById("datasets");
for (const d of presentDatasets()) {
  const lab = document.createElement("label");
  lab.id = "lab-" + d.id;
  lab.innerHTML = `<input type="checkbox" id="ds-${d.id}" checked><span class="sw" style="background:var(--s${d.slot})"></span>${d.label} <small></small>`;
  lab.querySelector("input").addEventListener("change", e => {
    e.target.checked ? state.on.add(d.id) : state.on.delete(d.id); setFull(); draw(); });
  box.append(lab);
}
async function loadSpecies() {
  status(`Loading ${state.sp}…`);
  try { SD = await EMI.load(state.sp); } catch (e) { status(e.message, true); return; }
  syncControls(); setFull(); draw();
}
spSel.addEventListener("change", () => { state.sp = spSel.value; loadSpecies(); });
subSel.addEventListener("change", () => { state.sub = subSel.value; syncControls(); setFull(); draw(); });
function seg(id, key) {
  document.querySelectorAll(`#${id} button`).forEach(b => b.addEventListener("click", () => {
    state[key] = b.dataset.v;
    document.querySelectorAll(`#${id} button`).forEach(x => x.setAttribute("aria-pressed", x === b));
    draw();
  }));
}
seg("res", "res"); seg("gapmode", "gap");
const sBtn = document.getElementById("season");
sBtn.addEventListener("click", () => { state.season = !state.season; sBtn.setAttribute("aria-pressed", state.season); draw(); });
document.getElementById("gen").textContent = EMI.index.generated;

window.addEventListener("resize", () => { eTS.resize(); eSC.resize(); });
matchMedia("(prefers-color-scheme: dark)").addEventListener("change", draw);
new MutationObserver(draw).observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
loadSpecies();
