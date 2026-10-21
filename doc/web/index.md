# emicmip

CMIP6 and CMIP7 emission datasets for OpenIFS/IFS. The tool `cmip_preemis` converts the
raw CMIP files (input4MIPs) into monthly, per-species NetCDF files, one tar per year,
that the OpenIFS emission pre-processor reads through an emission-specification file
(`.emi`).

These pages are the user guide: which data to use, which `.emi` reads them, and what is
worth knowing about them. A one-page PDF complements them:

:::{note}
- [Cheatsheet (PDF)](https://rchg.github.io/emicmip/emicmip-cheatsheet.pdf): one
  page with the commands, options, stores and configs. Source: `doc/cheatsheet/`.
:::

## Where to start

| If you want to                    | Read                                                                |
|-----------------------------------|---------------------------------------------------------------------|
| use the data in a model run       | [Datasets](datasets.md), [Emission specification](emission_spec.md) |
| see how the data were checked     | [Validation](validation.md)                                         |
| check the aerosol (M7) settings   | [Emissions for M7](m7_aerosols.md)                                  |
| see how the tools fit together    | [Tools](tooling.md)                                                 |
| produce a dataset                 | [Producing datasets](producing.md)                                  |
| know the limitations of the data  | [Notes and limitations](data_notes.md)                              |
| see the emissions of each dataset | [Time series](plots_timeseries.md), [By sector](plots_sectors.md)   |

## About/Contact

- *Developer/ maintainer*: Ramiro Checa-Garcia (KNMI).
- *Questions and problems*: [GitHub issues](https://github.com/rchg/emicmip/issues).
- *Contributors*:
  - Philippe Le Sager: feedback and testing of the produced datasets.
  - Twan van Noije, Lianghai Wu, Tommi Bergman: checking and review of the
    emission-specification files.
  - Vincent Huijnen: feedback and contribution on the emission-specification files.

emicmip is licensed under the Apache License 2.0; copyright KNMI (see `NOTICE`).

```{toctree}
:maxdepth: 2
:hidden:

tooling
datasets
emission_spec
m7_aerosols
validation
producing
data_notes
plots_timeseries
plots_sectors
```
