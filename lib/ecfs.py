#!/usr/bin/env python3
# ╭────────────────────────────────────────────────────────────────────────────╮
# │ ecfs.py                                               (updated 2026-08)    │
# │                                                                            │
# │ Author:  Ramiro Checa-Garcia (KNMI)                                        │
# │ Purpose: Transparently get ec:/... (ECMWF ecfs) archive paths to a         │
# │          local copy via `ecp`, so cmip_validate can be pointed directly    │
# │          at an ecfs-stored tar without a manual ecp step first.            │
# │                                                                            │
# │ Implemented based on how developer programmed this in an ocaml tool.       │
# │                                                                            │
# │ Notes on ECFS usage this module follows (see ECMWF's "Using ECFS in        │
# │ scripts" documentation):                                                   │
# │  - We always transfer exactly one archive with a single `ecp src dst`      │
# │    without wildcards/multiple sourcelist cases. Reason beyond saturation   │
# │    is a better report of issues for each isolated transfer.                │
# │  - `--order=tape` (it is an option recommended only when extraction many   │
# │  - files present in a tape). This doesn't apply to our case.               │
# │  - ECFS best practice is to avoid re-fetching the same file repeatedly;    │
# │    see resolve_local_path's `dest_dir` for the check-before-fetch this     │
# │    enables.                                                                │
# │ LLMs: reviewed code and added comment,refactor using ECFS_PREFIX           │
# ╰────────────────────────────────────────────────────────────────────────────╯

import os
import sys
import shutil
import subprocess

import lib.aux as aux

ECFS_PREFIX = "ec:/"


def is_ecfs_path(path: str) -> bool:
    """Whether `path` is an ECMWF ecfs path (starts with "ec:/")."""
    return path.startswith(ECFS_PREFIX)


def resolve_local_path(path: str, dest_dir: str) -> str:
    """Return a local filesystem path usable for `tarfile.open()`.

    If `path` is a plain local path, it's returned unchanged. If it's an
    ecfs path (see is_ecfs_path), it's fetched into `dest_dir` via `ecp`
    first -- tarfile can't read ecfs paths directly.

    Before fetching, checks whether `dest_dir` already has a readable file
    with the same basename and reuses it instead -- this is the check ECMWF
    recommends before any ecfs get (avoid re-copying the same file
    repeatedly), and is exactly what happens if the caller passes a
    persistent `dest_dir` across repeated runs (e.g. cmip_validate's
    --ecfs-cache) rather than a fresh temp dir each time. Whether it fetched
    or reused a cached copy is always printed -- this is state the caller
    needs to see, not verbose-only chatter.

    Args:
        path: local path or ec:/... ecfs path
        dest_dir: directory to fetch an ecfs file into (created if needed);
            pass a persistent directory to cache across runs, or a fresh
            temp dir for a one-off, always-refetched download

    Returns:
        Local filesystem path to operate on.
    """
    if not is_ecfs_path(path):
        return path

    os.makedirs(dest_dir, exist_ok=True)
    local_path = os.path.join(dest_dir, os.path.basename(path))

    if os.path.isfile(local_path) and os.access(local_path, os.R_OK):
        print(aux.pinfo(f"  > [ecfs] Found existing local copy, not re-fetching: {local_path}"))
        return local_path

    if shutil.which("ecp") is None:
        print(aux.perror(f"\n'{path}' is an ecfs path but 'ecp' is not on PATH."))
        print(aux.pinfo(" ecp normally ships with the ECMWF default environment; check your module setup."))
        sys.exit(1)

    print(aux.pinfo(f"  > [ecfs] Fetching {path} -> {local_path} via ecp"))
    result = subprocess.run(["ecp", path, local_path])

    if result.returncode != 0 or not os.path.isfile(local_path):
        print(aux.perror(f"\nFailed to fetch {path} via ecp (exit code {result.returncode})."))
        sys.exit(1)

    return local_path
