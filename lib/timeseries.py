#!/usr/bin/env python3
# ╭────────────────────────────────────────────────────────────────────────────╮
# │ timeseries.py                                         (updated 2026-10)    │
# │                                                                            │
# │ Author:  Ramiro Checa-Garcia (KNMI)                                        │
# │ Purpose: Join per-year emissions_stats CSVs into multi-year time series    │
# │          (one CSV per group) and plot them (one PDF page per species)      │
# │                                                                            │
# │ LLMs: Legacy code provided by developer. LLMs changed significantly the    │
# │       previous code, in particular seasonal plots                          │
# ╰────────────────────────────────────────────────────────────────────────────╯

import os
import re
import csv
import glob
import math

import lib.aux as aux
from lib.emissions_stats import MONTH_FIELDS, CSV_FIELDS

# Per-year CSVs as written by write_group_stats()/build_stats_from_tar():
# emissions_<group>_<year>.csv
STATS_CSV_RE = re.compile(r"^emissions_(?P<group>.+)_(?P<year>\d{4})\.csv$")

TS_FIELDS = CSV_FIELDS            # "year" is already the first column

# Sectors that already are the cross-sector total of their file (aggregate
# targets in etc/*.toml). When one is present it IS the total -- summing it
# together with the sectors it was built from would double count.
TOTAL_SECTORS = ("ALL", "bbALL")

# Fixed sector -> colour, so a sector keeps its colour on every page (colour
# follows the entity, not its position). Sectors not listed here take the
# remaining slots in order. Slots: blue, orange, aqua, yellow, magenta, green,
# violet, red.
PALETTE = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100",
           "#e87ba4", "#008300", "#6250d6", "#e34948"]
SECTOR_COLORS = {
    "AGR": PALETTE[0], "ENE": PALETTE[1], "IND": PALETTE[2], "TRA": PALETTE[3],
    "RCO": PALETTE[4], "SLV": PALETTE[5], "WST": PALETTE[6], "SHP": PALETTE[7],
    "bbAGRW": PALETTE[0], "bbFORE": PALETTE[1], "bbGRSS": PALETTE[2], "bbPEAT": PALETTE[3],
}
TOTAL_COLOR = "#222222"


def _to_float(value: str) -> float:
    """CSV cell -> float, blank (month absent from the source file) -> NaN."""
    return float(value) if value not in ("", None) else math.nan


def read_stats_csvs(indir: str, verbose: bool = False) -> dict[str, list[dict]]:
    """Read every emissions_<group>_<year>.csv in indir.

    Args:
        indir: directory with the per-year CSVs (e.g. outs/validation/<name>/
            or <outpath>/emissions_stats/)
        verbose: print each file read

    Returns:
        Dict group -> list of row dicts (CSV_FIELDS plus "year"), sorted by
        year. Empty if no CSV matched.
    """
    rows_by_group: dict[str, list[dict]] = {}
    for path in sorted(glob.glob(os.path.join(indir, "emissions_*.csv"))):
        m = STATS_CSV_RE.match(os.path.basename(path))
        if m is None:
            continue
        group, year = m.group("group"), int(m.group("year"))
        with open(path, newline="") as f:
            for row in csv.DictReader(f):
                row["year"] = year      # from the filename (older CSVs have no year column)
                rows_by_group.setdefault(group, []).append(row)
        if verbose:
            print(aux.pinfo(f"  > [timeseries] read {path}"))
    for rows in rows_by_group.values():
        rows.sort(key=lambda r: (r["dataset"], r["species"], r["sector"], r["year"]))
    return rows_by_group


