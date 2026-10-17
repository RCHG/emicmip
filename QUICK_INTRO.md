# emicmip: quick introduction

```
                    _                      _
  ___   _ __ ___   (_)   ___   _ __ ___   (_)  _ __
 / _ \ | '_ ` _ \  | |  / __| | '_ ` _ \  | | | '_ \
|  __/ | | | | | | | | | (__  | | | | | | | | | |_) |
 \___| |_| |_| |_| |_|  \___| |_| |_| |_| |_| | .__/
                                              |_|
```

Examples of the three tools, of `make` and of the stand-alone checks in `tools/`. Full
documentation: https://rchg.github.io/emicmip/. Every tool prints its options with `-h`.
A manual is in progress: contact the developer for questions or for a beta version.

## Producing datasets (`cmip_preemis`)

We recommend to use the --years otherwise the tool would process the full set of availiable
years that can be very long.

```bash
# Anthropogenic surface emissions (-a) of CMIP7 historical (default cmip/mip)
./cmip_preemis -a

# Biomass burning (-b) + aviation (-f), and copy each yearly tar to the store
./cmip_preemis -b -f --store year

# CMIP6 historical instead of CMIP7
./cmip_preemis -a -c cmip6

# ScenarioMIP medium instead of historical
./cmip_preemis -a -m scenariomip-m

# Historical only: also derive the EC-Earth3 biofuel-subtracted surface files
./cmip_preemis -a -e

# Only some years, overwriting existing output
./cmip_preemis -a --years 2020 2021 2022 --overwrite

# An explicit config file instead of the -c/-m lookup
./cmip_preemis -b --toml /path/to/custom.toml -c cmip7
```

`-c/--cmip` (`cmip6`/`cmip7`) and `-m/--mip` (`historical`, `scenariomip-m`, ...) select
the config in `etc/`; `--toml PATH` bypasses that lookup.

### At the end of a run: entries for an emission-specification file

`cmip_preemis` ends by printing ready-to-paste `src=` entries, built from the config and
from what was written (tar name, resolution tag and file suffix of each group):

```
 Examples of entries for emission specification files
 -- anthro. surface  :
     src=<store>/<tar_common>_{year}.tar#<tar_common>_<resol>_anthro-surf_{xfvar|_tag|species}_{year}.nc
 -- anthro. aviation :
     src=<store>/<tar_common>_{year}.tar#<tar_common>_<resol>_anthro-air_{xfvar|_tag|species}_{year}.nc
 -- biomass burning  :
     src=<store>/<tar_common>_{year}.tar#<tar_common>_<resol>_bburning_{xfvar|_tag|species}_{year}.nc
```

With `-e` it also prints the EC-Earth3 files (`anthro-surf-ecearth`, `anthro-biof`). A
local store gets the prefix `file:`; an ECFS store (`ec:/...`) is used as it is. In the
`.emi`, the entry goes after the sectors it applies to, followed by the conversion of the
variable to read, e.g.:

```
sector=AGR/ENE/IND/TRA/RCO/SLV/WST/SHP: src=<entry anthro. surface>, preconvert=cdo_grib1:{sector}, prespatial=box_avg, pretemporal=timeint
sector=biomass_burning: src=<entry biomass burning>, preconvert=cdo_grib1:bbALL, pretemporal=timeint
```

The `.emi` files in `doc/emis_spec/` are complete, tested examples.

## Official datasets (`make`)

The `Makefile` fixes how each official dataset is produced: all groups (`-a -b -f`) and
`--store year`. Run `make` to print the usage.

| Target                      | Runs                         |
|-----------------------------|------------------------------|
| `make cmip7-historical`     | `-c cmip7 -m historical -e`  |
| `make cmip7-scenariomip-m`  | `-c cmip7 -m scenariomip-m`  |
| `make cmip7-scenariomip-h`  | `-c cmip7 -m scenariomip-h`  |
| `make cmip7-scenariomip-l`  | `-c cmip7 -m scenariomip-l`  |
| `make cmip7-scenariomip-vl` | `-c cmip7 -m scenariomip-vl` |
| `make cmip6-historical`     | `-c cmip6 -m historical`     |

```bash
make cmip7-historical YEARS=1990-2019 OPTS="--nccompress --overwrite" SUBMIT=sbatch
make cmip7-historical YEARS=1850,1900          # selected years
make cmip7-historical YEARS=1850-1910          # interval (inclusive)
make cmip7-scenariomip-m YEARS=2022-2024,2050 OPTS=--overwrite
make -n cmip7-historical YEARS=1850-1855       # dry-run: print the command only
```

- `--nccompress`: lossless compression, 7-10 times smaller tars
- `--overwrite`: no files reused from earlier runs
- `--cleanafter`: frees `outpath` once each tar is in the store.
- `GROUPS`, `STORE` and `OPTS` override the defaults; with no `YEARS`, all years of the
  config are processed. Any other variable (e.g. a typo like `YAERS=`) stops `make`.

## Validating datasets (`cmip_validate`)

```bash
# Recompute the emission totals (Tg) of one yearly tar, from its NetCDF files only
./cmip_validate --tgz <tar>

