#!/usr/bin/env python3
# ╭────────────────────────────────────────────────────────────────────────────╮
# │ plotcompare.py                                        (updated 2026-10)    │
# │                                                                            │
# │ Author:  Ramiro Checa-Garcia (KNMI)                                        │
# │ Purpose: Plot and summarise the diff_stats CSVs of one or more             │
# │          `cmip_validate --compare` runs (same archive A, one reference B   │
# │          per run): annual Tg of A and of every B per sector over the       │
# │          years, and the relative difference of each B to A.                │
# │                                                                            │
# │ LLMs: the implementation was supported by LLMs. The developer provided     │
# │       examples, description, and legacy code to improve                    │
# ╰────────────────────────────────────────────────────────────────────────────╯

import os
import re
import csv
import glob
import math

import lib.aux as aux
from lib.timeseries import TOTAL_COLOR, _sector_colors

# diff_stats_<group>_<year>.csv, as written by compare_tars (_write_grouped_csv)
DIFF_RE = re.compile(r"^diff_stats_(?P<group>.+)_(?P<year>\d{4})\.csv$")

# |relative difference| (in %) below which two totals count as "close". The
# stats are rounded to 6 significant figures, so identical inputs give exactly
# 0 and rounding noise stays far below this.
CLOSE_PCT = 0.01

REF_STYLES = ["--", ":", "-.", (0, (5, 1, 1, 1))]


def _num(value: str) -> float | None:
    return float(value) if value not in ("", None) else None


def read_compare_dir(cdir: str) -> tuple[str, str, dict]:
    """Read every diff_stats CSV of one --compare output folder.

    Returns:
        (tag_a, tag_b, data) with data[(group, dataset, species, sector)][year] =
        {"A": total Tg or None, "B": total Tg or None, "status": ...}. The tags
        come from the folder name `<tagA>_vs_<tagB>` (folder name if not).
    """
    base = os.path.basename(os.path.normpath(cdir))
    tag_a, _, tag_b = base.partition("_vs_")
    if not tag_b:
        tag_a, tag_b = "A", base
    data: dict = {}
    for path in sorted(glob.glob(os.path.join(cdir, "diff_stats_*.csv"))):
        m = DIFF_RE.match(os.path.basename(path))
        if not m:
            continue
        group, year = m.group("group"), int(m.group("year"))
        with open(path, newline="") as f:
            for row in csv.DictReader(f):
                key = (group, row["dataset"], row["species"], row["sector"])
                data.setdefault(key, {})[year] = {"A": _num(row["total_Tg_A"]), "B": _num(row["total_Tg_B"]),
                                                  "status": row["status"]}
    return tag_a, tag_b, data


def summarise(data: dict) -> dict:
    """Per key: verdict over all years (equal / close / different / only_in_A / only_in_B)."""
    out = {}
    for key, by_year in data.items():
        statuses = {v["status"] for v in by_year.values()}
        rels = []
        for year, v in by_year.items():
            if v["A"] is not None and v["B"] is not None:
                rel = 0.0 if v["B"] == v["A"] else ((v["B"] - v["A"]) / v["A"] * 100 if v["A"] else math.inf)
                rels.append((abs(rel), rel, year))
        if not rels:
            verdict = "only_in_A" if statuses == {"only_in_A"} else "only_in_B" if statuses == {"only_in_B"} else "no data"
            out[key] = {"verdict": verdict, "max_rel_pct": "", "year_of_max": "", "n_years": 0,
                        "years": sorted(by_year)}
            continue
        worst = max(rels)
        verdict = "equal" if worst[0] == 0 else ("close" if worst[0] < CLOSE_PCT else "different")
        out[key] = {"verdict": verdict, "max_rel_pct": round(worst[1], 6), "year_of_max": worst[2],
                    "n_years": len(rels), "years": sorted(by_year)}
    return out


def _gapped(years: list[int], values: list[float | None]) -> tuple[list[float], list[float]]:
    """x/y with NaN between non-consecutive years, so lines do not bridge gaps."""
    xs, ys, prev = [], [], None
    for y, v in zip(years, values):
        if prev is not None and y != prev + 1:
            xs.append(math.nan)
            ys.append(math.nan)
        xs.append(y)
        ys.append(math.nan if v is None else v)
        prev = y
    return xs, ys