def write_timeseries_csv(rows: list[dict], csv_path: str) -> None:
    """Write one group's rows of all years as a single CSV: same columns as the
    per-year CSVs plus a leading "year" column, sorted by dataset, species,
    sector and year. No total row is added (see series_total for why the total
    is not always a plain sum of the rows).

    Args:
        rows: row dicts as returned by read_stats_csvs for one group
        csv_path: destination file (parent directory created if needed)
    """
    os.makedirs(os.path.dirname(csv_path) or ".", exist_ok=True)
    with open(csv_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=TS_FIELDS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def collect_series(rows: list[dict]) -> dict[tuple[str, str], dict[str, dict[int, list[float]]]]:
    """Reshape one group's rows into series per (dataset, species).

    Returns:
        {(dataset, species): {sector: {year: [12 monthly Tg values]}}}, with
        NaN for months absent from the source file.
    """
    series: dict[tuple[str, str], dict[str, dict[int, list[float]]]] = {}
    for row in rows:
        key = (row["dataset"], row["species"])
        months = [_to_float(row[mf]) for mf in MONTH_FIELDS]
        series.setdefault(key, {}).setdefault(row["sector"], {})[row["year"]] = months
    return series


def series_total(sectors: dict[str, dict[int, list[float]]]) -> tuple[str | None, dict[int, list[float]]]:
    """Total of one (dataset, species) across its sectors.

    The rows of a final file can mix raw sectors with aggregate/scaling
    targets (see etc/*.toml), so the total is chosen, not blindly summed:
      - an aggregate sector in TOTAL_SECTORS (ALL, bbALL) is the total as-is
        (e.g. CMIP7 historical anthro keeps ALL; bburning has bbALL, plus
        bbPEAT for CO2, which is scaled *from* bbALL);
      - a lone sector is the total (aviation AVI, CMIP6 biomass_burning);
      - otherwise the sectors are summed month by month (e.g. ScenarioMIP
        anthro, where ALL is removed after creation). A month missing in
        any sector makes that month's total NaN rather than an undercount.

    Returns:
        (sector_used, total): sector_used is the sector name taken as total,
        or None when it was summed; total maps year -> 12 monthly Tg values.
    """
    for name in TOTAL_SECTORS:
        if name in sectors:
            return name, sectors[name]
    if len(sectors) == 1:
        name = next(iter(sectors))
        return name, sectors[name]

    years = sorted({y for s in sectors.values() for y in s})
    total = {}
    for year in years:
        total[year] = [
            sum(s[year][i] for s in sectors.values()) if all(year in s for s in sectors.values()) else math.nan
            for i in range(12)
        ]
    return None, total


def _monthly_xy(by_year: dict[int, list[float]], years: list[int]) -> tuple[list[float], list[float]]:
    """Monthly series on a continuous time axis (year + fraction) over the
    full [min, max] range of `years`; years without data are NaN, so
    matplotlib breaks the line there instead of bridging the gap."""
    xs, ys = [], []
    for year in range(years[0], years[-1] + 1):
        vals = by_year.get(year, [math.nan] * 12)
        for i, v in enumerate(vals):
            xs.append(year + (i + 0.5) / 12)
            ys.append(v)
    return xs, ys


def _annual_xy(by_year: dict[int, list[float]], years: list[int]) -> tuple[list[int], list[float]]:
    """Annual totals (sum of the 12 months, NaN if any month is missing)."""
    xs = list(range(years[0], years[-1] + 1))
    ys = [sum(by_year[y]) if y in by_year else math.nan for y in xs]
    return xs, ys


def _sector_colors(sector_names: list[str]) -> dict[str, str]:
    """Fixed colour per known sector; unknown ones take free slots in order."""
    colors = {s: SECTOR_COLORS[s] for s in sector_names if s in SECTOR_COLORS}
    free = [c for c in PALETTE if c not in colors.values()] or PALETTE
    for i, s in enumerate(s for s in sector_names if s not in colors):
        colors[s] = free[i % len(free)]
    return colors


def plot_group(group: str, rows: list[dict], pdf_path: str, log: bool = False, verbose: bool = False) -> int:
    """One PDF for a group, one page per (dataset, species).

    Each page has two panels sharing the time axis: monthly Tg (top) and
    annual Tg (bottom). Every sector is drawn with alpha=0.5 and the total
    (see series_total) as a solid dark line on top.

    Args:
        group: group name, used in the page titles
        rows: row dicts as returned by read_stats_csvs for this group
        pdf_path: destination PDF (parent directory created if needed)
        log: logarithmic y axis (sectors can differ by orders of magnitude)
        verbose: print each page drawn

    Returns:
        Number of pages written.
    """
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.backends.backend_pdf import PdfPages

    os.makedirs(os.path.dirname(pdf_path) or ".", exist_ok=True)
    series = collect_series(rows)
    npages = 0

    with PdfPages(pdf_path) as pdf:
        for (dataset, species), sectors in sorted(series.items()):
            total_name, total = series_total(sectors)
            years = sorted({y for s in sectors.values() for y in s})
            others = sorted(s for s in sectors if s != total_name)
            colors = _sector_colors(others)

            fig, (ax_m, ax_y) = plt.subplots(2, 1, figsize=(11, 7.5), sharex=True,
                                             gridspec_kw={"height_ratios": [3, 2]})
            for sector in others:
                ax_m.plot(*_monthly_xy(sectors[sector], years), color=colors[sector], lw=1.2, alpha=0.5, label=sector)
                ax_y.plot(*_annual_xy(sectors[sector], years), color=colors[sector], lw=1.2, alpha=0.5,
                          marker="o", ms=3)
            total_label = f"Total ({total_name})" if total_name else "Total (sum of sectors)"
            ax_m.plot(*_monthly_xy(total, years), color=TOTAL_COLOR, lw=2, label=total_label)
            ax_y.plot(*_annual_xy(total, years), color=TOTAL_COLOR, lw=2, marker="o", ms=4)

            ax_m.set_ylabel("Monthly emission [Tg/month]")
            ax_y.set_ylabel("Annual emission [Tg/yr]")
            ax_y.set_xlabel("Year")
            for ax in (ax_m, ax_y):
                if log:
                    ax.set_yscale("log")
                ax.grid(True, color="#dddddd", lw=0.6)
                for side in ("top", "right"):
                    ax.spines[side].set_visible(False)
            ax_m.legend(loc="upper left", bbox_to_anchor=(1.01, 1.0), frameon=False, fontsize=9)
            fig.suptitle(f"{species}  --  {group} / {dataset}   ({years[0]}-{years[-1]})", fontsize=13)
            fig.tight_layout()
            pdf.savefig(fig)
            plt.close(fig)
            npages += 1
            if verbose:
                print(aux.pinfo(f"  > [timeseries] page {species} {dataset}: {len(others)} sectors + total"))
    return npages


def plot_seasonal(group: str, rows: list[dict], year: int, pdf_path: str,
                  log: bool = False, verbose: bool = False) -> int:
    """One PDF for a group and year, one page per (dataset, species), with
    the seasonal cycle of every sector.

    Each page is a grid with one row per sector -- the total first (see
    series_total; when it is a sector itself, e.g. ALL/bbALL, it is not
    repeated) -- and two columns: 12 monthly bars and a single annual-total
    bar, each with its own y axis (sharing it squashes the monthly bars,
    the annual total being ~12x any month). The y axes are per row, since
    sectors of one species can differ by orders of magnitude.

    Args:
        group: group name, used in the page titles
        rows: row dicts as returned by read_stats_csvs for this group
        year: year to plot; rows of other years are ignored
        pdf_path: destination PDF (parent directory created if needed)
        log: logarithmic y axis
        verbose: print each page drawn

    Returns:
        Number of pages written (0, and no file, if the year has no rows).
    """
    year_rows = [r for r in rows if r["year"] == year]
    if not year_rows:
        return 0

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.backends.backend_pdf import PdfPages

    os.makedirs(os.path.dirname(pdf_path) or ".", exist_ok=True)
    months = list(range(1, 13))
    npages = 0

    with PdfPages(pdf_path) as pdf:
        for (dataset, species), sectors in sorted(collect_series(year_rows).items()):
            total_name, total = series_total(sectors)
            others = sorted(s for s in sectors if s != total_name)
            colors = _sector_colors(others)
            total_label = f"Total ({total_name})" if total_name else "Total (sum)"
            panels = [(total_label, total[year], TOTAL_COLOR)]
            panels += [(s, sectors[s][year], colors[s]) for s in others]

            nrows = len(panels)
            fig = plt.figure(figsize=(11, 1.2 + 1.3 * nrows))
            gs = fig.add_gridspec(nrows, 2, width_ratios=[12, 1], wspace=0.08)
            for i, (label, vals, color) in enumerate(panels):
                ax_m = fig.add_subplot(gs[i, 0])
                ax_t = fig.add_subplot(gs[i, 1])
                ax_m.bar(months, vals, width=0.7, color=color)
                ax_t.bar([0], [sum(vals)], width=0.7, color=color)

                ax_m.set_ylabel(label, rotation=0, ha="right", va="center", fontsize=9)
                ax_m.set_xticks(months)
                ax_m.set_xticklabels([calendar_abbr(m) for m in months] if i == nrows - 1 else [])
                ax_t.set_xticks([0])
                ax_t.set_xticklabels(["Year"] if i == nrows - 1 else [])
                # The annual bar keeps its own y axis (ticks on the right): it is
                # ~12x any single month, so a shared axis flattens the seasonal
                # cycle into a strip at the bottom of the panel.
                ax_t.yaxis.tick_right()
                for ax in (ax_m, ax_t):
                    if log:
                        ax.set_yscale("log")
                    ax.grid(True, axis="y", color="#dddddd", lw=0.6)
                    ax.set_axisbelow(True)
                    ax.tick_params(labelsize=8)
                    ax.spines["top"].set_visible(False)
                ax_m.spines["right"].set_visible(False)
                ax_t.spines["left"].set_visible(False)

            fig.suptitle(f"{species}  --  {group} / {dataset}   {year}   [Tg/month | Tg/yr]", fontsize=13)
            fig.subplots_adjust(left=0.16, right=0.94, top=1 - 0.6 / fig.get_figheight(), bottom=0.5 / fig.get_figheight())
            pdf.savefig(fig)
            plt.close(fig)
            npages += 1
            if verbose:
                print(aux.pinfo(f"  > [seasonal] page {species} {dataset} {year}: {nrows} rows"))
    return npages


def plot_seasonal_v2(group: str, rows: list[dict], year: int, pdf_path: str,
                     log: bool = False, verbose: bool = False) -> int:
    """Compact version of plot_seasonal: two (dataset, species) side by side
    per page, month labels rotated, same panels (total first, then each
    sector; 12 monthly bars plus the annual bar on its own y axis).

    Returns:
        Number of pages written (0, and no file, if the year has no rows).
    """
    year_rows = [r for r in rows if r["year"] == year]
    if not year_rows:
        return 0

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.backends.backend_pdf import PdfPages

    os.makedirs(os.path.dirname(pdf_path) or ".", exist_ok=True)
    months = list(range(1, 13))

    # every (dataset, species) as a title and its list of panels
    items = []
    for (dataset, species), sectors in sorted(collect_series(year_rows).items()):
        total_name, total = series_total(sectors)
        others = sorted(s for s in sectors if s != total_name)
        colors = _sector_colors(others)
        total_label = f"Total ({total_name})" if total_name else "Total (sum)"
        panels = [(total_label, total[year], TOTAL_COLOR)]
        panels += [(s, sectors[s][year], colors[s]) for s in others]
        items.append((f"{species}  ({dataset})", panels))

    npages = 0
    with PdfPages(pdf_path) as pdf:
        for k in range(0, len(items), 2):
            pair = items[k:k + 2]
            nrows = max(len(p) for _, p in pair)
            fig = plt.figure(figsize=(11.7, 1.4 + 1.05 * nrows))
            outer = fig.add_gridspec(1, 2, wspace=0.42)
            for col, (title, panels) in enumerate(pair):
                inner = outer[0, col].subgridspec(nrows, 2, width_ratios=[12, 1.4],
                                                  wspace=0.10, hspace=0.35)
                for i, (label, vals, color) in enumerate(panels):
                    ax_m = fig.add_subplot(inner[i, 0])
                    ax_t = fig.add_subplot(inner[i, 1])
                    ax_m.bar(months, vals, width=0.7, color=color)
                    ax_t.bar([0], [sum(vals)], width=0.7, color=color)
                    ax_m.set_ylabel(label, rotation=0, ha="right", va="center", fontsize=8)
                    ax_m.set_xticks(months)
                    last = i == len(panels) - 1
                    ax_m.set_xticklabels([calendar_abbr(m) for m in months] if last else [],
                                         rotation=90)
                    ax_t.set_xticks([0])
                    ax_t.set_xticklabels(["Year"] if last else [], rotation=90)
                    ax_t.yaxis.tick_right()
                    for ax in (ax_m, ax_t):
                        if log:
                            ax.set_yscale("log")
                        ax.grid(True, axis="y", color="#dddddd", lw=0.6)
                        ax.set_axisbelow(True)
                        ax.tick_params(labelsize=7)
                        ax.spines["top"].set_visible(False)
                    ax_m.spines["right"].set_visible(False)
                    ax_t.spines["left"].set_visible(False)
                    if i == 0:
                        ax_m.set_title(title, fontsize=11, loc="left")
            fig.suptitle(f"{group}   {year}   [Tg/month | Tg/yr]", fontsize=12)
            fig.subplots_adjust(left=0.11, right=0.96, top=1 - 0.7 / fig.get_figheight(),
                                bottom=0.75 / fig.get_figheight())
            pdf.savefig(fig)
            plt.close(fig)
            npages += 1
            if verbose:
                print(aux.pinfo(f"  > [seasonal v2] page {' + '.join(t for t, _ in pair)} {year}"))
    return npages


def calendar_abbr(month: int) -> str:
    """Month number -> English 3-letter abbreviation (locale independent)."""
    return ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
            "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"][month - 1]


