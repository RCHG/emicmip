#!/usr/bin/env python3
# ╭────────────────────────────────────────────────────────────────────────────╮
# │ check_store.py                                        (updated 2026-10)    │
# │                                                                            │
# │ Author:  Ramiro Checa-Garcia (KNMI)                                        │
# │ Purpose: For a config (etc/*.toml), finds which years were produced before:│
# │          tars in the store (with our without -ec3) or local files. It reads│
# │          the toml bundled in each tar to evaluate the options used in the  │
# │          production of the tar files.                                      │
# │                                                                            │
# │ Note: This module is never writing to the store. ECFS should keep untouch  │
# │       Only tar for requested years are checked and eventually the metadata │
# │       of the production info is reported.                                  │
# │ LLMs: Reviewed a first version of this module. Implemented many of the     │
# │       functions based on the description of the specification to           │
# │       implement.                                                           │
# ╰────────────────────────────────────────────────────────────────────────────╯

import os
import re
import glob
import shutil
import tarfile
import datetime
import subprocess

import lib.aux as aux
import lib.ecfs as ecfs

# Header lines that cmip_preemis tool add at the beginning of the toml copy 
# inside each tar (see toml_header in cmip_preemis); tars older than 2026-10 
# only have the first two.
HEADER_KEYS = ("run as", "version", "created", "user@host")

# Group a subset suffix belongs to -- same rule as validate_tar.group_for_suffix,
# repeated here so cmip_check doesn't need xarray just to list a tar.
GROUP_BY_SUFFIX = {"anthro-air": "aviation", "bburning": "bburning"}
TOML_GROUPS = ("anthro", "aviation", "bburning")


#---[ Config ]------------------------------------------------------------------

def load_toml(toml_path: str) -> tuple[str, dict]:
    """Load a config file, whose only top-level key is the CMIP version.

    Returns:
        (cmip_key, datainfo), e.g. ("CMIP7", {...}).
    """
    import tomllib
    from lib.cmip_config import expand_user
    with open(toml_path, "rb") as f:
        data = expand_user(tomllib.load(f), source=toml_path)   # "{user}" in paths -> user running the tool
    if len(data) != 1:
        raise ValueError(f"{toml_path}: expected one top-level section, found {list(data)}")
    return next(iter(data.items()))


def expected_years(datainfo: dict) -> list[int]:
    """Years covered by the config (all groups), same as cmip_preemis without --years."""
    return aux.config_years(datainfo, list(TOML_GROUPS))


def parse_years(spec: str) -> list[int]:
    """"1850,1900", "1850-1910" or a mix -> sorted list of years (as the Makefile)."""
    years = set()
    for part in spec.split(","):
        part = part.strip()
        if not part:
            continue
        first, _, last = part.partition("-")
        years.update(range(int(first), int(last or first) + 1))
    return sorted(years)


def compress_years(years: list[int]) -> str:
    """[1850, 1851, 1852, 1900] -> "1850-1852, 1900"."""
    out, start = [], None
    for i, y in enumerate(years):
        if start is None:
            start = y
        if i == len(years) - 1 or years[i + 1] != y + 1:
            out.append(str(start) if start == y else f"{start}-{y}")
            start = None
    return ", ".join(out)


#---[ Store listing ]-----------------------------------------------------------

def _parse_date(text: str) -> str:
    """ls-style date ("Oct 12 10:18" or "Oct 12  2025") -> "YYYY-MM-DD", or the
    text unchanged if it doesn't look like either."""
    for fmt in ("%b %d %H:%M", "%b %d %Y"):
        try:
            d = datetime.datetime.strptime(" ".join(text.split()), fmt)
        except ValueError:
            continue
        if fmt == "%b %d %H:%M":
            # ls omits the year for recent files: this year, or last year if
            # that would put it in the future.
            today = datetime.date.today()
            d = d.replace(year=today.year)
            if d.date() > today:
                d = d.replace(year=today.year - 1)
        return d.strftime("%Y-%m-%d")
    return text


