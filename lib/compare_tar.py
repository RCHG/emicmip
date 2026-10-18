#!/usr/bin/env python3
# ╭────────────────────────────────────────────────────────────────────────────╮
# │ compare_tar.py                                        (updated 2026-08)    │
# │                                                                            │
# │ Author:  Ramiro Checa-Garcia (KNMI)                                        │
# │ Purpose: Diff of two archived tar/tgz of already-processed NetCDF files    │
# │          against each other. Goals: an old tool version vs a new one, or   │
# │          two datasets that both cover the same year (historical vs         │
# │          scenariomip)                                                      │
# │                                                                            │
# │ LLMs: This was programmed with assistance of LLMs as described in other    │
# │       cmip-validate related modules. AI made errors, fixed by human. The   │
# │       exhaustive comments/info were requested by developer to AI during    │
# │       review.                                                              │
# ╰────────────────────────────────────────────────────────────────────────────╯

import os
import csv
import math
import shutil
import hashlib
import tarfile
import tempfile
from collections import defaultdict
import xarray as xr
import numpy as np

import lib.aux as aux
import lib.emissions_stats as emissions_stats
from lib.validate_tar import list_nc_members, extract_member, parse_nc_files, list_sector_variables, group_for_suffix

STATS_FIELDS = (
    ["species", "dataset", "sector", "status"]
    + [f"month_{m:02d}_A" for m in range(1, 13)] + ["total_Tg_A"]
    + [f"month_{m:02d}_B" for m in range(1, 13)] + ["total_Tg_B"]
    + ["diff_total_Tg", "reldiff_total_Tg_pct"]
)

RAW_FIELDS = ["species", "dataset", "sector", "status", "file_md5_identical",
              "identical", "consistent", "tier", "mean_abs_diff", "rel_mean_abs_diff",
              "max_abs_diff", "rel_max_abs_diff"]

# Only used by _raw_row_historicalref -- comparing two genuinely different
# raw datasets (CEDS historical vs IIASA-IAMC scenariomip), where exact
# per-cell agreement was never expected. mean_abs_diff, normalized by a
# stable reference derived from the total annual mass (see
# _raw_row_historicalref -- NOT the per-cell mean magnitude, which turned
# out to be badly distorted by how spatially sparse a given species'
# emissions are), judges whether the field agrees *overall*; below this
# relative threshold a "both, not identical" row is reported as "consistent"
# instead of counted alongside genuine differences.
# _raw_row_strict (legacyref/legacyboth/plain --compare, same raw dataset on
# both sides) doesn't use this at all -- there, "consistent" means
# bit-identical, full stop, since any divergence is a real regression signal.
#
# Calibrated against a real production --historicalref run (anthro-surf,
# CMIP7hist vs ScenarioMIP m 2022), after fixing the two rel_mean_abs_diff
# scale bugs (missing /n_cells, then /12-too-strict -- see
# _raw_row_historicalref): sectors that visually look like noise (Tg totals
# matching to 5-6 sig figs, e.g. AGR/IND/RCO/SLV/WST/TRA) landed at
# rel_mean_abs_diff ~2e-6 to ~1e-4; sectors with a real difference (e.g.
# ENE/SHP, ~0.1-0.6% off in their Tg totals) landed at ~1.6e-3 to ~1.1e-2 --
# a clean ~16x-800x gap between the two groups. 2e-4 sits above the noisiest
# noise case with margin, and ~8x below the smallest real difference seen.
RAW_CONSISTENT_RELTOL = 2e-4

# Only used by _raw_row_historicalref, to tell apart two different reasons a
# sector can fail RAW_CONSISTENT_RELTOL: a real spatial/temporal pattern
# difference with a similar overall total (e.g. VOC species with CEDS vs
# IIASA-IAMC placing broadly similar emissions somewhat differently in
# space/time -- arguably not a meaningful difference given the underlying
# uncertainty on those species to begin with) vs. the totals themselves
# genuinely disagreeing (a difference no amount of "it's just placement"
# reasoning explains away). A sector's annual Tg totals within this percent
# of each other (see _stats_row's reldiff_total_Tg_pct) are "close" for this
# purpose; not independently calibrated the way RAW_CONSISTENT_RELTOL was --
# a starting point, adjust if it doesn't hold up against more real data.
TOTAL_TG_CONSISTENT_PCT = 5.0

# Average seconds/year (leap-year-inclusive), used only to turn a total
# annual Tg mass into an equivalent average kg/s for the rel_mean_abs_diff
# reference in _raw_row_historicalref. A coarse, ~0.3%-off-in-a-leap-year
# approximation is fine here -- this feeds a consistency *threshold*
# (RAW_CONSISTENT_RELTOL, order-of-magnitude sensitivity), not a mass
# accounting, so there's no need to thread the exact per-month day counts
# emissions_stats.py uses for the Tg totals themselves.
SECONDS_PER_YEAR = 365.25 * 86400

# Sig figs for max_abs_diff/mean_abs_diff/rel_max_abs_diff in print/CSV
# output, in _raw_row_historicalref only -- these are diagnostic magnitudes
# (is it real, is it noise), not a quantity anyone reads to more precision
# than "which order of magnitude". _raw_row_strict keeps full precision.
RAW_DIAG_SIG_FIGS = 4

# Sector names used by legacy archives, mapped to the name the current tool
# uses for the same computed quantity. Applied only to B (legacyref means
# "B is legacy, A is current") in _pair_sectors' plain name-based matching
# below -- e.g. legacy's anthro-biof "biofuel" sector (see
# check/lib/cmip_yaml.py's aggregate_sectors("biofuel", ..., remove_individual_
# sectors=False) call, ecearth3-only) is the same sum-of-sectors computation
# as the current tool's "ALL" aggregate target (etc/historical_cmip7.toml's
# [CMIP7.anthro].aggregate), just named differently. NOT applied under
# legacyboth: there, A is legacy too and would already say "biofuel" itself,
# so aliasing only B would break an otherwise-fine same-name match.
LEGACY_SECTOR_ALIASES = {
    "biofuel": "ALL",
}

# (species, subset_suffix) pairs expected to exist on only one side when
# comparing a scenariomip archive (A, the test side) against its historical
# predecessor (B, the reference side -- --historicalref, like --legacyref,
# is directional: B is always historical, never the other way round) --
# confirmed as known, accepted differences between the underlying datasets
# rather than config/tool bugs (see etc/historical_cmip7.toml vs
# etc/scenariomip-m_cmip7.toml). Both archives use current-tool naming
# throughout -- unlike --legacyref/--legacyboth this has nothing to do with
# old vs new tool versions, so it's independent of those flags:
#   - anthro-biof (all its species): CEDS-only SOLID-BIOFUEL sector, has no
#     scenariomip equivalent (only_in_B, dropped for the future period).
#   - anthro-surf-ecearth (same species): derived from anthro-biof by -e, so
#     only in historical -ec3 tars (only_in_B).
#   - bburning NOxasNO2 (only_in_B): historical (BB4CMIP7) only.
#   - Only against historical tars older than d (c and earlier), which lack
#     them: N2O (anthro-surf, anthro-air, bburning), HCN and NMVOCbulk
#     (bburning), CH4 (anthro-air) -- only_in_A. From d on historical has them
#     too, so these entries simply never match.
#   - CO2 (bburning, only_in_B): deliberately not provided by ScenarioMIP's
#     openburning source (etc/scenariomip-m_cmip7.toml's
#     [CMIP7.bburning.subsets.em-openburning] has CO2 excluded), to avoid
#     double-counting -- fire/openburning CO2 is a return of previously-
#     sequestered carbon, not a net emission (same CMIP6 practice); ESMs get
#     agricultural/above-ground-woody-biomass CO2 from the land-use product
#     instead. Not a raw-data gap.
# Only used when a (species, suffix, year) key is present in one archive and
# missing entirely in the other -- never suppresses a real value mismatch on
# a key present in both.
KNOWN_HISTORICAL_SCENARIO_DIFFS = {
    ("N2O", "anthro-surf"),
    ("N2O", "anthro-air"),
    ("N2O", "bburning"),
    ("CH4", "anthro-air"),
    *{(sp, sfx) for sp in ("BC", "CH4", "CO", "CO2", "N2O", "NH3",
                           "NMVOC", "NOx", "OC", "SO2")
               for sfx in ("anthro-biof", "anthro-surf-ecearth")},
    ("NOxasNO2", "bburning"),
    ("HCN", "bburning"),
    ("NMVOCbulk", "bburning"),
    ("CO2", "bburning"),
}

