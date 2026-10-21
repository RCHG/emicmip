// Shared by panel_timeseries.html and panel_sectors.html: data loading, names,
// colours, gap-aware series. Data files: data/index.js + data/<species>.js
// (written by _private/tools/make_webstats_js.py), loaded as scripts so the
// pages also work opened from disk.

window.EMI = {
  base: "data/",           // folder of the data files, relative to the page
  index: null,
  data: {},
  add(d) { this.data[d.species] = d; },
  load(sp) {
    if (this.data[sp]) return Promise.resolve(this.data[sp]);
    return new Promise((ok, fail) => {
      const s = document.createElement("script");
      s.src = this.base + this.index.species[sp].file;
      s.onload = () => ok(this.data[sp]);
      s.onerror = () => fail(new Error(`Could not load ${this.base}${this.index.species[sp].file}`));
      document.head.append(s);
    });
  },
};

// Datasets in fixed order: the colour slot follows the dataset, never its position
const DATASETS = [
  { id: "CMIP6-jointversion", label: "CMIP6 historical", slot: 1 },
  { id: "CMIP7-historical",   label: "CMIP7 historical", slot: 2 },
  { id: "ScenarioMIPh",       label: "ScenarioMIP-h",    slot: 3 },
  { id: "ScenarioMIPm",       label: "ScenarioMIP-m",    slot: 4 },
  { id: "ScenarioMIPl",       label: "ScenarioMIP-l",    slot: 5 },
  { id: "ScenarioMIPvl",      label: "ScenarioMIP-vl",   slot: 6 },
];
// Subsets as in the tar file names; inTotal: added to "Total"
const SUBSETS = [
  { id: "anthro-surf", label: "anthro-surf (surface anthropogenic)", inTotal: true },
  { id: "anthro-biof", label: "anthro-biof (solid biofuel, part of anthro-surf)", inTotal: false },
  { id: "anthro-air",  label: "anthro-air (aviation)", inTotal: true },
  { id: "bburning",    label: "bburning (open biomass burning)", inTotal: true },
];
const TOTAL_SECTORS = ["ALL", "bbALL"];   // already the total of their file: never add them to the sectors
const SECTORS = {
  AGR: ["Agriculture", 1], ENE: ["Energy", 2], IND: ["Industry", 3], TRA: ["Transport", 4],
  RCO: ["Residential & commercial", 5], SLV: ["Solvents", 6], WST: ["Waste", 7], SHP: ["Shipping", 8],
  AVI: ["Aviation", 1],
  bbAGRW: ["Agricultural waste burning", 1], bbFORE: ["Forest burning", 2],
  bbGRSS: ["Grassland burning", 3], bbPEAT: ["Peat burning", 4],
  ALL: ["All sectors", 1], bbALL: ["All open burning", 1],
};
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const COMMON_SPECIES = ["BC", "OC", "SO2", "NOx", "CO", "NH3", "CH4", "CO2", "N2O", "NMVOC"];
const ATTRIBUTION = "Made with emicmip (KNMI), doi:10.5281/zenodo.23440591 · CC BY 4.0 · data: CEDS, BB4CMIP7, ScenarioMIP (input4MIPs)";

// Colour tokens: from the .emiviz box when embedded in the web, else from :root
const css = n => getComputedStyle(document.querySelector(".emiviz") || document.documentElement).getPropertyValue(n).trim();
const dsLabel = id => (DATASETS.find(d => d.id === id) || { label: id }).label;
const dsColor = id => css("--s" + ((DATASETS.find(d => d.id === id) || { slot: 1 }).slot));
const fmt = v => v == null ? "no data" : v >= 100 ? v.toFixed(0) : v >= 10 ? v.toFixed(1) : v >= 1 ? v.toFixed(2) : v.toPrecision(3);
const sum12 = m => m == null ? null : m.reduce((a, b) => a + b, 0);

// Datasets present in the data, in fixed order
function presentDatasets() { return DATASETS.filter(d => EMI.index.datasets[d.id]); }

// Species list: common ones first, then the rest alphabetically
function fillSpecies(sel) {
  const all = Object.keys(EMI.index.species);
  const g1 = document.createElement("optgroup"); g1.label = "Main species";
  const g2 = document.createElement("optgroup"); g2.label = "Other species (VOC split, biomass-burning species)";
  COMMON_SPECIES.filter(s => all.includes(s)).forEach(s => g1.append(new Option(s, s)));
  all.filter(s => !COMMON_SPECIES.includes(s)).sort().forEach(s => g2.append(new Option(s, s)));
  sel.append(g1, g2);
}