def parse_els_line(line: str) -> tuple[str, int | None, str | None] | None:
    """One line of `els -l` -> (name, size, date), tolerant to the format.

    Expects `ls -l`-like lines (perms, links, user, group, size, month, day,
    time|year, name). If a line doesn't have that shape, still returns its
    last token as the name, with size/date None, so the check degrades to
    "present or not" rather than failing. Directories and "total N" lines
    are skipped (None).
    """
    tokens = line.split()
    if not tokens or tokens[0] == "total" or tokens[0].startswith("d"):
        return None
    name = tokens[-1]
    if len(tokens) >= 8 and tokens[4].isdigit() and re.match(r"^\d{4}-\d{2}-\d{2}$", tokens[5]):
        return name, int(tokens[4]), tokens[5]           # --time-style=iso-like dates
    if len(tokens) >= 9 and tokens[4].isdigit():
        return name, int(tokens[4]), _parse_date(" ".join(tokens[5:8]))
    return name, None, None


def list_store(tar_store: dict, verbose: bool = False) -> dict[str, dict] | None:
    """List the files in the tar store, without downloading anything.

    Args:
        tar_store: datainfo["tar_store"], {"cmd": "ecp"|"cp", "path": ...}

    Returns:
        {name: {"size": int|None, "date": "YYYY-MM-DD"|str|None}}, or None if
        the store could not be listed.
    """
    path = tar_store["path"]
    if not ecfs.is_ecfs_path(path):
        if not os.path.isdir(path):
            return None
        entries = {}
        for e in os.scandir(path):
            if e.is_file():
                st = e.stat()
                entries[e.name] = {"size": st.st_size,
                                   "date": datetime.date.fromtimestamp(st.st_mtime).isoformat()}
        return entries

    if shutil.which("els") is None:
        print(aux.perror(f"  'els' is not on PATH, can't list {path}"))
        return None
    if verbose:
        print(aux.pinfo(f"  > [check] els -l {path}"))
    result = subprocess.run(["els", "-l", path], capture_output=True, text=True)
    if result.returncode != 0:
        print(aux.perror(f"  els -l {path} failed (exit code {result.returncode}): {result.stderr.strip()}"))
        return None
    entries = {}
    for line in result.stdout.splitlines():
        parsed = parse_els_line(line)
        if parsed is not None:
            name, size, date = parsed
            entries[os.path.basename(name)] = {"size": size, "date": date}
    return entries


def tar_regex(tar_common: str) -> re.Pattern:
    """Tar names cmip_preemis writes: <tar_common>_<year>.tar, or
    <tar_common>-ec3_<year>.tar for runs with --ecearth3 (see tar_store_byyear)."""
    return re.compile(rf"^{re.escape(tar_common)}(?P<ec3>-ec3)?_(?P<year>\d{{4}})\.tar$")


def tars_by_year(entries: dict[str, dict], tar_common: str) -> dict[int, dict[str, dict]]:
    """{year: {"std"|"ec3": {"name", "size", "date"}}} for the tars in `entries`."""
    rx = tar_regex(tar_common)
    out: dict[int, dict[str, dict]] = {}
    for name, meta in entries.items():
        m = rx.match(name)
        if m:
            kind = "ec3" if m.group("ec3") else "std"
            out.setdefault(int(m.group("year")), {})[kind] = {"name": name, **meta}
    return out


#---[ Local outpath ]-----------------------------------------------------------

CSV_RE = re.compile(r"^emissions_(?P<group>.+)_(?P<year>\d{4})\.csv$")


def csv_groups(csv_dir: str) -> dict[int, set[str]]:
    """{year: {groups}} of the emissions_<group>_<year>.csv files in csv_dir."""
    out: dict[int, set[str]] = {}
    if os.path.isdir(csv_dir):
        for name in os.listdir(csv_dir):
            m = CSV_RE.match(name)
            if m:
                out.setdefault(int(m.group("year")), set()).add(m.group("group"))
    return out


def config_groups(datainfo: dict) -> list[str]:
    """Groups the config defines, i.e. the CSVs a full (-a -b -f) run writes per year."""
    return [g for g in TOML_GROUPS if g in datainfo]