# bburning sector names with no historical equivalent, for --historicalref.
# Scenariomip's bburning subset computes 4 raw sectors (bbAGRW/bbFORE/
# bbGRSS/bbPEAT) plus their "bbALL" aggregate, for every species (see
# etc/scenariomip-m_cmip7.toml's [CMIP7.bburning].sectors/aggregate).
# Historical's bburning subset only ever has a single raw sector, "bbALL"
# (etc/historical_cmip7.toml's [CMIP7.bburning].sectors = ["bbALL"]), plus a
# scaled "bbPEAT" derived *only* for CO2 (see its [[CMIP7.bburning.scaling]],
# species=["CO2"]). So under --historicalref: for CO2, "bbPEAT" is expected
# to match on both sides as normal (not listed as a species exception
# below); for every other species, "bbPEAT" is scenariomip-only same as
# "bbAGRW"/"bbFORE"/"bbGRSS" always are.
HISTORICAL_MISSING_BBURNING_SECTORS = {"bbAGRW", "bbFORE", "bbGRSS", "bbPEAT"}
HISTORICAL_MISSING_BBURNING_SECTORS_EXCEPT_SPECIES = {"bbPEAT": {"CO2"}}


def _regrid_to_match(file_ref: str, file_target: str, tmp_dir: str, verbose: bool = False) -> str:
    """Conservatively regrid `file_target` onto `file_ref`'s grid via cdo.

    Only needed when two matched (species, suffix, year) files turn out to
    be on different native grids -- e.g. historical's bburning at 0.25 deg
    vs scenariomip's bburning at 0.5 deg (etc/historical_cmip7.toml vs
    etc/scenariomip-m_cmip7.toml's [CMIP7.bburning].resol). Conservative
    (area-weighted, mass-preserving) remapping is the right choice for flux
    fields like these, not bilinear/nearest. compare_tar is a validation-only
    tool run by hand, not part of the daily processing pipeline, so the
    extra cdo call is an acceptable cost for getting a real per-cell
    comparison instead of a bare "shape_mismatch" row.

    Args:
        file_ref: final nc file whose grid is the regrid target (cdo accepts
            an existing nc file directly as a target-grid description)
        file_target: final nc file to regrid onto file_ref's grid
        tmp_dir: directory for the regridded output file
        verbose: print the cdo command being run

    Returns:
        Path to the regridded copy of file_target.
    """
    out = os.path.join(tmp_dir, f"regrid_{os.path.basename(file_target)}")
    cmd = f"cdo -s -O remapcon,{file_ref} {file_target} {out}"
    if verbose:
        print(aux.pinfo(f"      > [compare] regridding: {cmd}"))
    os.system(cmd)
    return out


def _cell_area(file_ref: str, tmp_dir: str, verbose: bool = False) -> np.ndarray | None:
    """Grid-cell area (m2), shape (lat, lon), via `cdo gridarea`.

    Only used under --historicalref, to area-weight the raw per-cell diff
    (see _raw_row_historicalref) -- a flux difference in a large low-latitude
    cell is a bigger real mass-rate discrepancy than the same flux
    difference in a tiny polar cell, and raw flux (kg m-2 s-1) alone doesn't
    reflect that.

    Args:
        file_ref: final nc file whose grid the area is computed for (any
            file on that grid gives the same result -- this is a property of
            the grid, not of any particular species/sector)
        tmp_dir: directory for the temporary `cdo gridarea` output
        verbose: print the cdo command being run

    Returns:
        2D (lat, lon) area array, or None if `cdo gridarea` failed (e.g. a
        grid it can't derive cell areas for) -- callers fall back to
        unweighted diffs rather than treat this as fatal.
    """
    out = os.path.join(tmp_dir, f"gridarea_{os.path.basename(file_ref)}")
    cmd = f"cdo -s -O gridarea {file_ref} {out}"
    if verbose:
        print(aux.pinfo(f"      > [compare] computing cell area: {cmd}"))
    os.system(cmd)
    if not os.path.isfile(out):
        print(aux.pwarn(f"      > [compare] gridarea failed for {file_ref} -- "
                         f"falling back to unweighted (per-unit-area) raw diffs"))
        return None
    ds = xr.open_dataset(out)
    if "cell_area" not in ds.data_vars:
        # Not "the sole data var" -- cdo keeps the source file's lat_bnds/
        # lon_bnds attached to their coordinate variables (CF-compliance)
        # even here, so the output can carry 3 data vars, not 1 (bit us on a
        # real aviation file: picking data_vars[0] silently grabbed lon_bnds,
        # shape (720, 2), instead of cell_area, shape (360, 720), and the
        # resulting broadcast crashed downstream instead of failing here
        # with a clear message). "cell_area" is cdo gridarea's own stable,
        # documented output name -- select it directly instead of guessing.
        ds.close()
        os.remove(out)
        print(aux.pwarn(f"      > [compare] gridarea produced no 'cell_area' variable for {file_ref} -- "
                         f"falling back to unweighted (per-unit-area) raw diffs"))
        return None
    area = ds["cell_area"].values
    ds.close()
    os.remove(out)
    return area


def _md5sum(path: str) -> str:
    """MD5 checksum of a file's bytes, for a fast whole-file identity check."""
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _stats_row(species: str, suffix: str, sector: str, status: str,
                row_a: dict | None, row_b: dict | None) -> dict:
    """Build one emissions-stats (Tg) comparison row for a single sector.

    Args:
        species: species token parsed from the filenames
        suffix: subset_suffix (the CSV "dataset" column)
        sector: sector/variable name
        status: "both", "only_in_A", or "only_in_B"
        row_a: this sector's row from compute_file_stats_rows() on archive
            A's file, or None if the sector isn't present there
        row_b: same, for archive B

    Returns:
        Row dict with per-month/total values for both sides, plus diff and
        relative diff of the annual totals when both sides have a value.
    """
    row = {"species": species, "dataset": suffix, "sector": sector, "status": status}
    for m in range(1, 13):
        key = f"month_{m:02d}"
        row[f"{key}_A"] = row_a[key] if row_a else ""
        row[f"{key}_B"] = row_b[key] if row_b else ""
    row["total_Tg_A"] = row_a["total_Tg"] if row_a else ""
    row["total_Tg_B"] = row_b["total_Tg"] if row_b else ""
    if row_a and row_b:
        diff = row_b["total_Tg"] - row_a["total_Tg"]
        row["diff_total_Tg"] = diff
        row["reldiff_total_Tg_pct"] = (diff / row_a["total_Tg"] * 100) if row_a["total_Tg"] else ""
    else:
        row["diff_total_Tg"] = ""
        row["reldiff_total_Tg_pct"] = ""
    return row


