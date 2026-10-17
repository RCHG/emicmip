#!/usr/bin/env python3
# ╭────────────────────────────────────────────────────────────────────────────╮
# │ validate_tar.py                                       (updated 2026-08)    │
# │                                                                            │
# │ Author:  Ramiro Checa-Garcia (KNMI)                                        │
# │ Purpose: Recreate emissions_stats CSVs from an archived tar/tgz of already │
# │          processed NetCDF files, to compare across tool versions/runs      │
# │ LLMs: as explained in other modules validate is designed, reviewed and     │ 
# │       and evaluated by developer but many functions here are rewritten     │
# │       implementations of AI.                                               │
# ╰────────────────────────────────────────────────────────────────────────────╯

import os
import re
import shutil
import tarfile
import tempfile
import xarray as xr

import lib.aux as aux
import lib.emissions_stats as emissions_stats

# Final nc filenames follow: {tag}_{resol}_{subset_suffix}_{species}_{year}.nc
# e.g. CMIP7hist-2025-04-18d_05x05_anthro-surf_BC_2015.nc  (see store_output() in
# lib/cmip_process.py). None of tag/resol/subset_suffix/species contain "_" in any
# shipped config, so this is unambiguous.
FNAME_RE = re.compile(r"^(?P<tag>.+)_(?P<resol>[^_]+)_(?P<suffix>[^_]+)_(?P<species>[^_]+)_(?P<year>\d{4})\.nc$")

# Fixed suffix -> group mapping, mirroring how cmip_preemis calls process_group()
# for each shipped config. Kept as an
# explicit table (not derived from the nc files) since the group only affects the
# CSV filename, not any computed value.
GROUP_BY_SUFFIX = {
    "anthro-air": "aviation",
    "bburning":   "bburning",
}

# subset_suffix names used by older tool versions, mapped to the suffix the
# current tool writes for the same subset. Applied in parse_nc_files() before
# anything else touches the suffix, so an old archive's files line up with a
# current one's under the same (species, suffix, year) key -- otherwise
# compare_tars() (which joins on that key) would treat e.g. an old archive's
# "bb4-2-0" files and a new archive's "bburning" files as two disjoint
# subsets that each look 100% missing from the other archive, rather than
# the same data under its old vs new name.
LEGACY_SUFFIX_ALIASES = {
    "bb4-2-0": "bburning",
}


def group_for_suffix(suffix: str, verbose: bool = False) -> str:
    """Map a subset_suffix (e.g. "anthro-surf") to its CSV group name.

    Args:
        suffix: subset_suffix parsed from a final nc filename
        verbose: print info steps

    Returns:
        The group name ("anthro", "aviation", "bburning") for known suffixes.
        For an unrecognized suffix, prints a warning and returns the suffix
        itself, so it lands in a clearly separate `emissions_<suffix>_<year>.csv`
        rather than silently being folded into the "anthro" group's CSV.
    """
    if suffix in GROUP_BY_SUFFIX:
        return GROUP_BY_SUFFIX[suffix]
    if suffix.startswith("anthro"):
        return "anthro"
    print(aux.pwarn(f"  > [validate] Warning: unrecognized subset suffix '{suffix}', "
                     f"cannot map it to a known group (anthro/aviation/bburning)."))
    print(aux.pwarn(f"    > Writing its rows to emissions_{suffix}_<year>.csv instead of "
                     f"guessing a group, so this is visible rather than silently wrong."))
    return suffix


def list_sector_variables(ncfile: str) -> list[str]:
    """List the sector/emission variables actually present in a final nc file.

    A final file produced by store_output()/aggregate_sectors()/scale_sector()
    only ever contains: coordinate variables (lat, lon, time -- auto-promoted to
    xarray coords), bounds variables (*_bnds), and the sector variables
    themselves (raw sectors, aggregate targets, scaling targets). So filtering
    data_vars to "has a time dimension, not a bounds variable" recovers exactly
    the sector set a live run would have reported for this file -- with no
    dependency on the toml config that produced it.

    Args:
        ncfile: path to a final, fully processed NetCDF file

    Returns:
        List of sector/variable names.
    """
    ds = xr.open_dataset(ncfile)
    svars = [v for v in ds.data_vars if "time" in ds[v].dims and "bnds" not in v.lower()]
    ds.close()
    return svars


