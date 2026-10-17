# Producing datasets

The official datasets are produced with the `Makefile` at the repository root, which runs
`cmip_preemis` with the production options: all groups (`-a -b -f`) and one tar per
year copied to the store (`--store year`).

| Target                                        | Runs `cmip_preemis` with                |
|-----------------------------------------------|-----------------------------------------|
| `make cmip7-historical`                       | `-c cmip7 -m historical -e`             |
| `make cmip7-scenariomip-h`, `-m`, `-l`, `-vl` | `-c cmip7 -m scenariomip-h` (and so on) |
| `make cmip6-historical`                       | `-c cmip6 -m historical`                |

`-e` (`--ecearth3`) only adds the `anthro-surf-ecearth` files and the `-ec3` suffix;
every other file is identical to a run without it.

:::{important}
The official tars are produced as **a single run** per year, with all groups
(`-a -b -f`) and `OPTS="--nccompress --overwrite"`:

- `--nccompress`: netCDF4, lossless, 7-10 times smaller. The targets do not add it by
  themselves; pass it so that every tar of a dataset is compressed.
- `--overwrite`: recomputes every file. Without it, files already in `outpath` from an
  earlier run (another tool version or config) are reused and end up in the new tar.
  It also replaces a tar already in an ECFS store (`ecp -o`); without it, `ecp` keeps
  the existing tar.
- single run: the tar of a year holds only the files of the run that created it, so
  all groups go in one run, not in separate runs.

```bash
make cmip7-historical YEARS=1990-2019 OPTS="--nccompress --overwrite" SUBMIT=sbatch
```
:::

## Variables

| Variable                                  | Meaning                                                           | Default                                   |
|-------------------------------------------|-------------------------------------------------------------------|-------------------------------------------|
| `YEARS`                                   | list (`1850,1900`), interval (`1850-1910`) or both                | every year of the config                  |
| `GROUPS`                                  | groups to process                                                 | `-a -b -f`                                |
| `STORE`                                   | `--store` value; `none` keeps the tars local                      | `year`                                    |
| `OPTS`                                    | other options, e.g. `--nccompress`, `--overwrite`, `--cleanafter` | --                                        |
| `SUBMIT=sbatch`                           | submit as a Slurm job                                             | run in this shell                         |
| `ACCOUNT`, `QOS`, `SBATCH_OPTS`, `LOGDIR` | batch options                                                     | own account, system QoS, --, `outs/logs/` |

Paths in the configs (`etc/*.toml`) may contain `{user}`, replaced by the user running
the tool: run as `nldac` they give the shared paths, run by another user that user's own
folders. A fixed path in the config works as well.

`--cleanafter` frees `outpath`: once a year's tar is safely copied to the store, that
year's final nc files and local tar are removed (nothing is removed if the copy fails;
the statistics CSVs are kept).

Any other variable stops `make` with an error, so a typo cannot silently run every year.
Files already produced are reused unless `OPTS="--overwrite"` is given.

```bash
make -n cmip7-historical YEARS=1990-2019 OPTS="--nccompress --overwrite"   # dry run
make cmip7-historical YEARS=1990-2019 OPTS="--nccompress --overwrite" SUBMIT=sbatch
make cmip7-scenariomip-m YEARS=2022-2030 OPTS="--nccompress --overwrite" SUBMIT=sbatch
```

Raw data cover 1750-2023 (historical) and 2022-2100 (ScenarioMIP, years between the raw
ones interpolated). At the end of a run `cmip_preemis` lists the interpolated years and
prints the `src=` lines for the `.emi`.
