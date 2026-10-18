# Datasets

Here a **dataset** is a set of emission files **prepared for IFS/OpenIFS** by
`cmip_preemis` from one raw CMIP source: CMIP7 historical, or one ScenarioMIP scenario.
Each dataset is stored as one tar per year, with monthly NetCDF files per species, ready
to be read by the OpenIFS/IFS emission pre-processor through a `.emi` file (an
emission-specification file). Tested examples are provided in `doc/emis_spec/` of the
repository; further information in [Emission specification](emission_spec.md).

This page explains which dataset to use, where it is stored, what is inside the tars,
which species they contain and which versions exist. The raw input4MIPs datasets used to
produce them are listed at the end ([Raw datasets from input4MIPs](#raw-datasets-from-input4mips)).

## Choosing a dataset

Each dataset covers one CMIP7 case: the historical period or one of the scenarios. As
explained above, a dataset is a set of files with the same structure, one tar per year
named `<tar name>_<YEAR>.tar`. The table gives, for each case, the prepared dataset and
one tested emission-specification file.

| CMIP7 case                | Dataset (one tar per year)                    | Tested emission-specification file                                       |
|---------------------------|-----------------------------------------------|--------------------------------------------------------------------------|
| Historical                | `CMIP7hist-2025-04-18d-ec3_<YEAR>.tar`        | `cmip7_m7_simchem.emi`                                                   |
| ScenarioMIP h (high)      | `ScenarioMIPh-a_<YEAR>.tar` (in preparation)  | `cmip7_scenariomip-h_m7_simchem.emi` (validated once data are prepared)  |
| ScenarioMIP m (medium)    | `ScenarioMIPm-a_<YEAR>.tar`                   | `cmip7_scenariomip-m_m7_simchem.emi`                                     |
| ScenarioMIP l (low)       | `ScenarioMIPl-a_<YEAR>.tar` (in preparation)  | `cmip7_scenariomip-l_m7_simchem.emi` (validated once data are prepared)  |
| ScenarioMIP vl (very low) | `ScenarioMIPvl-a_<YEAR>.tar` (in preparation) | `cmip7_scenariomip-vl_m7_simchem.emi` (validated once data are prepared) |
| Historical, legacy        | `CMIP7hist-2025-04-18c_<YEAR>.tar`            | `cmip7_m7_simchem_legacy_fixed.emi`                                      |

## What each dataset contains

Each dataset is stored on ECFS as **one tar per year**, named `{tar_common}_{year}.tar`:

| Source dataset                              | Store                                       | Tar of one year (example)            |
|---------------------------------------------|---------------------------------------------|--------------------------------------|
| CMIP7 historical                            | `ec:/nldac/emissions/cmip7hist/`            | `CMIP7hist-2025-04-18d-ec3_1850.tar` |
| CMIP7 ScenarioMIP, one dataset per scenario | `ec:/nldac/emissions/cmip7scenariomip/<x>/` | `m/ScenarioMIPm-a_2050.tar`          |

Inside each tar:

- **NetCDF files**, one per subset and species:
  `{tar_common}_{resolution}_{subset}_{species}_{year}.nc`, for example
  `CMIP7hist-2025-04-18d-ec3_05x05_anthro-surf_BC_1850.nc`. Each holds the 12 monthly
  fields of every sector of that subset (see the subsets below).
  Each file also says, as global attributes, where it comes from: the raw dataset
  (`source_id`, `source_version`, `tracking_id`, kept from input4MIPs) and what made it
  (`emicmip_version`, `emicmip_dataset` = the tar name without the year,
  `emicmip_config`). Years interpolated in the raw data are marked `interpolated`,
  derived species `derived_from`.
- **Emission statistics** of the year, one CSV per group:
  `emissions_stats/emissions_{anthro,aviation,bburning}_{year}.csv`, with columns
  `year, species, dataset, sector, month_01 ... month_12, total_Tg` (emitted mass in Tg).
- **The config used to produce it** (e.g. `historical_cmip7.toml`), with a header that
  records the run:

  ```
  # run as: ./cmip_preemis -a -b -f --store year -c cmip7 -m historical -e
  # version: 0.2.0
  # created: 2026-10-12T10:18:00
  # user@host: <username>@<host>
  ```

  `version` is the version of emicmip (`cmip_preemis`). `cmip_check --deep` reads
  this header back, and from the toml the raw-data version of each group.

The `d-ec3` tars are compressed (netCDF4, deflate level 4 + shuffle, lossless): the tar
of each year is 7-10 times smaller than an uncompressed one, so copies from ECFS are
faster; `cdo` reads them directly.

| Subset                | Content                                                                       | Resolution (historical / ScenarioMIP) |
|-----------------------|-------------------------------------------------------------------------------|---------------------------------------|
| `anthro-surf`         | surface anthropogenic, sectors AGR, ENE, IND, TRA, RCO, SLV, WST, SHP and ALL | 0.5° / 0.5°                           |
| `anthro-biof`         | solid biofuel, part of `anthro-surf`, 10 species (historical only)            | 0.5° / --                             |
| `anthro-surf-ecearth` | `anthro-surf` minus `anthro-biof`, same 10 species (`-ec3` tars only)         | 0.5° / --                             |
| `anthro-air`          | aviation, sector AVI, 3D (25 CEDS levels)                                     | 0.5° / 0.5°                           |
| `bburning`            | biomass burning, variable `bbALL` (total)                                     | 0.25° / 0.5°                          |

All data are monthly fluxes in kg m-2 s-1.

## Emission species provided

As described above, each tar holds a set of groups and subsets, and each subset a set of
species, so one species can come from several sources (for example BC from
`anthro-surf`, `anthro-biof`, `anthro-air` and `bburning`). In every file the sectors of
a species are separate variables (AGR, ENE, ...; AVI; bbALL), as in CAMS and in the
CMIP6 files prepared for the CONFESS project.

**Surface anthropogenic** (`anthro-surf`)

Anthropogenic emissions at the surface, given by sector: agriculture (AGR), energy (ENE),
industry (IND), transport (TRA), residential, commercial and other (RCO), solvents (SLV),
waste (WST) and international shipping (SHP). We also provide ALL, the sum of the eight,
for setups where reading a single total is more convenient or makes the model
pre-processing faster. Not all species are emitted in every sector, but all sectors are
provided (as zeros in such cases). The data are
monthly, so they include a seasonal cycle: the monthly totals of every species and sector
are in the statistics CSV files inside each tar, and `cmip_validate --timeseries
--seasonal` plots them.

| Species                       | CMIP7 historical     | CMIP7 ScenarioMIP |
|-------------------------------|:--------------------:|:-----------------:|
| BC, OC                        | yes (+ biofuel file) | yes               |
| CH4, CO, NH3, NOx, SO2, NMVOC | yes (+ biofuel file) | yes               |
| CO2                           | yes (+ biofuel file) | yes               |
| N2O                           | yes (+ biofuel file) | yes               |
| VOC01 ... VOC25 (23 species)  | yes                  | yes               |

NMVOC is the sum of the 23 VOCs: use one or the other, never both. The solid-biofuel
file (10 species; CH4 and N2O from 1970) is part of the surface total, not an extra
source.

**Aviation** (`anthro-air`)

A single sector, AVI, but on 25 vertical levels 0.61 km thick (centres from 0.305 to
14.945 km), the same in the historical and the ScenarioMIP data (checked, see
[Validation](validation.md)). Raw files do not exist for every year of every species:
historical CH4 and N2O aviation start in 1970, and the ScenarioMIP raw files hold
2022-2025 and then every fifth year (the years in between are interpolated).
`cmip_check --tarpath <full path of the tar>` lists the species in a tar, and `cmip_preemis` reports the missing
raw files at the end of a run.

| Species                               | CMIP7 historical | CMIP7 ScenarioMIP |
|---------------------------------------|:----------------:|:-----------------:|
| BC, CO, CO2, NH3, NMVOC, NOx, OC, SO2 | yes              | yes               |
| CH4 (all zero)                        | from 1970        | yes               |
| N2O                                   | from 1970        | yes               |

**Biomass burning** (`bburning`)

Open biomass burning: wildfires and other open fires. In the historical data the raw
files give only the total, without sectors; we call it `bbALL`. Sectors can be rebuilt
with the extra percentage files of BB4CMIP7, which is what we do for CO2 to add its peat
part, `bbPEAT`. ScenarioMIP gives the sectors directly, as for the surface anthropogenic
emissions.

| Species                                            | CMIP7 historical | CMIP7 ScenarioMIP |
|----------------------------------------------------|:----------------:|:-----------------:|
| BC, OC, SO2, CO, CH4, H2, N2O, NH3, NOx, NMVOCbulk | yes              | yes               |
| HCN and 24 speciated VOCs (C10H16 ... Toluenelump) | yes              | yes               |
| CO2                                                | yes              | no                |
| NOxasNO2                                           | yes              | no                |

| Variable (sector)            | CMIP7 historical               | CMIP7 ScenarioMIP                     |
|------------------------------|--------------------------------|---------------------------------------|
| `bbALL`                      | total                          | total: sum of the four below          |
| `bbAGRW`, `bbFORE`, `bbGRSS` | --                             | agricultural waste, forest, grassland |
| `bbPEAT`                     | CO2 only: peat part of `bbALL` | peat                                  |

Read `bbALL` for the total. `bbPEAT` is part of `bbALL`: never add the two.

## Versioning

The letter at the end of the tar name is the revision of a dataset made from the same
raw data.

| Version                     | Notes                                                                                                            |
|-----------------------------|------------------------------------------------------------------------------------------------------------------|
| `CMIP7hist-2025-04-18d-ec3` | **Use this one.** Complete CEDS 2025-04-18 data and BB4CMIP7 2-1.                                                |
| `CMIP7hist-2025-04-18c`     | Previous tool. CO2 biomass burning is only the peat part. For reproducing old runs.                              |
| `CMIP7hist-2025-04-18c-ec3` | Previous tool. CO2 biomass burning with an obsolete peat scaling.                                                |
| `ScenarioMIP{h,m,l,vl}-a`   | **Use this one.** Surface and biomass burning from IIASA 1-1-1, aviation from IIASA 1-1-2 (correct seasonality). |

ScenarioMIP raw files hold 2022-2025 and then every fifth year; the years in between are
interpolated linearly, month by month (files carry an `interpolated` attribute).

If in doubt about a tar, `cmip_check --tarpath <full path of the tar>` reads back from it the
emicmip version, the command and date of the run, and the raw-data version of each
group. Tars made with recent versions of emicmip carry the most information;
older ones lack part of it.

## Raw datasets from input4MIPs

The input4MIPs datasets read by the production configs (`etc/*.toml`). As explained
above, `cmip_check --tarpath <full path of the tar>` always recovers which raw dataset was
used to produce it.

| Dataset (tars)                                 | Group                                | Raw dataset (input4MIPs `source_id`)                                  | Years                          |
|------------------------------------------------|--------------------------------------|-----------------------------------------------------------------------|--------------------------------|
| CMIP7 historical (`CMIP7hist-2025-04-18d-ec3`) | surface anthropogenic, solid biofuel | `CEDS-CMIP-2025-04-18` (and `-supplemental` for CH4, N2O before 2000) | 1750-2023                      |
|                                                | aviation                             | `CEDS-CMIP-2025-04-18`                                                | 1750-2023 (CH4, N2O from 1970) |
|                                                | biomass burning                      | `DRES-CMIP-BB4CMIP7-2-1`, peat percentage `CO2percentagePEAT` 2-1     | 1750-2023                      |
| CMIP7 ScenarioMIP (`ScenarioMIP{h,m,l,vl}-a`)  | surface anthropogenic                | `IIASA-IAMC-{h,m,l,vl}-1-1-1`                                         | 2022-2100                      |
|                                                | aviation                             | `IIASA-IAMC-{h,m,l,vl}-1-1-2`                                         | 2022-2100                      |
|                                                | biomass burning                      | `IIASA-IAMC-{h,m,l,vl}-1-1-1`                                         | 2022-2100                      |
| CMIP6 historical (`CMIP6hist-2018-08-30`)      | surface anthropogenic                | `CEDS-2017-05-18` (and supplemental data)                             | 1850-2014                      |
|                                                | aviation                             | `CEDS-2017-08-30`                                                     | 1900-2014                      |
|                                                | biomass burning                      | `VUA-CMIP-BB4CMIP6-1-2`                                               | 1850-2015                      |

ScenarioMIP raw files hold 2022-2025 and then every fifth year to 2100; the years in
between are interpolated.