def build_timeseries(indir: str, outdir: str = "outs/validation", name: str | None = None,
                     log: bool = False, seasonal: list[int] | None = None,
                     verbose: bool = False) -> None:
    """Join the per-year emissions_stats CSVs of indir into one time-series
    CSV per group and plot it, writing to <outdir>/<name>/:
      timeseries_<group>.csv         all years of the group, one row per
                                     species/dataset/sector/year
      timeseries_<group>.pdf         one page per (dataset, species)
      seasonal_<group>_<year>.pdf    only with `seasonal`: two (dataset,
                                     species) per page, see plot_seasonal_v2

    Args:
        indir: directory with emissions_<group>_<year>.csv files
        outdir: base output directory
        name: output subdirectory; defaults to indir's own basename, so
            `--timeseries outs/validation/X` writes next to its inputs
        log: logarithmic y axis in the plots
        seasonal: years to draw seasonal-cycle pages for; an empty list means
            every year found, None means no seasonal pages
        verbose: print info steps
    """
    if not os.path.isdir(indir):
        print(aux.perror(f"\n{indir} is not a directory."))
        return
    rows_by_group = read_stats_csvs(indir, verbose=verbose)
    if not rows_by_group:
        print(aux.pwarn(f"No emissions_<group>_<year>.csv files found in {indir}"))
        return

    dname = name if name is not None else os.path.basename(os.path.normpath(indir))
    dest_root = os.path.join(outdir, dname)
    for group, rows in sorted(rows_by_group.items()):
        nyears = len({r["year"] for r in rows})
        csv_path = os.path.join(dest_root, f"timeseries_{group}.csv")
        write_timeseries_csv(rows, csv_path)
        print(aux.pshow(f"  > [timeseries] wrote {csv_path} ({nyears} years)"))
        pdf_path = os.path.join(dest_root, f"timeseries_{group}.pdf")
        npages = plot_group(group, rows, pdf_path, log=log, verbose=verbose)
        print(aux.pshow(f"  > [timeseries] wrote {pdf_path} ({npages} pages)"))

        if seasonal is None:
            continue
        available = sorted({r["year"] for r in rows})
        for year in (seasonal or available):
            if year not in available:
                print(aux.pwarn(f"  > [seasonal] {group}: no CSV for year {year}, skipped"))
                continue
            # two species per page (plot_seasonal_v2); plot_seasonal, one species
            # per page, is kept for a larger view
            pdf_path = os.path.join(dest_root, f"seasonal_{group}_{year}.pdf")
            npages = plot_seasonal_v2(group, rows, year, pdf_path, log=log, verbose=verbose)
            print(aux.pshow(f"  > [seasonal] wrote {pdf_path} ({npages} pages, two species per page)"))