def list_nc_members(tar: tarfile.TarFile) -> dict[str, tarfile.TarInfo]:
    """List the .nc members of an already-open tar, without extracting them.

    `tar.getmembers()` reads the archive's index (already necessary before
    extracting anything), but doesn't touch member contents -- so this is
    fast even for a large tar. Lets a caller comparing two archives (see
    compare_tars) decide which members are actually worth extracting, and in
    what order, before paying for any extraction at all.

    Args:
        tar: an already-open tarfile.TarFile (caller owns open/close)

    Returns:
        Dict of member name -> TarInfo, in tar order.
    """
    return {m.name: m for m in tar.getmembers() if m.name.endswith(".nc")}


def extract_member(tar: tarfile.TarFile, member: tarfile.TarInfo, dest_dir: str) -> str:
    """Extract one member from an already-open tar into dest_dir.

    Args:
        tar: an already-open tarfile.TarFile matching `member`
        member: the TarInfo to extract (see list_nc_members)
        dest_dir: directory to extract into (created if needed)

    Returns:
        Path to the extracted file.
    """
    # extractall/extract's `filter=` kwarg needs Python >= 3.12; setting the
    # instance attribute instead works from 3.11.4+ (the security backport)
    # through 3.12+, and is a silent no-op filter set on older 3.11.x patch
    # releases that predate the backport.
    if hasattr(tar, "extraction_filter"):
        tar.extraction_filter = tarfile.data_filter
    os.makedirs(dest_dir, exist_ok=True)
    tar.extract(member, dest_dir)
    return os.path.join(dest_dir, member.name)


def extract_tar(tar_path: str, dest_dir: str, verbose: bool = False) -> list[str]:
    """Extract every .nc member of a tar/tgz archive into dest_dir.

    Args:
        tar_path: path to the .tgz/.tar.gz/.tar archive
        dest_dir: directory to extract into (created if needed)
        verbose: print info steps

    Returns:
        Paths of the extracted .nc files.
    """
    with tarfile.open(tar_path, "r:*") as tar:
        # extractall's `filter=` kwarg needs Python >= 3.12; setting the
        # instance attribute instead works from 3.11.4+ (the security
        # backport) through 3.12+, and is a silent no-op filter set on
        # older 3.11.x patch releases that predate the backport.
        if hasattr(tar, "extraction_filter"):
            tar.extraction_filter = tarfile.data_filter
        members = [m for m in tar.getmembers() if m.name.endswith(".nc")]
        if verbose:
            print(aux.pinfo(f"  > [validate] Extracting {len(members)} .nc files from {tar_path}"))
        tar.extractall(dest_dir, members=members)
    return [os.path.join(dest_dir, m.name) for m in members]


def parse_nc_files(ncfiles: list[str], verbose: bool = False,
                    apply_legacy_aliases: bool = False) -> tuple[dict[tuple[str, str, str], str], str | None]:
    """Parse final nc filenames into a lookup keyed by (species, suffix, year).

    Args:
        ncfiles: paths of extracted final nc files
        verbose: print info steps
        apply_legacy_aliases: normalize a suffix found in LEGACY_SUFFIX_ALIASES
            to its current name before building the key (see
            compare_tars' legacyref/legacyboth). Off by default: with no
            legacy flag given, a run is expected to use consistent current
            naming throughout, so an old suffix like "bb4-2-0" is left as
            itself and, downstream, group_for_suffix() will warn about it
            rather than silently reinterpreting it.

    Returns:
        (files_by_key, inferred_tag): files_by_key maps (species, suffix,
        year) -> ncfile path (files not matching FNAME_RE are skipped, with
        a warning); inferred_tag is the first parsed file's tag (in sorted
        order), or None if nothing matched.
    """
    files_by_key: dict[tuple[str, str, str], str] = {}
    inferred_tag = None
    reported_aliases = set()
    for ncfile in sorted(ncfiles):
        base = os.path.basename(ncfile)
        m = FNAME_RE.match(base)
        if m is None:
            print(aux.pwarn(f"  > [validate] skipping (name doesn't match the expected pattern): {base}"))
            continue
        tag, suffix, species, year = m.group("tag"), m.group("suffix"), m.group("species"), m.group("year")
        if apply_legacy_aliases and suffix in LEGACY_SUFFIX_ALIASES:
            canonical = LEGACY_SUFFIX_ALIASES[suffix]
            if suffix not in reported_aliases:
                reported_aliases.add(suffix)
                print(aux.pinfo(f"  > [validate] treating legacy suffix '{suffix}' as '{canonical}'"))
            suffix = canonical
        if inferred_tag is None:
            inferred_tag = tag
        files_by_key[(species, suffix, year)] = ncfile
    return files_by_key, inferred_tag


