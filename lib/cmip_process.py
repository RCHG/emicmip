#!/usr/bin/env python3
# ╭────────────────────────────────────────────────────────────────────────────╮
# │ cmip_process.py                                        (updated 2025-07)   │
# │                                                                            │
# │ Author:  Ramiro Checa-Garcia (KNMI)                                        │
# │ Purpose: General methods for CMIP emissions preprocessing                  │
# │                                                                            │
# │ Info: fully inherit by oifs-emis-spec previous tool from same author       │
# │       changes to cover both historical and scenarios improved with LLMs    │
# │       assistance.                                                          │
# ╰────────────────────────────────────────────────────────────────────────────╯

import os
import re
import sys
import shutil
import subprocess
import lib.aux as aux
import lib.emissions_stats as emissions_stats

#-------------------------------------------------------------------------------
# Raw files not found during a run
#
# process_subset() records every (group suffix, subset, species, period) whose
# raw file could not be found, so cmip_preemis can print one summary at the end
# of the run (print_missing_raw_summary) instead of the gaps being noticed only
# by inspecting the tars. Module-level because the records are collected deep
# inside process_group/process_subset, whose return values the callers already
# use for other things.

MISSING_RAW: list[tuple[str, str, str, str]] = []

# (suffix, species) built by a [[derivespecies]] rule in this run (see derive_species):
# their raw files are expected to be missing, so the summary says so.
DERIVED: set[tuple[str, str]] = set()

# Years missing from a raw file's time axis that were interpolated in this run
# (see extract_or_interpolate_year): (group suffix, species, year, y0, y1).
INTERPOLATED: list[tuple[str, str, str, int, int]] = []

# Years present in each raw file's time axis, read once per file (cdo showyear).
_RAW_YEARS: dict[str, set[int] | None] = {}


def print_missing_raw_summary() -> None:
    """Print the species/periods whose raw file was not found in this run
    (see MISSING_RAW); prints a one-line confirmation if there were none."""
    if not MISSING_RAW:
        print(aux.pgood("\n All configured species/periods had a raw file."))
        return
    print(aux.pwarn(f"\n ------ Raw files NOT found ({len(MISSING_RAW)} species/periods) -------------"))
    by_species: dict[tuple[str, str, str], list[str]] = {}
    for suffix, subset, species, syear in MISSING_RAW:
        by_species.setdefault((suffix, subset, species), []).append(syear)
    for (suffix, subset, species), spans in sorted(by_species.items()):
        line = f"   {suffix:<14} {subset:<32} {species:<20} {', '.join(spans)}"
        if (suffix, species) in DERIVED:
            print(aux.pinfo(line + "  -> derived instead ([[derivespecies]] rule)"))
        else:
            print(aux.pwarn(line))
    print(aux.pwarn(" These species/periods are not in the output (unless derived). "
                    "Check the raw folder or the config."))


def print_interpolated_summary() -> None:
    """Print the years built by interpolation in this run (see INTERPOLATED);
    nothing if there were none."""
    if not INTERPOLATED:
        return
    print(aux.pinfo(f"\n ------ Years interpolated (linear, month by month) ------------------"))
    by_year: dict[tuple[str, int, int], dict[str, list[str]]] = {}
    for suffix, species, yr, y0, y1 in INTERPOLATED:
        by_year.setdefault((yr, y0, y1), {}).setdefault(suffix, []).append(species)
    for (yr, y0, y1), by_suffix in sorted(by_year.items()):
        parts = ", ".join(f"{suffix}: {len(sp)} species" for suffix, sp in sorted(by_suffix.items()))
        print(aux.pinfo(f"   {yr}  from {y0} and {y1}   {parts}"))
    print(aux.pinfo(" Interpolated as input4MIPs suggests (global attribute 'interpolated'); "
                    "\"(forced)\" = --forceinterp validation, the raw file has that year."))

#-------------------------------------------------------------------------------
# General helper methods
#

