#!/usr/bin/env python3
# ╭────────────────────────────────────────────────────────────────────────────╮
# │ server_env.py                                         (updated 2026-08)    │
# │                                                                            │
# │ Author:  Ramiro Checa-Garcia (KNMI)                                        │
# │ Purpose: Preflight check for the server environment both cmip_preemis and  │
# │          cmip_validate run in (mostly module-based HPC systems, where      │
# │          cdo/nco/eccodes/python aren't on PATH until the right modules     │
# │          are loaded)                                                       │
# │                                                                            │
# │ Info:  Deliberately uses only stdlib and no 3.10+ syntax (no `X | Y`       │
# │        annotations, no builtin generics), and is never imported by any     │
# │        other module here -- this is the one module either entry point      │
# │        can safely import and run *before* confirming the interpreter is    │
# │        new enough for the rest of the codebase (lib/cmip_process.py,       │
# │        lib/validate_tar.py, etc use 3.10+ syntax that would raise a        │
# │        confusing TypeError at import time on an older interpreter,         │
# │        instead of this module's clear message).                            │
# │ LLMs: Developer has a previous version for this feature but LLMs proposed  │
# │       several useful changes and now it is mostly the version of AI.       │
# ╰────────────────────────────────────────────────────────────────────────────╯

# IMPORTANT: do NOT add `from __future__ import annotations` here, even
# though it looks harmless/helpful. That statement itself needs Python >= 3.7
# just to parse -- on the servers this tool actually runs on, the bare
# `python3` on PATH before any module is loaded is 3.6.8, so the import
# raises `SyntaxError: future feature annotations is not defined` before
# check_environment() ever runs, i.e. before we can print the friendly
# "module load python3" message. That defeats the entire point of this file.
# This module has no annotations that need it anyway. Once the servers'
# actual default python3 (not the module-loaded one) is upgraded past 3.7,
# this restriction can be dropped -- but as of 2026-08 it still applies.

import sys
import shutil

MIN_PYTHON = (3, 11)

# command -> (module to load, human label for the message)
REQUIRED_COMMANDS = {
    "cdo":     ("cdo",            "cdo"),
    "ncks":    ("nco",            "ncks (part of nco)"),
    "grib_ls": ("ecmwf-toolbox",  "grib_ls (part of ecmwf-toolbox)"),
}


def check_environment(verbose=False, commands=True):
    """Check the runtime has everything cmip_preemis/cmip_validate need.

    Checks the running interpreter's version and, via shutil.which, that
    cdo, ncks (representative of the nco toolset) and grib_ls (from
    ecmwf-toolbox) are on PATH -- the module set this tool expects on the
    servers it mostly runs on.

    Args:
        verbose: print a confirmation line for each check that passes
        commands: also check the external commands; False for modes that
            only read CSVs (cmip_validate --timeseries)

    Returns:
        List of human-readable problem strings, each ending with the
        `module load ...` command that fixes it; empty if everything's fine.
    """
    problems = []

    if sys.version_info < MIN_PYTHON:
        got = ".".join(str(v) for v in sys.version_info[:3])
        need = ".".join(str(v) for v in MIN_PYTHON)
        problems.append(f"Python {got} found, need >= {need}. Fix: module load python3")
    elif verbose:
        got = ".".join(str(v) for v in sys.version_info[:3])
        print(f"  > [env] Python {got} OK")

    for cmd, (module, label) in (REQUIRED_COMMANDS.items() if commands else []):
        found = shutil.which(cmd)
        if found is None:
            problems.append(f"'{cmd}' not found on PATH ({label}). Fix: module load {module}")
        elif verbose:
            print(f"  > [env] {label} found: {found}")

    return problems


def print_problems_and_exit(problems, tool_name="this tool"):
    """Print `problems` (see check_environment) as a single actionable block and exit(1).

    Args:
        problems: list of problem strings from check_environment
        tool_name: name of the calling entry point, for the message
            (e.g. "cmip_preemis" or "cmip_validate")
    """
    print(f"\nMissing requirements for {tool_name}:")
    for p in problems:
        print(f"  - {p}")
    print("\nLoad the modules above (or confirm they're already loaded) and re-run.")
    sys.exit(1)
