<!--
 ! ╭───────────────────────────────────────────────────────────────────────────╮
 ! │ doc/emis_spec/INFO.md                                (updated 2026-10-17) │
 ! │                                                                           │
 ! │ Author:  Ramiro Checa-Garcia (KNMI)                                       │
 ! │ Purpose: Which emission-specification file goes with which tars           │
 ! ╰───────────────────────────────────────────────────────────────────────────╯
-->

# Emission-specification files (OpenIFS/IFS, M7 + SimChem)

Explained in the web page "Emission specification"

## Source files:

Each `.emi` file reads the yearly tars produced by `cmip_preemis` through lines like

```
sector=...: src=ec:/nldac/emissions/<store>/<tar_common>_{year}.tar#<tar_common>_<resol>_<suffix>_{xfvar|_tag|species}_{year}.nc, preconvert=cdo_grib1:<variable>
```

so a file only works with the tars whose `tar_common`, resolution tag, subset suffix
and variable names it spells out. Inside a tar every file starts with the tar's own
name (`tar_common`, plus `-ec3` for `--ecearth3` runs).

## Which file for which data

| File                                            | Status                                                                                                     |
|-------------------------------------------------|------------------------------------------------------------------------------------------------------------|
| `cmip7_m7_simchem.emi`                          | **CMIP7 historical, use this**                                                                             |
| `cmip7_m7_simchem_co2-bbALL.emi`                | example: historical + CO2, fire CO2 **total** (`bbALL`); tested (pre-processing)                           |
| `cmip7_m7_simchem_co2-bbPEAT.emi`               | example: historical + CO2, fire CO2 **peat only** (`bbPEAT`); tested (pre-processing)                      |
| `cmip7_m7_simchem_aviation.emi`                 | example: historical + aviation BC/POM/SO4 (Aitken) and SO2; tested (pre-processing, run)                   |
| `cmip7_scenariomip-<x>_m7_simchem.emi`          | ScenarioMIP; m: tested (pre-processing, run); h, l, vl: not run yet                                        |
| `cmip7_scenariomip-<x>_m7_simchem_aviation.emi` | ScenarioMIP + aviation BC/POM/SO4 (Aitken) and SO2; m: tested (pre-processing, run); h, l, vl: not run yet |
| `cmip7_m7_simchem_legacy_fixed.emi`             | legacy tars `c`, without the CO2 problem of `c-ec3`                                                        |
| `cmip7_m7_simchem_legacy.emi`                   | legacy tars `c-ec3`, as used until 2026 (to reproduce old runs)                                            |
| `cams_m7_simchem.emi`                           | CAMS sources, for comparison                                                                               |

`<x>` = h (high), m (medium), l (low), vl (very low).


Tars and store read by each file:

| File                                            | Reads tars                            | Store                                       |
|-------------------------------------------------|---------------------------------------|---------------------------------------------|
| `cmip7_m7_simchem.emi`                          | `CMIP7hist-2025-04-18d-ec3`           | `ec:/nldac/emissions/cmip7hist/`            |
| `cmip7_m7_simchem_co2-bbALL.emi`                | `CMIP7hist-2025-04-18d-ec3`           | `ec:/nldac/emissions/cmip7hist/`            |
| `cmip7_m7_simchem_co2-bbPEAT.emi`               | `CMIP7hist-2025-04-18d-ec3`           | `ec:/nldac/emissions/cmip7hist/`            |
| `cmip7_m7_simchem_aviation.emi`                 | `CMIP7hist-2025-04-18d-ec3`           | `ec:/nldac/emissions/cmip7hist/`            |
| `cmip7_scenariomip-<x>_m7_simchem.emi`          | `ScenarioMIP<x>-a`                    | `ec:/nldac/emissions/cmip7scenariomip/<x>/` |
| `cmip7_scenariomip-<x>_m7_simchem_aviation.emi` | `ScenarioMIP<x>-a`                    | `ec:/nldac/emissions/cmip7scenariomip/<x>/` |
| `cmip7_m7_simchem_legacy_fixed.emi`             | `CMIP7hist-2025-04-18c`               | `ec:/nldac/emissions/cmip7hist/`            |
| `cmip7_m7_simchem_legacy.emi`                   | `CMIP7hist-2025-04-18c-ec3`           | `ec:/nldac/emissions/cmip7hist/`            |
| `cams_m7_simchem.emi`                           | CAMS datasets (not tars of this tool) | --                                          |

## Years of each dataset

Status 2026-10-18. The current datasets are (re)produced with emicmip 0.2.0, the
historical one overwriting the years already in the store.

