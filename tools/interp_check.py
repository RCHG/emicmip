#!/usr/bin/env python3
# ╭────────────────────────────────────────────────────────────────────────────╮
# │ interp_check.py                                       (updated 2026-10)    │
# │                                                                            │
# │ Author:  Ramiro Checa-Garcia (KNMI)                                        │
# │ Purpose: Independent test of the interpolate_years method by using raw     │
# │          files that DO have every year.                                    │
# │          Idea: discard years inside a gap Y0->Y1, rebuild them by linear   │
# │          interpolation month by month (like cdo intyear) and compare them  │
# │          with the real ones. Two naive baselines are scored as well:       │
# │          "hold" (repeat Y0) and "nearest" (closest of Y0/Y1).              │
# │                                                                            │
# │ LLMs:    Created by LLMs under developer directives. Developers provided   │
# │          method, sources, testing ideas. LLMs did the low level coding     │
# │                                                                            │
# │ Usage:   python3 tools/interp_check.py etc/X.toml SPECIES [SPECIES ...]    │
# │              [--groups anthro aviation bburning] [--gaps 2015:2020 ...]    │
# │              [--sectors] [--cdo] [--rawpath DIR] [--out DIR] [--name NAME] │
# │   X.toml    a cmip_preemis config: raw files are found as cmip_preemis     │
# │             finds them (rawpath + group path + subset + version + period)  │
# │   SPECIES   as in the toml (SO2, NOx, BC, CO2, VOC01 ...), in every group  │
# │             and subset that lists it                                       │
# │   --gaps    Y0:Y1 windows; default: in the LAST period of each group,      │
# │             2022:2025 if present plus every 5-year window Y0:Y0+5          │
# │   --sectors also every sector: CSV, an annual + monthly line per sector    │
# │             on screen and a per-sector page in the PDF                     │
# │   --cdo     also check, once per file, that `cdo intyear` gives the same   │
# │             field as the formula used here                                 │
# │   --files   instead of toml + species: explicit raw file paths             │
# │                                                                            │
# │ Outputs: <out>/<name>/interp_check.csv and interp_check.pdf                │
# │          with a full summary shown as stdout                               │
# │ Read-only on the raw files.                                                │
# │ Requirements: python >= 3.11 (tomllib), numpy, xarray                      │
# │               (+cftime), matplotlib; cdo for --cdo option                  │
# ╰────────────────────────────────────────────────────────────────────────────╯

import os
import sys
import csv
import argparse
import tempfile
import subprocess
import numpy as np
import xarray as xr

sys.dont_write_bytecode = True

R_EARTH = 6.371e6                     # m
METHODS = ("linear", "hold", "nearest")
SHORT = {"linear": "lin", "hold": "hold", "nearest": "near"}
MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")


# ─── reading ──────────────────────────────────────────────────────────────────

def open_ds(path: str) -> xr.Dataset:
    """open_dataset with cftime dates (365_day calendars), old and new xarray."""
    try:
        return xr.open_dataset(path, decode_times=xr.coders.CFDatetimeCoder(use_cftime=True))
    except AttributeError:
        return xr.open_dataset(path, use_cftime=True)


def main_var(ds: xr.Dataset) -> str:
    """The data variable with the most dimensions (skips bounds)."""
    cands = [v for v in ds.data_vars if "bnds" not in v and "bounds" not in v]
    return max(cands, key=lambda v: ds[v].ndim)


def sector_names(ds: xr.Dataset, n: int) -> list[str]:
    """Sector labels from the `ids` attribute ("0: Agriculture; 1: Energy; ..."),
    else s0, s1, ..."""
    ids = ds["sector"].attrs.get("ids", "") if "sector" in ds else ""
    names = [p.split(":", 1)[1].strip() for p in ids.split(";") if ":" in p]
    return names if len(names) == n else [f"s{i}" for i in range(n)]


def cell_area(lat: np.ndarray, lon: np.ndarray) -> np.ndarray:
    """(nlat, nlon) cell area in m2 for a regular lat/lon grid."""
    dlat = np.deg2rad(abs(float(lat[1] - lat[0])))
    dlon = np.deg2rad(abs(float(lon[1] - lon[0])))
    phi = np.deg2rad(lat)
    band = R_EARTH ** 2 * dlon * (np.sin(np.minimum(phi + dlat / 2, np.pi / 2))
                                  - np.sin(np.maximum(phi - dlat / 2, -np.pi / 2)))
    return np.repeat(band[:, None], len(lon), axis=1)