// One subset of one dataset -> {years, rows: [12 values | null] per year, key}
// The total sector (ALL / bbALL) when present, else the single sector, else the sum.
function subsetRows(sd, ds, sub) {
  const d = sd.datasets[ds]; const secs = d && d.subsets[sub];
  if (!secs) return null;
  let key = TOTAL_SECTORS.find(k => secs[k]) || (Object.keys(secs).length === 1 ? Object.keys(secs)[0] : null);
  if (key) return { years: d.years, rows: secs[key], key };
  const keys = Object.keys(secs);
  return { years: d.years, key: "sum", rows: d.years.map((_, i) =>
    keys.some(k => secs[k][i] == null) ? null : MONTHS.map((_, m) => keys.reduce((a, k) => a + secs[k][i][m], 0))) };
}
// "Total" = sum of the inTotal subsets present for this species/dataset
function totalRows(sd, ds) {
  const parts = SUBSETS.filter(s => s.inTotal).map(s => ({ s, r: subsetRows(sd, ds, s.id) })).filter(o => o.r);
  if (!parts.length) return null;
  const years = parts[0].r.years;
  return { years, used: parts.map(o => o.s.id), rows: years.map((_, i) =>
    parts.some(o => o.r.rows[i] == null) ? null : MONTHS.map((_, m) => parts.reduce((a, o) => a + o.r.rows[i][m], 0))) };
}

// Gap-aware points over the continuous years y0..y1: missing years -> null (line breaks)
function points(years, rows, res) {
  const byYear = new Map(years.map((y, i) => [y, rows[i]]));
  const out = [];
  for (let y = years[0]; y <= years[years.length - 1]; y++) {
    const m = byYear.get(y);
    if (res === "year") out.push([y + 0.5, m ? sum12(m) : null]);
    else for (let i = 0; i < 12; i++) out.push([y + (i + 0.5) / 12, m ? m[i] : null]);
  }
  return out;
}
// Annual points in runs of 1-2 years (e.g. 1800, or 1850-1851): too short to see
// as a line, also drawn as dots
function isolated(years, rows) {
  const have = new Set(years.filter((y, i) => rows[i] != null));
  const runLen = y => { let a = y, b = y; while (have.has(a - 1)) a--; while (have.has(b + 1)) b++; return b - a + 1; };
  return years.filter(y => have.has(y) && runLen(y) <= 2).map(y => [y + 0.5, sum12(rows[years.indexOf(y)])]);
}
// Runs of missing years inside the covered period, e.g. [[1752, 1799], ...]
function gaps(years) {
  const out = [];
  for (let i = 1; i < years.length; i++) if (years[i] - years[i - 1] > 1) out.push([years[i - 1] + 1, years[i] - 1]);
  return out;
}
const decLabel = (x, res) => { const y = Math.floor(x); return res === "year" ? `${y}` : `${MONTHS[Math.min(11, Math.floor((x - y) * 12))]} ${y}`; };

// Theme-aware ECharts pieces
const tipStyle = () => ({ backgroundColor: css("--bg"), borderColor: css("--line"), textStyle: { color: css("--fg"), fontSize: 12 } });
const axisStyle = () => ({ axisLine: { lineStyle: { color: css("--line") } }, axisLabel: { color: css("--muted") },
                           splitLine: { lineStyle: { color: css("--grid") } } });
const attribution = () => ({ type: "text", right: 10, bottom: 2, silent: true,
  style: { text: ATTRIBUTION, fill: css("--muted"), font: "10px Lato, Arial, sans-serif" } });
const gapArea = gs => ({ silent: true, itemStyle: { color: css("--gap") },
  label: { show: true, position: "insideTop", color: css("--muted"), fontSize: 10, formatter: "no data" },
  data: gs.map(([a, b]) => [{ xAxis: a }, { xAxis: b + 1 }]) });
const toolbox = extra => ({ right: 8, top: 66, itemSize: 16, itemGap: 16,
  feature: Object.assign({ dataZoom: { title: { zoom: "Box zoom", back: "Undo zoom" } }, restore: { title: "Full view" } }, extra || {},
    { saveAsImage: { title: "Save PNG", backgroundColor: css("--bg"), pixelRatio: 2, excludeComponents: ["toolbox", "dataZoom"] } }),
  iconStyle: { borderColor: css("--muted") },
  emphasis: { iconStyle: { borderColor: css("--accent"), textFill: css("--fg"), textPosition: "bottom", textAlign: "right" } } });
const titleOpt = (text, sub) => ({ left: 0, top: 0, text, subtext: sub,
  textStyle: { color: css("--fg"), fontSize: 14, fontWeight: 600, fontFamily: "Lato, Arial, sans-serif" },
  subtextStyle: { color: css("--muted"), fontSize: 11 }, itemGap: 4 });
