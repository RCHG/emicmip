#!/usr/bin/env python3
# ╭────────────────────────────────────────────────────────────────────────────╮
# │ cli_check.py                                          (updated 2026-10)    │
# │                                                                            │
# │ Author:  Ramiro Checa-Garcia (KNMI)                                        │
# │ Purpose: Parser for cmip_check cli commands                                │
# │                                                                            │
# │ Info:  like cli_validate.py, kept free of 3.10+ syntax so it can run       │
# │        before server_env has checked the interpreter version.              │
# │                                                                            │
# │ LLMs:  Programmed with assistance of LLMs, which added rich_argparse, help │
# │        and description according to developer directive.                   │
# │                                                                            │
# ╰────────────────────────────────────────────────────────────────────────────╯

import argparse

# rich_argparse only colours the --help output: optional, plain argparse otherwise
try:
    from rich_argparse import RawDescriptionRichHelpFormatter
except ImportError:
    from argparse import RawDescriptionHelpFormatter as RawDescriptionRichHelpFormatter

from lib._version import __version__

CHECK_HELP = """
What is checked:
  quick (default)   with --toml: one `els -l` (or ls, for a cp store) of the
                    toml's tar_store path, plus the local outpath. Per year of
                    the toml: is the tar there, plain or -ec3 (EC-Earth3, made
                    with -e) or both, its date and size; local nc/CSV files
                    and local tars. Nothing is downloaded.

  --deep            additionally copies the tars of --years (ecp or cp, cached
                    with --ecfs-cache) and reads the toml bundled inside: the
                    exact command line, emicmip version, creation date (tars
                    made after 2026-10), the raw-data version of each group,
                    whether it matches the given toml, and which groups and
                    subsets the tar holds.

  --tarpath PATH    one tar by its full path, e.g.
                    ec:/<user>/emissions/cmip7scenariomip/m/ScenarioMIPm-a_2024.tar,
                    always read in depth (--deep). No --toml needed: the store
                    is the tar's folder, and no local outpath is checked. With
                    --years, the same name for other years. With --toml, that
                    toml is only a reference, compared with the toml inside
                    the tar.

Contact: Ramiro Checa-Garcia (KNMI), https://github.com/rchg/emicmip/issues
"""


def cli_arguments_check():
    """Parse CLI arguments for cmip_check.

    Returns:
        argparse.Namespace with the parsed arguments.
    """
    parser = argparse.ArgumentParser(
                        prog='cmip_check',
                        description='Checks which years of a config (etc/*.toml) are already produced: tars in the store, local files, and (with --deep) the options each tar was made with',
                        epilog=CHECK_HELP,
                        formatter_class=RawDescriptionRichHelpFormatter)

    parser.add_argument('--toml',     action='store',      default=None,
                        help="Config file, e.g. etc/historical_cmip7.toml. Not needed with --tarpath.")
    parser.add_argument('--version',  action='version',    version=f'%(prog)s {__version__}')
    parser.add_argument('--verbose',  action='store_true', default=False, help="To show info each step in processing.")
    parser.add_argument('--years',    action='store',      default=None,
                        help="Restrict to these years: 1850,1900 or 1850-1910 or a mix (like the Makefile). Required with --deep.")
    parser.add_argument('--deep',     action='store_true', default=False,
                        help="Fetch the tars of --years and read the toml and file list inside them -- see below.")
    parser.add_argument('--tarpath',  action='store',      default=None, metavar='PATH',
                        help="Check one tar by its full path (ec:/.../ScenarioMIPm-a_2024.tar): no --toml needed, the store is its folder. Also sets --years if not given.")
    parser.add_argument('--outpath',  action='store',      default=None,
                        help="Local output path to look at instead of the toml's outpath.")
    parser.add_argument('--ecfs-cache', action='store',    default=None, metavar='DIR',
                        help="Only with --deep. Directory to fetch ec:/... tars into, reused across runs (default: a temp dir removed at the end unless --keep).")
    parser.add_argument('--keep',     action='store_true', default=False,
                        help="Only with --deep. Keep the temp dir with fetched tars.")
    return parser.parse_args()