def local_status(outpath: str, datainfo: dict, years: list[int]) -> dict[int, dict]:
    """Per year: number of final nc files in outpath, stats CSV groups in
    outpath/emissions_stats/ and in the repo copy outs/validation/<outputname>/
    (relative to CWD, see write_group_stats), and local tars."""
    status = {}
    val_csv = csv_groups(os.path.join("outs", "validation", datainfo["outputname"]))
    if not os.path.isdir(outpath):
        return {y: {"nc": 0, "csv": set(), "val": val_csv.get(y, set()), "tars": {}}
                for y in years if val_csv.get(y)}
    entries = {}
    for e in os.scandir(outpath):
        if e.is_file() and e.name.endswith(".tar"):
            st = e.stat()
            entries[e.name] = {"size": st.st_size,
                               "date": datetime.date.fromtimestamp(st.st_mtime).isoformat()}
    local_tars = tars_by_year(entries, datainfo["tar_common"])
    nc_all = glob.glob(os.path.join(outpath, f"{datainfo['outputname']}_*.nc"))
    nc_by_year: dict[int, int] = {}
    for nc in nc_all:
        stem = os.path.splitext(os.path.basename(nc))[0]
        year = stem.rsplit("_", 1)[-1]
        if year.isdigit():
            nc_by_year[int(year)] = nc_by_year.get(int(year), 0) + 1
    out_csv = csv_groups(os.path.join(outpath, "emissions_stats"))
    for y in years:
        status[y] = {"nc": nc_by_year.get(y, 0), "csv": out_csv.get(y, set()),
                     "val": val_csv.get(y, set()), "tars": local_tars.get(y, {})}
    return status


#---[ Report ]------------------------------------------------------------------

def _kinds(tars: dict) -> str:
    return {("std",): "plain", ("ec3",): "ec3", ("ec3", "std"): "plain+ec3"}.get(tuple(sorted(tars)), "-")


def _fmt_size(n: int | None) -> str:
    if n is None:
        return "?"
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024:
            return f"{n:.1f}{unit}" if unit in ("GB", "TB") else f"{n:.0f}{unit}"
        n /= 1024
    return f"{n:.1f}PB"


def _range(values: list[str]) -> str:
    vals = sorted({v for v in values if v})
    if not vals:
        return "?"
    return vals[0] if len(vals) == 1 else f"{vals[0]} .. {vals[-1]}"


def print_report(years: list[int], store: dict[int, dict] | None, local: dict[int, dict],
                 ngroups: int) -> None:
    """Table of consecutive years with the same status, then a summary.

    CSV columns read "n/N": groups with an emissions_<group>_<year>.csv out
    of the N groups in the config, in outpath/emissions_stats/ ("CSV out")
    and in the repo copy outs/validation/<outputname>/ ("CSV val")."""
    def key(y):
        s = _kinds(store.get(y, {})) if store is not None else "n/a"
        loc = local.get(y, {})
        return (s, loc.get("nc", 0) > 0, len(loc.get("csv", ())), len(loc.get("val", ())),
                _kinds(loc.get("tars", {})))

    def frac(n):
        return f"{n}/{ngroups}" if n else "-"

    print(aux.pshow(f"\n {'Years':<13} {'Store tar':<10} {'Store date':<24} {'Size/tar':<16} "
                    f"{'Local nc':<9} {'CSV out':<8} {'CSV val':<8} {'Local tar'}"))
    i = 0
    while i < len(years):
        j = i
        while j + 1 < len(years) and years[j + 1] == years[j] + 1 and key(years[j + 1]) == key(years[i]):
            j += 1
        block = years[i:j + 1]
        skind, has_nc, ncsv, nval, lkind = key(years[i])
        tars = [t for y in block for t in (store or {}).get(y, {}).values()]
        dates = _range([t["date"] for t in tars]) if tars else ""
        sizes = [t["size"] for t in tars if t["size"] is not None]
        if not tars:
            size = ""
        elif not sizes:
            size = "?"
        else:
            lo, hi = _fmt_size(min(sizes)), _fmt_size(max(sizes))
            size = lo if lo == hi else f"{lo}..{hi}"
        nc = [local.get(y, {}).get("nc", 0) for y in block]
        nc_txt = "-" if not has_nc else (str(nc[0]) if min(nc) == max(nc) else f"{min(nc)}..{max(nc)}")
        yrs = compress_years(block)
        color = aux.pgood if skind not in ("-", "n/a") else aux.pwarn
        print(color(f" {yrs:<13} {skind:<10}") + f" {dates:<24} {size:<16} "
              f"{nc_txt:<9} {frac(ncsv):<8} {frac(nval):<8} {lkind}")
        i = j + 1

    if store is None:
        return
    missing = [y for y in years if not store.get(y)]
    both = [y for y in years if len(store.get(y, {})) == 2]
    ec3 = [y for y in years if "ec3" in store.get(y, {})]
    print(aux.pshow("\n Summary"))
    print(f"   years in config : {len(years)}  ({compress_years(years)})")
    print(f"   tars in store   : {len(years) - len(missing)}   (with -ec3: {len(ec3)})")
    if missing:
        print(aux.pwarn(f"   missing         : {compress_years(missing)}"))
    if both:
        print(aux.pwarn(f"   plain AND -ec3  : {compress_years(both)}  (two runs, with and without -e)"))