def build_stats_from_tar(tar_path: str, outdir: str = "outs/validation", name: str | None = None,
                          verbose: bool = False, keep: bool = False) -> None:
    """Recreate emissions_stats CSVs from an archived tar/tgz of final nc files.

    Extracts every .nc member, parses each filename to recover species/dataset
    (subset_suffix)/year, computes the same per-sector monthly/annual Tg rows a
    live cmip_preemis run would have written (see list_sector_variables and
    compute_file_stats_rows), and writes them to
    `<outdir>/<name>/emissions_<group>_<year>.csv` -- grouped exactly like
    write_group_stats(), but only to this one location (there is no live
    `outpath` to colocate a copy with).

    Args:
        tar_path: path to the .tgz/.tar.gz/.tar archive
        outdir: base directory for the recreated CSVs
        name: dataset-name subdirectory; if None, inferred from the tag
            embedded in the nc filenames (the first .nc file's tag, in sorted
            order)
        verbose: print info steps
        keep: keep the extracted files (in a temp dir) instead of removing
            them once done
    """
    if not os.path.isfile(tar_path):
        print(aux.perror(f"\n{tar_path} not found."))
        return

    tmp_dir = tempfile.mkdtemp(prefix="cmip_validate_", dir=aux.default_tmp_root())
    tmp_fldint = os.path.join(tmp_dir, "_fldint")

    try:
        ncfiles = extract_tar(tar_path, tmp_dir, verbose=verbose)
        if not ncfiles:
            print(aux.pwarn(f"No .nc files found inside {tar_path}"))
            return

        files_by_key, inferred_name = parse_nc_files(ncfiles, verbose=verbose)
        if not files_by_key:
            print(aux.pwarn(f"No recognizable final emission nc files found inside {tar_path}"))
            return

        stats_rows_by_group: dict[str, list[dict]] = {}

        for (species, suffix, year), ncfile in files_by_key.items():
            base = os.path.basename(ncfile)
            group = group_for_suffix(suffix, verbose=verbose)
            sector_vars = list_sector_variables(ncfile)
            rows = emissions_stats.compute_file_stats_rows(
                ncfile, sector_vars, species, suffix, year, tmp_fldint, verbose=verbose)

            stats_rows_by_group.setdefault(group, []).extend(rows)
            if verbose:
                print(aux.pinfo(f"  > [validate] {base}: {len(rows)} sector rows -> group '{group}'"))

        dname = name if name is not None else inferred_name
        dest_root = os.path.join(outdir, dname)

        for group, rows in stats_rows_by_group.items():
            by_year: dict[str, list[dict]] = {}
            for row in rows:
                by_year.setdefault(row["year"], []).append(row)
            for year, yrows in by_year.items():
                csv_path = os.path.join(dest_root, f"emissions_{group}_{year}.csv")
                emissions_stats.write_year_csv(yrows, csv_path)
                print(aux.pshow(f"  > [validate] wrote {csv_path}"))

    finally:
        if keep:
            print(aux.pinfo(f" Kept extracted files at {tmp_dir}"))
        else:
            shutil.rmtree(tmp_dir, ignore_errors=True)