def default_gaps(years: set[int]) -> list[tuple[int, int]]:
    gaps = []
    if all(y in years for y in range(2022, 2026)):
        gaps.append((2022, 2025))
    for y0 in sorted(years):
        if y0 % 5 == 0 and all(y in years for y in range(y0, y0 + 6)):
            gaps.append((y0, y0 + 5))
    return gaps


# ─── scoring ──────────────────────────────────────────────────────────────────

def estimates(f0: np.ndarray, f1: np.ndarray, w: float) -> dict[str, np.ndarray]:
    """The three reconstructions of a missing month, w = (Y-Y0)/(Y1-Y0)."""
    return {"linear":  (1.0 - w) * f0 + w * f1,
            "hold":    f0,
            "nearest": f0 if w <= 0.5 else f1}


def field_metrics(truth: np.ndarray, est: np.ndarray, area: np.ndarray) -> tuple[float, float]:
    """(pattern correlation, area-weighted RMSE / area-weighted mean |truth|).
    Fields are (..., lat, lon); extra leading dims (levels) are flattened.
    Correlation only over cells where either field is non-zero."""
    a = np.broadcast_to(area, truth.shape)
    nz = (truth != 0) | (est != 0)
    if not nz.any():
        return float("nan"), float("nan")
    t, e, w = truth[nz], est[nz], a[nz]
    corr = float(np.corrcoef(t, e)[0, 1]) if t.size > 2 and np.std(t) > 0 and np.std(e) > 0 else float("nan")
    mean_abs = np.sum(w * np.abs(t)) / np.sum(w)
    nrmse = float(np.sqrt(np.sum(w * (e - t) ** 2) / np.sum(w)) / mean_abs) if mean_abs > 0 else float("nan")
    return corr, nrmse


def total_tg(field: np.ndarray, area: np.ndarray, seconds: float) -> float:
    """Global total (Tg) of a flux field in kg m-2 s-1 over `seconds`; any
    leading dims (levels) are summed."""
    return float(np.sum(field * area) * seconds / 1e9)


def rel(est: float, truth: float) -> float:
    return (est - truth) / truth if truth != 0 else float("nan")


# ─── one file ─────────────────────────────────────────────────────────────────

