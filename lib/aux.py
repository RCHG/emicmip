#!/usr/bin/env bash
# ╭────────────────────────────────────────────────────────────────────────────╮
# │ aux.py                                                (updated 2025-04-09) │
# │                                                                            │
# │                                                                            │
# │ Author:  Ramiro Checa-Garcia (KNMI)                                        │
# │ Purpose: Auxiliary functions/classes/variables                             │
# │          Extended from previous own tools aux.py module                    │
# │ Info:  import lib.aux as aux  can be ok                                    │
# │ LLMs:  module created by human except: banner, round_sig, default_tmp_root │
# │        function comments/docstrings added by LLMs under developer request. │
# ╰────────────────────────────────────────────────────────────────────────────╯

import os
import io
import math
import glob
import shutil
import tarfile
import argparse
import subprocess

# Terminal color definitions
class fg:
    BLACK   = '\033[30m'
    RED     = '\033[31m'
    GREEN   = '\033[32m'
    YELLOW  = '\033[33m'
    BLUE    = '\033[34m'
    MAGENTA = '\033[35m'
    CYAN    = '\033[36m'
    WHITE   = '\033[37m'
    RESET   = '\033[39m'

class bg:
    BLACK   = '\033[40m'
    RED     = '\033[41m'
    GREEN   = '\033[42m'
    YELLOW  = '\033[43m'
    BLUE    = '\033[44m'
    MAGENTA = '\033[45m'
    CYAN    = '\033[46m'
    WHITE   = '\033[47m'
    RESET   = '\033[49m'

class style:
    BRIGHT    = '\033[1m'
    DIM       = '\033[2m'
    NORMAL    = '\033[22m'
    RESET_ALL = '\033[0m'


def pshow(sshow: str) -> str:
    """Wrap `sshow` in cyan ANSI color codes, for section/progress headers."""
    return fg.CYAN+sshow+fg.RESET

def pinfo(sinfo: str) -> str:
    """Wrap `sinfo` in blue ANSI color codes, for informational messages."""
    return fg.BLUE+sinfo+fg.RESET

def pgood(sgood: str) -> str:
    """Wrap `sgood` in green ANSI color codes, for confirmed-ok results."""
    return fg.GREEN+sgood+fg.RESET

def ppath(spath: str) -> str:
    """Wrap `spath` in magenta ANSI color codes, for filesystem paths."""
    return fg.MAGENTA+spath+fg.RESET

def pwarn(swarn: str) -> str:
    """Wrap `swarn` in yellow ANSI color codes, for warnings."""
    return fg.YELLOW+swarn+fg.RESET

def perror(swarn: str) -> str:
    """Wrap `swarn` in red ANSI color codes, for errors."""
    return fg.RED+swarn+fg.RESET

_BANNER = r"""
                    _                      _
  ___   _ __ ___   (_)   ___   _ __ ___   (_)  _ __
 / _ \ | '_ ` _ \  | |  / __| | '_ ` _ \  | | | '_ \
|  __/ | | | | | | | | | (__  | | | | | | | | | |_) |
 \___| |_| |_| |_| |_|  \___| |_| |_| |_| |_| | .__/
                                              |_|
"""


def banner(tool: str) -> str:
    """ASCII-art name of the project, then a rule with the tool and the
    arguments it was called with: ──[ cmip_check --deep --years 2024 ... ]──.

    Printed in cyan at the start of cmip_preemis, cmip_check and cmip_validate,
    right after the arguments are parsed (only stdlib is needed here).
    """
    import sys, shlex
    label = f"[ {tool} {shlex.join(sys.argv[1:])} ]" if len(sys.argv) > 1 else f"[ {tool} ]"
    return pshow(_BANNER) + pinfo(f" ──{label}".ljust(79, "─")) + "\n"

def round_sig(x: float, sig: int) -> float:
    """Round `x` to `sig` significant figures.

    Shared by emissions_stats.py (Tg totals, spanning trace species at
    ~1e-4 next to CO2 at ~1e4) and compare_tar.py (raw diff diagnostics,
    spanning real Tg-scale differences down to ~1e-16/1e-20 float noise) --
    both need a fixed *significant-figure* count rather than a fixed decimal
    count, which would either truncate real values or print noise digits
    depending which end of the magnitude range it's applied to. Each caller
    passes its own sig-figs constant; there's no shared "reasonable
    default" across such different magnitude ranges.
    """
    if x == 0:
        return 0.0
    return round(x, sig - 1 - int(math.floor(math.log10(abs(x)))))