# Compare two tars of the same year: A (under test) against B (reference)
./cmip_validate --compare <tar_A> <tar_B>

# B made by the previous tool (old file and sector names)
./cmip_validate --compare <tar_A> <tar_B> --legacyref

# A ScenarioMIP tar against a historical tar of an overlapping year
./cmip_validate --compare <tar_scenariomip> <tar_historical> --historicalref

# Tars in ECFS, cached locally between runs
./cmip_validate --compare ec:/<path>/<tar_A> ec:/<path>/<tar_B> --ecfs-cache $SCRATCH/ecfs_cache

# Time series of the yearly CSVs of a folder, log axis, seasonal cycle of two years
./cmip_validate --timeseries <dir_with_csvs> --log --seasonal 2000 2020

# Plot several --compare results that share the same A
./cmip_validate --plotcompare <outdir>/<A>_vs_<B1> <outdir>/<A>_vs_<B2>
```

Outputs go to `outs/validation/<name>/` (`--outdir`, `--name` to change it).

## Checking what is produced (`cmip_check`)

```bash
./cmip_check --toml etc/historical_cmip7.toml                     # all years of the config
./cmip_check --toml etc/historical_cmip7.toml --years 1850-1860
./cmip_check --toml etc/historical_cmip7.toml --years 1850,2022 --deep --ecfs-cache $SCRATCH/ecfs_cache
./cmip_check --tarpath <path>/<tar_name>_1850.tar                  # one tar, no toml
```

- **Quick (default, downloads nothing):** per year, whether the tar is in the store (plain
  or `-ec3`), its date and size, local NetCDF files and statistics CSVs; missing years at
  the end. Consecutive years with the same status share one line, e.g.:

  ```
   Config  :  etc/historical_cmip7.toml [CMIP7]
   Tar name:  <tar_name>[-ec3]_<year>.tar   (<name>-<revision>; -ec3: run with --ecearth3)
   Store   :  ec:/<user>/emissions/cmip7hist/ (ecp)
   Years   :  2020-2023

   Years         Store tar  Store date               Size/tar         Local nc  CSV out  CSV val  Local tar
   2020-2023     ec3        2026-10-14               1.3GB            100       3/3      3/3      ec3

   Summary
     years in config : 4  (2020-2023)
     tars in store   : 4   (with -ec3: 4)
  ```
- **`--deep` (needs `--years`):** fetches the tars and reads what is inside: the toml used,
  the emicmip version and raw-data versions, the groups present, and the statistics CSVs.
  After the quick table, one block per tar, e.g.:

  ```
   <tar_name>-ec3_2020.tar
     run as    : ./cmip_preemis -a -b -f --store year --years 2020 2021 2022 2023 --nccompress -c cmip7 -m historical -e
     emicmip   : <version>  (version of the code that made the tar)
     created   : 2026-10-14T12:35:30
     user@host : <user>@<host>
     toml      : historical_cmip7.toml -- DIFFERS from etc/historical_cmip7.toml
     raw data  : (version of the input files, from the toml in the tar)
       anthro     CEDS-CMIP-2025-04-18, CEDS-CMIP-2025-04-18-supplemental
       aviation   CEDS-CMIP-2025-04-18
       bburning   DRES-CMIP-BB4CMIP7-2-1
     contents  : 100 nc, 3 csv
       anthro-air              10 species     294MB  (29MB/species)
       anthro-biof             10 species      72MB  (7MB/species)
       anthro-surf             33 species     667MB  (20MB/species)
       anthro-surf-ecearth     10 species     236MB  (24MB/species)
       bburning                37 species      76MB  (2MB/species)
     stats csv : anthro, aviation, bburning
  ```

  `DIFFERS` means the toml used for that tar is not the current one in `etc/`.
- **`--tarpath PATH`:** one tar by its full path (the store is its folder); with `--toml`,
  that toml is a reference compared with the toml inside the tar.

Nothing is ever written to the store.

## Stand-alone checks (`tools/`)

Read-only scripts, independent of `lib/` (details in `tools/INFO.md`).

```bash
# rawcheck: are the raw input4MIPs folders consistent, up to date, and read by the configs?
cp -r tools/rawcheck $HPCPERM/raw_emissions/cmip7/historical/
cd $HPCPERM/raw_emissions/cmip7/historical/rawcheck
make REPO=~/emicmip                              # every folder + what etc/*_cmip7.toml read
make ONLY="BB4CMIP7 CEDS-CMIP" REPO=~/emicmip    # only folders starting so

# interp_check.py: how good is the linear interpolation of missing years?
python3 tools/interp_check.py etc/scenariomip-m_cmip7.toml SO2 NOx BC CO --cdo
python3 tools/interp_check.py etc/historical_cmip7.toml SO2 NOx BC CO \
        --gaps 2000:2005 2005:2010 2010:2015 2015:2020 2018:2023 --sectors
```

`rawcheck` was used to check the raw folders before the official productions;
`interp_check.py` to choose linear interpolation for the years missing in the ScenarioMIP
raw files (see the web page "Datasets").