def check_file(path: str, gaps: list[tuple[int, int]] | None, per_sector: bool,
               do_cdo: bool) -> tuple[list[dict], list[dict]]:
    """Returns (rows for the CSV, series for the plots)."""
    ds = open_ds(path)
    var = main_var(ds)
    da = ds[var]
    years_all = da["time"].dt.year.values
    months_all = da["time"].dt.month.values
    secs_all = da["time"].dt.days_in_month.values * 86400.0
    years = set(int(y) for y in years_all)
    area = cell_area(ds["lat"].values, ds["lon"].values)
    has_sector = "sector" in da.dims
    snames = sector_names(ds, da.sizes["sector"]) if has_sector else []
    label = os.path.basename(path)
    print(f"\n {label}\n   variable {var}, dims {da.dims}, years {min(years)}-{max(years)}")

    gaps = [g for g in (gaps or default_gaps(years))
            if all(y in years for y in range(g[0], g[1] + 1)) and g[1] - g[0] >= 2]
    if not gaps:
        print("   no usable gap (every year Y0..Y1 must be in the file, Y1-Y0 >= 2) -- skipped")
        return [], []

    def idx(y: int, m: int) -> int:
        return int(np.where((years_all == y) & (months_all == m))[0][0])

    def month_field(y: int, m: int) -> np.ndarray:
        """(sector, [level,] lat, lon) or ([level,] lat, lon), NaN -> 0."""
        f = da.isel(time=idx(y, m)).values.astype("float64")
        return np.nan_to_num(f)

    rows, series = [], []
    cdo_done = not do_cdo
    for y0, y1 in gaps:
        inner = list(range(y0 + 1, y1))
        print(f"   gap {y0} -> {y1}: rebuilding {', '.join(map(str, inner))}")
        # monthly totals of every year of the window, for the plots
        tot = {s: {y: [0.0] * 12 for y in range(y0, y1 + 1)} for s in ["TOTAL"]}
        est_tot = {m_: {y: [0.0] * 12 for y in inner} for m_ in METHODS}
        # accumulators for annual rows: key (sector, year)
        ann: dict[tuple[str, int], dict[str, float]] = {}
        mon_corr: dict[tuple[str, int, str], list[float]] = {}
        # monthly totals per sector (with --sectors): (sector, year) -> {"truth"|method: [12]}
        sec_mon: dict[tuple[str, int], dict[str, list[float]]] = {}

        for m in range(1, 13):
            f0, f1 = month_field(y0, m), month_field(y1, m)
            for y in range(y0, y1 + 1):
                secs = float(secs_all[idx(y, m)])
                fy = f0 if y == y0 else f1 if y == y1 else month_field(y, m)
                tot["TOTAL"][y][m - 1] = total_tg(fy, area, secs)
                if y in (y0, y1):
                    continue
                w = (y - y0) / (y1 - y0)
                ests = estimates(f0, f1, w)
                # which fields to score: the sum of sectors, and each sector
                parts = [("TOTAL", lambda f: f.sum(axis=0) if has_sector else f)]
                if per_sector and has_sector:
                    parts += [(snames[i], (lambda i: lambda f: f[i])(i)) for i in range(len(snames))]
                for sname, pick in parts:
                    t = pick(fy)
                    t_tot = total_tg(t, area, secs)
                    a = ann.setdefault((sname, y), {"truth": 0.0, **{k: 0.0 for k in METHODS}})
                    a["truth"] += t_tot
                    sm = sec_mon.setdefault((sname, y), {k: [0.0] * 12 for k in ("truth",) + METHODS})
                    sm["truth"][m - 1] = t_tot
                    for meth, e_full in ests.items():
                        e = pick(e_full)
                        e_tot = total_tg(e, area, secs)
                        a[meth] += e_tot
                        sm[meth][m - 1] = e_tot
                        corr, nrmse = field_metrics(t, e, area)
                        mon_corr.setdefault((sname, y, meth), []).append(corr)
                        if sname == "TOTAL":
                            est_tot[meth][y][m - 1] = e_tot
                        rows.append({"file": label, "variable": var, "gap": f"{y0}:{y1}", "year": y,
                                     "month": m, "sector": sname, "method": meth,
                                     "truth_Tg": f"{t_tot:.6g}", "estimate_Tg": f"{e_tot:.6g}",
                                     "rel_err": f"{rel(e_tot, t_tot):.4g}",
                                     "pattern_corr": f"{corr:.5f}", "nrmse": f"{nrmse:.4g}"})

                if not cdo_done:
                    cdo_done = True
                    cdo_check(path, y0, y1, y, m, ests["linear"])

        # annual rows + screen summary
        for (sname, y), a in sorted(ann.items(), key=lambda kv: (kv[0][1], kv[0][0] != "TOTAL", kv[0][0])):
            for meth in METHODS:
                cs = [c for c in mon_corr[(sname, y, meth)] if np.isfinite(c)]
                rows.append({"file": label, "variable": var, "gap": f"{y0}:{y1}", "year": y,
                             "month": "annual", "sector": sname, "method": meth,
                             "truth_Tg": f"{a['truth']:.6g}", "estimate_Tg": f"{a[meth]:.6g}",
                             "rel_err": f"{rel(a[meth], a['truth']):.4g}",
                             "pattern_corr": f"{np.mean(cs):.5f}" if cs else "nan", "nrmse": ""})
            if sname == "TOTAL":
                errs = "  ".join(f"{meth} {100 * rel(a[meth], a['truth']):+7.2f}%" for meth in METHODS)
                cl = [c for c in mon_corr[(sname, y, 'linear')] if np.isfinite(c)]
                print(f"     {y}  annual total {a['truth']:11.4g} Tg   {errs}"
                      f"   linear pattern corr {np.mean(cl) if cl else float('nan'):.4f}")
                # month by month: real vs linear total, error, pattern correlation
                print(f"           {'month':<8}" + "".join(f"{MONTHS[i]:>9}" for i in range(12)))
                print(f"           {'real Tg':<8}" + "".join(f"{v:9.3g}" for v in tot['TOTAL'][y]))
                print(f"           {'lin Tg':<8}" + "".join(f"{v:9.3g}" for v in est_tot['linear'][y]))
                for meth in METHODS:
                    print(f"           {SHORT[meth] + ' %':<8}" + "".join(
                        f"{100 * rel(e, t):+9.2f}" for e, t in zip(est_tot[meth][y], tot['TOTAL'][y])))
                print(f"           {'lin corr':<8}" + "".join(f"{c:9.4f}" for c in mon_corr[(sname, y, 'linear')]))
                if per_sector and has_sector:
                    print(f"           per sector: annual error (lin/hold/near) | linear error % per month")
            else:
                # --sectors: one annual line + the linear monthly errors of this sector
                sm = sec_mon[(sname, y)]
                if a["truth"] == 0 and all(a[meth] == 0 for meth in METHODS):
                    print(f"           {sname[:22]:<22}         0 Tg  (no emissions in this sector)")
                    continue
                errs = " ".join(f"{100 * rel(a[meth], a['truth']):+6.2f}" for meth in METHODS)
                cl = [c for c in mon_corr[(sname, y, 'linear')] if np.isfinite(c)]
                print(f"           {sname[:22]:<22} {a['truth']:9.3g} Tg  {errs} %"
                      f"  corr {np.mean(cl) if cl else float('nan'):.4f}")
                print(f"           {'lin %':<8}" + "".join(
                    f"{100 * rel(e, t):+9.2f}" for e, t in zip(sm['linear'], sm['truth'])))

        series.append({"file": label, "variable": var, "gap": (y0, y1),
                       "truth": tot["TOTAL"], "est": est_tot,
                       "corr": {y: mon_corr[("TOTAL", y, "linear")] for y in inner},
                       "sectors": {sn: {y: [100 * rel(e, t) for e, t in zip(v["linear"], v["truth"])]
                                        for (sn2, y), v in sec_mon.items() if sn2 == sn}
                                   for sn in dict.fromkeys(k[0] for k in sec_mon if k[0] != "TOTAL")}})
    ds.close()
    return rows, series


