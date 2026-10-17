# Source and produced datasets: notes and limitations

What is worth knowing about the data in the tars.

## How the data are built

- **Surface NMVOC and the speciated VOCs describe the same emissions**: use one or the
  other, never both. In ScenarioMIP the bulk NMVOC equals the sum of the 23 VOCs (checked,
  ratio 1.0000); in historical `d-ec3` the bulk NMVOC is the official CEDS file. VOC10
  and VOC11 do not exist in CMIP7.
- **ScenarioMIP years between the raw years are interpolated.** The IIASA files hold
  2022-2025 and then every fifth year. The years in between are interpolated linearly,
  month by month, as input4MIPs asks; their files carry an `interpolated` attribute.
  They are plausible, not real: no single-year events.
- **Historical biomass-burning CO2 has a peat part.** Besides the total `bbALL`, the CO2
  file holds `bbPEAT`. Use `bbALL` for the total; never add `bbPEAT` to it.
- **Historical `d-ec3` uses the complete CEDS 2025-04-18 data**: official CO2 aviation
  (with a real 2023) and the official bulk surface NMVOC.

## Limitations

- **CH4 aviation is zero**: the maximum over time, space and levels is exactly 0 in both
  CEDS 2025-04-18 files and in IIASA-IAMC-h-1-1-2 and m-1-1-2 (checked with `cdo`,
  year by year; l and vl not checked, expected the same). The files are processed for
  completeness. Every other aviation species (BC, OC, SO2, NMVOC, CO2, CO, NH3, NOx,
  N2O) is not zero (historical, checked 2000-2023).
- **Historical CH4 and N2O of aviation and of solid biofuel start in 1970** (CEDS);
  earlier tars have no such files. The other species of aviation and solid biofuel, and
  surface CH4 and N2O, cover 1750-2023.
- **Legacy tars `c` and `c-ec3`: CO2 biomass burning is not the total** (peat only in
  `c`, wrong scaling in `c-ec3`). Use `d-ec3`.
- **ScenarioMIP aviation is read from IIASA 1-1-2, not 1-1-1**: the 1-1-1 aviation has a
  wrong seasonal cycle, corrected in 1-1-2.
- **The IIASA files carry global attributes copied from CEDS** (`time_range`, `history`,
  `global_total_emission_2000`). Trust `start_date`, `end_date` and the time axis.
- **ScenarioMIP biomass burning has no CO2.**

## OpenIFS pre-processor

- **GRIB parameter numbers**: a new tracer needs a number that does not clash with the
  others; see the `paramid` entries of the `.emi` files in `doc/emis_spec/`.
- **Error messages** of `cdo` differ between versions for the same problem; some
  versions reset an unknown paramId to zero.
- **Time interpolation** anchors each month on its 15th day.