def _raw_row_common(species: str, suffix: str, sector: str, status: str, file_md5_identical: bool | None,
                     ds_a: xr.Dataset | None, ds_b: xr.Dataset | None,
                     sector_a: str | None = None, sector_b: str | None = None
                     ) -> tuple[dict, np.ndarray | None, np.ndarray | None]:
    """Shared prologue for _raw_row_strict/_raw_row_historicalref.

    Builds the blank row shape (all diff fields default to "") and resolves
    the two sides' sector arrays, handling the two cases where there's
    nothing left to diff.

    Args:
        species, suffix, sector, status: see _raw_row_strict/_historicalref
        file_md5_identical: whole-file MD5 identity, or None if only one
            side has this file
        ds_a, ds_b: open xarray.Dataset for archive A/B's file, or None
        sector_a, sector_b: variable name to read from ds_a/ds_b, if it
            differs from `sector` (see _pair_sectors' legacy-vs-current
            matching); defaults to `sector`

    Returns:
        (row, arr_a, arr_b). If status != "both", or the two arrays' shapes
        don't match, `row` is already the finished result (arr_a/arr_b are
        both None) and the caller should return it as-is without further
        work. Otherwise arr_a/arr_b are the raw sector arrays to diff.
    """
    row = {"species": species, "dataset": suffix, "sector": sector, "status": status,
           "file_md5_identical": file_md5_identical if file_md5_identical is not None else "",
           "identical": "", "consistent": "", "tier": "", "mean_abs_diff": "", "rel_mean_abs_diff": "",
           "max_abs_diff": "", "rel_max_abs_diff": ""}
    if status != "both":
        return row, None, None

    arr_a, arr_b = ds_a[sector_a or sector].values, ds_b[sector_b or sector].values
    if arr_a.shape != arr_b.shape:
        row["identical"] = False
        row["consistent"] = False
        row["tier"] = "different"
        row["max_abs_diff"] = "shape_mismatch"
        return row, None, None

    return row, arr_a, arr_b


def _raw_row_strict(species: str, suffix: str, sector: str, status: str, file_md5_identical: bool | None,
                     ds_a: xr.Dataset | None, ds_b: xr.Dataset | None,
                     sector_a: str | None = None, sector_b: str | None = None) -> dict:
    """Build one raw-field (kg m-2 s-1) comparison row, same-source case.

    Used without --historicalref (legacyref/legacyboth/plain --compare):
    both sides come from the *same* raw dataset (a tool-version regression
    test, or re-running the same input). Any divergence, however small or
    localized to a single cell, is a real signal worth seeing -- that's
    exactly the shape of a processing bug. This is the tool's original,
    pre-historicalref behavior verbatim: "consistent" means bit-identical,
    full precision, no magnitude-aware tolerance -- unlike
    _raw_row_historicalref, which judges consistency by how close the field
    is overall rather than requiring an exact match.

    Args:
        species: species token parsed from the filenames
        suffix: subset_suffix (the CSV "dataset" column)
        sector: sector/variable name used as the row's display label
        status: "both", "only_in_A", or "only_in_B"
        file_md5_identical: whether the two whole nc files are byte-identical,
            or None if only one side has this file
        ds_a: open xarray.Dataset for archive A's file, or None
        ds_b: same, for archive B
        sector_a: variable name to read from ds_a, if it differs from
            `sector` (see _pair_sectors' legacy-vs-current matching);
            defaults to `sector`
        sector_b: same, for ds_b

    Returns:
        Row dict; "identical"/"consistent"/"tier"/"max_abs_diff"/
        "mean_abs_diff" are only filled in when the sector is present on
        both sides, at full precision. "consistent"/"tier" ("consistent" or
        "different", never "similar") are exactly "identical" here -- no
        tolerance, no middle ground, in this path.
    """
    row, arr_a, arr_b = _raw_row_common(species, suffix, sector, status, file_md5_identical, ds_a, ds_b,
                                         sector_a=sector_a, sector_b=sector_b)
    if arr_a is None:
        return row

    identical = bool(np.array_equal(arr_a, arr_b))
    absdiff = np.abs(arr_a - arr_b)
    row["identical"] = identical
    row["consistent"] = identical
    row["tier"] = "consistent" if identical else "different"  # no middle ground here -- see _raw_row_historicalref
    row["max_abs_diff"] = float(absdiff.max())
    row["mean_abs_diff"] = float(absdiff.mean())
    return row