def cdo_check(path: str, y0: int, y1: int, y: int, m: int, linear: np.ndarray) -> None:
    """Compare month m of year y from `cdo intyear` with the formula above."""
    with tempfile.TemporaryDirectory() as tmp:
        a, b, base = (os.path.join(tmp, n) for n in ("y0.nc", "y1.nc", "int_"))
        try:
            for yy, out in ((y0, a), (y1, b)):
                subprocess.run(["cdo", "-s", "-O", f"selyear,{yy}", path, out], check=True)
            subprocess.run(["cdo", "-s", "-O", f"intyear,{y}", a, b, base], check=True)
        except (OSError, subprocess.CalledProcessError) as exc:
            print(f"     cdo check skipped: {exc}")
            return
        outs = [f for f in os.listdir(tmp) if f.startswith("int_")]
        if not outs:
            print("     cdo check: intyear wrote no file")
            return
        ds = open_ds(os.path.join(tmp, outs[0]))
        da = ds[main_var(ds)]
        sel = np.where(da["time"].dt.month.values == m)[0]
        f = np.nan_to_num(da.isel(time=int(sel[0])).values.astype("float64"))
        yrs = sorted(set(int(v) for v in da["time"].dt.year.values))
        ds.close()
        if f.shape != linear.shape:
            print(f"     cdo check: shape {f.shape} vs {linear.shape} -- NOT comparable")
            return
        scale = np.max(np.abs(linear)) or 1.0
        diff = np.max(np.abs(f - linear)) / scale
        print(f"     cdo intyear check ({y}-{m:02d}, time axis years {yrs}): "
              f"max |diff| / max |field| = {diff:.2e}  ({'same' if diff < 1e-6 else 'DIFFERENT'})")


# ─── output ───────────────────────────────────────────────────────────────────

def write_csv(rows: list[dict], path: str) -> None:
    with open(path, "w", newline="") as fh:
        wr = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        wr.writeheader()
        wr.writerows(rows)


