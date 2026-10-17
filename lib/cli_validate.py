#!/usr/bin/env bash
# ╭────────────────────────────────────────────────────────────────────────────╮
# │ cli_validate.py                                       (updated 2026-08)    │
# │                                                                            │
# │                                                                            │
# │ Author:  Ramiro Checa-Garcia (KNMI)                                        │
# │ Purpose: Parser for cmip_validate cli commands                             │
# │                                                                            │
# │ Info:  import lib.cli_validate as cli_validate  can be ok                  │
# │                                                                            │
# │ LLMs: Added layout_help and rewrote the description of cli args. Note:     │
# │       validate (all modules) was human designed, reviewed by LLMs. LLMs    │
# │       introduced conceptual errors in the validation, corrected by the     │
# │       developer (grid inconsistency, issues with thresholds and units)     │
# │                                                                            │
# ╰────────────────────────────────────────────────────────────────────────────╯

import argparse

# rich_argparse only colours the --help output: optional, plain argparse otherwise
try:
    from rich_argparse import RawDescriptionRichHelpFormatter
except ImportError:
    from argparse import RawDescriptionHelpFormatter as RawDescriptionRichHelpFormatter

from lib._version import __version__

OUTPUT_LAYOUT_HELP = """
Output layout:
  --tgz TGZ                 -> <outdir>/<name>/emissions_<group>_<year>.csv
                                one CSV per group (anthro/aviation/bburning)
                                and year found in the archive; <name>
                                defaults to the tag embedded in the nc
                                filenames (see --name).

  --compare TGZ_A TGZ_B     -> <outdir>/<name>/diff_stats_<group>_<year>.csv
                                <outdir>/<name>/diff_raw_<group>_<year>.csv
                                one pair of CSVs per group and year found
                                across both archives; <name> defaults to
                                "<tagA>_vs_<tagB>" (see --name).

  --timeseries DIR          -> <outdir>/<name>/timeseries_<group>.csv
                                <outdir>/<name>/timeseries_<group>.pdf
                                one CSV (all years) and one PDF (one page
                                per species/dataset) per group; <name>
                                defaults to the basename of DIR, so
                                --timeseries outs/validation/X writes
                                next to its inputs.
                                The total line is ALL/bbALL when present,
                                the single sector when there is only one,
                                otherwise the sum of the sectors.
     --seasonal [YEAR ...]  -> <outdir>/<name>/seasonal_<group>_<year>.pdf
                                two species/datasets per page: monthly
                                bars + annual bar, one row per sector.

  --plotcompare DIR [DIR..] -> <outdir>/<name>/plotcompare_<group>.pdf
                                <outdir>/<name>/plotcompare_summary.csv
                                DIR = --compare outputs with the same A;
                                <name> defaults to "<tagA>_plotcompare".

<outdir> defaults to outs/validation (see --outdir).

Contact: Ramiro Checa-Garcia (KNMI), https://github.com/rchg/emicmip/issues
"""