def plot_compare(compare_dirs: list[str], outdir: str = "outs/validation", name: str | None = None,
                 log: bool = False, verbose: bool = False) -> None:
    """Plot and summarise one or more --compare outputs sharing the same A.

    Writes to <outdir>/<name>/:
      plotcompare_<group>.pdf    first page: what is not equal; then one page per
                                 (dataset, species): annual Tg per sector (A solid,
                                 each reference with its own dash style) and the
                                 relative difference (B - A) / A in %.
      plotcompare_summary.csv    one row per reference, group, dataset, species,
                                 sector: verdict, max relative difference, year.
    """
    refs = []
    for d in compare_dirs:
        if not os.path.isdir(d):
            print(aux.perror(f"\n{d} is not a directory."))
            return
        tag_a, tag_b, data = read_compare_dir(d)
        if not data:
            print(aux.pwarn(f"No diff_stats_<group>_<year>.csv in {d}, skipped"))
            continue
        refs.append({"dir": d, "tag_a": tag_a, "tag_b": tag_b, "data": data, "summary": summarise(data)})
    if not refs:
        return
    tags_a = {r["tag_a"] for r in refs}
    if len(tags_a) > 1:
        print(aux.pwarn(f"  > [plotcompare] the folders do not share the same A: {sorted(tags_a)}"))
    tag_a = refs[0]["tag_a"]
    dname = name or f"{tag_a}_plotcompare"
    dest = os.path.join(outdir, dname)
    os.makedirs(dest, exist_ok=True)

    # ---- summary CSV + screen
    summary_path = os.path.join(dest, "plotcompare_summary.csv")
    fields = ["reference", "group", "dataset", "species", "sector", "verdict", "max_rel_pct", "year_of_max",
              "n_years", "years"]
    with open(summary_path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for r in refs:
            for (group, dataset, species, sector), s in sorted(r["summary"].items()):
                w.writerow({"reference": r["tag_b"], "group": group, "dataset": dataset, "species": species,
                            "sector": sector, "verdict": s["verdict"], "max_rel_pct": s["max_rel_pct"],
                            "year_of_max": s["year_of_max"], "n_years": s["n_years"],
                            "years": " ".join(str(y) for y in s["years"])})
    print(aux.pshow(f"\n ====== {tag_a} against {len(refs)} reference(s) ======"))
    for r in refs:
        counts: dict[str, int] = {}
        for s in r["summary"].values():
            counts[s["verdict"]] = counts.get(s["verdict"], 0) + 1
        years = sorted({y for v in r["data"].values() for y in v})
        print(aux.pinfo(f"\n {r['tag_b']}  ({len(years)} years: {years[0]}..{years[-1]})"))
        print("   " + ", ".join(f"{k}: {counts[k]}" for k in
                                ("equal", "close", "different", "only_in_A", "only_in_B", "no data") if k in counts))
        for (group, dataset, species, sector), s in sorted(r["summary"].items()):
            if s["verdict"] == "different":
                print(aux.pwarn(f"   DIFFERENT {group}/{dataset} {species} {sector}: "
                                f"max {s['max_rel_pct']:+.4g} % ({s['year_of_max']})"))
    print(aux.pshow(f"\n  > [plotcompare] wrote {summary_path}"))

    # ---- plots, one PDF per group
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D
    from matplotlib.backends.backend_pdf import PdfPages

    groups = sorted({k[0] for r in refs for k in r["data"]})
    for group in groups:
        pages = sorted({(k[1], k[2]) for r in refs for k in r["data"] if k[0] == group})
        pdf_path = os.path.join(dest, f"plotcompare_{group}.pdf")
        with PdfPages(pdf_path) as pdf:
            # first page: everything that is not equal
            lines = []
            for r in refs:
                for (g, dataset, species, sector), s in sorted(r["summary"].items()):
                    if g == group and s["verdict"] != "equal":
                        extra = f"max {s['max_rel_pct']:+.4g} % ({s['year_of_max']})" if s["max_rel_pct"] != "" else ""
                        lines.append(f"{r['tag_b']:<30} {dataset:<20} {species:<14} {sector:<10} {s['verdict']:<10} {extra}")
            fig = plt.figure(figsize=(11, 8.5))
            fig.text(0.04, 0.95, f"{group}: {tag_a} (A) vs reference(s), not equal", fontsize=13, weight="bold")
            body = "\n".join(lines[:55]) if lines else "Everything equal."
            if len(lines) > 55:
                body += f"\n... {len(lines) - 55} more, see plotcompare_summary.csv"
            fig.text(0.04, 0.90, body, fontsize=7.5, family="monospace", va="top")
            pdf.savefig(fig)
            plt.close(fig)

            for dataset, species in pages:
                sectors = sorted({k[3] for r in refs for k in r["data"] if k[:3] == (group, dataset, species)})
                colors = _sector_colors(sectors)
                fig, (ax_t, ax_r) = plt.subplots(2, 1, figsize=(11, 7.5), sharex=True,
                                                 gridspec_kw={"height_ratios": [3, 2]})
                only_notes = []
                for sector in sectors:
                    color = TOTAL_COLOR if sector in ("ALL", "bbALL") else colors[sector]
                    a_drawn = False
                    for i, r in enumerate(refs):
                        by_year = r["data"].get((group, dataset, species, sector), {})
                        if not by_year:
                            continue
                        years = sorted(by_year)
                        if not a_drawn and any(by_year[y]["A"] is not None for y in years):
                            ax_t.plot(*_gapped(years, [by_year[y]["A"] for y in years]), color=color, lw=1.8,
                                      marker="o", ms=3, label=sector)
                            a_drawn = True
                        if any(by_year[y]["B"] is not None for y in years):
                            ax_t.plot(*_gapped(years, [by_year[y]["B"] for y in years]), color=color, lw=1.4,
                                      ls=REF_STYLES[i % len(REF_STYLES)], marker="x", ms=4)
                        rel = [((by_year[y]["B"] - by_year[y]["A"]) / by_year[y]["A"] * 100)
                               if by_year[y]["A"] and by_year[y]["B"] is not None else None for y in years]
                        if any(v is not None for v in rel):
                            ax_r.plot(*_gapped(years, rel), color=color, lw=1.4,
                                      ls=REF_STYLES[i % len(REF_STYLES)], marker="x", ms=4)
                        verdict = r["summary"][(group, dataset, species, sector)]["verdict"]
                        if verdict.startswith("only_in"):
                            side = tag_a if verdict == "only_in_A" else r["tag_b"]
                            only_notes.append(f"{sector}: only in {side}")
                if log:
                    ax_t.set_yscale("log")
                ax_t.set_ylabel("Annual emission [Tg/yr]")
                ax_r.set_ylabel("(ref - A) / A  [%]")
                ax_r.set_xlabel("Year")
                ax_r.axhline(0, color="#999999", lw=0.8)
                for ax in (ax_t, ax_r):
                    ax.grid(True, color="#dddddd", lw=0.6)
                    for side in ("top", "right"):
                        ax.spines[side].set_visible(False)
                sector_legend = ax_t.legend(loc="upper left", bbox_to_anchor=(1.01, 1.0), frameon=False,
                                            fontsize=8, title="sector")
                ax_t.add_artist(sector_legend)
                style_handles = [Line2D([], [], color="#444444", lw=1.8, marker="o", ms=3, label=f"{tag_a} (A)")]
                style_handles += [Line2D([], [], color="#444444", lw=1.4, ls=REF_STYLES[i % len(REF_STYLES)],
                                         marker="x", ms=4, label=r["tag_b"]) for i, r in enumerate(refs)]
                ax_t.legend(handles=style_handles, loc="lower left", bbox_to_anchor=(1.01, 0.0), frameon=False,
                            fontsize=8, title="archive")
                fig.suptitle(f"{species}  --  {group} / {dataset}", fontsize=13)
                if only_notes:
                    fig.text(0.01, 0.01, "; ".join(sorted(set(only_notes))), fontsize=8, color="#aa5500")
                fig.tight_layout(rect=(0, 0.03, 1, 1))
                pdf.savefig(fig)
                plt.close(fig)
                if verbose:
                    print(aux.pinfo(f"  > [plotcompare] page {group} {dataset} {species}"))
        print(aux.pshow(f"  > [plotcompare] wrote {pdf_path} ({len(pages) + 1} pages)"))