def _raw_row_historicalref(species: str, suffix: str, sector: str, status: str, file_md5_identical: bool | None,
                            ds_a: xr.Dataset | None, ds_b: xr.Dataset | None,
                            sector_a: str | None = None, sector_b: str | None = None,
                            area: np.ndarray | None = None,
                            total_tg_a: float | None = None, total_tg_b: float | None = None) -> dict:
    """Build one raw-field (kg/s, area-weighted) comparison row, cross-source case.

    Used under --historicalref, where A and B come from genuinely different
    raw sources (CEDS historical vs IIASA-IAMC scenariomip) -- exact
    per-cell agreement was never expected or physically meaningful, so a
    single-cell max-based check is too sensitive (one differing cell
    anywhere flags the whole sector "different" even if every other cell
    matches closely -- this is what happened for VOC14/anthro-surf: ENE and
    SHP's worst cell dominated even though most of the field agreed).
    Consistency is instead judged by mean_abs_diff (does the field agree
    *overall*) relative to a stable magnitude reference (see `total_tg_a`/
    `total_tg_b` below), with RAW_CONSISTENT_RELTOL as the bar. max_abs_diff
    is still reported (relative to peak magnitude) as a diagnostic for
    spotting a genuine localized outlier -- it just no longer decides
    consistent/different on its own.

    Both max/mean_abs_diff are computed on the area-weighted field (flux *
    cell area, kg/s -- see `area`) rather than the raw flux (kg m-2 s-1): a
    given flux difference in a large low-latitude cell represents far more
    actual mass-rate discrepancy than the same flux difference in a tiny
    polar cell, so weighing every cell equally (as the raw flux does) would
    over-count small cells and under-count large ones.

    Args:
        species: species token parsed from the filenames
        suffix: subset_suffix (the CSV "dataset" column)
        sector: sector/variable name used as the row's display label
        status: "both", "only_in_A", or "only_in_B"
        file_md5_identical: whether the two whole nc files are byte-identical,
            or None if only one side has this file
        ds_a: open xarray.Dataset for archive A's file, or None
        ds_b: same, for archive B
        sector_a: variable name to read from ds_a, if it differs from
            `sector` (see _pair_sectors' legacy-vs-current matching);
            defaults to `sector`
        sector_b: same, for ds_b
        area: grid-cell area (m2), shape (lat, lon), broadcasting against
            arr_a/arr_b's (time, lat, lon) -- see _cell_area. None falls
            back to the unweighted raw flux (with a warning printed by the
            caller), rather than failing outright.
        total_tg_a: this sector's annual total mass (Tg) on A's side, from
            the same _stats_row/compute_file_stats_rows() computation as the
            A=.../B=... totals printed alongside this row -- used as the
            magnitude reference for rel_mean_abs_diff (see below). None (the
            sector's Tg total wasn't available, e.g. cdo fldint failed for
            it) falls back to the less robust per-cell mean(|F|) reference.
        total_tg_b: same, for B's side.

    Returns:
        Row dict; "identical"/"consistent"/"tier"/"mean_abs_diff"/
        "rel_mean_abs_diff"/"max_abs_diff"/"rel_max_abs_diff" are only
        filled in when the sector is present on both sides, rounded to
        RAW_DIAG_SIG_FIGS for display (the consistency check itself runs on
        the full-precision values, before rounding). rel_mean_abs_diff is
        the value actually compared against RAW_CONSISTENT_RELTOL to decide
        "consistent" -- rel_max_abs_diff is diagnostic only (see above).
        "tier" is "consistent"/"similar"/"different": "similar" is a
        not-quite-"consistent" row (rel_mean_abs_diff over threshold) whose
        annual Tg totals still agree within TOTAL_TG_CONSISTENT_PCT -- same
        overall mass, different spatial/temporal placement, as opposed to a
        genuine "different" where the totals themselves disagree too.
    """
    row, arr_a, arr_b = _raw_row_common(species, suffix, sector, status, file_md5_identical, ds_a, ds_b,
                                         sector_a=sector_a, sector_b=sector_b)
    if arr_a is None:
        return row

    identical = bool(np.array_equal(arr_a, arr_b))  # scale-invariant, so unaffected by area weighting below

    # Area-weight before diffing: a flux (kg m-2 s-1) difference in a large
    # low-latitude cell is a bigger real mass-rate discrepancy than the same
    # flux difference in a tiny polar cell -- multiplying by each cell's
    # area (m2) turns the field into kg/s (mass rate) so every cell's
    # contribution to max/mean_abs_diff reflects its actual physical weight,
    # not just its per-unit-area flux value. Falls back to the raw
    # (unweighted) flux if area is unavailable (see _cell_area) rather than
    # failing the whole comparison over it.
    weighted_a = arr_a * area if area is not None else arr_a
    weighted_b = arr_b * area if area is not None else arr_b
    absdiff = np.abs(weighted_a - weighted_b)
    max_abs = float(absdiff.max())
    mean_abs = float(absdiff.mean())

    # mean(|F|) over the whole grid is a bad "typical magnitude" reference --
    # emissions are extremely spatially concentrated (most cells near-zero,
    # a few source cells carry nearly all the mass), so how far it's dragged
    # down depends on how sparse THAT species happens to be, not on whether
    # A and B agree. Confirmed on real data: VOC17's clearly noise-level
    # sectors (Tg totals identical to 6 sig figs) landed ~1000x "worse" by
    # this ratio than BC's equivalent noise, purely from VOC17 being a
    # sparser field. The total annual mass (Tg, already computed for the
    # A=.../B=... totals) doesn't have that problem -- converted to an
    # equivalent average kg/s, it's used as the reference instead.
    #
    # Total_Tg = sum over 12 months of [ (sum over n_cells spatial cells of F)
    # * seconds(month) ] * 1e-9. Approximating the spatial mean as roughly
    # constant month to month, sum-over-cells ~= n_cells * mean(F), and
    # sum-over-months of seconds(month) = SECONDS_PER_YEAR exactly, giving
    # Total_Tg ~= n_cells * mean(F) * SECONDS_PER_YEAR * 1e-9, i.e.
    # mean(F) ~= Total_Tg * 1e9 / (n_cells * SECONDS_PER_YEAR) -- divided by
    # n_cells (SPATIAL cells only), *not* absdiff.size (= 12 * n_cells,
    # months included): Total_Tg already accumulates over all 12 months by
    # itself, so dividing by 12 again here double-counts the time axis and
    # under-scales the reference by 12x, inflating every rel_mean_abs_diff
    # by 12x in turn (confirmed on real data: bburning bbALL sectors showing
    # rel~10-18 dropped to a plausible ~0.9-1.5 once corrected).
    if isinstance(total_tg_a, (int, float)) and isinstance(total_tg_b, (int, float)):
        n_cells = int(np.prod(absdiff.shape[1:]))  # spatial (and level, for aviation) cells -- excludes the time axis
        ref_mean = 0.5 * ((total_tg_a + total_tg_b) * 1e9 / SECONDS_PER_YEAR) / n_cells
    else:
        ref_mean = 0.5 * (float(np.abs(weighted_a).mean()) + float(np.abs(weighted_b).mean()))
    rel_mean_abs = (mean_abs / ref_mean) if ref_mean else (0.0 if mean_abs == 0 else math.inf)

    # Still reported (diagnostic only, doesn't drive "consistent"): peak-
    # relative max_abs_diff, for spotting a genuine localized outlier even
    # when the field agrees on average.
    ref_peak = 0.5 * (float(np.abs(weighted_a).max()) + float(np.abs(weighted_b).max()))
    rel_max_abs = (max_abs / ref_peak) if ref_peak else (0.0 if max_abs == 0 else math.inf)

    row["identical"] = identical
    row["consistent"] = identical or rel_mean_abs < RAW_CONSISTENT_RELTOL
    row["mean_abs_diff"] = aux.round_sig(mean_abs, RAW_DIAG_SIG_FIGS)
    row["rel_mean_abs_diff"] = "inf" if math.isinf(rel_mean_abs) else aux.round_sig(rel_mean_abs, RAW_DIAG_SIG_FIGS)
    row["max_abs_diff"] = aux.round_sig(max_abs, RAW_DIAG_SIG_FIGS)
    row["rel_max_abs_diff"] = "inf" if math.isinf(rel_max_abs) else aux.round_sig(rel_max_abs, RAW_DIAG_SIG_FIGS)

    # A sector can fail RAW_CONSISTENT_RELTOL for two very different reasons:
    # the totals themselves disagree (a real difference), or the totals
    # agree but the spatial/temporal *pattern* doesn't (plausibly just
    # placement uncertainty on a species neither source pins down precisely
    # -- see VOC01/VOC02: ENE/SHP read [DIFFERENT] on pattern alone despite
    # matching Tg totals to within ~0.6%). "similar" separates that second
    # case out from a genuine "different" -- same overall mass, different
    # placement -- rather than collapsing both into one DIFFERENT bucket.
    if row["consistent"]:
        row["tier"] = "consistent"
    elif (isinstance(total_tg_a, (int, float)) and isinstance(total_tg_b, (int, float)) and total_tg_a):
        reldiff_total_pct = abs((total_tg_b - total_tg_a) / total_tg_a * 100)
        row["tier"] = "similar" if reldiff_total_pct < TOTAL_TG_CONSISTENT_PCT else "different"
    else:
        row["tier"] = "different"  # can't tell totals apart (e.g. total_tg_a == 0) -- safer default
    return row