def default_tmp_root() -> str | None:
    """Preferred root directory for large temp extraction dirs on HPC systems.

    tempfile.mkdtemp() defaults to $TMPDIR (falling back to /tmp etc.),
    which on these HPC systems is often a small tmpfs/quota-limited
    partition -- too small for the tar/tgz archives cmip_validate extracts.
    If $SCRATCH is set and exists, prefer a "_tempfiles" subdirectory of it
    instead (created if missing, so scratch stays tidy rather than filling
    up with bare "cmip_validate_ecfs_..." dirs at its root); otherwise
    return None so callers fall back to tempfile's normal ($TMPDIR-based)
    default.
    """
    scratch = os.environ.get("SCRATCH")
    if not scratch or not os.path.isdir(scratch):
        return None
    tmp_root = os.path.join(scratch, "_tempfiles")
    ensure_dir(tmp_root, "scratch tempfiles")
    return tmp_root

def ensure_dir(path: str, label: str = "") -> None:
    """Create a local directory `path` upfront if it doesn't exist yet.

    Meant to be called early (right after config/paths are resolved, before
    any processing starts) so a missing target directory is reported and
    fixed immediately, instead of surfacing as a bare "No such file or
    directory" from `cp`/`shutil.copy` at the very end of a run.

    Only for real local filesystem paths -- do not call this on remote/ECFS
    targets (e.g. "ec:/..." paths used with the "ecp" command), which this
    process cannot create with os.makedirs.
    """
    if not os.path.isdir(path):
        tag = f" ({label})" if label else ""
        print(pwarn(f" Target directory{tag} does not exist yet, creating it: ") + ppath(path))
        os.makedirs(path, exist_ok=True)

def validate_paths(rawpath: dict, propath: str, outpath: str, tar_store: dict = None) -> None:
    """Preflight-check every path a run depends on, before any processing starts.

    Args:
        rawpath: group -> raw-input root path (see cmip_preemis.parse_args).
            Each one must already exist -- nothing can be produced without
            it, so a missing raw root is treated as fatal (unlike a missing
            file for one species, which process_subset already skips with
            just a warning).
        propath: working directory for temp files; owned by this tool, so
            it's created automatically if missing.
        outpath: final output directory; owned by this tool, so it's
            created automatically if missing (this is the fix for the
            "cp: cannot create regular file ... No such file or directory"
            failure seen when a toml pointed outpath/tar_store at a
            directory that hadn't been created yet).
        tar_store: datainfo["tar_store"] dict ({"cmd": ..., "path": ...}),
            or None. Only checked/created when cmd == "cp" (a local copy);
            remote/ECFS targets (e.g. cmd == "ecp" to an "ec:/..." path)
            are left alone since this process can't create them.
    """
    missing_raw = [(group, path) for group, path in rawpath.items() if not os.path.isdir(path)]
    if missing_raw:
        for group, path in missing_raw:
            print(perror(f" Raw input path for '{group}' does not exist: ") + ppath(path))
        print(perror(" Fix the path (or --rawpath override) and re-run."))
        raise SystemExit(1)

    ensure_dir(propath, "processing/temp")
    ensure_dir(outpath, "output")

    if tar_store and tar_store.get("cmd") == "cp":
        ensure_dir(tar_store["path"], "tar store")

# Given "YYYYDD-YYYYDD": give list of years between fst YYYY and snd YYYY.
# example "178403-178602" -> 1784 1785 1786
def get_list_years(yrs: str) -> range:
    """Parse a "YYYYMM-YYYYMM" year-interval string into a range of years.

    Args:
        yrs: interval string, e.g. "178403-178602"

    Returns:
        range covering every year from the first to the last interval year,
        inclusive, e.g. "178403-178602" -> range(1784, 1787)
    """
    ini=int(yrs.split("-")[0][0:4])
    fin=int(yrs.split("-")[1][0:4])

    return range(ini, fin+1)


