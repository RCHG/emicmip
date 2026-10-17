#!/usr/bin/env python3
# ╭────────────────────────────────────────────────────────────────────────────╮
# │ emissions_stats.py                                    (updated 2025-08)    │
# │                                                                            │
# │ Author:  Ramiro Checa-Garcia (KNMI)                                        │
# │ Purpose: Monthly/annual emission totals (Tg) per species, written as CSV   │
# │                                                                            │
# │ LLMs: AI reimplemented a previous human draft. Corrections based on        │
# │       examples and description of developer.                               │
# ╰────────────────────────────────────────────────────────────────────────────╯

import os
import csv
import xarray as xr
import lib.aux as aux

MONTH_FIELDS = [f"month_{m:02d}" for m in range(1, 13)]
# "year" first, so files joined later (e.g. cat) still say which year a row is
CSV_FIELDS   = ["year", "species", "dataset", "sector"] + MONTH_FIELDS + ["total_Tg"]

STATS_SIG_FIGS = 6


def _stats_row(year: int | str, species: str, dataset: str, sector: str, 
               months_tg: dict[int, float]) -> dict:
    """Build one flat CSV-ready row dict from a sector's per-month Tg values.

    Args:
        year: year this row belongs to (first CSV column; also used to group
            rows by year in write_group_stats)
        species: on-disk species token (see get_species_filename)
        dataset: subset's filename suffix (e.g. "anthro-surf"), or "ALL"
        sector: sector/variable name, or "ALL" for the cross-sector total row
        months_tg: dict mapping calendar month (1-12) -> emission total (Tg);
            months absent from the source file are simply absent here

    Returns:
        Row dict with keys "year", "species", "dataset", "sector",
        "month_01".."month_12" (blank string for missing months, otherwise
        rounded to STATS_SIG_FIGS significant figures), "total_Tg" (sum of
        the rounded month values, itself rounded the same way).
    """
    row = {"year": year, "species": species, "dataset": dataset, "sector": sector}
    total = 0.0
    for m in range(1, 13):
        if m in months_tg:
            row[f"month_{m:02d}"] = aux.round_sig(months_tg[m], STATS_SIG_FIGS)
            total += row[f"month_{m:02d}"]
        else:
            row[f"month_{m:02d}"] = ""
    row["total_Tg"] = aux.round_sig(total, STATS_SIG_FIGS)
    return row