def _pair_sectors(sectors_a: list[str], sectors_b: list[str],
                   ds_a: xr.Dataset | None, ds_b: xr.Dataset | None,
                   verbose: bool = False, legacyref: bool = False) -> list[tuple[str, str | None, str | None]]:
    """Pair up sector names across the two sides for one (species, suffix, year).

    Normally pairs sectors of the same name (the else branch below). But
    when `legacyref` is set and B (the reference archive -- legacyref means
    "B is legacy", never A) reports exactly one sector under a name A
    doesn't have -- the shape of a legacy bburning archive (a single,
    often genericly-named sector, e.g. CMIP6's "biomass_burning" -- see
    etc/historical_cmip6.toml -- or CMIP7's "biomass_burning"-style legacy
    name) vs a current one ("bbALL" alone for most species, or "bbALL" plus
    "bbPEAT" for scaled species -- see etc/historical_cmip7.toml's
    [[CMIP7.bburning.scaling]], which only lists species=["CO2"]) --
    name-based pairing would report B's sector as 100% missing on A's side
    and every one of A's sectors as 100% missing on B's side, hiding a real
    comparison that's actually possible: whether A has one current sector
    or several, B's single legacy value should end up numerically close to
    whichever of them it corresponds to (bbALL is the unscaled total,
    bbPEAT a derived subset of it). This compares B's solo sector's raw
    field against each of A's candidates (however many there are) and
    pairs it with whichever is closest (smallest mean abs diff) -- if it
    doesn't actually match well, that still shows up downstream as a
    normal "different" row with a real diff magnitude, rather than a
    misleading "only in A"/"only in B". When B's solo name already matches
    one of A's sectors exactly, this is skipped entirely and the plain
    same-name path below handles it directly (no naming mismatch to
    resolve).

    This heuristic only makes sense when B really is a legacy reference
    with a collapsed/differently-named sector -- for two current-tool
    archives, a lone unrecognized sector on one side is more likely a real
    bug than a naming difference, so it's opt-in via `legacyref`
    (--legacyref on cmip_validate) rather than always applied. It's
    specifically directional (B only): if A has the lone sector instead,
    that's left as a plain mismatch regardless of `legacyref`, since a test
    archive collapsing to one sector isn't the legacy-data shape this is
    meant to explain away.

    Regardless of the solo-vs-multi case, plain name-based matching (the
    branch below) first canonicalizes B's sector names through
    LEGACY_SECTOR_ALIASES when `legacyref` is set, so e.g. B's "biofuel"
    lines up with A's "ALL" instead of showing as two unmatched extras.

    Args:
        sectors_a: sector names present in archive A's file
        sectors_b: same, for archive B
        ds_a: open xarray.Dataset for archive A's file, or None
        ds_b: same, for archive B
        verbose: print info steps
        legacyref: enable the B-solo-vs-A-multi matching described above,
            and the LEGACY_SECTOR_ALIASES canonicalization

    Returns:
        List of (label, name_a, name_b) triples for the per-sector loop.
        name_a/name_b are the actual per-side variable names to look values
        up with (None when that side has nothing for this label) -- they
        only differ from each other when a solo/alias match kicked in;
        `label` is the shared display/grouping name used in the output CSVs.
    """
    if not (legacyref and len(sectors_b) == 1 and len(sectors_a) >= 1 and sectors_b[0] not in sectors_a):
        b_by_label = {}
        for s in sectors_b:
            label = LEGACY_SECTOR_ALIASES.get(s, s) if legacyref else s
            b_by_label[label] = s
        return [(s, s if s in sectors_a else None, b_by_label.get(s))
                for s in sorted(set(sectors_a) | set(b_by_label))]

    solo_name = sectors_b[0]
    best_match, best_diff = None, None
    candidate_diffs = {}
    if ds_a is not None and ds_b is not None:
        solo_arr = ds_b[solo_name].values
        for cand in sectors_a:
            cand_arr = ds_a[cand].values
            if cand_arr.shape != solo_arr.shape:
                candidate_diffs[cand] = "shape_mismatch"
                continue
            d = float(np.abs(solo_arr - cand_arr).mean())
            candidate_diffs[cand] = d
            if best_diff is None or d < best_diff:
                best_diff, best_match = d, cand

    print(aux.pinfo(f"  > [compare] B's single sector '{solo_name}' vs every A candidate:"))
    for cand in sorted(sectors_a):
        d = candidate_diffs.get(cand, "n/a")
        marker = " <- matched" if cand == best_match else ""
        print(aux.pinfo(f"      A '{cand}': mean_abs_diff={d}") + marker)

    pairs = []
    if best_match is not None:
        pairs.append((best_match, best_match, solo_name))
        remaining = [m for m in sectors_a if m != best_match]
    else:
        remaining = sectors_a

    for m in remaining:
        pairs.append((m, m, None))
    return pairs


def _known_file_diff_side(species: str, suffix: str, file_a: str | None, file_b: str | None) -> str | None:
    """Under --historicalref, is this a known one-sided (species, suffix) key?

    Args:
        species: species token for this key
        suffix: subset_suffix for this key
        file_a: matched file path on the A (scenariomip) side, or None
        file_b: matched file path on the B (historical) side, or None

    Returns:
        "A" or "B" (the side the file is present on) if this key is present
        on exactly one side and listed in KNOWN_HISTORICAL_SCENARIO_DIFFS,
        else None -- including when both or neither side has the file, since
        a real mismatch always has exactly one side present.
    """
    if (file_a is None) == (file_b is None):
        return None
    if (species, suffix) not in KNOWN_HISTORICAL_SCENARIO_DIFFS:
        return None
    return "A" if file_b is None else "B"


def _is_known_bburning_sector(species: str, suffix: str, label: str, status: str) -> bool:
    """Under --historicalref, is this a known scenariomip-only bburning sector?

    Scenariomip's bburning subset always computes bbAGRW/bbFORE/bbGRSS/bbPEAT
    (see HISTORICAL_MISSING_BBURNING_SECTORS), none of which historical has
    except bbPEAT for CO2 specifically (see
    HISTORICAL_MISSING_BBURNING_SECTORS_EXCEPT_SPECIES) -- so an
    otherwise-real-looking only_in_A sector row is actually expected
    whenever it's one of those, for a non-excepted species.

    Args:
        species: species token for this sector's file
        suffix: subset_suffix for this sector's file
        label: sector/variable name from _pair_sectors' pairing
        status: "both"/"only_in_A"/"only_in_B" for this sector, from the
            same pairing

    Returns:
        True if this sector row is a known, accepted historical-vs-
        scenariomip difference rather than a real one.
    """
    return (status == "only_in_A" and suffix == "bburning"
            and label in HISTORICAL_MISSING_BBURNING_SECTORS
            and species not in HISTORICAL_MISSING_BBURNING_SECTORS_EXCEPT_SPECIES.get(label, set()))


def _print_known_diffs(known_file_diffs: list[tuple[str, str, str, str]],
                        known_sector_diffs: list[tuple[str, str, str]]) -> None:
    """Print the --historicalref "known differences" reminder block.

    Args:
        known_file_diffs: (species, suffix, year, side) rows excluded by
            _known_file_diff_side
        known_sector_diffs: (species, sector, year) rows excluded by
            _is_known_bburning_sector (always only_in_A)
    """
    if not (known_file_diffs or known_sector_diffs):
        return

    file_diff_years: dict[tuple[str, str, str], list[str]] = defaultdict(list)
    for species, suffix, year, side in known_file_diffs:
        file_diff_years[(species, suffix, side)].append(year)

    sector_diff_years: dict[tuple[str, str], list[str]] = defaultdict(list)
    for species, sector, year in known_sector_diffs:
        sector_diff_years[(species, sector)].append(year)

    print(" ------ Known historical-vs-scenariomip differences (--historicalref) ---")
    print(
        " Not counted above -- accepted differences between the underlying\n"
        " datasets, not tool/config problems (see KNOWN_HISTORICAL_SCENARIO_DIFFS\n"
        " and HISTORICAL_MISSING_BBURNING_SECTORS in lib/compare_tar.py):\n")
    for (species, suffix, side), years in sorted(file_diff_years.items()):
        print(f"   {species:<12} {suffix:<14} only in {side}  ({len(years)} year file(s))")
    for (species, sector), years in sorted(sector_diff_years.items()):
        print(f"   {species:<12} bburning/{sector:<10} only in A  ({len(years)} year file(s))")
    print(" ------------------------------------------------------------------")


