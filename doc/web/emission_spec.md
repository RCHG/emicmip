# Emission specification

The OpenIFS emission pre-processor reads the tars through an emission-specification file
(`.emi`). The files are in `doc/emis_spec/` of the repository.

:::{note}
The `.emi` files are examples for **OpenIFS with HAMM7** (M7 aerosols) and **Simplified
Chemistry** (SimChem, interactive SO2 / H2SO4). The current historical file
and the aviation file have been tested in OpenIFS with this setup; the CO2 files in the
emission pre-processing (see below).
Other aerosol or chemistry schemes need their own species, tracers and paramids.
:::

## `.emi` files provided

| File                                            | Reads tars                  | Target                                     | Status                                                           | Issues (of dataset)                                    |
|-------------------------------------------------|-----------------------------|--------------------------------------------|------------------------------------------------------------------|--------------------------------------------------------|
| `cmip7_m7_simchem.emi`                          | `CMIP7hist-2025-04-18d-ec3` | CMIP7 historical.                          | tested: OpenIFS run, 10 days (see [Validation](validation.md))   | -                                                      |
| `cmip7_m7_simchem_co2-bbALL.emi`                | `CMIP7hist-2025-04-18d-ec3` | CMIP7 historical + CO2, fire CO2 total     | tested: pre-processing (CO2 added as extra tracer, see below)    | -                                                      |
| `cmip7_m7_simchem_co2-bbPEAT.emi`               | `CMIP7hist-2025-04-18d-ec3` | CMIP7 historical + CO2, fire CO2 peat only | tested: pre-processing (CO2 added as extra tracer, see below)    | -                                                      |
| `cmip7_m7_simchem_aviation.emi`                 | `CMIP7hist-2025-04-18d-ec3` | CMIP7 historical + aviation aerosols       | tested: pre-processing and run, 2 legs (see below)               | -                                                      |
| `cmip7_scenariomip-<x>_m7_simchem.emi`          | `ScenarioMIP<x>-a`          | ScenarioMIP                                | m: tested, pre-processing and run, 2 legs; h, l, vl: not run yet | -                                                      |
| `cmip7_scenariomip-<x>_m7_simchem_aviation.emi` | `ScenarioMIP<x>-a`          | ScenarioMIP + aviation aerosols            | m: tested, pre-processing and run, 2 legs; h, l, vl: not run yet | -                                                      |
| `cmip7_m7_simchem_legacy_fixed.emi`             | `CMIP7hist-2025-04-18c`     | CMIP7 historical, previous tool            | tested (\*)                                                      | 2023 CO2-AIR (copy of 2022)                            |
| `cmip7_m7_simchem_legacy.emi`                   | `CMIP7hist-2025-04-18c-ec3` | CMIP7 historical, decommissioned           | tested (\*)                                                      | 2023 CO2-AIR (copy of 2022); obsolete CO2 PEAT scaling |
| `cams_m7_simchem.emi`                           | CAMS datasets               | CAMS, for cross-comparisons                | --                                                               | -                                                      |

`<x>` = h (high), m (medium), l (low), vl (very low).

(\*) These files read no CO2 emissions, so the issues of their tars do not affect them at
all: for every species they read, the tars are identical to `CMIP7hist-2025-04-18d-ec3`
(see [Validation](validation.md)).

About CO2-AIR in those tars: the only serious issue is 2023, a copy of the 2022 file. The
new tars also update the source (official CEDS 2025-04-18); in other years the annual
total of CO2 aviation differs by about 0.8% (+0.84% in 2020).


## How a `.emi` reads the tars

Schematically, each source line is

```
src=<store>/<tar>_{year}.tar#<tar>_<res>_<subset>_<species>_{year}.nc, preconvert=cdo_grib1:<variable>
```

and the real line for the surface sectors in `cmip7_m7_simchem.emi` is (one line, scroll):

```
sector=AGR/ENE/IND/TRA/RCO/SLV/WST/SHP:   src=ec:/nldac/emissions/cmip7hist/CMIP7hist-2025-04-18d-ec3_{year}.tar#CMIP7hist-2025-04-18d-ec3_05x05_anthro-surf_{xfvar|_tag|species}_{year}.nc, preconvert=cdo_grib1:{sector}, prespatial=box_avg, pretemporal=timeint
```

| Part               | In the example                         | Meaning                                                     |
|--------------------|----------------------------------------|-------------------------------------------------------------|
| `<store>`          | `ec:/nldac/emissions/cmip7hist`        | where the tars are                                          |
| `<tar>_{year}.tar` | `CMIP7hist-2025-04-18d-ec3_{year}.tar` | the tar of the year                                         |
| `#<tar>_...nc`     | `#CMIP7hist-2025-04-18d-ec3_...nc`     | the file inside the tar (starts with the tar name)          |
| `<res>`            | `05x05`                                | resolution tag (`025x025` for historical biomass burning)   |
| `<subset>`         | `anthro-surf`                          | subset suffix                                               |
| `<species>`        | `{xfvar\|_tag\|species}`               | filled in by the pre-processor (species name or its `_tag`) |
| `<variable>`       | `{sector}`                             | the variable read: `AGR` ... `SLV`, `AVI`, `bbALL`          |