def config_years(datainfo: dict, groups: list[str] | None = None) -> list[int]:
    """Every year a config covers: the union of the groups' "years" intervals
    and of their subsets' extra_years periods, i.e. the years process_group
    handles when no --years is given.

    Args:
        datainfo: config dict for one CMIP version
        groups: config group keys to include ("anthro", "aviation",
            "bburning"); None means all of them present in the config

    Returns:
        Sorted list of years.
    """
    if groups is None:
        groups = ["anthro", "aviation", "bburning"]
    years = set()
    for group in groups:
        gconf = datainfo.get(group, {})
        spans = list(gconf.get("years", []))
        for subset in gconf.get("subsets", {}).values():
            spans += [e["period"] for e in subset.get("extra_years", []) if "period" in e]
        for span in spans:
            years.update(get_list_years(span))
    return sorted(years)

NC_DEFLATE_LEVEL = 4


def compress_nc(path: str, level: int = NC_DEFLATE_LEVEL) -> bool:
    """Rewrite a NetCDF file as netCDF4 with deflate compression (+ shuffle),
    in place. Lossless: values, attributes and coordinates are unchanged;
    readers (cdo, nco, xarray, the emissions pre-processor) decompress
    transparently. Uses `ncks -4 -L` (nco is already a requirement).

    Returns:
        True if compressed; False if ncks failed (the original file is kept).
    """
    tmp = path + ".zip.tmp"
    try:
        result = subprocess.run(["ncks", "-O", "-4", "-L", str(level), path, tmp],
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    except OSError as e:                       # ncks not on PATH: keep the file, don't stop the tar
        print(pwarn(f"    Warning: could not compress {path} ({e}); kept as is"))
        return False
    if result.returncode != 0 or not os.path.isfile(tmp):
        print(pwarn(f"    Warning: could not compress {path} (ncks exit {result.returncode}); kept as is"))
        if result.stdout:
            print(result.stdout)
        if os.path.isfile(tmp):
            os.remove(tmp)
        return False
    os.replace(tmp, path)
    return True


def compress_year_files(files: list[str], year: str) -> None:
    """Compress a year's final files (see compress_nc) and report the saving.
    Files already compressed are rewritten at the same level, so re-running is
    harmless."""
    before = sum(os.path.getsize(f) for f in files if os.path.isfile(f))
    ok = sum(compress_nc(f) for f in files if os.path.isfile(f))
    after = sum(os.path.getsize(f) for f in files if os.path.isfile(f))
    if before:
        print(pshow(f"** Compressed {ok}/{len(files)} files of {year}: "
                    f"{before/1024**3:.2f} GB -> {after/1024**3:.2f} GB ({100*after/before:.0f}%)"))


def tag_provenance(files: list[str], dataset: str, config: str) -> None:
    """Write emicmip's provenance into every final file, as global attributes
    (emicmip_version, emicmip_dataset, emicmip_config), so a file taken out
    of its tar still says what made it. `ncatted -h`: history is not touched."""
    from lib._version import __version__
    for f in files:
        cmd = ["ncatted", "-O", "-h",
               "-a", f"emicmip_version,global,o,c,{__version__}",
               "-a", f"emicmip_dataset,global,o,c,{dataset}",
               "-a", f"emicmip_config,global,o,c,{config}", f]
        try:
            result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        except OSError as e:                   # ncatted not on PATH: warn, don't stop the tar
            print(pwarn(f"    Warning: could not tag {f} ({e})"))
            continue
        if result.returncode != 0:
            print(pwarn(f"    Warning: could not tag {f} (ncatted exit {result.returncode})"))
            if result.stdout:
                print(result.stdout)


def tar_store_byyear(args: argparse.Namespace, datainfo: dict, lstore_nc: list[str], lyears: list[str],
                      toml_path: str = None, toml_header: str = None) -> None:
    """Tar the stored nc files for each requested year, optionally copy the
    tar to the configured remote store, and print example emission-spec
    entries for the resulting layout.

    Args:
        args: parsed CLI arguments (see lib.cli.cli_arguments); uses
            args.ecearth3, args.store and args.nccompress
        datainfo: config dict for the selected CMIP version; uses
            datainfo["tar_common"], datainfo["outputname"], datainfo["tar_store"]
        lstore_nc: paths of the nc files created/found by process_group,
            across every requested group
        lyears: years to tar, as strings
        toml_path: path to the toml config file this run used; if given,
            it's bundled into every year's tar alongside the nc files and
            emissions_stats CSVs, so a shipped tar carries the exact config
            that produced it
        toml_header: text (e.g. "# run as: ...\\n# version: ...\\n") prepended
            to the bundled toml's contents inside the tar -- the file on
            disk is never modified, only the copy written into the tar
    """
    toml_abspath = os.path.abspath(toml_path) if toml_path is not None else None

    def tar_as_cmd(lfiles: list[str], ltaro: list[str], tarfname: str) -> str:
        """Copy `lfiles` to their `ltaro` names, then tar them as `tarfname`.

        Note: not currently called anywhere in tar_store_byyear; its body
        also references an undefined name `ltar` rather than the `ltaro`
        parameter, so it would fail if invoked as-is.
        """
        # Store files in tar without fullpath
        for a,b in zip(lfiles, ltar):
            print(pshow(f"Copy {a} to {b} before tar"))
            shutil.copy2(a,b)

        cmd_tar = "tar -cf "+tarfname+" "+" ".join(ltar)
        cmd_rm  = "rm " ".join(ltar)"
        print(pshow(f"Run: {cmd_tar}"))
        os.system(cmd_tar)
        print(pshow(f"Remove temp files: {cmd_rm}"))
        os.system(cmd_rm)
        return tarfname

    def tarfname(name: str) -> str:
        """Derive a tar filename from one stored nc path (drop its trailing
        `_<year>` segment and swap the extension for `.tar`)."""
        tarf = os.path.basename(name)
        tard = os.path.dirname(name)
        tarf = "_".join(tarf.split("_")[0:-1])+".tar"
        return os.path.join(tard,tarf)

    for year in lyears:
        tar_store=False       # Local Variable 
        lstore_nc_year = [] 
        if len(lstore_nc) > 0: 
            for nc in  lstore_nc:
                ncyear = os.path.splitext(nc)[0].split('_')[-1] 
                if ncyear == year:
                    lstore_nc_year.append(nc) 
            tarf_ini = tarfname(lstore_nc[0])
            if len(lstore_nc_year) > 0:
                tar_store= True
            else:
                print(pwarn(f"--> We did not find new created nc files for year {year}"))
                continue 

        if tar_store==True:
            # In principle to avoid names with full path inside the tar file we move 
            # temporaly to os.path.dirname. Maybe -C option is equivalent but not sure 
            # for explicit list of files.
            if args.ecearth3:
                tar_common = datainfo["tar_common"]+"-ec3" # we add in the name that it is ec3 convention
            else:
                tar_common = datainfo["tar_common"] 

            return_dir = os.getcwd()
            tardir     = os.path.dirname(tarf_ini)
            tarf_inib  = os.path.basename(tarf_ini) 
            tarf_name  = "_".join([tar_common, year])+".tar"

            lstore_base = [os.path.basename(a) for a in lstore_nc_year]
            lstore_tar  = [a.replace(datainfo["outputname"],tar_common) for a in lstore_base]
            os.chdir(tardir)

            # Provenance attributes in every file of the year (dataset = tar name
            # without the year, as the files are named inside the tar)
            tag_provenance(lstore_base, tar_common,
                           os.path.basename(toml_path) if toml_path else "")

            # --nccompress: compress every file of the year before it goes into the
            # tar (last step, after scaling/derive/ncatted have modified the files)
            if getattr(args, "nccompress", False):
                compress_year_files(lstore_base, year)

            print(pshow(f"** Creating a tar file with this year ..."))
            with tarfile.open(tarf_name, "w") as tar:
                for src, new in zip(lstore_base, lstore_tar):
                    print(pshow(f"Store {src} with name {new} inside tar"))
                    tar.add(src, arcname=new)

                # Also bundle this year's emissions_stats CSVs (written by
                # lib.emissions_stats.write_group_stats into
                # <outpath>/emissions_stats/, i.e. tardir/emissions_stats/
                # since tardir == outpath), one per processed group -- these
                # were previously left out of the tar entirely.
                stats_dir = "emissions_stats"
                stats_pattern = os.path.join(stats_dir, f"emissions_*_{year}.csv")
                for csv_path in sorted(glob.glob(stats_pattern)):
                    arcname = os.path.join(stats_dir, os.path.basename(csv_path))
                    print(pshow(f"Store {csv_path} with name {arcname} inside tar"))
                    tar.add(csv_path, arcname=arcname)

                # Also bundle the toml config that produced this run, so a
                # shipped tar is self-describing (resolved to an absolute
                # path before the os.chdir(tardir) above, since toml_path
                # may be a relative path from the original cwd). A header
                # (run command + tool version, see toml_header) is prepended
                # to the copy written into the tar -- the file on disk is
                # never touched.
                if toml_path is not None:
                    toml_arcname = os.path.basename(toml_path)
                    print(pshow(f"Store {toml_path} with name {toml_arcname} inside tar"))
                    with open(toml_abspath, "r") as f:
                        toml_content = f.read()
                    if toml_header:
                        toml_content = toml_header + toml_content
                    toml_bytes = toml_content.encode("utf-8")
                    toml_info = tarfile.TarInfo(name=toml_arcname)
                    toml_info.size = len(toml_bytes)
                    toml_info.mtime = os.path.getmtime(toml_abspath)
                    tar.addfile(toml_info, io.BytesIO(toml_bytes))

            os.chdir(return_dir)

            if args.store in ["both","year"]:
                if os.path.isfile(os.path.join(tardir, tarf_name)):
                    print(pshow(f"** Tar completed {tarf_name} copying to store..."))
                    xx=datainfo["tar_store"]
                    local_tar = os.path.join(tardir, tarf_name)
                    remote_tar = os.path.join(xx["path"], tarf_name)
                    cmd = [xx["cmd"]]
                    if getattr(args, "overwrite", False) and xx["cmd"] == "ecp":
                        cmd.append("-o")               # ecp does not overwrite by default (-n)
                    cmd += [local_tar, remote_tar]
                    print(pshow(f"  using {' '.join(cmd)}"))
                    copied = subprocess.run(cmd).returncode == 0
                    if not copied:
                        print(perror(f"  Copy to the store FAILED for {tarf_name}: the tar stays in {tardir}"
                                     + (" and nothing is removed (--cleanafter)." if getattr(args, "cleanafter", False) else ".")))
                    elif getattr(args, "cleanafter", False):
                        # --cleanafter: the tar is in the store, so this year's final nc
                        # files and the local tar can go (the stats CSVs are kept)
                        nremoved = 0
                        for nc in lstore_base:
                            path = os.path.join(tardir, nc)
                            if os.path.isfile(path):
                                os.remove(path); nremoved += 1
                        os.remove(local_tar)
                        print(pgood(f"  removed {nremoved} nc files + local tar "
                                    f"(note: tar safely stored in {remote_tar})"))


    # Ready-to-paste entries for the emission-specification files. Built from the
    # config and from what was actually written: tar name (with -ec3 under
    # --ecearth3, as in the tar made above), resolution tag and biomass-burning
    # suffix of each group. "file:" only for a local store; an ECFS path
    # ("ec:/...") already is a source scheme.
    tar_common = datainfo["tar_common"] + ("-ec3" if args.ecearth3 else "")
    s1 = datainfo["tar_store"]["path"]
    s2 = tar_common + "_{year}.tar"
    scheme = "" if s1.startswith("ec:") else "file:"

    def entry(group: str, suffix: str | None = None):
        gcfg = datainfo.get(group)
        if not gcfg:
            return None
        if suffix is None:                       # suffix of the group's first subset
            suffix = next(iter(gcfg["subsets"].values()))["suffix"]
        return (f"src={scheme}{s1}{s2}#{tar_common}_{gcfg['resol'][1]}_{suffix}"
                "_{xfvar|_tag|species}_{year}.nc")

    entries = [(" -- anthro. surface  :", entry("anthro", "anthro-surf"))]
    if args.ecearth3:
        entries += [(" -- (above for BC/OC):", entry("anthro", "anthro-surf-ecearth")),
                    (" -- biofuel BC/OC    :", entry("anthro", "anthro-biof"))]
    entries += [(" -- anthro. aviation :", entry("aviation", "anthro-air")),
                (" -- biomass burning  :", entry("bburning"))]

    print("\n======================================================\n")
    print(pinfo(f" Examples of entries for emission specification files"))
    for label, text in entries:
        if text:
            print(pshow(label))
            print(ppath(f"     {text}"))
    print("")

    if args.store in ["both","year"]:
        print(pinfo(f" We moved the tar files to {datainfo['tar_store']}"))
    else:
        print(perror(f" Note: that --store was not set in command line"))
        print(perror(f"       so files where not copied to {datainfo['tar_store']}"))
        print(pinfo( f"       for each tarfile {s2} you can now")) 
        xx=datainfo["tar_store"]
        cmd_store = xx["cmd"]+" "+s2+" "+os.path.join(xx["path"], s2)
        print(ppath(f"        {cmd_store}"))
    print("\n======================================================\n")

    return 