| Status  | Dataset            | Raw files | Processed (in the store)                | Pending                                                |
|---------|--------------------|-----------|-----------------------------------------|--------------------------------------------------------|
| legacy  | historical `c`     | 1750-2023 | 1750-1752, 1850-1851, 1990-2023         | none (not produced any more)                           |
| legacy  | historical `c-ec3` | 1750-2023 | 1750-1751, 1753, 1850-1851, 1990-2023   | none (not produced any more)                           |
| current | historical `d-ec3` | 1750-2023 | 1750, 1800, 1850, 1900, 1950, 1990-2023 | 1751-1799, 1801-1849, 1851-1899, 1901-1949, 1951-1989 |
| current | ScenarioMIP `h-a`  | 2022-2100 | 2022-2030                               | 2031-2100                                              |
| current | ScenarioMIP `m-a`  | 2022-2100 | 2022-2030                               | 2031-2100                                              |
| current | ScenarioMIP `l-a`  | 2022-2100 | 2022-2030                               | 2031-2100                                              |
| current | ScenarioMIP `vl-a` | 2022-2100 | 2022-2030                               | 2031-2100                                              |

ScenarioMIP raw files hold 2022-2025 and then every fifth year; the years in between
are interpolated (see the web page "Datasets").

## Naming in each family

| Family              | Historical `d-ec3` (current tool)      | ScenarioMIP `-a` (current tool)      | Historical `c` / `c-ec3` (previous tool)        |
|---------------------|----------------------------------------|--------------------------------------|-------------------------------------------------|
| anthro surface      | `_05x05_anthro-surf_`                  | `_05x05_anthro-surf_`                | `_05x05_anthro-surf_`                           |
| aviation (3D)       | `_05x05_anthro-air_`                   | `_05x05_anthro-air_`                 | `_05x05_anthro-air_`                            |
| biomass burning     | `_025x025_bburning_`, variable `bbALL` | `_05x05_bburning_`, variable `bbALL` | `_025x025_bb4-2-0_`, variable `biomass_burning` |
| CO2 biomass burning | `bbALL` (total) + `bbPEAT` (peat part) | not provided                         | peat part only, in `biomass_burning`            |

The biomass-burning line therefore differs: 
- `preconvert=cdo_grib1:bbALL` in the current files,
- `preconvert=cdo_grib1:{sector}` (= `biomass_burning`) in the legacy ones. 

`bbPEAT` exists only for CO2: a file must never read it for other species, nor read `bbALL` and
`bbPEAT` for the same tracer (`bbPEAT` is part of `bbALL`).

## CO2 examples

`cmip7_m7_simchem_co2-{bbALL,bbPEAT}.emi` = `cmip7_m7_simchem.emi` + CO2 from the same
`d-ec3` tars: anthro-surf (paramid 216101--216108), aviation AVI (212253) and biomass
burning (210080). They differ only in section 1.5:

- `bbALL`: one biomass-burning line for every species, CO2 included -> total fire CO2;
- `bbPEAT`: `species!=CO2` line with `bbALL` + `species=CO2` line with `bbPEAT` -> only
  the CO2 of peat fires (for models with interactive land carbon).

The species name `CO2` must match the model's CO2 tracer. Tested: the emission
pre-processing and a run work (SimChem does not use CO2).

## Why two legacy files

The previous tool produced `CMIP7hist-2025-04-18c` (plain) and
`CMIP7hist-2025-04-18c-ec3` (`--ecearth3`). The original legacy file read `c-ec3`, but
that is the problematic version: its CO2 biomass burning had an obsolete peat
scaling. Every other file is the same in `c` and `c-ec3`, and the legacy
`.emi` reads no `-ec3`-only files (`anthro-surf-ecearth`, `anthro-biof`) and no CO2. So:

- `cmip7_m7_simchem_legacy.emi` -- reads `c-ec3`, unchanged, to reproduce runs made
  with it;
- `cmip7_m7_simchem_legacy_fixed.emi` -- the same file reading the plain `c` tars:
  same results for every species it uses, without depending on the `c-ec3` tars.

For new work use `cmip7_m7_simchem.emi` with `d-ec3`.

## Checks done

For `cmip7_m7_simchem.emi`, the `src=` lines were checked against the config
(`etc/historical_cmip7.toml`): `tar_common`
(+`-ec3`), resolution tag and suffix of each group, biomass-burning
variable, and that the species they read (BC, OC, SO2, CO through `_tag`, NH3, and
C2H6S in `xfexpr=SO2+1.03*C2H6S`) are output species of the config. All consistent.

## More

- Dataset versions and their limitations: web pages "Datasets" (Versioning) and
  "Source and produced datasets: notes and limitations".
- Aerosol settings of these files: web page "Emissions for M7".
- Each `.emi` has comments before its biomass-burning line and a HISTORY section.