Rules:

- A `.emi` works only with the tars it names (tar name, resolution, suffix, variable).
- Biomass burning is read through `bbALL`, the total. `bbPEAT` exists only for CO2 and
  is part of `bbALL`: never read it for other species, nor add it to `bbALL`.
- Only species that exist in the tars, in the years they exist (e.g. CH4 and N2O
  aviation only from 1970).
- At the end of every run `cmip_preemis` prints the matching `src=` lines: the safest
  starting point for a new `.emi`.

## Names in each family of tars

|                     | Historical `d-ec3`               | ScenarioMIP `-a`            | Historical `c`, `c-ec3`                |
|---------------------|----------------------------------|-----------------------------|----------------------------------------|
| Surface             | `_05x05_anthro-surf_`            | `_05x05_anthro-surf_`       | `_05x05_anthro-surf_`                  |
| Aviation (3D)       | `_05x05_anthro-air_`             | `_05x05_anthro-air_`        | `_05x05_anthro-air_`                   |
| Biomass burning     | `_025x025_bburning_`, `bbALL`    | `_05x05_bburning_`, `bbALL` | `_025x025_bb4-2-0_`, `biomass_burning` |
| CO2 biomass burning | `bbALL` (total), `bbPEAT` (peat) | not provided                | peat part only                         |

## Validating CO2 emissions

To validate the CO2 emissions we used the M7 + SimChem `.emi` files extended with the CO2
emissions. Two extra files read CO2 for every sector: `cmip7_m7_simchem_co2-bbALL.emi`
and `cmip7_m7_simchem_co2-bbPEAT.emi`, with the biomass burning from `bbALL` or from
`bbPEAT` (anthro-surf paramid 216101-216108, aviation 212253, biomass burning 210080).
CO2 must also be in the list of species passed to the OpenIFS/IFS emission pre-processor;
otherwise these lines of the `.emi` are ignored. Therefore:

- By default CO2 is not pre-processed: the run setup passes to the emission pre-processor
  only the species that are tracers of the model, and SimChem+M7 has no CO2 tracer.
- For this test only, CO2 was added to that list in `lib_icmcl_compo.sh`:
  `compo_tracers_list+=" CO2"`.
- Pre-processing result, for both files: CO2 in the emission namelist (10 entries: 8
  anthro-surf sectors, aviation, biomass burning); 2D fields non-zero except AGR (216101),
  which is zero; aviation 212253 on 91 levels, non-zero (largest values at levels 69-71).
  Biomass burning 210080 from `bbPEAT` is much smaller than from `bbALL`.
- To be used by the model, a 3D emission (aviation) must be in the upper-air initial file
  (INIUA), which may require editing `oifs-preprocess.sh`; and the model needs a tracer
  with the species name, otherwise it stops.

| File   | Fire CO2                                                        | Use                                                                                             |
|--------|-----------------------------------------------------------------|-------------------------------------------------------------------------------------------------|
| bbALL  | `bbALL`: total, all fire types incl. peat                       | CO2 transport without interactive land carbon                                                   |
| bbPEAT | `bbPEAT`: peat fires only (2022: 2.53 Tg vs 5508 Tg in `bbALL`) | models with interactive land carbon, where the CO2 of the other fires is taken back by regrowth |

## Aviation aerosols (M7)

The datasets include aviation species that fit the M7 aerosol emissions, not used in the
earlier emission-specification files. `cmip7_m7_simchem_aviation.emi` adds aviation
`BC_KI`, `POM_KI`, `SO4_KS` (Aitken modes, radius 0.016 µm) and `SO2`. Unlike CO2, the
model uses these emissions, so they can change its results. See
[Emissions for M7](m7_aerosols.md#aviation-aerosol-emissions).

Tested (OpenIFS 48r1, L91, 2 legs of 2 days): the four fields (paramid 219034, 219035,
219037, 212230) are pre-processed on 91 levels, non-zero, and the run works. Two points of
the run setup (TO BE CONFIRMED):

- 3D emissions are read from the upper-air initial file (INIUA), not from the INIT-COMPO
  file of the 2D emissions: the run setup must place them there (`oifs-preprocess.sh`).
- A leg that starts from restart files takes all 3D fields (including emissions) from the
  restart, so they may keep the values of the first leg and are not updated per leg (e.g.
  per month), unlike the 2D emissions.

The same aviation entries were also tested with the ScenarioMIP m file
`cmip7_scenariomip-m_m7_simchem_aviation.emi` (start 2024-01-01, 2 legs of 2 days):
pre-processing and run work.
