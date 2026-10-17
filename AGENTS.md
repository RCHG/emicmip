# AGENTS.md

Guide for AI assistants and human contributors using them when working on emicmip: what the project
is, where things are, and the rules to follow.

## What this is

emicmip converts raw CMIP6/CMIP7 emission datasets (input4MIPs: CEDS, BB4CMIP7,
IIASA ScenarioMIP) into monthly, per-species NetCDF files, one tar per year, for the
OpenIFS/IFS emission pre-processor, which reads them through emission-specification
files (`.emi`).

Developed by Ramiro Checa-Garcia (KNMI). License Apache 2.0, copyright KNMI (see
`LICENSE` and `NOTICE`).

## Repository layout

| Path             | Content                                                                      |
|------------------|------------------------------------------------------------------------------|
| `cmip_preemis`   | produces the datasets (raw files + config -> yearly tars)                    |
| `cmip_validate`  | compares tars, plots time series and seasonal cycles                         |
| `cmip_check`     | which years of a config are produced, when, with which options               |
| `lib/`           | library shared by the three tools                                            |
| `etc/*.toml`     | one config per dataset (historical CMIP6/CMIP7, ScenarioMIP h/m/l/vl)        |
| `tools/`         | stand-alone checks: raw files, interpolation of years (`tools/INFO.md`)      |
| `Makefile`       | production runs (`make cmip7-historical`, `make cmip7-scenariomip-m`, ...)   |
| `doc/web/`       | user documentation web (Sphinx + MyST, GitHub Pages)                         |
| `doc/emis_spec/` | tested `.emi` files for OpenIFS + HAMM7 + SimChem (`INFO.md`)                |

## Documentation map

| Document                                                                         | Content                                                                   |
|----------------------------------------------------------------------------------|---------------------------------------------------------------------------|
| [Web: Tools](https://rchg.github.io/emicmip/tooling.html)                        | the tools, repository layout, workflow diagrams                           |
| [Web: Datasets](https://rchg.github.io/emicmip/datasets.html)                    | which tars to use, stores, tar content, species, versions, raw datasets   |
| [Web: Emission specification](https://rchg.github.io/emicmip/emission_spec.html) | which `.emi`, how a `src=` line reads the tars, CO2 and aviation examples |
| [Web: Emissions for M7](https://rchg.github.io/emicmip/m7_aerosols.html)            | M7 modes, densities, scaling factors, paramids, aviation proposal         |
| [Web: Notes and limitations](https://rchg.github.io/emicmip/data_notes.html)     | notes and limitations of the source and produced datasets                 |
| [Web: Producing datasets](https://rchg.github.io/emicmip/producing.html)         | production with `make`                                                    |
| `doc/emis_spec/INFO.md`                                                          | which `.emi` reads which tars                                             |
| `tools/INFO.md`                                                                  | what each script in `tools/` does                                         |

## Rules

### General

- Do not run `git commit`, `git add` or `git push`; other git commands only with the
  maintainer's approval.
- Do not install software. Stay inside the repository.
- This repository is maintained and developed by humans; LLMs are asked for revision,
  checking and atomic improvements. The rule is that the human should:
  - carefully indicate the steps to be done: fully directed implementation;
  - review any code changes done by LLMs.
- Edits must be atomic and made only under precise, bounded directives from the
  developers: one change at a time, limited to what was asked.
- Agents must not enter autonomous loops of changes: everything is reviewed step by
  step by the developers before the next change.

### Emission-specification files (`doc/emis_spec/*.emi`)

- They are among the most important files of the project: review every change carefully.
- Comments: only what a user needs. History goes in the `HISTORY` section at the end.
- Legacy files (`*_legacy*.emi`) reproduce old runs: never change their active lines.
- Same physics in every CMIP7 file: after a change, compare the active lines of all
  files (scaling, PSD, density, paramids) and the tables of the web page Emissions for M7
  (`doc/web/m7_aerosols.md`).

### Documentation

- AI can be asked to review consistency of documentation with files paths, or
  recent updates.
- After a change, build the web pages and the cheatsheet without errors:

  ```bash
  sphinx-build -b html doc/web doc/web/_build/html
  typst compile doc/cheatsheet/cheatsheet-emicmip.typ <out>.pdf
  ```