def plot(series: list[dict], path: str) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.backends.backend_pdf import PdfPages

    style = {"linear": ("#2a78d6", "--", "o"), "hold": ("#eb6834", ":", "s"), "nearest": ("#1baf7a", ":", "^")}
    with PdfPages(path) as pdf:
        for s in series:
            y0, y1 = s["gap"]
            yrs = list(range(y0, y1 + 1))
            inner = yrs[1:-1]
            fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(11.7, 4.6), gridspec_kw={"width_ratios": [1, 2]})
            ax1.plot(yrs, [sum(s["truth"][y]) for y in yrs], color="black", lw=2, marker="o", label="real")
            for meth, (c, ls, mk) in style.items():
                ax1.plot([y0] + inner + [y1],
                         [sum(s["truth"][y0])] + [sum(s["est"][meth][y]) for y in inner] + [sum(s["truth"][y1])],
                         color=c, ls=ls, marker=mk, ms=4, lw=1.5, label=meth)
            ax1.set_title("annual total (Tg)", fontsize=9)
            ax1.set_xticks(yrs)
            ax1.legend(fontsize=7, frameon=False)
            # monthly: real for every year of the window, linear for the inner years
            x = [y + (m - 0.5) / 12 for y in yrs for m in range(1, 13)]
            ax2.plot(x, [v for y in yrs for v in s["truth"][y]], color="black", lw=1.6, label="real")
            xi = [y + (m - 0.5) / 12 for y in inner for m in range(1, 13)]
            ax2.plot(xi, [v for y in inner for v in s["est"]["linear"][y]], color=style["linear"][0],
                     ls="--", lw=1.5, label="linear (month by month)")
            ax2.set_title("monthly total (Tg)", fontsize=9)
            ax2.legend(fontsize=7, frameon=False)
            for ax in (ax1, ax2):
                ax.grid(alpha=0.3, lw=0.5)
                ax.tick_params(labelsize=7)
            fig.suptitle(f"{s['variable']}   gap {y0} -> {y1}   (sum of sectors)\n{s['file']}", fontsize=8)
            fig.tight_layout()
            pdf.savefig(fig)
            plt.close(fig)

            # second page: month by month, one row per rebuilt year
            mx = list(range(1, 13))
            fig, axes = plt.subplots(len(inner), 2, figsize=(11.7, 1.9 + 1.9 * len(inner)), squeeze=False)
            for row, y in enumerate(inner):
                ax_v, ax_e = axes[row]
                ax_v.plot(mx, s["truth"][y0], color="#999999", lw=1, label=f"real {y0}")
                ax_v.plot(mx, s["truth"][y1], color="#555555", lw=1, ls="-.", label=f"real {y1}")
                ax_v.plot(mx, s["truth"][y], color="black", lw=2, marker="o", ms=3, label=f"real {y}")
                ax_v.plot(mx, s["est"]["linear"][y], color=style["linear"][0], ls="--", marker="o", ms=3,
                          lw=1.5, label=f"linear {y}")
                ax_v.set_ylabel(f"{y}  (Tg/month)", fontsize=8)
                for meth, (c, ls, mk) in style.items():
                    ax_e.plot(mx, [100 * rel(e, t) for e, t in zip(s["est"][meth][y], s["truth"][y])],
                              color=c, ls=ls if meth != "linear" else "-", marker=mk, ms=3, lw=1.5, label=meth)
                ax_e.axhline(0, color="black", lw=0.6)
                ax_e.set_ylabel("error vs real (%)", fontsize=8)
                corr = [c for c in s["corr"][y] if np.isfinite(c)]
                ax_e.text(0.01, 0.04, f"linear pattern corr: min {min(corr):.4f}, mean {np.mean(corr):.4f}"
                          if corr else "", transform=ax_e.transAxes, fontsize=7, color="#444444")
                for ax in (ax_v, ax_e):
                    ax.set_xticks(mx, MONTHS)
                    ax.grid(alpha=0.3, lw=0.5)
                    ax.tick_params(labelsize=7)
                if row == 0:
                    ax_v.legend(fontsize=6.5, frameon=False, ncol=2)
                    ax_e.legend(fontsize=6.5, frameon=False, ncol=3)
            fig.suptitle(f"{s['variable']}   gap {y0} -> {y1}   month by month (sum of sectors)\n{s['file']}",
                         fontsize=8)
            fig.tight_layout()
            pdf.savefig(fig)
            plt.close(fig)

            # third page (--sectors): linear monthly error of each sector, one line per year
            secs = s.get("sectors") or {}
            if secs:
                ncol = 4
                nrow = -(-len(secs) // ncol)
                fig, axes = plt.subplots(nrow, ncol, figsize=(11.7, 1.2 + 2.3 * nrow), squeeze=False, sharex=True)
                ycols = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#8a5cd1"]
                for k, (sn, by_year) in enumerate(secs.items()):
                    ax = axes[k // ncol][k % ncol]
                    for j, y in enumerate(inner):
                        ax.plot(mx, by_year[y], color=ycols[j % len(ycols)], marker="o", ms=2.5, lw=1.2, label=str(y))
                    ax.axhline(0, color="black", lw=0.6)
                    ax.set_title(sn, fontsize=8)
                    ax.set_xticks(mx, [mo[0] for mo in MONTHS])
                    ax.grid(alpha=0.3, lw=0.5)
                    ax.tick_params(labelsize=7)
                    if k % ncol == 0:
                        ax.set_ylabel("linear error (%)", fontsize=7)
                for k in range(len(secs), nrow * ncol):
                    axes[k // ncol][k % ncol].axis("off")
                axes[0][0].legend(fontsize=6.5, frameon=False)
                fig.suptitle(f"{s['variable']}   gap {y0} -> {y1}   linear, month by month, per sector\n{s['file']}",
                             fontsize=8)
                fig.tight_layout()
                pdf.savefig(fig)
                plt.close(fig)


def summary(rows: list[dict]) -> None:
    """How often linear beats both baselines on annual totals."""
    ann = [r for r in rows if r["month"] == "annual"]
    keys = sorted({(r["file"], r["gap"], r["year"], r["sector"]) for r in ann})
    wins = n = 0
    for k in keys:
        e = {r["method"]: abs(float(r["rel_err"])) for r in ann
             if (r["file"], r["gap"], r["year"], r["sector"]) == k and r["rel_err"] != "nan"}
        if len(e) == 3:
            n += 1
            wins += e["linear"] <= min(e["hold"], e["nearest"])
    if n:
        print(f"\n linear is the best (or tied) of the three on {wins}/{n} annual totals "
              f"({100 * wins / n:.0f} %)")


# ─── finding the raw files from a toml ────────────────────────────────────────

def span_years(span: str) -> tuple[int, int]:
    """"200001-202312" -> (2000, 2023)."""
    a, b = span.split("-")
    return int(a[:4]), int(b[:4])


def files_from_toml(toml_path: str, species: list[str], groups: list[str],
                    gaps: list[tuple[int, int]] | None, rawpath: str | None) -> list[str]:
    """Raw files cmip_preemis would read for these species, named like
    lib/cmip_process.py::build_raw_path (keep in sync). Periods: those holding
    a requested gap, or the last period of the group when no --gaps."""
    import tomllib
    with open(toml_path, "rb") as fh:
        _, d = next(iter(tomllib.load(fh).items()))
    root = rawpath or d["rawpath"]
    prefix = "_".join([d["origin"], d["category"], d["target_mip"]])
    found, wanted = [], set(species)
    for group in groups:
        g = d.get(group)
        if not g:
            continue
        gdir = os.path.join(root, g["path"])
        versions = [f"{prefix}_{v}_gn" for v in g["version"]]
        if gaps:
            spans = [s for s in g["years"]
                     if any(span_years(s)[0] <= y0 and y1 <= span_years(s)[1] for y0, y1 in gaps)]
        else:
            spans = [max(g["years"], key=lambda s: span_years(s)[1])]
        for subset_key, sub in g.get("subsets", {}).items():
            for sp in sub["species"]:
                # "VOC01" also matches the raw name "VOC01-alcohols"
                if not any(sp == w or sp.startswith(w + "-") for w in species):
                    continue
                for span in spans:
                    for v in versions:
                        fname = (f"{sp}_{v}_{span}.nc" if subset_key in (None, "none")
                                 else f"{sp}-{subset_key}_{v}_{span}.nc")
                        path = os.path.join(gdir, fname)
                        if os.path.isfile(path):
                            found.append(path)
                            wanted.discard(next(w for w in species if sp == w or sp.startswith(w + "-")))
                            break
                    else:
                        print(f" not found: {group} {subset_key} {sp} {span} in {gdir}")
    for w in sorted(wanted):
        print(f" species {w}: no raw file found in groups {', '.join(groups)}")
    return found


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Leave-out test of month-by-month linear interpolation between years.",
        epilog="examples:\n"
               "  python3 tools/interp_check.py etc/scenariomip-m_cmip7.toml SO2 NOx BC CO --cdo\n"
               "  python3 tools/interp_check.py etc/historical_cmip7.toml SO2 BC --groups anthro \\\n"
               "      --gaps 2000:2005 2005:2010 2010:2015 2015:2020 2018:2023 --sectors",
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("toml", nargs="?", help="cmip_preemis config, e.g. etc/historical_cmip7.toml")
    ap.add_argument("species", nargs="*", help="species as in the toml (SO2 NOx BC CO2 VOC01 ...)")
    ap.add_argument("--groups", nargs="+", default=["anthro", "aviation", "bburning"],
                    choices=["anthro", "aviation", "bburning"], help="groups to look in (default: all three)")
    ap.add_argument("--files", nargs="+", default=None, metavar="RAW.nc",
                    help="explicit raw files instead of toml + species")
    ap.add_argument("--rawpath", default=None, help="override the toml's rawpath")
    ap.add_argument("--gaps", nargs="+", default=None, metavar="Y0:Y1",
                    help="windows to test (default: last period of each group; 2022:2025 if present "
                         "+ every 5-year window Y0:Y0+5, Y0 multiple of 5)")
    ap.add_argument("--sectors", action="store_true", help="also score every sector: CSV rows, one annual + one monthly line per sector on screen, a per-sector PDF page")
    ap.add_argument("--cdo", action="store_true", help="check `cdo intyear` against the formula once per file")
    ap.add_argument("--out", default="outs/validation", help="base output directory (default outs/validation)")
    ap.add_argument("--name", default=None,
                    help="subdirectory under --out (default interp_check_<toml name>_<species>)")
    args = ap.parse_args()
    # show progress line by line also when redirected (> log &), not in 8 KB blocks
    sys.stdout.reconfigure(line_buffering=True)

    gaps = None
    if args.gaps:
        try:
            gaps = [tuple(int(v) for v in g.split(":")) for g in args.gaps]
        except ValueError:
            sys.exit(f"--gaps must look like 2015:2020, got {args.gaps}")

    if args.files:
        files = args.files
        name = args.name or "interp_check"
    elif args.toml and args.species:
        files = files_from_toml(args.toml, args.species, args.groups, gaps, args.rawpath)
        tname = os.path.splitext(os.path.basename(args.toml))[0]
        name = args.name or f"interp_check_{tname}_{'-'.join(args.species)}"
    else:
        ap.error("give a toml and at least one species, or --files")
    if not files:
        sys.exit(" no raw file to check")

    all_rows, all_series = [], []
    skipped = []
    for f in files:
        try:
            rows, series = check_file(f, gaps, args.sectors, args.cdo)
        except OSError as exc:
            # e.g. a filesystem hiccup on /hpcperm (Errno 108): report, go on with the others
            print(f"\n {os.path.basename(f)}\n   could not be read ({exc.__class__.__name__}: {exc}) -- skipped")
            skipped.append(f)
            continue
        all_rows += rows
        all_series += series
    if not all_rows:
        sys.exit("\n nothing to score")

    outdir = os.path.join(args.out, name)
    os.makedirs(outdir, exist_ok=True)
    write_csv(all_rows, os.path.join(outdir, "interp_check.csv"))
    plot(all_series, os.path.join(outdir, "interp_check.pdf"))
    summary(all_rows)
    print(f" written: {outdir}/interp_check.csv, interp_check.pdf")
    if skipped:
        print(f" NOT checked (read error, run again for them with --files): {' '.join(skipped)}")


if __name__ == "__main__":
    main()