#---[ Deep: inside the tar ]----------------------------------------------------

def _group_for_suffix(suffix: str) -> str:
    if suffix in GROUP_BY_SUFFIX:
        return GROUP_BY_SUFFIX[suffix]
    return "anthro" if suffix.startswith("anthro") else suffix


def split_toml_header(text: str) -> tuple[dict[str, str], str]:
    """Separate cmip_preemis' "# key: value" header lines (HEADER_KEYS) from
    the toml body. Returns (header, body)."""
    header = {}
    lines = text.splitlines(keepends=True)
    n = 0
    for line in lines:
        m = re.match(r"^# (?P<key>[^:]+): (?P<val>.*)$", line.rstrip("\n"))
        if not m or m.group("key") not in HEADER_KEYS:
            break
        header[m.group("key")] = m.group("val")
        n += 1
    return header, "".join(lines[n:])


def raw_versions(toml_body: str) -> dict[str, list[str]]:
    """Raw-data version(s) of each group, from the toml bundled in a tar:
    {"anthro": ["IIASA-IAMC-m-1-1-1"], "aviation": [...], ...}. {} if unreadable."""
    import tomllib
    try:
        data = tomllib.loads(toml_body)
    except tomllib.TOMLDecodeError:
        return {}
    datainfo = next(iter(data.values()), {}) if len(data) == 1 else {}
    return {g: list(datainfo[g]["version"]) for g in TOML_GROUPS
            if isinstance(datainfo.get(g), dict) and "version" in datainfo[g]}


def inspect_tar(tar_path: str, toml_text: str, datainfo: dict) -> dict:
    """What a tar holds and how it was made, from its own contents.

    Args:
        tar_path: local path of the tar
        toml_text: contents of the toml given to cmip_check, to compare with
            the copy bundled in the tar
        datainfo: config section, for the groups the run should contain

    Returns:
        {"header": {...}, "toml_name", "toml_same": bool|None,
         "subsets": {suffix: n_species}, "groups": [...], "missing_groups": [...],
         "csv_groups": [...], "csv_missing": [...], "n_nc", "n_csv",
         "other_year": [nc files whose name has another year than the tar]}
    """
    info = {"header": {}, "toml_name": None, "toml_same": None, "subsets": {}, "n_nc": 0, "n_csv": 0,
            "other_year": []}
    m_year = re.search(r"_(\d{4})\.tar$", os.path.basename(tar_path))
    tar_year = m_year.group(1) if m_year else None
    species: dict[str, set] = {}
    subset_bytes: dict[str, int] = {}
    csv_grps: set[str] = set()
    with tarfile.open(tar_path, "r:*") as tar:
        for m in tar.getmembers():
            base = os.path.basename(m.name)
            if base.endswith(".nc"):
                info["n_nc"] += 1
                parts = os.path.splitext(base)[0].split("_")
                if len(parts) >= 5:
                    species.setdefault(parts[-3], set()).add(parts[-2])
                    if tar_year and parts[-1] != tar_year:
                        info["other_year"].append(base)
                    subset_bytes[parts[-3]] = subset_bytes.get(parts[-3], 0) + m.size
            elif base.endswith(".csv"):
                info["n_csv"] += 1
                m_csv = CSV_RE.match(base)
                if m_csv:
                    csv_grps.add(m_csv.group("group"))
            elif base.endswith(".toml") and "/" not in m.name.strip("./"):
                text = tar.extractfile(m).read().decode("utf-8", errors="replace")
                info["header"], body = split_toml_header(text)
                info["toml_name"] = base
                info["toml_same"] = (body == toml_text) if toml_text is not None else None
                info["raw_versions"] = raw_versions(body)
    info["subsets"] = {s: len(sp) for s, sp in sorted(species.items())}
    info["subset_bytes"] = subset_bytes
    info["groups"] = sorted({_group_for_suffix(s) for s in species})
    info["missing_groups"] = [g for g in config_groups(datainfo) if g not in info["groups"]]
    info["csv_groups"] = sorted(csv_grps)
    # A group with nc files but no stats CSV in emissions_stats/ (tars made
    # before the CSVs were bundled, or a run whose stats failed)
    info["csv_missing"] = [g for g in info["groups"] if g not in csv_grps]
    return info


