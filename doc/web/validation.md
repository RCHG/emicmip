# Validation

The validation has two parts. First, the tool itself was validated during its
development against the previous tool, which shares most of its code, so this part was
almost automatic. Second, the datasets produced:

- compared with those made by the previous tool (`cmip_validate --compare --legacyref`);
- for ScenarioMIP, compared with the historical dataset in the overlapping years. The
  raw files are not the same, so the products cannot be bit-identical, but their values
  must be reasonably consistent; `cmip_validate` has a mode for this,
  `--compare --historicalref`.

The rest of the page explains the validation tools and how each check was done. The same
tools can repeat every check.

## Tools

| Tool                                      | What it checks                                                                         |
|-------------------------------------------|----------------------------------------------------------------------------------------|
| `cmip_check --deep`, `--tarpath`         | provenance of each tar: emicmip version, command, date, raw-data version of each group |
| `cmip_validate --compare A B`             | two tars file by file and sector by sector: totals (Tg) and fields cell by cell        |
| `cmip_validate --compare --legacyref`     | the same, with B made by the previous tool (old file and sector names)                 |
| `cmip_validate --compare --historicalref` | ScenarioMIP (A) against the historical dataset (B) in a common year                    |
| `tools/interp_check.py`                   | the interpolation of years missing in a raw file (leave-out test)                      |

## How to read a comparison

`cmip_validate --compare A B` pairs the files of the two tars by species, subset and year,
and inside each pair the sectors. Each sector gets one status:

| Status                    | Meaning                                                                                |
|---------------------------|----------------------------------------------------------------------------------------|
| `identical`               | bit-identical fields                                                                   |
| `consistent`              | differences at float-rounding level only                                               |
| `different`               | real differences: the totals of A and B (Tg) and the largest cell difference are given |
| `only_in_A` / `only_in_B` | the sector (or the whole file) exists in one tar only                                  |

At the end, a summary gives the counts and a verdict per group (anthro, aviation,
bburning), and the largest differences of the annual totals.

## Validation of CMIP7 historical

### Against the previous tool

The previous tool produced the CMIP7 historical tars `CMIP7hist-2025-04-18c` and
`CMIP7hist-2025-04-18c-ec3`. The current `CMIP7hist-2025-04-18d-ec3` was compared with both,
for 2020 and 2023:

```bash
S=ec:/<user>/emissions/cmip7hist
for y in 2020 2023; do
  ./cmip_validate --compare $S/CMIP7hist-2025-04-18d-ec3_$y.tar $S/CMIP7hist-2025-04-18c-ec3_$y.tar \
                  --legacyref --ecfs-cache $SCRATCH/ecfs_cache
  ./cmip_validate --compare $S/CMIP7hist-2025-04-18d-ec3_$y.tar $S/CMIP7hist-2025-04-18c_$y.tar \
                  --legacyref --ecfs-cache $SCRATCH/ecfs_cache
done
```

| B       | Year | Matched files | Identical sectors | Different sectors | Only in B |
|---------|------|---------------|-------------------|-------------------|-----------|
| `c-ec3` | 2020 | 76            | 314               | 2                 | 0         |
| `c-ec3` | 2023 | 76            | 314               | 2                 | 0         |
| `c`     | 2020 | 74            | 299               | 1                 | 0         |
| `c`     | 2023 | 74            | 299               | 1                 | 0         |

No sector is only "consistent": every shared field is either bit-identical or one of the
differences explained below. Nothing of `c` or `c-ec3` is missing in `d`.

The summary of one comparison (`d-ec3` against `c`, 2020):

