#!/usr/bin/env python3
# ╭────────────────────────────────────────────────────────────────────────────╮
# │ raw_check.py                                          (updated 2026-10)    │
# │                                                                            │
# │ Author:  Ramiro Checa-Garcia (KNMI)                                        │
# │ Purpose: Inventory of raw input4MIPs folders: check NetCDF metadata vs     │
# │          filename version, compare the same species/subset/period across   │
# │          related folders, and check which files etc/*.toml configs would   │
# │          read (same lookup as cmip_preemis).                               │
# │                                                                            │
# │ LLMs:    Created by LLMs under developer directives. Developers provided   │
# │          method, sources, testing ideas. LLMs did the low level coding     │
# │                                                                            │
# │ Self-contained: copy the whole rawcheck/ folder next to the raw data       │
# │ folders and run `make` (see Makefile). Only needs xarray for metadata.     │
# │ Read-only: never modifies, moves or deletes any file.                      │
# ╰────────────────────────────────────────────────────────────────────────────╯

import os
import re
import sys
import csv
import glob
import argparse
import filecmp

sys.dont_write_bytecode = True

#---[ Helpers (self-contained, no dependency on the emicmip lib/) ]---------

def _c(code):
    return (lambda s: f"\033[{code}m{s}\033[39m") if sys.stdout.isatty() else (lambda s: s)

pgood, pinfo, pwarn, pshow = _c(32), _c(34), _c(33), _c(36)