def _mark_exclusive(sectors: list[str], exclusive: set) -> str:
    """Join `sectors` into a display string, common ones first (alphabetical),
    then ones in `exclusive` (present on this side only) last, wrapped as
    **name** so they stand out -- otherwise spotting the one real difference
    in two long, mostly-identical comma lists means diffing them by eye."""
    ordered = sorted(sectors, key=lambda s: (s in exclusive, s))
    return ", ".join(f"**{s}**" if s in exclusive else s for s in ordered) or "(none)"


def _write_grouped_csv(rows: list[dict], fields: list[str], dest_root: str, prefix: str) -> None:
    """Write one CSV per (group, year) found in `rows`, sorted like write_year_csv."""
    by_group_year: dict[tuple[str, str], list[dict]] = {}
    for row in rows:
        by_group_year.setdefault((row["_group"], row["_year"]), []).append(row)

    for (group, year), grows in by_group_year.items():
        csv_path = os.path.join(dest_root, f"{prefix}_{group}_{year}.csv")
        os.makedirs(dest_root, exist_ok=True)
        grows_sorted = sorted(grows, key=lambda r: (r["dataset"], r["species"], r["sector"]))
        with open(csv_path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(grows_sorted)
        print(aux.pshow(f"  > [compare] wrote {csv_path}"))


def compare_tars(tar_a: str, tar_b: str, outdir: str = "outs/validation", name: str | None = None,
                  verbose: bool = False, keep: bool = False,
                  legacyref: bool = False, legacyboth: bool = False,
                  historicalref: bool = False) -> None:
    """Diff two archived tar/tgz of final nc files against each other.

    Matches files across the two archives by (species, subset_suffix, year)
    -- the same identity a live cmip_preemis run keys its output files by,
    regardless of the tag/version embedded in the filename, which is exactly
    what differs between the two archives being compared. For every matched
    (or one-sided) key, compares every sector actually present in either
    file (see list_sector_variables), and writes two reports per (group,
    year) to `<outdir>/<name>/`:

      - diff_stats_<group>_<year>.csv: emissions-stats (Tg) comparison, via
        the same compute_file_stats_rows() a live run uses.
      - diff_raw_<group>_<year>.csv: raw per-sector field (kg m-2 s-1) diff,
        plus a whole-file MD5 identity check -- for exact regression testing
        (same tool, same raw input, different version) as well as magnitude
        reporting for genuinely different datasets (e.g. historical vs
        scenariomip on an overlapping year).

    A sector/species/file present on only one side is reported as a
    "only_in_A"/"only_in_B" row rather than silently skipped.

    If a matched (species, suffix, year) pair turns out to be on different
    native grids (e.g. historical bburning at 0.25 deg vs scenariomip
    bburning at 0.5 deg), B is conservatively regridded onto A's grid before
    the raw per-sector diff (see _regrid_to_match) -- printed even without
    --verbose, since it changes what's being compared. Within diff_raw, a
    "both, not identical" row that's really just float noise (relative
    max_abs_diff below RAW_CONSISTENT_RELTOL) is reported as "consistent"
    rather than lumped in with genuine differences (see
    _raw_row_strict/_raw_row_historicalref).

    Args:
        tar_a: path to the archive under test (the "A" side throughout --
            printed output, CSV status values, and diff signs all treat A as
            the candidate being checked against B)
        tar_b: path to the reference/baseline archive (the "B" side)
        outdir: base directory for the diff CSVs
        name: dataset-name subdirectory; if None, inferred as
            "<tagA>_vs_<tagB>" from the tags embedded in each archive's
            filenames
        verbose: print info steps
        keep: keep the extracted files (in temp dirs) instead of removing
            them once done
        legacyref: B is a legacy archive, A is current/under test. Applies
            LEGACY_SUFFIX_ALIASES to B's filenames only (see parse_nc_files),
            and lets a lone sector on B stand in for any of several current
            sectors on A (see _pair_sectors) instead of a plain name-based
            only-in-A/only-in-B mismatch. Mutually exclusive with legacyboth.
        legacyboth: both A and B are legacy archives with the same old
            naming/sector conventions as each other. Applies
            LEGACY_SUFFIX_ALIASES to both sides' filenames (so e.g. both
            being "bb4-2-0" still group/compare as "bburning"), but does
            *not* enable the solo-vs-multi sector matching that legacyref
            does -- with both sides equally legacy, plain same-name sector
            matching is expected to just work, so a sector mismatch here is
            treated as a real problem. Mutually exclusive with legacyref.
        historicalref: B is the historical archive, A is scenariomip (like
            legacyref, directional -- B is always historical, never the
            other way round). Both archives use current-tool naming (this
            is not about old vs new tool versions), so mutually exclusive
            with legacyref/legacyboth. Excludes the known, accepted
            historical-vs-scenariomip differences (KNOWN_HISTORICAL_
            SCENARIO_DIFFS at the whole species/suffix level,
            HISTORICAL_MISSING_BBURNING_SECTORS at the bburning sector
            level) from the only_in_A/only_in_B rows, counts, and warnings
            -- they're listed separately in a "known differences" reminder
            at the end instead.
    """
    for tar_path in (tar_a, tar_b):
        if not os.path.isfile(tar_path):
            print(aux.perror(f"\n{tar_path} not found."))
            return

    tmp_a = tempfile.mkdtemp(prefix="cmip_compare_a_", dir=aux.default_tmp_root())
    tmp_b = tempfile.mkdtemp(prefix="cmip_compare_b_", dir=aux.default_tmp_root())
    tmp_fldint = tempfile.mkdtemp(prefix="cmip_compare_fldint_", dir=aux.default_tmp_root())

    try:
        # Listing (tar.getmembers(), no extraction) is fast even for a large
        # tar, so both archives' contents are known before paying for any
        # actual extraction -- lets matched keys (the two-sided comparisons
        # that are the whole point of --compare) be processed, and their
        # results streamed out, before the merely one-sided ones, and lets
        # each file be extracted lazily, on demand, right where it's needed
        # below, instead of two full-archive extractions blocking up front.
        with tarfile.open(tar_a, "r:*") as tf_a, tarfile.open(tar_b, "r:*") as tf_b:
            members_a = list_nc_members(tf_a)
            members_b = list_nc_members(tf_b)
            if verbose:
                print(aux.pinfo(f"  > [compare] Found {len(members_a)} .nc files in {tar_a}"))
                print(aux.pinfo(f"  > [compare] Found {len(members_b)} .nc files in {tar_b}"))

            files_a, tag_a = parse_nc_files(list(members_a), verbose=verbose, apply_legacy_aliases=legacyboth)
            files_b, tag_b = parse_nc_files(list(members_b), verbose=verbose,
                                             apply_legacy_aliases=(legacyref or legacyboth))

            if not files_a and not files_b:
                print(aux.pwarn(f"No recognizable final emission nc files found in either archive"))
                return

            keys_a, keys_b = set(files_a), set(files_b)
            # Matched keys first (see comment above); only-in-A/only-in-B
            # last -- each needs at most one extraction and is reported as a
            # plain fact rather than a two-sided comparison, so there's no
            # benefit to seeing those before the real comparisons.
            all_keys = sorted(keys_a & keys_b) + sorted(keys_a - keys_b) + sorted(keys_b - keys_a)

            stats_rows: list[dict] = []
            raw_rows: list[dict] = []
            n_identical = n_consistent = n_similar = n_different = n_only_a = n_only_b = 0
            group_counts: dict[str, dict[str, int]] = defaultdict(
                lambda: {"identical": 0, "consistent": 0, "similar": 0, "different": 0, "only_a": 0, "only_b": 0})
            biggest_diffs: list[tuple[float, str, float, float]] = []
            known_file_diffs: list[tuple[str, str, str, str]] = []    # (species, suffix, year, side)
            known_sector_diffs: list[tuple[str, str, str]] = []       # (species, sector, year)
            # Cell area only depends on the grid's shape (a regular lat-lon grid
            # at a given resolution always has the same cell areas), not on the
            # specific file/species -- caching by shape avoids a redundant `cdo
            # gridarea` call for every one of the many files sharing a grid.
            area_cache: dict[tuple[int, int], np.ndarray | None] = {}

            for species, suffix, year in all_keys:
                member_a = files_a.get((species, suffix, year))
                member_b = files_b.get((species, suffix, year))
                file_a = extract_member(tf_a, members_a[member_a], tmp_a) if member_a else None
                file_b = extract_member(tf_b, members_b[member_b], tmp_b) if member_b else None
                group = group_for_suffix(suffix, verbose=verbose)

                known_side = _known_file_diff_side(species, suffix, file_a, file_b) if historicalref else None
                if known_side is not None:
                    known_file_diffs.append((species, suffix, year, known_side))
                    print(aux.pinfo(f"  > [compare] {species}/{suffix}/{year} -- known historical-vs-scenariomip "
                                     f"difference (only in {known_side}), not reported as a difference (--historicalref)"))
                    continue

                print(aux.pshow(f"  > [compare] {species}/{suffix}/{year}"))
                print(aux.pinfo(f"      A: ") + (file_a or "(no matching file in A)"))
                print(aux.pinfo(f"      B: ") + (file_b or "(no matching file in B)"))

                sectors_a = list_sector_variables(file_a) if file_a else []
                sectors_b = list_sector_variables(file_b) if file_b else []

                stats_a = {r["sector"]: r for r in emissions_stats.compute_file_stats_rows(
                    file_a, sectors_a, species, suffix, year, tmp_fldint, verbose=verbose)} if file_a else {}
                stats_b = {r["sector"]: r for r in emissions_stats.compute_file_stats_rows(
                    file_b, sectors_b, species, suffix, year, tmp_fldint, verbose=verbose)} if file_b else {}

                file_md5_identical = _md5sum(file_a) == _md5sum(file_b) if (file_a and file_b) else None
                ds_a = xr.open_dataset(file_a) if file_a else None
                ds_b = xr.open_dataset(file_b) if file_b else None

                # Actual array shape (last two axes = spatial, per
                # store_output()'s (..., lat, lon) layout) rather than dataset
                # dims by name -- input4MIPs-derived files aren't guaranteed to
                # name their spatial dims "lat"/"lon" consistently across
                # sources, and a wrong guess here would silently no-op instead
                # of catching a real grid mismatch. Computed once and reused
                # below for both the mismatch/regrid check and the area-cache
                # key, since both need exactly this.
                grid_a = ds_a[sectors_a[0]].shape[-2:] if (ds_a is not None and sectors_a) else None

                if grid_a is not None and ds_b is not None and sectors_b:
                    grid_b = ds_b[sectors_b[0]].shape[-2:]
                    if grid_a != grid_b:
                        print(aux.pwarn(f"      grid mismatch: A is {grid_a[0]}x{grid_a[1]}, B is "
                                         f"{grid_b[0]}x{grid_b[1]} -- regridding B onto A's grid (cdo remapcon)"))
                        ds_b.close()
                        file_b_regridded = _regrid_to_match(file_a, file_b, tmp_fldint, verbose=verbose)
                        ds_b = xr.open_dataset(file_b_regridded)

                area = None
                if historicalref and grid_a is not None:
                    # A's grid, cached by shape -- valid for both sides here,
                    # since B is already on A's grid by this point (either
                    # natively, or via the regrid just above).
                    if grid_a not in area_cache:
                        area_cache[grid_a] = _cell_area(file_a, tmp_fldint, verbose=verbose)
                    area = area_cache[grid_a]

                exact_matches: list[str] = []
                pairs = _pair_sectors(sectors_a, sectors_b, ds_a, ds_b, verbose=verbose, legacyref=legacyref)
                for label, name_a, name_b in pairs:
                    status = "both" if (name_a and name_b) else ("only_in_A" if name_a else "only_in_B")

                    if historicalref and _is_known_bburning_sector(species, suffix, label, status):
                        known_sector_diffs.append((species, label, year))
                        continue

                    srow = _stats_row(species, suffix, label, status, stats_a.get(name_a), stats_b.get(name_b))
                    srow["_group"], srow["_year"] = group, year
                    stats_rows.append(srow)

                    if historicalref:
                        rrow = _raw_row_historicalref(species, suffix, label, status, file_md5_identical, ds_a, ds_b,
                                                       sector_a=name_a, sector_b=name_b, area=area,
                                                       total_tg_a=srow["total_Tg_A"], total_tg_b=srow["total_Tg_B"])
                    else:
                        rrow = _raw_row_strict(species, suffix, label, status, file_md5_identical, ds_a, ds_b,
                                                sector_a=name_a, sector_b=name_b)
                    rrow["_group"], rrow["_year"] = group, year
                    raw_rows.append(rrow)

                    if status == "both" and rrow["max_abs_diff"] == 0.0:
                        # Bit-identical raw field (max_abs_diff exactly 0.0) isn't
                        # interesting to see line by line -- still counted in
                        # n_identical below, just rolled into one summary line
                        # after the loop (see exact_matches) instead of a page of
                        # "A=0.0 B=0.0 max_abs_diff=0.0" rows for always-empty
                        # sectors (e.g. SLV), so it doesn't bury the ones with an
                        # actual diff to look at -- but it's never silently
                        # dropped without a trace either.
                        exact_matches.append(label)
                    elif status == "both":
                        val_a, val_b = srow["total_Tg_A"], srow["total_Tg_B"]
                        a_tag = f" (A:'{name_a}')" if name_a != label else ""
                        b_tag = f" (B:'{name_b}')" if name_b != label else ""
                        # An explicit text tag alongside the color, not instead of
                        # it -- ANSI color is invisible/stripped in a lot of the
                        # places this output ends up (batch job logs, pasted into
                        # a chat, redirected to a file), so "not green" shouldn't
                        # be the only way to tell the tiers apart. "similar"
                        # (--historicalref only, see _raw_row_historicalref) gets
                        # its own tag/color, not folded into either consistent or
                        # DIFFERENT -- same overall Tg total, different
                        # spatial/temporal placement is a different finding from
                        # either of those.
                        tag = {"consistent": "consistent", "similar": "similar", "different": "DIFFERENT"}[rrow["tier"]]
                        color = {"consistent": aux.pgood, "similar": aux.pinfo, "different": aux.pwarn}[rrow["tier"]]
                        if historicalref:
                            # mean_abs_diff/rel_mean_abs_diff are what
                            # "consistent" is actually decided on (see
                            # _raw_row_historicalref) -- shown first, not
                            # max_abs_diff/rel_max_abs_diff, which are
                            # diagnostic-only here (spotting a localized
                            # outlier even when the field agrees on average).
                            print(color(
                                f"      sector {label:<14} [{tag:<10}] A={str(val_a):<14} B={str(val_b):<14} "
                                f"mean_abs_diff={rrow['mean_abs_diff']} (rel={rrow['rel_mean_abs_diff']})  "
                                f"max_abs_diff={rrow['max_abs_diff']} (rel={rrow['rel_max_abs_diff']}){a_tag}{b_tag}"))
                        else:
                            print(color(
                                f"      sector {label:<14} [{tag:<10}] A={str(val_a):<14} B={str(val_b):<14} "
                                f"max_abs_diff={rrow['max_abs_diff']}{a_tag}{b_tag}"))

                    if status == "only_in_A":
                        n_only_a += 1
                        group_counts[group]["only_a"] += 1
                    elif status == "only_in_B":
                        n_only_b += 1
                        group_counts[group]["only_b"] += 1
                    elif rrow["identical"] is True:
                        n_identical += 1
                        group_counts[group]["identical"] += 1
                    elif rrow["tier"] == "consistent":
                        n_consistent += 1
                        group_counts[group]["consistent"] += 1
                    elif rrow["tier"] == "similar":
                        n_similar += 1
                        group_counts[group]["similar"] += 1
                    else:
                        n_different += 1
                        group_counts[group]["different"] += 1
                        if isinstance(srow["diff_total_Tg"], float):
                            biggest_diffs.append((abs(srow["diff_total_Tg"]), f"{species}/{suffix}/{label}/{year}",
                                                   srow["total_Tg_A"], srow["total_Tg_B"]))

                if exact_matches:
                    print(aux.pinfo(f"      {len(exact_matches)} sector(s) exactly identical (not shown above): ")
                          + ", ".join(sorted(exact_matches)))

                if ds_a is not None:
                    ds_a.close()
                if ds_b is not None:
                    ds_b.close()

                # Unpaired sectors after _pair_sectors (so a --legacyref alias such
                # as B's "biofuel" -> A's "ALL", or B's solo legacy sector matched
                # to one of A's, is not reported as a mismatch: those were
                # compared by value above)
                only_in_a = {name_a for _, name_a, name_b in pairs if name_a and not name_b}
                only_in_b = {name_b for _, name_a, name_b in pairs if name_b and not name_a}
                if historicalref:
                    # Sectors already excused above (recorded in known_sector_diffs)
                    # -- don't re-flag them here as a sector-set mismatch.
                    only_in_a = {s for s in only_in_a if not _is_known_bburning_sector(species, suffix, s, "only_in_A")}

                if only_in_a or only_in_b:
                    # Sector sets differing is exactly the signal that catches a
                    # legacy-vs-current naming mismatch (e.g. old bburning
                    # archives had one unnamed default sector, current ones have
                    # "bbALL"/"bbPEAT") -- a bare count ("0 in A, 1 in B") hides
                    # which sectors, so always spell out both lists, not just
                    # under --verbose. Indented as a continuation of this
                    # (species, suffix, year)'s "> [compare]" entry above, not a
                    # new one -- no repeated header line.
                    print(aux.pwarn(f"      sector sets differ (checking only names):"))
                    print(aux.pwarn(f"          A ({len(sectors_a)}): ") + _mark_exclusive(sectors_a, only_in_a))
                    print(aux.pwarn(f"          B ({len(sectors_b)}): ") + _mark_exclusive(sectors_b, only_in_b))
                elif verbose:
                    print(aux.pinfo(f"      {len(sectors_a)} sectors in A, {len(sectors_b)} in B"))

        # tar handles closed here -- nothing below needs them.
        dname = name if name is not None else f"{tag_a or 'A'}_vs_{tag_b or 'B'}"
        dest_root = os.path.join(outdir, dname)

        _write_grouped_csv(stats_rows, STATS_FIELDS, dest_root, "diff_stats")
        _write_grouped_csv(raw_rows, RAW_FIELDS, dest_root, "diff_raw")

        known_a_keys = {(s, suf, y) for s, suf, y, side in known_file_diffs if side == "A"}
        known_b_keys = {(s, suf, y) for s, suf, y, side in known_file_diffs if side == "B"}
        only_a_keys = (keys_a - keys_b) - known_a_keys
        only_b_keys = (keys_b - keys_a) - known_b_keys

        print(aux.pshow("\n ------ Comparison summary ---------------------------------------"))
        print(aux.pinfo(f" Archive A (test)     :") + f" {tar_a} (tag: {tag_a})")
        print(aux.pinfo(f" Archive B (reference):") + f" {tar_b} (tag: {tag_b})")
        print(aux.pinfo(f" Matched (species, dataset, year) keys: ") + f"{len(keys_a & keys_b)}")
        print(aux.pinfo(f" Only in A / Only in B (whole files):   ") + f"{len(only_a_keys)} / {len(only_b_keys)}")
        print(aux.pinfo(f" Sector rows -- identical:               ") + f"{n_identical}")
        print(aux.pgood(f" Sector rows -- consistent (float noise):") + f" {n_consistent}")
        if historicalref:
            print(aux.pinfo(f" Sector rows -- similar (same total, diff. pattern): ") + f"{n_similar}")
        print((aux.pinfo if n_different == 0 else aux.pwarn)(f" Sector rows -- different:               ") + f"{n_different}")
        print(aux.pinfo(f" Sector rows -- only in A / only in B:   ") + f"{n_only_a} / {n_only_b}")
        if group_counts:
            # Per-group (anthro/aviation/bburning) roll-up: a group is
            # "DIFFERENT" only if a sector present on *both* sides actually
            # disagrees (known/excused rows never reach group_counts, since
            # they're skipped before the per-sector counting above) --
            # only_a/only_b (a species/sector present on just one side) is
            # coverage, not a value disagreement, and is expected/inherent
            # when comparing historical against a future scenario (the two
            # species lists were never going to be 100% the same to begin
            # with) -- shown alongside the verdict for visibility, but
            # doesn't drive it. Gives a quick "do the shared values agree"
            # answer without scrolling back through every per-sector line.
            print(aux.pinfo(f" Per-group verdict:"))
            for group in sorted(group_counts, key=lambda g: {"anthro": 0, "aviation": 1, "bburning": 2}.get(g, 9)):
                s = group_counts[group]
                is_different = s["different"] > 0
                verdict = "DIFFERENT" if is_different else "consistent"
                color = aux.pwarn if is_different else aux.pgood
                similar_part = f", similar={s['similar']}" if historicalref else ""
                print(color(f"   {group.upper():<10} {verdict:<10}")
                      + f" (identical={s['identical']}, consistent={s['consistent']}{similar_part}, "
                        f"different={s['different']}, only_in_A={s['only_a']}, only_in_B={s['only_b']})")
        if biggest_diffs:
            print(aux.pinfo(f" Largest annual-total (Tg) diffs:"))
            for diff, label, val_a, val_b in sorted(biggest_diffs, reverse=True)[:10]:
                print(aux.pinfo(f"   {diff:.6g} Tg  ") + f"{label}  (A={val_a:.6g}, B={val_b:.6g})")
        print(aux.pshow(" ------------------------------------------------------------------"))
        print(aux.pinfo(
            f" Full detail behind the summary above (every species/sector/year row,\n"
            f" not just what's printed) was written to {dest_root}/:\n"
            f"   diff_stats_<group>_<year>.csv  -- Tg totals per sector, monthly\n"
            f"                                     breakdown, and A-vs-B diffs\n"
            f"   diff_raw_<group>_<year>.csv    -- raw-field max/mean/relative abs diff,\n"
            f"                                     consistent flag, and whole-file MD5\n"
            f"                                     identity per sector\n"))

        if historicalref:
            _print_known_diffs(known_file_diffs, known_sector_diffs)

    finally:
        for tmp_dir in (tmp_a, tmp_b, tmp_fldint):
            if keep:
                print(aux.pinfo(f" Kept extracted files at {tmp_dir}"))
            else:
                shutil.rmtree(tmp_dir, ignore_errors=True)