```
 ------ Comparison summary ---------------------------------------
 Archive A (test)     : <cache>/CMIP7hist-2025-04-18d-ec3_2020.tar (tag: CMIP7hist-2025-04-18d-ec3)
 Archive B (reference): <cache>/CMIP7hist-2025-04-18c_2020.tar (tag: CMIP7hist-2025-04-18c)
 Matched (species, dataset, year) keys: 74
 Only in A / Only in B (whole files):   26 / 0
 Sector rows -- identical:               299
 Sector rows -- consistent (float noise): 0
 Sector rows -- different:               1
 Sector rows -- only in A / only in B:   225 / 0
 Per-group verdict:
   ANTHRO     consistent (identical=258, consistent=0, different=0, only_in_A=219, only_in_B=0)
   AVIATION   DIFFERENT  (identical=7, consistent=0, different=1, only_in_A=2, only_in_B=0)
   BBURNING   consistent (identical=34, consistent=0, different=0, only_in_A=4, only_in_B=0)
 Largest annual-total (Tg) diffs:
   4.77 Tg  CO2/anthro-air/AVI/2020  (A=574.621, B=569.851)
 ------------------------------------------------------------------
```

Three kinds of result, from the same output:

**Identical.** Most files, for example surface CO: the 8 sectors are bit-identical, and
`ALL` (the sum of the sectors) is new in `d`:

```
  > [compare] CO/anthro-surf/2020
      8 sector(s) exactly identical (not shown above): AGR, ENE, IND, RCO, SHP, SLV, TRA, WST
      sector sets differ (checking only names):
          A (9): AGR, ENE, IND, RCO, SHP, SLV, TRA, WST, **ALL**
          B (8): AGR, ENE, IND, RCO, SHP, SLV, TRA, WST
```

**A small, explained difference.** CO2 aviation, the only different sector against `c`:

```
  > [compare] CO2/anthro-air/2020
      sector AVI            [DIFFERENT ] A=574.621        B=569.851        max_abs_diff=2.6722180024307818e-11
```

+0.84 % in 2020 (and +28 % in 2023): `d` has the official CEDS 2025-04-18 CO2 aviation,
`c` the CEDS 2024-10-21 test release, with 2023 copied from 2022. Every other aviation
species is bit-identical.

**Matching old names.** In `c` the CO2 biomass burning has a single variable
`biomass_burning`, the peat part only; `d` has the total `bbALL` and the peat part `bbPEAT`.
With `--legacyref`, the single sector of B is compared with every candidate of A and paired
with the closest:

```
  > [compare] CO2/bburning/2020
  > [compare] B's single sector 'biomass_burning' vs every A candidate:
      A 'bbALL': mean_abs_diff=3.102965662193924e-10
      A 'bbPEAT': mean_abs_diff=0.0 <- matched
      1 sector(s) exactly identical (not shown above): bbPEAT
```

Against `c` it is bit-identical to `bbPEAT`. Against `c-ec3` it differs (3.88 Tg against
15.11 Tg in 2020): in `c-ec3` the peat scaling is obsolete.

**Conclusion.** `d-ec3` reproduces the previous historical datasets exactly, except CO2
aviation (new source) and the CO2 peat part of `c-ec3` (wrong there). Everything else in
`d` is an addition: `ALL` sectors, bulk NMVOC, N2O, solid biofuel of every species, CH4
and N2O aviation, and in biomass burning CO2 `bbALL`, HCN, N2O and NMVOCbulk.

## Validation of CMIP7 ScenarioMIPs

### Interpolated years

The IIASA raw files hold 2022-2025 and then every fifth year; the years in between are
interpolated linearly, month by month. Two checks, on scenario medium:

- **Leave-out test** (`tools/interp_check.py`): 2023 and 2024 rebuilt from 2022 and 2025
  and compared with the real ones. Annual totals within -0.5 % to -2.4 %; the seasonal
  cycle and the spatial pattern are kept (monthly pattern correlation 0.997-0.9998), the
  error is a level offset.

  ```bash
  python3 tools/interp_check.py etc/scenariomip-m_cmip7.toml BC CO --cdo --sectors
  ```

- **End to end** (`cmip_preemis --forceinterp`): 2024, which the raw files have, is
  interpolated from 2023 and 2025 anyway and compared with a normal run that reads it:

  ```bash
  ./cmip_preemis -a -f -b -c cmip7 -m scenariomip-m --years 2024 --forceinterp 2024 --outpath $SCRATCH/forceinterp
  ./cmip_validate --compare $SCRATCH/forceinterp/ScenarioMIPm-a_2024.tar <normal run>/ScenarioMIPm-a_2024.tar
  ```

  Every species and sector agrees to 0.03 % or better (most ~1e-5): the raw 2024 is
  almost exactly the interpolation of 2023 and 2025, and the whole chain (interpolation,
  sectors, statistics, tar) works.