def cli_arguments_validate() -> argparse.Namespace:
    """Parse CLI arguments for cmip_validate, the tar-based validation tool.

    Exactly one of --tgz (recreate emissions_stats CSVs from one archive) or
    --compare (diff two archives against each other) must be given -- they
    are mutually exclusive, and argparse itself prints usage and exits(2) if
    neither (or both) is given.

    Also defines the output name override (--name) and processing options
    (--outdir, --keep, --verbose), shared by both modes.

    Returns:
        argparse.Namespace with the parsed arguments.
    """
    parser = argparse.ArgumentParser(
                        prog='Validation tool for CMIP emissions stats',
                        description='Recreates emissions_stats CSVs from an archived tar/tgz of already-processed NetCDF files, or diffs two such archives against each other, for comparing output across tool versions/datasets',
                        epilog=OUTPUT_LAYOUT_HELP,
                        formatter_class=RawDescriptionRichHelpFormatter)

    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--tgz',     action='store', default=None,
                       help="Path to a .tgz/.tar.gz/.tar file with the final NetCDF files of a specific year, as produced by cmip_preemis's --store tar output (or an ec:/... ecfs path, copied locally via ecp first). Recreates its emissions_stats CSVs -- see 'Output layout' below.")
    mode.add_argument('--compare', action='store', nargs=2, default=None, metavar=('TGZ_A', 'TGZ_B'),
                       help="Two .tgz/.tar.gz/.tar archives to diff against each other: TGZ_A is the dataset under test, TGZ_B is the reference/baseline it's compared against (e.g. a new tool version's output as A vs an old one as B, or historical vs scenariomip for an overlapping year). Either or both may be ec:/... ecfs paths. Matches files by (species, dataset, year) and reports both an emissions-stats (Tg) diff and a raw per-sector field diff -- see 'Output layout' below.")
    mode.add_argument('--timeseries', action='store', default=None, metavar='DIR',
                       help="Directory with per-year emissions_<group>_<year>.csv files (from cmip_preemis or --tgz). Joins all years into one time-series CSV per group and plots it: one PDF page per species/dataset, sectors with alpha=0.5 and the total as a solid line. Needs no cdo/nco -- see 'Output layout' below.")

    mode.add_argument('--plotcompare', action='store', nargs='+', default=None, metavar='DIR',
                       help="One or more output folders of --compare (<tagA>_vs_<tagB>) sharing the same archive A, one per reference B. Plots annual Tg per sector over the years (A solid, each reference dashed/dotted) and the relative difference to A, and writes a summary CSV of what is equal/close/different/only on one side. Needs no cdo/nco -- see 'Output layout' below.")

    parser.add_argument('--version',  action='version',    version=f'%(prog)s {__version__}')
    parser.add_argument('--verbose',  action='store_true', default=False,               help="To show info each step in processing.")
    parser.add_argument('--name',     action='store',      default=None,                help="Override the dataset-name subdirectory under --outdir (default: inferred from the tag(s) embedded in the nc filenames -- see 'Output layout' below).")
    parser.add_argument('--outdir',   action='store',      default="outs/validation",   help="Base directory the <name>/ subdirectory is created under (default: outs/validation) -- see 'Output layout' below.")
    parser.add_argument('--keep',     action='store_true', default=False,               help="Keep the extracted NetCDF files (in a temp dir) instead of removing them after processing.")
    parser.add_argument('--log',      action='store_true', default=False,               help="Only meaningful with --timeseries or --plotcompare. Logarithmic y axis (annual totals), useful when sectors differ by orders of magnitude.")
    parser.add_argument('--seasonal', action='store',      default=None, nargs='*', type=int, metavar='YEAR',
                         help="Only meaningful with --timeseries. Also draw seasonal-cycle pages (12 monthly bars + annual bar, one row per sector) for the given years, or for every year found if no year is given -- one PDF per group and year, so with a long historical directory prefer a few years.")

    legacy = parser.add_mutually_exclusive_group()
    legacy.add_argument('--legacyref', action='store_true', default=False,
                         help="Only meaningful with --compare. B is a legacy archive, A is current/under test (never the other way round). Applies old-suffix aliases (e.g. \"bb4-2-0\" -> \"bburning\") to B's filenames only, and lets a lone sector on B stand in for any of several current sectors on A -- compared by value and paired with whichever is numerically closest -- instead of being reported as a plain only-in-A/only-in-B mismatch. Off by default: with none of --legacyref/--legacyboth/--historicalref given, both archives are expected to use the same current suffix/sector naming throughout, and any mismatch is reported as-is. Mutually exclusive with --legacyboth/--historicalref.")
    legacy.add_argument('--legacyboth', action='store_true', default=False,
                         help="Only meaningful with --compare. Both A and B are legacy archives sharing the same old naming/sector conventions. Applies old-suffix aliases (e.g. \"bb4-2-0\" -> \"bburning\") to both sides' filenames, but -- unlike --legacyref -- does not try to match a lone sector against several others: with both sides equally legacy, plain same-name sector matching is expected to just work, so a sector mismatch here is reported as a real problem. Mutually exclusive with --legacyref/--historicalref.")
    legacy.add_argument('--historicalref', action='store_true', default=False,
                         help="Only meaningful with --compare. B is the historical archive, A is scenariomip (directional, like --legacyref -- B is always historical, never the other way round). Both archives use current-tool naming (this is not about old vs new tool versions), so mutually exclusive with --legacyref/--legacyboth. Excludes the known, accepted historical-vs-scenariomip differences (e.g. N2O only in scenariomip, the anthro-biof subset only in historical, bburning's extra sectors/species on each side) from the only-in-A/only-in-B rows, counts, and warnings -- they're listed separately as a reminder at the end instead of being reported as found differences.")
    parser.add_argument('--ecfs-cache', action='store', default=None, metavar='DIR',
                         help="Directory to fetch ec:/... ecfs archives into, persisting across runs (default: a fresh temp dir per run, always removed unless --keep). If an archive with the same name is already there, it's reused instead of re-fetched via ecp -- following ECMWF's guidance not to re-copy the same ecfs file repeatedly.")
    return parser.parse_args()