def compute_file_stats_rows(ncfile: str, sector_vars: list[str], species: str, 
                            dataset: str, year: int | str, tmp_dir: str, 
                            verbose: bool = False) -> list[dict]:
    """Per-sector monthly/annual emission totals (Tg) for one final file.

    These files hold already-monthly-mean flux data (kg m-2 s-1), one value per
    calendar month, so `cdo fldint` (field integral, derives cell area from the
    file's own grid) is enough to turn each variable into a kg/s time series
    (for 3D variables, e.g. aviation, the vertical levels are then summed);
    multiplying each month's rate by that month's length *in the file's own
    calendar* then gives that month's mass, and Tg = kg * 1e-9. For a
    `365_day` file (e.g. the IIASA ScenarioMIP data) February has 28 days in
    every year, so the totals match the dataset's own convention; for a
    standard calendar, leap years count 29 days.

    Reports exactly the sector variables actually present in the file, one
    row each -- no synthetic summary row is computed. Whatever sectors a
    given config produces (raw, aggregate targets, scaling targets, ...) are
    reported as-is; the variable's own name conveys its meaning.

    Args:
        ncfile: path to the final, fully processed NetCDF file (one species,
            one year, one subset)
        sector_vars: candidate sector/variable names to look for (raw
            sectors plus any aggregate/scaling target names that may apply
            to this species); names not present in the file are skipped
        species: on-disk species token, used only to tag the returned rows
        dataset: subset's filename suffix, used only to tag the returned rows
        year: year of this file, used only to tag the returned rows
        tmp_dir: directory for the temporary `cdo fldint` output (removed
            again before returning)
        verbose: print info steps

    Returns:
        Flat list of CSV-ready row dicts (see _stats_row): one per sector in
        `sector_vars` that is actually present in the file. Empty list if
        `cdo fldint` failed to produce output.
    """
    os.makedirs(tmp_dir, exist_ok=True)
    tmp_out = os.path.join(tmp_dir, f"fldint_{os.path.basename(ncfile)}")
    os.system(f"cdo -s -O fldint {ncfile} {tmp_out}")

    if not os.path.isfile(tmp_out):
        if verbose:
            print(aux.pwarn(f"      > [stats] fldint failed for {ncfile}"))
        return []

    # cftime dates, so days_in_month follows the file's calendar (365_day, ...)
    try:
        ds = xr.open_dataset(tmp_out, decode_times=xr.coders.CFDatetimeCoder(use_cftime=True))
    except AttributeError:                                    # older xarray
        ds = xr.open_dataset(tmp_out, use_cftime=True)
    years, months = ds["time"].dt.year.values, ds["time"].dt.month.values
    days = ds["time"].dt.days_in_month.values

    rows = []
    for sector in sector_vars:
        if sector not in ds:
            if verbose:
                print(aux.pwarn(f"      > [stats] sector {sector} not found in {ncfile}"))
            continue
        # After fldint every non-time dimension is either a size-1 horizontal
        # one or a vertical one (aviation files have ~25 altitude levels): sum
        # them all, so each time step gets the column total. (Flattening
        # instead -- the previous behaviour -- paired the first 12 *levels*
        # of January with the 12 months for 3D files.)
        arr = ds[sector]
        vals = arr.sum(dim=[d for d in arr.dims if d != "time"]).values
        months_tg = {}
        for kgs, yr, mo, nd in zip(vals, years, months, days):
            seconds = int(nd) * 86400
            tg = float(kgs) * seconds * 1e-9
            months_tg[int(mo)] = tg
        rows.append(_stats_row(year, species, dataset, sector, months_tg))

    ds.close()
    os.remove(tmp_out)
    return rows


def write_year_csv(rows: list[dict], csv_path: str) -> None:
    """Write one CSV: one row per (species, sector) reported, grouped/sorted
    by dataset+species then alphabetically by sector name.

    Args:
        rows: row dicts as produced by compute_file_stats_rows/_stats_row;
            a no-op if empty
        csv_path: destination file path (parent directory is created if
            needed); overwritten if it already exists
    """
    if not rows:
        return
    os.makedirs(os.path.dirname(csv_path), exist_ok=True)
    rows_sorted = sorted(rows, key=lambda r: (r["dataset"], r["species"], r["sector"]))
    with open(csv_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows_sorted)


def write_group_stats(datainfo: dict, group: str, outpath: str, stats_rows: list[dict], 
                      verbose: bool = False) -> None:
    """Write one CSV per year for a group's accumulated stats rows, to both:
      - <outpath>/emissions_stats/          (colocated with the final nc's)
      - outs/validation/<datasetname>/      (local copy, relative to CWD)
    `datasetname` is datainfo["outputname"], the common string shared by every
    final nc filename for this config.

    Args:
        datainfo: full config dict for this CMIP version; uses
            datainfo["outputname"]
        group: group name ("anthro", "bburning", "aviation"), used to build
            each CSV's filename
        outpath: path for final output files, where the primary
            emissions_stats/ copy is written
        stats_rows: rows accumulated across every subset/species processed
            for this group (see process_group); a no-op if empty
        verbose: print the path of each CSV written
    """
    if not stats_rows:
        return
    dname = datainfo["outputname"]
    by_year = {}
    for row in stats_rows:
        by_year.setdefault(row["year"], []).append(row)

    for year, rows in by_year.items():
        for base in (os.path.join(outpath, "emissions_stats"),
                     os.path.join("outs", "validation", dname)):
            csv_path = os.path.join(base, f"emissions_{group}_{year}.csv")
            write_year_csv(rows, csv_path)
            if verbose:
                print(aux.pshow(f"      > [stats] wrote {csv_path}"))