def run_cmd(cmd: str, verbose: bool = False) -> None:
    """Run a shell command, only surfacing its output if verbose or it failed.

    Routine cdo/nco chatter (progress lines, plus benign library diagnostics
    such as HDF5 probing an output file that doesn't exist yet on first
    write) is noisy but harmless, so a normal run stays quiet. If the
    command exits non-zero, the captured output is printed regardless of
    verbose, so real failures are never silently swallowed.
    """
    if verbose:
        os.system(cmd)
        return
    result = subprocess.run(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    if result.returncode != 0:
        print(aux.pwarn(f"    Command failed (exit {result.returncode}): {cmd}"))
        if result.stdout:
            print(result.stdout)

def get_varname_from_file(filename: str) -> str:
    """Derive the expected NetCDF variable name from a raw filename.

    BC-em-anthro_... -> BC_em_anthro
    NMVOC-C2H2-em-anthro_... -> NMVOC_C2H2_em_anthro

    Args:
        filename: raw input NetCDF filename or path

    Returns:
        Guessed variable name (the part before the first "_", with "-" -> "_").
    """
    basename = os.path.splitext(os.path.basename(filename))[0]
    name_part = basename.split("_")[0]
    return name_part.replace("-", "_")

def get_varname_from_netcdf(nc_file: str) -> str | None:
    """Read the actual first variable name inside a NetCDF file via `cdo showvar`.

    Args:
        nc_file: path to the NetCDF file

    Returns:
        The first variable name found, or None if it couldn't be read
        (missing file, cdo not available, timeout, ...).
    """
    try:
        result = subprocess.run(['cdo', 'showvar', nc_file], 
                              capture_output=True, text=True, timeout=30)
        # Output format: "varname\n" or "varname1 varname2\n"
        varname = result.stdout.strip().split()[0]
        return varname
    except (subprocess.TimeoutExpired, FileNotFoundError, IndexError, OSError):
        return None

def validate_varname(filename_varname: str, nc_file: str, verbose: bool = False) -> str:
    """Validate that a filename-derived varname matches the actual NetCDF variable.

    Compares the varname derived from the filename with the actual variable
    inside the NetCDF file (via get_varname_from_netcdf).

    Args:
        filename_varname: varname guessed from the filename (see
            get_varname_from_file)
        nc_file: path to the NetCDF file to check against
        verbose: print info steps

    Returns:
        The varname to use: the NetCDF's actual variable name if it differs
        from `filename_varname` (or if the NetCDF could not be read, falls
        back to `filename_varname`), otherwise `filename_varname` unchanged.
    """
    nc_varname = get_varname_from_netcdf(nc_file)
    
    if nc_varname is None:
        if verbose:
            print(aux.pwarn(f"    Could not read variable name from {nc_file}, using filename varname"))
        return filename_varname
    
    if filename_varname != nc_varname:
        if verbose:
            print(aux.pwarn(f"    Warning: varname mismatch!"))
            print(aux.pwarn(f"      Filename suggests: {filename_varname}"))
            print(aux.pwarn(f"      NetCDF contains:  {nc_varname}"))
            print(aux.pinfo(f"      Using NetCDF varname: {nc_varname}"))
        return nc_varname
    
    if verbose:
        print(aux.pinfo(f"    Varname validated: {filename_varname}"))
    return filename_varname

def get_sector_count_from_netcdf(nc_file: str) -> int | None:
    """Read the size of the "sector" dimension from a NetCDF file, via ncdump.

    Args:
        nc_file: path to the NetCDF file

    Returns:
        Number of sectors: the "sector" dimension size if present, 1 if the
        file has no such dimension (single-sector file), or None if it
        couldn't be determined (missing file, ncdump failure, ...).
    """
    try:
        cmd = f"ncdump -h {nc_file} | sed -n 's/.*sector = \\([0-9]*\\).*/\\1/p'"
        output = subprocess.check_output(cmd, shell=True).decode().strip()
        nsector = int(output) if output else 1  # empty means one single sector no-dimension
        return nsector
    except (subprocess.TimeoutExpired, FileNotFoundError, IndexError, OSError):
        return None

def validate_sector_count(nc_file: str, expected_sectors: list[str], verbose: bool = False) -> bool:
    """Validate that number of sectors in NetCDF matches config specification.

    Args:
        nc_file: path to NetCDF file
        expected_sectors: list of sector names from config (e.g., ["AGR", "ENE", ...])
        verbose: print info steps

    Returns:
        True if validation passes (including when the sector count couldn't
        be read, or the file has more sectors than expected), False if the
        file has fewer sectors than expected (in which case a fatal-mismatch
        message is printed unconditionally, regardless of `verbose`).
    """
    nc_sector_count = get_sector_count_from_netcdf(nc_file)
    expected_count = len(expected_sectors)
    
    if nc_sector_count is None:
        if verbose:
            print(aux.pwarn(f"    Could not read sector count from {nc_file}"))
        return True  # Continue processing, assume OK
    
    if nc_sector_count != expected_count:
        if nc_sector_count > expected_count:
            if verbose:
                print(aux.pwarn(f"    Warning: sector count mismatch!"))
                print(aux.pwarn(f"      Config specifies: {expected_count} sectors {expected_sectors}"))
                print(aux.pwarn(f"      NetCDF contains: {nc_sector_count} sectors"))
                print(aux.pwarn(f"    Warning: we are using the first set of sectors"))
            return True
        else:
            print(aux.perror(f"    Fatal: sector count mismatch in {nc_file}"))
            print(aux.perror(f"      Config specifies: {expected_count} sectors {expected_sectors}"))
            print(aux.perror(f"      NetCDF contains: {nc_sector_count} sectors (fewer than expected)"))
            return False
    
    if verbose:
        print(aux.pinfo(f"    Sector count validated: {nc_sector_count} sectors"))
    return True

def get_species_filename(species: str, species_filename_map: dict[str, str] | None) -> str:
    """Map a config species key to the token used in output filenames.

    BC -> BC
    VOC01-alcohols -> VOC01 (from map)
    NMVOC-C2H2 -> C2H2 (from map)

    Args:
        species: species key as it appears in the config's species list
        species_filename_map: optional dict mapping species key -> filename
            token, for species whose on-disk name differs from the config key

    Returns:
        `species_filename_map[species]` if present, otherwise `species` unchanged.
    """
    if species_filename_map and species in species_filename_map:
        return species_filename_map[species]
    return species

def build_raw_path(grawpath: str, species: str, subset_key: str | None, versions: list[str], syear: str, verbose: bool = False) -> str | None:
    """Construct the raw input file path, trying each version in order.

    subset_key="none" -> {species}_{version}_{syear}.nc
    subset_key="em-anthro" -> {species}-{subset_key}_{version}_{syear}.nc

    Args:
        grawpath: path to the raw input data directory for this group
        species: species key as it appears in the config's species list
        subset_key: subset key from config (e.g. "em-anthro"), or "none"/None
            for datasets with no subset in the filename
        versions: version strings to try, in order (see process_group's
            version_list)
        syear: year-interval string as it appears in the raw filename (e.g.
            "175001-179912")
        verbose: print info steps

    Returns:
        Path to the first existing raw file found across `versions`, or None
        if none of them exist on disk.
    """
    for v in versions:
        if subset_key is None or subset_key == "none":
            fname = f"{species}_{v}_{syear}.nc"
        else:
            fname = f"{species}-{subset_key}_{v}_{syear}.nc"
        path = os.path.join(grawpath, fname)
        if os.path.isfile(path):
            if verbose:
                print(f"File for {species} subset={subset_key} found as:\n      " + aux.ppath(f"{path}"))
            return path
    if verbose:
        print(aux.pwarn(f"Warning: no file found for {species} subset={subset_key} years={syear}"))
    return None

def extract_year(raw_file: str, year: int | str, output_file: str, verbose: bool = False) -> None:
    """Extract a single year from a multi-year raw file, via `cdo selyear`.

    Args:
        raw_file: path to the multi-year raw input NetCDF file
        year: year to extract
        output_file: path to write the single-year NetCDF to
        verbose: print info steps
    """
    cdo_cmd = f"cdo -S -O -selyear,{year} {raw_file} {output_file}"
    run_cmd(cdo_cmd, verbose)


def _cdo_lines(args: list[str]) -> list[str] | None:
    """Output words of a quiet cdo query (showyear, ntime), None if it failed."""
    try:
        res = subprocess.run(["cdo", "-s"] + args, capture_output=True, text=True, timeout=600)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return res.stdout.split() if res.returncode == 0 else None


def raw_years(raw_file: str) -> set[int] | None:
    """Years present in a raw file's time axis (`cdo showyear`), cached per
    file; None if cdo could not tell (then the year is just selected as before)."""
    if raw_file not in _RAW_YEARS:
        words = _cdo_lines(["showyear", raw_file])
        _RAW_YEARS[raw_file] = {int(w) for w in words if w.isdigit()} if words else None
    return _RAW_YEARS[raw_file]


def _ntime(nc_file: str) -> int | None:
    words = _cdo_lines(["ntime", nc_file])
    return int(words[0]) if words and words[0].isdigit() else None


def extract_or_interpolate_year(raw_file: str, year: int | str, output_file: str, propath: str,
                                interpolate: bool = False, force: bool = False,
                                verbose: bool = False) -> tuple[int, int] | str | None:
    """Write the 12 months of `year` to `output_file`: read from the raw file
    if its time axis holds that year, otherwise (only with `interpolate`)
    interpolate it linearly, month by month, from the nearest previous and
    next years of the SAME file -- as input4MIPs suggests for the ScenarioMIP
    data (annual to 2025, then every 5 years). Every month, sector, level and
    grid cell independently; never extrapolated.

        F(year, m) = F(y0, m) + (year - y0) / (y1 - y0) * (F(y1, m) - F(y0, m))   (cdo intyear)

    Missing values are set to 0 in y0 and y1 *before* interpolating, otherwise
    a cell present in only one of the two years would end up 0 instead of a
    blend (cdo intyear gives a missing value where either input is missing).

    Args:
        raw_file: raw input file (multi-year), found for the period of `year`
        year: year to write
        output_file: 12-month file to write
        propath: directory for the temporary y0/y1 files
        interpolate: interpolate_years of the group config (a permission:
            a year present in the file is always read as is)
        force: validation only (--forceinterp): interpolate even if the year
            is present, from the nearest OTHER years of the file
        verbose: print info steps

    Returns:
        None if the year was read from the file, (y0, y1) if it was
        interpolated, or a short reason (str) if it is not available.
    """
    yr = int(year)
    avail = raw_years(raw_file)
    if avail is None or (yr in avail and not force):
        extract_year(raw_file, yr, output_file, verbose=verbose)
        return None
    if not (interpolate or force):
        return "not in the file (interpolate_years is off)"
    before = [y for y in avail if y < yr]
    after = [y for y in avail if y > yr]
    if not before or not after:
        return f"not in the file ({min(avail)}-{max(avail)}), no year on both sides to interpolate"
    y0, y1 = max(before), min(after)

    stem = os.path.join(propath, os.path.splitext(os.path.basename(output_file))[0])
    f0, f1, base = f"{stem}_y0_{y0}.nc", f"{stem}_y1_{y1}.nc", f"{stem}_int_"
    if verbose:
        print(aux.pinfo(f"      > {yr} not in raw file: interpolating from {y0} and {y1}"))
    run_cmd(f"cdo -s -O -setmisstoc,0 -selyear,{y0} {raw_file} {f0}", verbose)
    run_cmd(f"cdo -s -O -setmisstoc,0 -selyear,{y1} {raw_file} {f1}", verbose)
    try:
        for f, y in ((f0, y0), (f1, y1)):
            if _ntime(f) != 12:
                return f"year {y} of the file does not have 12 months, cannot interpolate"
        run_cmd(f"cdo -s -O intyear,{yr} {f0} {f1} {base}", verbose)
        made = [os.path.join(propath, f) for f in os.listdir(propath)
                if f.startswith(os.path.basename(base) + f"{yr:04d}")]
        if not made or _ntime(made[0]) != 12:
            return "cdo intyear failed"
        shutil.move(made[0], output_file)
    finally:
        for f in (f0, f1):
            if os.path.isfile(f):
                os.remove(f)
    return (y0, y1)

def split_sectors(input_file: str, sectors: list[str], output_file: str, varname: str | None = None, verbose: bool = False) -> None:
    """Split a sector dimension into one variable per sector.

    Input:  var(sector, time, lat, lon)
    Output: varAGR(time,lat,lon), varENE(time,lat,lon), ...

    Args:
        input_file: input NetCDF file with sector dimension
        sectors: list of sector names, in the dimension's index order
        output_file: output file path
        varname: variable name inside NetCDF (if None, extracted from filename)
        verbose: print info steps
    """
    if varname is None:
        varname = get_varname_from_file(input_file)
    for i, sector in enumerate(sectors):
        temp = f"{output_file}_temp_{sector}"
        if verbose:
            print(f"    Extracting sector {i} ({sector}) as variable {sector}")
        
        # Extract sector by index
        cmd_ncks_get = f"ncks -O -d sector,{i} {input_file} {temp}"
        run_cmd(cmd_ncks_get, verbose)

        # Collapse sector dimension
        cmd_ncwa = f"ncwa -O -a sector {temp} {temp}"
        run_cmd(cmd_ncwa, verbose)

        # Remove sector coordinate variables
        cmd_ncks_del = f"ncks -O -x -v sector,sector_bnds {temp} {temp}"
        run_cmd(cmd_ncks_del, verbose)

        # Rename variable to sector name
        cmd_ncrename = f"ncrename -O -v {varname},{sector} {temp} {temp}"
        run_cmd(cmd_ncrename, verbose)

        # Append to output file
        if i == 0:
            shutil.copy(temp, output_file)
        else:
            cmd_ncks_append = f"ncks -A {temp} {output_file}"
            run_cmd(cmd_ncks_append, verbose)
        
        os.remove(temp)

def rename_single_sector(input_file: str, sector_name: str, output_file: str, varname: str | None = None, verbose: bool = False) -> None:
    """Single-sector case: rename the NetCDF's variable to the sector name.

    Args:
        input_file: input NetCDF file
        sector_name: target sector name (the file's only sector)
        output_file: output file path
        varname: variable name inside NetCDF (if None, extracted from filename)
        verbose: print info steps
    """
    if varname is None:
        varname = get_varname_from_file(input_file)
    if verbose:
        print(f"    Renaming variable {varname} to {sector_name}")
    cmd_cdorename = f"cdo chname,{varname},{sector_name} -setmisstoc,0 {input_file} {output_file}"
    run_cmd(cmd_cdorename, verbose)

def store_output(input_file: str, datasetname: str, resol: str, subset_suffix: str,
                 species_filename: str, year: int | str, outpath: str) -> str:
    """Copy a processed file to its final location, with standard naming.

    Output: {datasetname}_{resol}_{subset_suffix}_{species_filename}_{year}.nc

    Args:
        input_file: path to the fully processed (sectors split/aggregated)
            temporary NetCDF file
        datasetname: dataset name for output filenames (datainfo["outputname"])
        resol: resolution string for filenames (e.g., "05x05")
        subset_suffix: subset's filename suffix (e.g., "anthro-surf")
        species_filename: on-disk species token (see get_species_filename)
        year: year of the data being stored
        outpath: directory to copy the final file into

    Returns:
        Path to the stored final file.
    """
    fname = f"{datasetname}_{resol}_{subset_suffix}_{species_filename}_{year}.nc"
    dest = os.path.join(outpath, fname)
    shutil.copy(input_file, dest)
    print(aux.pwarn(f" Stored as: {dest}"))
    return dest

#-------------------------------------------------------------------------------
# Sector aggregation methods
#

def validate_aggregate_config(sectors: list[str], aggregate_config: list[dict] | None, verbose: bool = False) -> bool:
    """Validate that aggregation configuration is valid.

    Verifies that all sectors in 'from' exist in the sectors list, and that
    there are no duplicate aggregate targets.

    Args:
        sectors: list of sector names from config
        aggregate_config: list of aggregation rules [{"target": "total", "from": [...]}]
        verbose: print info steps

    Returns:
        True if validation passes, False if invalid (in which case a
        warning has already been printed for each problem found).
    """
    if aggregate_config is None:
        return True
    
    valid = True
    for rule in aggregate_config:
        target = rule["target"]
        source_sectors = rule["from"]
        
        for sector in source_sectors:
            if sector not in sectors:
                print(aux.pwarn(f"    Warning: sector '{sector}' in aggregate rule '{target}' not found in sectors list {sectors}"))
                valid = False
        
        # Check for duplicate targets
        target_count = sum(1 for r in aggregate_config if r["target"] == target)
        if target_count > 1:
            print(aux.pwarn(f"    Warning: duplicate aggregate target '{target}'"))
            valid = False

    return valid

def validate_derive_config(group_config: dict, derive_config: list[dict] | None, verbose: bool = False) -> bool:
    """Validate the group's [[derivespecies]] rules (see derive_species).

    Every rule needs a `target`, a `suffix` used by one of the group's subsets,
    and a non-empty `from` list whose names are output species names (after
    species_filename_map) of subsets with that same suffix.

    Returns:
        True if valid, False otherwise (a warning is printed for each problem).
    """
    if not derive_config:
        return True
    valid = True
    outputs: dict[str, set[str]] = {}
    for sub in group_config["subsets"].values():
        fmap = sub.get("species_filename_map") or {}
        outputs.setdefault(sub["suffix"], set()).update(fmap.get(sp, sp) for sp in sub["species"])
    for rule in derive_config:
        target, suffix, sources = rule.get("target"), rule.get("suffix"), rule.get("from") or []
        if not target or not suffix or not sources:
            print(aux.pwarn(f"    Warning: derivespecies rule {rule} needs 'target', 'suffix' and a non-empty 'from'"))
            valid = False
            continue
        if suffix not in outputs:
            print(aux.pwarn(f"    Warning: derivespecies rule '{target}': suffix '{suffix}' is not used by any subset"))
            valid = False
            continue
        unknown = [s for s in sources if s not in outputs[suffix]]
        if unknown:
            print(aux.pwarn(f"    Warning: derivespecies rule '{target}': {unknown} are not species of suffix '{suffix}'"))
            valid = False
    return valid


def derive_species(rule: dict, created_lfiles: list[str], outpath: str, resol: str, datasetname: str,
                   stats_sectors: list[str], propath: str, overwrite: bool = False,
                   verbose: bool = False) -> tuple[list[str], list[dict]]:
    """Build a species as the sum of other species already produced ([[derivespecies]] rule).

    For every year in which the final files of *all* `from` species exist
    (among `created_lfiles`), sums them sector by sector with `cdo enssum`
    (same sector variables and grid in every file) into
    {datasetname}_{resol}_{suffix}_{target}_{year}.nc, and tags it with a
    `derived_from` global attribute so it is not mistaken for a raw dataset.
    With `only_if_missing = true` (default), years in which the target was
    produced from its own raw file are left alone.

    Used for the bulk anthropogenic NMVOC of CEDS (CMIP7 historical), which is
    not published: the 23 speciated VOCs add up exactly to the bulk NMVOC (checked
    on the IIASA ScenarioMIP data, where both exist: ratio 1.0000).

    Returns:
        (files, stats_rows) of the derived files (created or already found).
    """
    target, suffix, sources = rule["target"], rule["suffix"], rule["from"]
    only_if_missing = rule.get("only_if_missing", True)

    def final_name(species: str, yr: str) -> str:
        return os.path.join(outpath, f"{datasetname}_{resol}_{suffix}_{species}_{yr}.nc")

    created = set(created_lfiles)
    years = sorted({os.path.splitext(f)[0].rsplit("_", 1)[-1] for f in created_lfiles
                    if os.path.basename(f).startswith(f"{datasetname}_{resol}_{suffix}_")})
    files, rows = [], []
    for yr in years:
        out = final_name(target, yr)
        if only_if_missing and out in created:
            continue                                  # produced from its own raw file
        missing = [s for s in sources if final_name(s, yr) not in created]
        if missing:
            print(aux.pwarn(f"    Warning: cannot derive {target} ({suffix}) for {yr}: "
                            f"{len(missing)} of {len(sources)} source species missing ({', '.join(missing[:5])}...)"))
            continue
        if os.path.isfile(out) and not overwrite:
            print(aux.pinfo(f"      > Found {out}, not overwriting"))
        else:
            if verbose:
                print(aux.pshow(f"      > [derive] {target} {yr} = sum of {len(sources)} species"))
            run_cmd(f"cdo -s -O enssum {' '.join(final_name(s, yr) for s in sources)} {out}", verbose)
            if not os.path.isfile(out):
                print(aux.pwarn(f"    Warning: derive {target} {yr} failed (cdo enssum)"))
                continue
            note = f"sum of {len(sources)} species ({sources[0]}..{sources[-1]}) by emicmip derivespecies rule"
            run_cmd(f'ncatted -O -h -a derived_from,global,o,c,"{note}" '
                    f'-a variable_id,global,o,c,"{target}" {out}', verbose)
        files.append(out)
        rows.extend(emissions_stats.compute_file_stats_rows(out, stats_sectors, target, suffix, yr, propath,
                                                            verbose=verbose))
    if files:
        DERIVED.add((suffix, target))
        print(aux.pinfo(f"    > [derive] {target} ({suffix}): {len(files)} year(s) as sum of {len(sources)} species"))
    return files, rows


def periods_for(group_config: dict, subset_config: dict, species: str) -> list[str]:
    """Raw-file periods searched for one species: the group's `years`, plus the
    `extra_years` periods its subset declares for that species (e.g. CEDS CH4
    and N2O aviation, cut as 197001-199912 instead of 195001-199912).

    Args:
        group_config: config dict of the group (uses "years")
        subset_config: config dict of the subset (uses "extra_years", optional)
        species: species key as in the subset's species list

    Returns:
        Periods sorted by start date, each once.
    """
    periods = list(group_config["years"])
    periods += [e["period"] for e in subset_config.get("extra_years", []) if species in e["species"]]
    return sorted(dict.fromkeys(periods), key=lambda p: p[:6])


def validate_extra_years(group: str, subset_key: str, subset_config: dict) -> None:
    """Check a subset's `extra_years`: a list of {period = "YYYYMM-YYYYMM",
    species = [...]}, with every species in the subset's species list.

    Raises:
        SystemExit: on a malformed entry
    """
    for entry in subset_config.get("extra_years", []):
        period, species = entry.get("period"), entry.get("species")
        if not (isinstance(period, str) and re.fullmatch(r"\d{6}-\d{6}", period)
                and isinstance(species, list) and species):
            print(aux.perror(f"Error: extra_years of [{group}.subsets.{subset_key}]: each entry must be "
                             f'{{ period = "YYYYMM-YYYYMM", species = [...] }}, got {entry!r}'))
            sys.exit(1)
        unknown = [s for s in species if s not in subset_config["species"]]
        if unknown:
            print(aux.perror(f"Error: extra_years of [{group}.subsets.{subset_key}], period {period}: "
                             f"{', '.join(unknown)} not in the subset's species"))
            sys.exit(1)


def check_sources(datainfo: dict, rawpaths: dict[str, str], years: list[str] | None = None) -> None:
    """One year, one file: before anything is processed, check that no year of
    a species is covered by two raw files (two periods that overlap, e.g. a
    main 197001-199912 file next to a -supplemental 195001-199912 one). The
    tool never chooses between them: the overlaps are listed and the run stops,
    so that one of each pair is moved aside (e.g. to an _unused/ folder).

    Only file names are looked at (as build_raw_path does). A missing file is
    not an error here: process_subset reports it and goes on.

    Args:
        datainfo: config dict for one CMIP version
        rawpaths: raw folder of each group to check, e.g. {"anthro": ...}
        years: requested years (None = all)

    Raises:
        SystemExit: if any overlap is found
    """
    version_prefix = "_".join([datainfo["origin"], datainfo["category"], datainfo["target_mip"]])
    overlaps = []
    for group, grawpath in rawpaths.items():
        group_config = datainfo[group]
        versions = [f"{version_prefix}_{v}_gn" for v in group_config["version"]]
        for subset_key, subset_config in group_config["subsets"].items():
            validate_extra_years(group, subset_key, subset_config)
            for species in subset_config["species"]:
                files_of_year: dict[str, list[str]] = {}
                for syear in periods_for(group_config, subset_config, species):
                    span = [str(a) for a in aux.get_list_years(syear)]
                    if years is not None:
                        span = [yy for yy in span if yy in years]
                    if not span:
                        continue
                    fnc = build_raw_path(grawpath, species, subset_key, versions, syear)
                    if fnc is not None:
                        for yy in span:
                            files_of_year.setdefault(yy, []).append(fnc)
                # one line per pair of files, with the years they share
                shared: dict[tuple[str, ...], list[str]] = {}
                for yy, files in files_of_year.items():
                    if len(files) > 1:
                        shared.setdefault(tuple(files), []).append(yy)
                for files, yys in shared.items():
                    overlaps.append((group, subset_key, species, yys, files))

    if not overlaps:
        print(aux.pgood(" Raw sources: one file per species and year."))
        return
    print(aux.perror(f"\n Raw sources: {len(overlaps)} case(s) of years covered by more than one file:"))
    for group, subset_key, species, yys, files in overlaps:
        span = yys[0] if len(yys) == 1 else f"{yys[0]}-{yys[-1]}"
        print(aux.pwarn(f"   {group}/{subset_key} {species} years {span}:"))
        for f in files:
            print(f"      {f}")
    print(aux.pwarn(" Nothing was processed. Keep one file of each case in the raw folder "
                    "(move the other aside, e.g. to _unused/) and run again."))
    sys.exit(1)


def validate_scaling_config(sectors: list[str], scaling_config: list[dict] | None, verbose: bool = False) -> bool:
    """Validate that scaling configuration is valid.

    Verifies that each rule's 'from' sector exists in the sectors list, that
    no rule's 'target' collides with an existing raw sector name, and that
    there are no duplicate targets.

    Args:
        sectors: list of sector names from config
        scaling_config: list of scaling rules
            [{"target": "bbPEAT", "from": "bbALL", "species": [...], "file": ...}]
        verbose: print info steps

    Returns:
        True if validation passes, False if invalid (in which case a
        warning has already been printed for each problem found).
    """
    if scaling_config is None:
        return True

    valid = True
    for rule in scaling_config:
        target = rule["target"]
        source_sector = rule["from"]

        if source_sector not in sectors:
            print(aux.pwarn(f"    Warning: sector '{source_sector}' in scaling rule '{target}' not found in sectors list {sectors}"))
            valid = False

        if target in sectors:
            print(aux.pwarn(f"    Warning: scaling target '{target}' collides with an existing sector name"))
            valid = False

        # Check for duplicate targets
        target_count = sum(1 for r in scaling_config if r["target"] == target)
        if target_count > 1:
            print(aux.pwarn(f"    Warning: duplicate scaling target '{target}'"))
            valid = False

    return valid

def aggregate_sectors(input_file: str, aggregate_config: list[dict] | None, verbose: bool = False) -> None:
    """Aggregate sectors according to defined rules, via `ncap2`.

    Adds new variables to the NetCDF file (in place) that are sums of
    specified sectors.

    Args:
        input_file: NetCDF file with sector variables (AGR, ENE, etc.),
            modified in place
        aggregate_config: list of aggregation rules
            [{"target": "total", "from": ["AGR", "ENE", ...]}], or None to
            do nothing
        verbose: print info steps
    """
    if aggregate_config is None:
        return
    
    for rule in aggregate_config:
        target = rule["target"]
        source_sectors = rule["from"]
        
        if verbose:
            print(aux.pinfo(f"      > Aggregating: {target} = {' + '.join(source_sectors)}"))
        
        rule_str = f"{target}=" + "+".join(source_sectors)
        cmd = f'ncap2 -s "{rule_str}" -O {input_file} {input_file}'
        if verbose:
            print(cmd)
        run_cmd(cmd, verbose)

def remove_sectors(input_file: str, sectors_to_remove: list[str] | None, verbose: bool = False) -> None:
    """Remove specified sector variables from a NetCDF file, via `ncks`.

    Args:
        input_file: NetCDF file with sector variables, modified in place
        sectors_to_remove: list of sector/variable names to remove, or
            None/empty to do nothing
        verbose: print info steps
    """
    if sectors_to_remove is None or len(sectors_to_remove) == 0:
        return
    
    if verbose:
        print(aux.pinfo(f"      > Removing sectors: {', '.join(sectors_to_remove)}"))
    
    cmd = f"ncks -O -x -v {','.join(sectors_to_remove)} {input_file} {input_file}"
    if verbose:
        print(cmd)
    run_cmd(cmd, verbose)

def apply_ecearth3_biofuel_subtraction(group_config: dict, created_lfiles: list[str], overwrite: bool = False, verbose: bool = False) -> list[str]:
    """Derive extra anthro-surf-ecearth files for EC-Earth3 compatibility.

    For every species with both an anthro-surf and an anthro-biof file (i.e.
    a species listed under the group's "em-SOLID-BIOFUEL-anthro" subset,
    today BC and OC), computes anthro-surf-ecearth = anthro-surf minus
    anthro-biof, sector by sector, via `ncdiff`. This is an exact partition,
    not an approximation: anthro-biof holds only the solid-biofuel-combustion
    portion of the same per-sector values anthro-surf reports, so
    anthro-surf-ecearth + anthro-biof == anthro-surf by construction.

    Neither anthro-surf nor anthro-biof is modified -- this only adds new
    files alongside them.

    Args:
        group_config: config dict for the group being processed (e.g.
            datainfo["anthro"]); uses group_config["subsets"]
        created_lfiles: paths of files already produced for this group (by
            process_group), searched for anthro-biof files to pair up
        overwrite: overwrite an existing anthro-surf-ecearth file if found
        verbose: print info steps

    Returns:
        Paths of the anthro-surf-ecearth files created or already found.
        Empty if the group config has no "em-SOLID-BIOFUEL-anthro" subset
        (e.g. ScenarioMIP configs), which is the expected/clean no-op case.
    """
    biof_subset = group_config["subsets"].get("em-SOLID-BIOFUEL-anthro")
    if biof_subset is None:
        print(aux.pwarn("    --ecearth3: no solid-biofuel dataset (em-SOLID-BIOFUEL-anthro) in this config, nothing extra to derive"))
        return []

    biof_suffix = biof_subset["suffix"]  # "anthro-biof"
    surf_suffix = "anthro-surf"

    biofuel_files = [f for f in created_lfiles if f"_{biof_suffix}_" in os.path.basename(f)]

    lstore_ecearth3 = []
    for fbiof in biofuel_files:
        fsurf = fbiof.replace(f"_{biof_suffix}_", f"_{surf_suffix}_")
        if not os.path.isfile(fsurf):
            print(aux.pwarn(f"    --ecearth3: no matching {surf_suffix} file for {os.path.basename(fbiof)}, skipping"))
            continue

        fec3 = fbiof.replace(f"_{biof_suffix}_", f"_{surf_suffix}-ecearth_")
        if os.path.isfile(fec3) and not overwrite:
            print(aux.pinfo(f"      > Found {fec3}, not overwriting"))
            lstore_ecearth3.append(fec3)
            continue

        if verbose:
            print(aux.pinfo(f"      > Deriving {os.path.basename(fec3)} = {surf_suffix} - {biof_suffix}"))
        cmd_ncdiff = f"ncdiff -O {fsurf} {fbiof} -o {fec3}"
        if verbose:
            print(cmd_ncdiff)
        run_cmd(cmd_ncdiff, verbose)
        print(aux.pshow(f"  Created: ") + aux.pinfo(f"{fec3}"))
        lstore_ecearth3.append(fec3)

    return lstore_ecearth3

def scale_sector(store_ncfile: str, target: str, from_sector: str, factor_file: str, propath: str, yr: int | str, verbose: bool = False) -> None:
    """Derive a new sector variable by scaling an existing one, appended in place.

    Multiplies the `from_sector` variable already inside `store_ncfile` by an
    external factor file (percentage values converted to fractions), renames
    the result to `target`, and appends it into `store_ncfile` as a new
    variable (via `ncks -A`, same append pattern `split_sectors()` uses).
    `from_sector` itself is left untouched -- the original/unscaled field
    stays available alongside the derived one.

    Args:
        store_ncfile: path to the already-stored final emission NetCDF file,
            modified in place (a new variable is appended)
        target: name of the new sector variable to create (e.g. "bbPEAT")
        from_sector: name of the existing sector variable to scale (e.g. "bbALL")
        factor_file: path to the external percentage-factor NetCDF file
        propath: path for temporary processing files
        yr: year to extract from the factor file
        verbose: print info steps
    """
    scaling_tmp = os.path.join(propath, f"scaling_factor_{target}_{yr}.nc")
    scaled_tmp = os.path.join(propath, f"scaled_{target}_{yr}.nc")

    if verbose:
        print(aux.pshow(f"      > [scaling] Source factor: {factor_file}"))
        print(aux.pshow(f"      > [scaling] Extracting year {yr} and converting % to fraction..."))

    cmd_scale = (
        f"cdo divc,100 -selyear,{yr} -setmisstoc,0 {factor_file} {scaling_tmp}"
    )
    run_cmd(cmd_scale, verbose)
    if not os.path.isfile(scaling_tmp):
        print(aux.pwarn(f"      > [scaling] Failed: {scaling_tmp} was not produced "
                         f"(cdo divc/selyear/setmisstoc step above failed) -- "
                         f"'{target}' NOT added to {store_ncfile}"))
        return

    if verbose:
        print(aux.pshow(f"      > [scaling] Deriving {target} = {from_sector} * factor..."))

    cmd_mul = f"cdo -chname,{from_sector},{target} -mul {store_ncfile} {scaling_tmp} {scaled_tmp}"
    run_cmd(cmd_mul, verbose)
    if not os.path.isfile(scaled_tmp):
        print(aux.pwarn(f"      > [scaling] Failed: {scaled_tmp} was not produced "
                         f"(cdo mul step above failed) -- '{target}' NOT added to {store_ncfile}"))
        if os.path.isfile(scaling_tmp):
            os.remove(scaling_tmp)
        return

    if verbose:
        print(aux.pshow(f"      > [scaling] Appending {target} into {os.path.basename(store_ncfile)}..."))

    cmd_append = f"ncks -A {scaled_tmp} {store_ncfile}"
    run_cmd(cmd_append, verbose)

    if os.path.isfile(scaling_tmp):
        os.remove(scaling_tmp)
    if os.path.isfile(scaled_tmp):
        os.remove(scaled_tmp)

    if verbose:
        print(aux.pshow(f"      > [scaling] Done: {target} added to {store_ncfile}"))

#-------------------------------------------------------------------------------
# Core processing methods
#

def process_subset(version: list[str], species: str, subset_key: str, subset_config: dict, lsyears: list[str], lsectors: list[str],
                   grawpath: str, propath: str, outpath: str, resol: str, datasetname: str,
                   species_filename_map: dict[str, str] | None = None, aggregate_config: list[dict] | None = None,
                   sectors_to_remove: list[str] | None = None, scaling: list[dict] | None = None,
                   verbose: bool = False, clean: bool = True, overwrite: bool = False, years: list[str] | None = None,
                   interpolate: bool = False, force_interp: list[str] | None = None) -> tuple[list[str], list[dict]]:
    """Process a single subset of species data.

    Args:
        version: list of version strings to try (in order)
        species: species name (e.g., "BC", "VOC01-alcohols")
        subset_key: subset key from config (e.g., "em-anthro", "none")
        subset_config: subset config dict with "suffix" key
        lsyears: list of year intervals (e.g., ["175001-179912", ...])
        lsectors: list of sector names (e.g., ["AGR", "ENE", ...] or ["bbALL"])
        grawpath: path to raw input netcdf data
        propath: path for temporary processing files
        outpath: path for final output files
        resol: resolution string for filenames (e.g., "05x05")
        datasetname: dataset name for output filenames
        species_filename_map: dict mapping species to filename versions
        aggregate_config: list of aggregation rules (optional)
        sectors_to_remove: list of sectors to remove after aggregation (optional)
        scaling: list of scaling rules (optional), e.g.
            [{"target": "bbPEAT", "from": "bbALL", "species": ["CO2"], "file": ...}]
        verbose: print info steps
        clean: clean intermediate files after processing
        overwrite: overwrite existing files
        years: list of specific years to process (None = all)
        interpolate: interpolate_years of the group: a year the raw file of its
            period lacks is interpolated from the file's neighbouring years
            (see extract_or_interpolate_year); off = reported as missing
        force_interp: validation only (--forceinterp): years interpolated even
            if the raw file has them

    Returns:
        (lstore_nc, stats_rows): stored file paths, and per-file monthly/annual
        emission stats rows (one per sector variable actually present in the
        final file) for every file processed or already found, ready for
        emissions_stats.write_group_stats().
    """

    lstore_nc = []
    stats_rows = []
    subset_suffix = subset_config["suffix"]

    # Sectors that may end up in this species' final file: the raw sectors,
    # any aggregate targets, and any scaling targets that apply to this
    # species -- compute_file_stats_rows() silently skips names not actually
    # present in a given file, so it's fine to pass candidates that don't apply.
    applicable_scaling = [r for r in (scaling or []) if species in r["species"]]
    stats_sectors = list(lsectors)
    if aggregate_config:
        stats_sectors += [r["target"] for r in aggregate_config]
    stats_sectors += [r["target"] for r in applicable_scaling]

    for syear in lsyears:
        # Periods holding none of the requested years are not needed at all
        if years is not None and not any(yy in [str(a) for a in aux.get_list_years(syear)] for yy in years):
            continue

        fnc_found = build_raw_path(grawpath, species, subset_key, version, syear, verbose=verbose)
        if fnc_found is None:
            # A missing period no longer ends the species: later periods are
            # still processed (e.g. a species that only starts in 1970). Always
            # reported, and collected for the end-of-run summary.
            print(aux.pwarn(f"    Warning: no raw file for {species} ({subset_key}) period {syear} "
                            f"in {grawpath} -- skipping that period"))
            MISSING_RAW.append((subset_suffix, subset_key, species, syear))
            continue

        # Extract varname from raw file BEFORE year loop (Option A)
        varname = get_varname_from_file(fnc_found)
        
        # Validate varname against actual NetCDF (Option B)
        varname = validate_varname(varname, fnc_found, verbose=verbose)
        
        # Validate sector count matches YAML specification
        if not validate_sector_count(fnc_found, lsectors, verbose=verbose):
            sys.exit(1)
        
        # Determine which years to process
        if years is None:
            list_yrs = aux.get_list_years(syear)
            if verbose:
                print(f"    Processing all years in interval {syear}")
        else:
            section_years = [str(a) for a in aux.get_list_years(syear)]
            list_yrs = [yy for yy in years if yy in section_years]
            if verbose:
                print(f"    Processing years: {','.join(list_yrs)}")
        
        for yr in list_yrs:
            # Check if output already exists
            species_fn = get_species_filename(species, species_filename_map)
            final_name = os.path.join(outpath, 
                f"{datasetname}_{resol}_{subset_suffix}_{species_fn}_{yr}.nc")
            
            if os.path.isfile(final_name) and not overwrite:
                print(aux.pinfo(f"      > Found {final_name}, not overwriting"))
                lstore_nc.append(final_name)
                stats_rows.extend(emissions_stats.compute_file_stats_rows(
                    final_name, stats_sectors, species_fn, subset_suffix, yr, propath, verbose=verbose))
                continue
            
            # 1. Extract year - use new naming convention {species}_{yr}_temp.nc
            #    (or interpolate it, if the raw file lacks it and the group allows it)
            temp1 = os.path.join(propath, f"{species}_{yr}_temp.nc")
            if verbose:
                print(aux.pinfo(f"      > Extracting year {yr}"))
            forced = str(yr) in (force_interp or [])
            interp = extract_or_interpolate_year(fnc_found, yr, temp1, propath,
                                                 interpolate=interpolate, force=forced,
                                                 verbose=verbose)
            if isinstance(interp, str):
                print(aux.pwarn(f"    Warning: {species} ({subset_key}) year {yr} {interp} "
                                f"-- skipping that year"))
                MISSING_RAW.append((subset_suffix, subset_key, species, f"{yr} ({interp.split(' (')[0]})"))
                if os.path.isfile(temp1):
                    os.remove(temp1)
                continue
            
            # 2. Handle sectors - pass varname
            temp2 = os.path.join(propath, f"{species}_{yr}_processed.nc")
            if len(lsectors) > 1:
                if verbose:
                    print(aux.pinfo(f"      > Splitting {len(lsectors)} sectors"))
                split_sectors(temp1, lsectors, temp2, varname=varname, verbose=verbose)
            else:
                if verbose:
                    print(aux.pinfo(f"      > Single sector: {lsectors[0]}"))
                rename_single_sector(temp1, lsectors[0], temp2, varname=varname, verbose=verbose)
            
            # 3. Aggregate sectors if configured (after split, before store)
            if len(lsectors) > 1 and aggregate_config:
                aggregate_sectors(temp2, aggregate_config, verbose=verbose)
            
            # 4. Remove sectors if configured (after aggregation, before store)
            if sectors_to_remove:
                remove_sectors(temp2, sectors_to_remove, verbose=verbose)
            
            # 5. Store output
            store_output(temp2, datasetname, resol, subset_suffix,
                        species_fn, yr, outpath)
            
            # 5b. Tag interpolated years, so they are never mistaken for raw data
            if interp:
                y0, y1 = interp
                why = ("FORCED for validation (--forceinterp), the raw file has this year" if forced
                       else f"{yr} not in the raw file")
                run_cmd(f'ncatted -O -h -a interpolated,global,o,c,'
                        f'"from {y0} and {y1}, linear, month by month (cdo intyear); {why}" '
                        f'{final_name}', verbose)
                INTERPOLATED.append((subset_suffix, species_fn, str(yr) + (" (forced)" if forced else ""), y0, y1))

            # 6. Apply scaling if configured (after store, appends a new sector variable)
            for rule in applicable_scaling:
                factor_file = os.path.join(grawpath, rule["file"])
                scale_sector(final_name, rule["target"], rule["from"], factor_file, propath, yr, verbose=verbose)

            # 7. Compute monthly/annual emission stats for the completed file
            stats_rows.extend(emissions_stats.compute_file_stats_rows(
                final_name, stats_sectors, species_fn, subset_suffix, yr, propath, verbose=verbose))

            # 8. Clean
            if clean:
                if os.path.isfile(temp1):
                    os.remove(temp1)
                if os.path.isfile(temp2):
                    os.remove(temp2)

            lstore_nc.append(final_name)

    return lstore_nc, stats_rows

def process_group(datainfo: dict, group: str, rawpath: str, outpath: str, propath: str, verbose: bool,
                  clean: bool = True, store: str | bool = True, overwrite: bool = False, years: list[str] | None = None,
                  force_interp: list[str] | None = None) -> list[str]:
    """Process emissions data for a given group (anthro, aviation, bburning).

    For every (subset, species) in the group's config, delegates to
    process_subset() to create/find each year's final file, then writes the
    accumulated monthly/annual emission-stats CSVs for this group via
    emissions_stats.write_group_stats() (see lib/emissions_stats.py) as a
    side effect before returning.

    Args:
        datainfo: full config dict for this CMIP version
        group: group name ("anthro", "bburning", "aviation")
        rawpath: path to raw input data for this group
        outpath: path for final output files
        propath: path for temporary processing files
        verbose: print info steps
        clean: clean intermediate files after processing
        store: accepted but not used within this function; kept for
            interface compatibility with callers (cmip_preemis passes
            args.store, a string)
        overwrite: overwrite existing files
        years: list of specific years to process (None = all)
        force_interp: validation only (--forceinterp): years interpolated even
            if the raw files have them, in any group (end-to-end check of the
            interpolation against the real year)

    Returns:
        Paths of every final file processed or already found, across all
        subsets/species in this group.
    """
    
    group_config = datainfo[group]
    
    # Construct version list
    version_prefix = "_".join([datainfo["origin"], datainfo["category"], datainfo["target_mip"]])
    version_list = [f"{version_prefix}_{v}_gn" for v in group_config["version"]]
    
    resol = group_config["resol"][1]  # filename resolution string
    dname = datainfo["outputname"]
    aggregate_config = group_config.get("aggregate", None)
    sectors_to_remove = group_config.get("remove_sectors", None)
    scaling = group_config.get("scaling", None)
    
    # Validate aggregate configuration
    if aggregate_config:
        validate_aggregate_config(group_config["sectors"], aggregate_config, verbose=verbose)

    # Validate scaling configuration
    if scaling:
        validate_scaling_config(group_config["sectors"], scaling, verbose=verbose)

    # Years missing inside a raw file: interpolated only if the group allows it
    interpolate = group_config.get("interpolate_years", False)
    if not isinstance(interpolate, bool):
        print(aux.perror(f"Error: interpolate_years of [{group}] must be true or false, got {interpolate!r}"))
        sys.exit(1)

    # Validate derivespecies configuration (species built as the sum of other species)
    derive_config = group_config.get("derivespecies", None)
    if derive_config:
        validate_derive_config(group_config, derive_config, verbose=verbose)

    created_lfiles = []
    all_stats_rows = []

    # Ensure propath exists (constant for the whole call, so checked once)
    if not os.path.isdir(propath):
        os.makedirs(propath)

    for subset_key, subset_config in group_config["subsets"].items():
        subset_species = subset_config["species"]
        subset_filename_map = subset_config.get("species_filename_map", None)
        validate_extra_years(group, subset_key, subset_config)

        if verbose:
            print(aux.pshow(f"\n*** Processing subset {subset_key} ({len(subset_species)} species) ***"))

        for species in subset_species:
            if verbose:
                print(aux.pshow(f"  > Processing {species}"))
            
            lstore_nc, stats_rows = process_subset(
                version_list, species, subset_key, subset_config,
                periods_for(group_config, subset_config, species), group_config["sectors"],
                rawpath, propath, outpath, resol, dname,
                species_filename_map=subset_filename_map,
                aggregate_config=aggregate_config,
                sectors_to_remove=sectors_to_remove,
                scaling=scaling,
                verbose=verbose, clean=clean, overwrite=overwrite, years=years,
                interpolate=interpolate, force_interp=force_interp
            )
            created_lfiles.extend(lstore_nc)
            all_stats_rows.extend(stats_rows)

    # Derived species, once every subset of the group is done (they are sums
    # of final files of other species, see derive_species)
    if derive_config and validate_derive_config(group_config, derive_config):
        stats_sectors = list(group_config["sectors"]) + [r["target"] for r in (aggregate_config or [])]
        for rule in derive_config:
            dfiles, drows = derive_species(rule, created_lfiles, outpath, resol, dname, stats_sectors,
                                           propath, overwrite=overwrite, verbose=verbose)
            created_lfiles.extend(dfiles)
            all_stats_rows.extend(drows)

    emissions_stats.write_group_stats(datainfo, group, outpath, all_stats_rows, verbose=verbose)

    return created_lfiles
