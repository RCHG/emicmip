# emicmip

```
                    _                      _
  ___   _ __ ___   (_)   ___   _ __ ___   (_)  _ __
 / _ \ | '_ ` _ \  | |  / __| | '_ ` _ \  | | | '_ \
|  __/ | | | | | | | | | (__  | | | | | | | | | |_) |
 \___| |_| |_| |_| |_|  \___| |_| |_| |_| |_| | .__/
                                              |_|
```

Tools to convert raw CMIP6/CMIP7 emission datasets (input4MIPs NetCDF) into
yearly tars of per-species NetCDF files for the OpenIFS/IFS emission
pre-processor. They can also check and validate the produced datasets. It is
provided a set of tested emission-specification files (`.emi`) for OpenIFS
CY48R1.

- **Version:** `0.2.0` (first release): CMIP7 historical and CMIP7 ScenarioMIP.
- **Documentation:** https://rchg.github.io/emicmip/ (tools, datasets, emission
  specification, [validation](https://rchg.github.io/emicmip/validation.html)).
- **Author:** Ramiro Checa-Garcia (KNMI)
- **Contributors:** Detailed in the documentation

## Tools

| Tool            | Does                                                              |
|-----------------|-------------------------------------------------------------------|
| `cmip_preemis`  | raw files + a TOML config in `etc/` -> one tar per year           |
| `cmip_check`    | which years of a config are produced, when and with which options |
| `cmip_validate` | compares tars, recomputes totals, plots time series               |

Note that the main rationale of the tools is that adding a dataset should mean
writing a new `etc/*.toml`, not changing `lib/`, therefore if an specific MIP is
not able to fit the given features, please open an issue with the details.

## Requirements

Python 3.11+, [CDO](https://code.mpimet.mpg.de/projects/cdo),
[NCO](https://nco.sourceforge.net), `tar`; [`xarray`](https://xarray.dev) for
the statistics and validation, [`matplotlib`](https://matplotlib.org) for the
plots; `ecp`/`els` for an ECFS (`ec:/...`) store. Optional: `rich_argparse`
(coloured `--help`).

## Getting started

No installation: run the tools from the repository root.

```bash
git clone https://github.com/rchg/emicmip.git
cd emicmip
./cmip_preemis -h
```

## Examples

More examples, and what the tools print: [QUICK_INTRO.md](QUICK_INTRO.md).

```bash
# produce: anthro (-a), biomass burning (-b) and aviation (-f), copy each tar to the store
./cmip_preemis -a -b -f -c cmip7 -m historical --years 2020 --store year

# official datasets, always with the same options (see `make`)
make cmip7-scenariomip-m YEARS=2022-2030 OPTS="--nccompress --overwrite"

# check what is produced, and read one tar
./cmip_check --toml etc/historical_cmip7.toml --years 1850-1860
./cmip_check --tarpath <path>/<tar_name>_1850.tar

# compare two tars
./cmip_validate --compare <tar_A> <tar_B>
```

## Layout

| Path              | Content                                             |
|-------------------|-----------------------------------------------------|
| `lib/`            | library shared by the three tools                   |
| `etc/`            | one TOML config per dataset                         |
| `tools/`          | stand-alone checks (`rawcheck/`, `interp_check.py`) |
| `doc/web/`        | documentation web (Sphinx)                          |
| `doc/emis_spec/`  | tested `.emi` files for OpenIFS + HAMM7 + SimChem   |
| `doc/cheatsheet/` | cheatsheet (Typst)                                  |

## Development and use of AI

emicmip derives from a previous tool written entirely by the author (human). It
was extended to the future scenarios in continuous interaction with AI coding
assistants (LLMs). The author set the goals, the design and the validation
criteria, reviews the code and checks all outputs; LLMs wrote part of the new
functions, helped refactor the previous code, supported the cross
validation-comparison of all the emission-specification files, and translated or
improved part of the comments and documentation. The header of each file gives
the details.

## License

[Apache License, Version 2.0](LICENSE). Copyright KNMI; see [NOTICE](NOTICE).

## Contact

Ramiro Checa-Garcia (KNMI)
https://github.com/rchg/emicmip/issues