def fmt_size(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024:
            return f"{n:.1f}{unit}" if unit in ("GB", "TB") else f"{n:.0f}{unit}"
        n /= 1024
    return f"{n:.1f}PB"


def canon(path: str) -> str:
    """Comparable path: resolves symlinked *folders* (e.g. a linked $HPCPERM ->
    its real filesystem path) but not the file itself, so a file read through a
    symlink keeps its own name (needed to report 'link->target')."""
    return os.path.join(os.path.realpath(os.path.dirname(os.path.abspath(path))), os.path.basename(path))


def build_raw_path(grawpath, species, subset_key, versions, syear):
    """Mirror of lib/cmip_process.py::build_raw_path (keep both in sync): the
    first {species}[-{subset}]_{version}_{syear}.nc that exists, or None."""
    for v in versions:
        if subset_key is None or subset_key == "none":
            fname = f"{species}_{v}_{syear}.nc"
        else:
            fname = f"{species}-{subset_key}_{v}_{syear}.nc"
        path = os.path.join(grawpath, fname)
        if os.path.isfile(path):
            return path
    return None


# {species}[-{subset}]_{origin}_{category}_{target_mip}_{version}_gn[_{YYYYMM-YYYYMM}]{extra}.nc
# subset always starts with "em-"; extra catches non-standard tails such as "_backup".
RAW_RE = re.compile(
    r"^(?P<species>.+?)(?:-(?P<subset>em-.+?))?"
    r"_(?P<origin>input4MIPs)_(?P<category>[^_]+)_(?P<mip>[^_]+)_(?P<version>.+?)_gn"
    r"(?:_(?P<span>\d{6}-\d{6}))?(?P<extra>.*)\.nc$")

META_ATTRS = ("source_id", "source_version", "variable_id", "target_mip", "creation_date", "tracking_id")

try:
    import xarray as xr
except ImportError:
    xr = None


#---[ Inventory ]---------------------------------------------------------------

def read_meta(path: str) -> dict:
    """Global attributes of interest + dtype/compression of the main variable
    (header only: xarray opens lazily)."""
    meta = {k: "" for k in META_ATTRS} | {"var": "", "dtype": "", "zlib": "", "error": ""}
    if xr is None:
        return meta
    try:
        with xr.open_dataset(path, decode_times=False) as ds:
            for k in META_ATTRS:
                meta[k] = str(ds.attrs.get(k, ""))
            vid = meta["variable_id"]
            var = vid if vid in ds.data_vars else max(ds.data_vars, key=lambda v: ds[v].ndim, default="")
            if var:
                enc = ds[var].encoding
                meta["var"] = var
                meta["dtype"] = str(enc.get("dtype", ds[var].dtype))
                meta["zlib"] = f"zlib{enc.get('complevel', '')}" if enc.get("zlib") else "none"
    except Exception as e:                      # unreadable/corrupt file: report, don't stop
        meta["error"] = str(e).splitlines()[0][:120]
    return meta


def metadata_issues(e: dict) -> list[str]:
    """Inconsistencies between a file's name and its contents."""
    m = e["meta"]
    if m["error"]:
        return [f"unreadable: {m['error']}"]
    issues = []
    if m["source_id"] and m["source_id"] not in e["version"]:
        issues.append(f"filename version {e['version']} but source_id={m['source_id']}")
    norm = lambda s: s.replace("-", "_").lower()
    if m["variable_id"] and norm(e["species"]) not in norm(m["variable_id"]):
        issues.append(f"species {e['species']} but variable_id={m['variable_id']}")
    if e["link"]:
        t = RAW_RE.match(os.path.basename(e["realpath"]))
        if t and t.group("version") != e["version"]:
            issues.append(f"symlink to a file of another version: {t.group('version')}")
    if e["extra"]:
        issues.append(f"non-standard name tail '{e['extra']}' (never read by cmip_preemis)")
    return issues


def scan_dir(d: str) -> tuple[list[dict], list[str]]:
    """Parse and read the header of every *.nc in d. Returns (entries, unparsed names)."""
    entries, unparsed = [], []
    for path in sorted(glob.glob(os.path.join(d, "*.nc"))):
        name = os.path.basename(path)
        m = RAW_RE.match(name)
        if m is None:
            unparsed.append(name)
            continue
        real = os.path.realpath(path)
        ok = os.path.exists(real)
        e = {"dir": d, "name": name, "path": path, "realpath": real, "link": os.path.islink(path),
             "cdir": os.path.realpath(d), "cpath": canon(path),
             "size": os.path.getsize(real) if ok else -1,
             "species": m.group("species"), "subset": m.group("subset") or "none",
             "version": m.group("version"), "span": m.group("span") or "", "extra": m.group("extra")}
        e["key"] = (e["species"], e["subset"], e["span"], e["extra"])
        e["meta"] = read_meta(path) if ok else {k: "" for k in META_ATTRS} | {
            "var": "", "dtype": "", "zlib": "", "error": "broken symlink"}
        e["issues"] = metadata_issues(e)
        entries.append(e)
    return entries, unparsed


#---[ Families of related folders ]---------------------------------------------

def families(entries: list[dict], dirs: list[str]) -> list[list[str]]:
    """Group folders that share at least one (species, subset, period) key --
    e.g. two versions of the same dataset -- so unrelated datasets are not
    compared against each other. Connected components of the overlap graph."""
    keys = {d: {e["key"] for e in entries if e["dir"] == d} for d in dirs}
    parent = {d: d for d in dirs}

    def find(d):
        while parent[d] != d:
            d = parent[d]
        return d

    for i, a in enumerate(dirs):
        for b in dirs[i + 1:]:
            if keys[a] & keys[b]:
                parent[find(b)] = find(a)
    groups: dict[str, list[str]] = {}
    for d in dirs:
        groups.setdefault(find(d), []).append(d)
    return list(groups.values())


def same_file(a: dict, b: dict, check_bytes: bool) -> str:
    """Cheapest test first: same file, size, then bytes or tracking_id."""
    if a["realpath"] == b["realpath"]:
        return "identical (same file via symlink)"
    if a["size"] != b["size"]:
        return "different (size)"
    if check_bytes:
        same = filecmp.cmp(a["realpath"], b["realpath"], shallow=False)
        return "identical (bytes)" if same else "different (bytes)"
    ta, tb = a["meta"]["tracking_id"], b["meta"]["tracking_id"]
    if ta and ta == tb:
        return "likely identical (same size + tracking_id)"
    return "unsure (same size; run with --bytes)"


def compare_family(entries: list[dict], fam: list[str], check_bytes: bool) -> list[dict]:
    by_key: dict[tuple, dict[str, dict]] = {}
    for e in entries:
        if e["dir"] in fam:
            by_key.setdefault(e["key"], {})[e["dir"]] = e
    rows = []
    for key, per_dir in sorted(by_key.items()):
        present = [d for d in fam if d in per_dir]
        if len(present) == 1:
            rows.append({"key": key, "status": "only in", "dirs": present, "detail": "", "per_dir": per_dir})
            continue
        ref = per_dir[present[0]]
        st = [same_file(ref, per_dir[d], check_bytes) for d in present[1:]]
        overall = ("identical" if all(s.startswith("identical") for s in st) else
                   "different" if any(s.startswith("different") for s in st) else
                   "unsure" if any(s.startswith("unsure") for s in st) else "likely identical")
        detail = "; ".join(f"vs {os.path.basename(d)}: {s}" for d, s in zip(present[1:], st))
        rows.append({"key": key, "status": overall, "dirs": present, "detail": detail, "per_dir": per_dir})
    return rows


def created(e: dict) -> str:
    """creation_date attribute (ISO, so it sorts), '' if absent. The folder
    name is not used: it can disagree with the content (symlinks)."""
    return e["meta"]["creation_date"]


def newest_per_species(rows: list[dict], used_by: dict[str, list[str]]) -> list[dict]:
    """Per (species, subset) of a family: the folder(s) holding the most recent
    file (by creation_date, over all its periods), the folder(s) the configs
    read, and whether what they read is that most recent version."""
    # Compared period by period: within one version the periods of a species
    # can have different creation dates, so "newest" only makes sense per period.
    groups: dict[tuple, dict] = {}
    for r in rows:
        if r["key"][3]:                       # non-standard tails (_backup) are never read
            continue
        g = groups.setdefault((r["key"][0], r["key"][1]),
                              {"files": [], "used": [], "older": [], "nodate": False, "newest_files": []})
        files = list(r["per_dir"].values())
        dates = [created(e) for e in files if created(e)]
        period_newest = max(dates) if dates else ""
        g["newest_files"] += [e for e in files if period_newest and created(e) == period_newest]
        for e in files:
            g["files"].append(e)
            if e["cpath"] in used_by:
                g["used"].append(e)
                if not created(e) or not period_newest:
                    g["nodate"] = True
                elif created(e) < period_newest:
                    g["older"].append(r["key"][2] or "(no period)")
    res = []
    for (sp, sub), g in sorted(groups.items()):
        dates = [created(e) for e in g["files"] if created(e)]
        newest = max(dates) if dates else ""
        if not g["used"]:
            verdict = "not read by any config"
        elif g["older"]:
            verdict = f"reads an OLDER file for: {', '.join(g['older'])}"
        elif g["nodate"]:
            verdict = "no creation_date: cannot tell"
        else:
            verdict = "ok, reads the most recent"
        # A symlink counts as its target: attribute files to the folder that
        # really holds them, and show reads through a link as "link->target".
        real_dir = lambda e: os.path.basename(os.path.dirname(e["realpath"]))
        shown = lambda e: (f"{os.path.basename(e['dir'])}->{real_dir(e)}"
                           if e["link"] and real_dir(e) != os.path.basename(e["dir"]) else os.path.basename(e["dir"]))
        res.append({"species": sp, "subset": sub, "newest": newest,
                    "newest_dirs": sorted({real_dir(e) for e in g["newest_files"]}),
                    "used_dirs": sorted({shown(e) for e in g["used"]}),
                    "verdict": verdict})
    return res


#---[ Config (toml) check ]-----------------------------------------------------

def check_toml(toml_path: str, rawpath_override: str | None) -> dict:
    """What cmip_preemis would read for this config, per (group, subset, species,
    period): the file found, or missing. Each period is independent (as in
    cmip_preemis' process_subset); a species' periods are the group's `years`
    plus the `extra_years` its subset declares for it. Years covered by two
    found files are listed as overlaps (cmip_preemis stops on them, see
    check_sources in lib/cmip_process.py)."""
    import tomllib
    with open(toml_path, "rb") as f:
        cmip_key, d = next(iter(tomllib.load(f).items()))
    import getpass
    rawpath = rawpath_override or d["rawpath"].replace("{user}", getpass.getuser())   # as lib/cmip_config.expand_user
    if not rawpath_override and "{user}" in d["rawpath"]:
        print(f" Config  :  {{user}} -> {getpass.getuser()} in {toml_path} (rawpath)")
    prefix = "_".join([d["origin"], d["category"], d["target_mip"]])
    res = {"toml": toml_path, "cmip": cmip_key, "found": [], "missing": [], "derived": [],
           "scaling": [], "overlap": [], "group_dirs": set(), "used": set()}
    for group in ("anthro", "aviation", "bburning"):
        g = d.get(group)
        if not g:
            continue
        gdir = os.path.realpath(os.path.join(rawpath, g["path"]))
        res["group_dirs"].add(gdir)
        versions = [f"{prefix}_{v}_gn" for v in g["version"]]
        # [[derivespecies]] rules: a species built by cmip_preemis as a sum of others,
        # so its raw file is expected to be missing
        derived = {(r.get("suffix"), r.get("target")): len(r.get("from", [])) for r in g.get("derivespecies", [])}
        for subset_key, sub in g.get("subsets", {}).items():
            for species in sub["species"]:
                # Each period on its own, as cmip_preemis does since 2026-10-12
                # (before, it stopped at the first missing period of a species).
                # Same periods as cmip_process.periods_for
                spans = list(g["years"]) + [e["period"] for e in sub.get("extra_years", [])
                                            if species in e.get("species", [])]
                files_of_year: dict[int, list[str]] = {}
                for span in sorted(dict.fromkeys(spans), key=lambda p: p[:6]):
                    item = (group, subset_key, species, span)
                    path = build_raw_path(gdir, species, subset_key, versions, span)
                    fmap = sub.get("species_filename_map") or {}
                    nsrc = derived.get((sub.get("suffix"), fmap.get(species, species)))
                    if path is None and nsrc:
                        res["derived"].append(item + (nsrc,))
                    elif path is None:
                        res["missing"].append(item)
                    else:
                        res["found"].append(item + (path,))
                        res["used"].add(canon(path))
                        for yy in range(int(span[:4]), int(span[7:11]) + 1):
                            files_of_year.setdefault(yy, []).append(os.path.basename(path))
                # one year, one file (as cmip_process.check_sources)
                shared: dict[tuple, list[int]] = {}
                for yy, files in files_of_year.items():
                    if len(files) > 1:
                        shared.setdefault(tuple(files), []).append(yy)
                for files, yys in shared.items():
                    res["overlap"].append((group, subset_key, species, f"{min(yys)}-{max(yys)}", files))
        for rule in g.get("scaling", []):
            path = canon(os.path.join(gdir, rule["file"]))
            res["scaling"].append((group, rule["target"], path, os.path.isfile(path)))
            res["used"].add(path)
    return res


#---[ Report ]------------------------------------------------------------------

def print_inventory(entries, unparsed, dirs):
    print(pshow("\n ====== 1. Inventory and metadata ======"))
    if xr is None:
        print(pwarn(" xarray not available: metadata (source_id, dtype, compression) not checked"))
    for d in dirs:
        es = [e for e in entries if e["dir"] == d]
        print(pinfo(f"\n {d}") + f"  ({len(es)} files, {sum(e['link'] for e in es)} symlinks, "
                                  f"{fmt_size(sum(max(e['size'], 0) for e in es if not e['link']))})")
        for name in unparsed.get(d, []):
            print(pwarn(f"   not an input4MIPs name, skipped: {name}"))
        if not es:
            continue
        # Goal (1): does the folder hold what its name says? Content version =
        # source_id attribute; the folder name should be (part of) it.
        folder = os.path.basename(d)
        by_src: dict[str, list[dict]] = {}
        for e in es:
            by_src.setdefault(e["meta"]["source_id"] or "?", []).append(e)
        print("   content (source_id): " + ", ".join(
            f"{src}: {len(v)}" + (f" ({sum(x['link'] for x in v)} via symlink)" if any(x["link"] for x in v) else "")
            for src, v in sorted(by_src.items())))
        for src, v in sorted(by_src.items()):
            own = [x for x in v if not x["link"]]
            if src != "?" and own and folder not in src and src not in folder:
                print(pwarn(f"   FOLDER NAME vs CONTENT: {len(own)} own (non-symlink) files here have "
                            f"source_id={src}, not matching folder '{folder}'"))
        storage = {}
        for e in es:
            storage.setdefault(f"{e['meta']['dtype'] or '?'}/{e['meta']['zlib'] or '?'}", []).append(e)
        print("   storage (main variable): " + ", ".join(f"{k}: {len(v)}" for k, v in sorted(storage.items())))
        for e in es:
            if e["issues"]:
                print(pwarn(f"   {e['name']}"))
                for i in e["issues"]:
                    print(pwarn(f"      - {i}"))
        print("   largest:")
        for e in sorted(es, key=lambda e: e["size"], reverse=True)[:3]:
            print(f"     {fmt_size(e['size']):>8} [{e['meta']['dtype']}/{e['meta']['zlib']}] {e['name']}")


def print_families(entries, dirs, check_bytes, used_by, version_rows):
    """Per family of related folders: first the most recent version per species
    and whether the configs read it, then the file-by-file comparison.
    Appends one row per file to version_rows (species_versions.csv)."""
    print(pshow("\n ====== 2. Related folders (sharing species/subset/period) ======"))
    fmt = lambda k: f"{k[0]} {k[1]} {k[2] or '(no period)'}{k[3]}"
    for fam in families(entries, dirs):
        fam_name = " | ".join(os.path.basename(d) for d in fam)
        rows = compare_family(entries, fam, check_bytes)
        for r in rows:
            dates = [created(e) for e in r["per_dir"].values() if created(e)]
            for d, e in r["per_dir"].items():
                version_rows.append({
                    "family": fam_name, "species": e["species"], "subset": e["subset"],
                    "span": e["span"], "extra": e["extra"], "folder": os.path.basename(d),
                    "version": e["version"], "source_id": e["meta"]["source_id"],
                    "creation_date": created(e), "newest": bool(dates) and created(e) == max(dates),
                    "vs_other_folders": r["status"], "link": e["link"],
                    "read_by": " ".join(used_by.get(e["cpath"], [])),
                    "issues": " | ".join(e["issues"])})

        print(pinfo(f"\n {fam_name}"))
        print(pshow("   Most recent version per species (by creation_date) vs what the configs read:"))
        for n in newest_per_species(rows, used_by):
            color = pgood if n["verdict"].startswith("ok") else (
                    pinfo if n["verdict"].startswith("not read") else pwarn)
            print(f"     {n['species'] + ' ' + n['subset']:<50} newest: {','.join(n['newest_dirs']) or '?'}"
                  f" ({n['newest'][:10] or '?'})  read: {','.join(n['used_dirs']) or '-'}  " + color(n["verdict"]))
        if len(fam) == 1:
            continue
        print(pshow("   File by file:"))
        shared = [r for r in rows if r["status"] != "only in"]
        for status, color in (("identical", pgood), ("likely identical", pinfo),
                              ("unsure", pinfo), ("different", pwarn)):
            sel = [r for r in shared if r["status"] == status]
            print(color(f"   {status}: {len(sel)} files"))
            if status == "identical":
                continue
            # one line per species/subset and folder set; full detail in species_versions.csv
            grouped: dict[tuple, list[str]] = {}
            for r in sel:
                sp, sub, span, extra = r["key"]
                folders = " vs ".join(os.path.basename(d) for d in r["dirs"])
                grouped.setdefault((sp, sub, folders), []).append((span or "(no period)") + extra)
            for (sp, sub, folders), spans in sorted(grouped.items()):
                print(f"     {sp} {sub} [{folders}]: {', '.join(spans)}")
        if any(r["status"] == "unsure" for r in shared):
            print(pinfo("   (unsure = same size, different tracking_id: run `make bytes` to settle)"))
        for d in fam:
            only = [r for r in rows if r["status"] == "only in" and r["dirs"] == [d]]
            if not only:
                continue
            print(pinfo(f"   only in {os.path.basename(d)}: {len(only)} files"))
            grouped: dict[tuple, list[str]] = {}
            for r in only:
                sp, sub, span, extra = r["key"]
                grouped.setdefault((sp, sub), []).append((span or "(no period)") + extra)
            for (sp, sub), spans in sorted(grouped.items()):
                print(f"     {sp} {sub}: {', '.join(spans)}")


def print_toml(res, entries):
    scanned = {e["cdir"] for e in entries}
    if not res["group_dirs"] & scanned:
        print(pinfo(f"\n ====== 3. {res['toml']}: reads none of the scanned folders, skipped ======"))
        return
    print(pshow(f"\n ====== 3. {res['toml']} [{res['cmip']}] ======"))
    print(pgood(f"   found   : {len(res['found'])} species/periods"))
    by_path = {e["cpath"]: e for e in entries}
    for item in res["found"]:
        e = by_path.get(canon(item[4]))
        if e and e["issues"]:
            print(pwarn(f"   uses {e['name']}: " + "; ".join(e["issues"])))
    for group, subset, species, span in res["missing"]:
        print(pwarn(f"   MISSING : {group}/{subset} {species} {span}"))
    for group, subset, species, span, files in res["overlap"]:
        print(pwarn(f"   OVERLAP : {group}/{subset} {species} years {span} in {len(files)} files "
                    f"(cmip_preemis stops: move all but one aside):"))
        for f in files:
            print(pwarn(f"             {f}"))
    for group, subset, species, span, nsrc in res["derived"]:
        print(pinfo(f"   DERIVED : {group}/{subset} {species} {span} (no raw file: built by cmip_preemis "
                    f"as the sum of {nsrc} species, [[derivespecies]] rule)"))
    for group, target, path, ok in res["scaling"]:
        line = f"   scaling : {group} {target} <- {os.path.basename(path)} {'ok' if ok else 'MISSING'}"
        print(line if ok else pwarn(line))
    for gdir in sorted(res["group_dirs"] - scanned):
        print(pwarn(f"   folder not scanned (outside --raw?): {gdir}"))
    unused = [e for e in entries if e["cdir"] in res["group_dirs"]
              and e["cpath"] not in res["used"]]
    if unused:
        print(pinfo(f"   in its folders but never read ({len(unused)}):"))
        # Goal (3): explain why each file is not read
        read = {}
        for group, subset, species, span, path in res["found"]:
            read.setdefault((species, subset), []).append((span, os.path.basename(path)))
        missing = {}
        for _, sub, sp, span in res["missing"]:
            missing.setdefault((sp, sub), []).append(span)
        configured = set(missing) | set(read)
        years = lambda span: (int(span[:4]), int(span[7:11])) if span else None
        overlaps = lambda s, a: years(s) and years(s)[0] <= a[1] and a[0] <= years(s)[1]
        for e in unused:
            key = (e["species"], e["subset"])
            if e["extra"]:
                why = "non-standard name, never read (expected)"
            elif not e["span"]:
                why = "no period: auxiliary file (e.g. cell areas)"
            elif key not in configured:
                why = "SPECIES NOT IN CONFIG: candidate to add"
            else:
                a = years(e["span"])
                read_over = [f for s, f in read.get(key, []) if overlaps(s, a)]
                miss_over = [s for s in missing.get(key, []) if overlaps(s, a)]
                if read_over:
                    why = f"SHADOWED: years {a[0]}-{a[1]} are read from " + ", ".join(read_over)
                elif miss_over:
                    why = (f"PERIOD MISMATCH: the config looks for period(s) {', '.join(miss_over)}, "
                           f"this file covers {e['span']}, so these years are not produced")
                else:
                    why = "species in config, but these years are outside the config's periods"
            print(f"     {e['name']}")
            print((pwarn if why[:8].isupper() else pinfo)(f"        -> {why}"))


def write_csvs(entries, version_rows, outdir):
    """inventory.csv: one row per file with all metadata; species_versions.csv:
    one row per file within its family, with newest / identical / read_by."""
    os.makedirs(outdir, exist_ok=True)
    inv = os.path.join(outdir, "inventory.csv")
    fields = ["dir", "name", "species", "subset", "version", "span", "extra", "link", "realpath",
              "size"] + list(META_ATTRS) + ["var", "dtype", "zlib", "issues"]
    with open(inv, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for e in entries:
            w.writerow({**e, **e["meta"], "issues": " | ".join(e["issues"])})
    ver = os.path.join(outdir, "species_versions.csv")
    with open(ver, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(version_rows[0]) if version_rows else ["family"])
        w.writeheader()
        w.writerows(version_rows)
    print(pshow(f"\n wrote {inv}\n wrote {ver}"))


#---[ Main ]--------------------------------------------------------------------

if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Check raw input4MIPs folders (read-only).")
    p.add_argument("--raw", required=True,
                   help="parent folder: every subfolder with *.nc files is scanned (e.g. .../raw_emissions/cmip7)")
    p.add_argument("--toml", nargs="*", default=[], help="emicmip configs to check, e.g. etc/*cmip7.toml")
    p.add_argument("--rawpath", default=None, help="use instead of the configs' rawpath")
    p.add_argument("--bytes", action="store_true",
                   help="byte-compare same-size files across related folders (slow on large files)")
    p.add_argument("--only", nargs="*", default=[],
                   help="only scan subfolders whose name starts with one of these, e.g. BB4CMIP7 CEDS-CMIP")
    p.add_argument("--out", default=None, help="write inventory.csv and species_versions.csv to this folder")
    args = p.parse_args()

    raw = os.path.abspath(args.raw)
    here = os.path.dirname(os.path.abspath(__file__))
    dirs = sorted(os.path.join(raw, n) for n in os.listdir(raw)
                  if os.path.isdir(os.path.join(raw, n)) and os.path.join(raw, n) != here
                  and (not args.only or any(n.startswith(o) for o in args.only))
                  and glob.glob(os.path.join(raw, n, "*.nc")))
    print(pshow(f" Scanning {len(dirs)} folders under {raw}"
                + (f" (only: {' '.join(args.only)})" if args.only else "")))

    entries, unparsed = [], {}
    for d in dirs:
        print(pinfo(f"   reading headers: {os.path.basename(d)}"), flush=True)
        es, un = scan_dir(d)
        entries += es
        unparsed[d] = un

    # Configs first: section 2 needs to know which files they read
    toml_results = [check_toml(t, args.rawpath) for t in args.toml]
    used_by: dict[str, list[str]] = {}
    for res in toml_results:
        for path in res["used"]:
            used_by.setdefault(path, []).append(os.path.basename(res["toml"]))

    version_rows: list[dict] = []
    print_inventory(entries, unparsed, dirs)
    print_families(entries, dirs, args.bytes, used_by, version_rows)
    for res in toml_results:
        print_toml(res, entries)
    if args.out:
        write_csvs(entries, version_rows, args.out)
    print("")