def print_inspect(name: str, info: dict, toml_path: str) -> None:
    print(aux.pshow(f"\n {name}"))
    h = info["header"]
    if info["toml_name"] is None:
        print(aux.pwarn("   no toml inside (tar made before 2026-08): options unknown"))
    else:
        print(f"   run as    : {h.get('run as', '?')}")
        print(f"   emicmip   : {h.get('version', '?')}  (version of the code that made the tar)")
        print(f"   created   : {h.get('created', '? (not recorded before 2026-10)')}")
        if "user@host" in h:
            print(f"   user@host : {h['user@host']}")
        if info["toml_same"] is None:
            same = "(no --toml given to compare)"
        else:
            same = aux.pgood("same as " + toml_path) if info["toml_same"] else aux.pwarn("DIFFERS from " + toml_path)
        print(f"   toml      : {info['toml_name']} -- {same}")
    if info.get("raw_versions"):
        print("   raw data  : (version of the input files, from the toml in the tar)")
        for grp, vers in info["raw_versions"].items():
            print(f"     {grp:<10} {', '.join(vers)}")
    print(f"   contents  : {info['n_nc']} nc, {info['n_csv']} csv")
    for suffix, n in info["subsets"].items():
        nbytes = info["subset_bytes"].get(suffix, 0)
        print(f"     {suffix:<22} {n:>3} species  {_fmt_size(nbytes):>8}  ({_fmt_size(nbytes // n)}/species)")
    print(f"   stats csv : {', '.join(info['csv_groups']) or '-'}")
    if info["csv_missing"]:
        print(aux.pwarn(f"   no stats csv for: {', '.join(info['csv_missing'])}"))
    if info["missing_groups"]:
        print(aux.pwarn(f"   missing groups: {', '.join(info['missing_groups'])} "
                        f"(tar overwritten by a run without them?)"))
    if info.get("other_year"):
        shown = ", ".join(info["other_year"][:5]) + (" ..." if len(info["other_year"]) > 5 else "")
        print(aux.pwarn(f"   {len(info['other_year'])} nc file(s) of another year than the tar: {shown}"))


def deep_check(years: list[int], store: dict[int, dict], datainfo: dict, toml_path: str,
               cache_dir: str, verbose: bool = False) -> None:
    """Fetch (or reuse from cache_dir) every store tar of `years` and report
    its bundled toml header and contents (see inspect_tar)."""
    toml_text = None
    if toml_path:
        with open(toml_path) as f:
            toml_text = f.read()
    base = datainfo["tar_store"]["path"]
    for y in years:
        tars = store.get(y, {})
        if not tars:
            print(aux.pwarn(f"\n {y}: no tar in the store"))
            continue
        for kind in sorted(tars):
            name = tars[kind]["name"]
            local = ecfs.resolve_local_path(os.path.join(base, name), cache_dir)
            print_inspect(name, inspect_tar(local, toml_text, datainfo), toml_path)