### Emission-specification files

- **Aviation levels.** The AVI line of the `.emi` (`clev(AVI)*1e3`, `-divc,610`) assumes
  levels in km and layers of 0.61 km, as in CEDS. The IIASA aviation raw files have the
  same 25 levels (centres 0.305 to 14.945 km, bounds 0-0.61, 0.61-1.22, ...) and the
  same units as CEDS (kg m-2 s-1).
- **DMS from fires.** The fire C2H6S is DMS: it enters SO2 with the factor
  1.03 = 64.07/62.13 (molar masses of SO2 and DMS), as in CAMS.

### Overlap with the historical dataset

During the development of the tool, the ScenarioMIP processing was checked against the
historical tars of the previous tool (`CMIP7hist-2025-04-18c`) in the overlapping years,
with `cmip_validate --compare`. This comparison led to the comparison modes of
`cmip_validate` (`--historicalref`, which lists the known historical/ScenarioMIP
differences apart) and confirmed that the ScenarioMIP data are processed correctly.

With the final datasets each scenario is compared with `CMIP7hist-2025-04-18d-ec3` in
2022, the year they share, with this command (here for the medium scenario `m`):

```bash
./cmip_validate --historicalref --ecfs-cache $SCRATCH/ecfs_cache --compare \
  ec:/<user>/emissions/cmip7scenariomip/m/ScenarioMIPm-a_2022.tar \
  ec:/<user>/emissions/cmip7hist/CMIP7hist-2025-04-18d-ec3_2022.tar
```

| Scenario | Anthropogenic surface                          | Aviation                     | Biomass burning                  |
|----------|------------------------------------------------|------------------------------|----------------------------------|
| `m`      | equal to 6 significant figures; VOCs within 0.3 % | 0.17 % lower, every species | different (projection vs. observed fires) |
| `h`      | _to be added after the production_             |                              |                                  |
| `l`      | _to be added after the production_             |                              |                                  |
| `vl`     | _to be added after the production_             |                              |                                  |

- Anthropogenic surface: IIASA is harmonized to CEDS in 2022, so the annual totals of
  every species and sector agree. The 23 speciated VOCs differ slightly by sector, while
  their bulk NMVOC total is equal.
- Aviation: ScenarioMIP is 0.17 % lower than the historical data, the same factor in
  every grid cell and species (CH4 aviation is zero on both sides).
- Biomass burning: ScenarioMIP is a projection, the historical dataset follows the
  observed fires of 2022, so totals and patterns differ (ScenarioMIP higher for every
  species but H2). The historical field (0.25°) is regridded conservatively to 0.5°
  before the comparison.

## Checks in OpenIFS runs

### CMIP7 historical

An OpenIFS experiment reading `CMIP7hist-2025-04-18d-ec3` through
`cmip7_m7_simchem.emi`:

| Setting              | Value                                                  |
|----------------------|--------------------------------------------------------|
| chemistry / aerosols | SimChem / HAM-M7                                       |
| resolution           | 255, 91 levels (grid `l_2`)                            |
| period               | 2020-01-01, 10 days, in two blocks of 5 days (restart) |

The aerosol optical depth of the M7 species in its reports is reasonable when compared
with earlier experiments that used the previous historical dataset.

### CMIP7 ScenarioMIPs

OpenIFS experiments with the ScenarioMIP m emission specifications
(`cmip7_scenariomip-m_m7_simchem.emi` and `cmip7_scenariomip-m_m7_simchem_aviation.emi`):

| Setting              | Value                                                 |
|----------------------|-------------------------------------------------------|
| chemistry / aerosols | SimChem / HAM-M7                                      |
| resolution           | 255 (grid `l_2`)                                      |
| period               | 2024-01-01, 4 days, in two legs of 2 days (restart)   |

For both, the emission pre-processing and the run complete. With aviation, the four 3D
fields (paramid 219034, 219035, 219037, 212230) are on 91 levels and non-zero. The files
for h, l and vl have not been run yet.
