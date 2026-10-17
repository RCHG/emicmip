# Emissions for M7 in OpenIFS/IFS

This page describes how the datasets are used when the aerosol scheme is M7 (HAMM7;
[Vignati et al., 2004](https://doi.org/10.1029/2003JD004485)), following the
implementation described for EC-Earth3-AerChem
([van Noije et al., 2021](https://doi.org/10.5194/gmd-14-5637-2021)). The
emission-specification files (`.emi`) in `doc/emis_spec/` are the concrete form of
everything described here. The values below have been compared not only with the
references but also with the HAMM7 code integrated in OpenIFS CY48R1.

## Modes

The first table summarises the modes of the scheme: the expected range of radii of each
mode, the tracers emitted into it, and the properties of the emitted distribution, which
match those of the mode that receives it (the same $\sigma$). Each species is also
emitted with the density defined in the scheme, so that the conversion from mass flux to
number flux gives a number of particles consistent with those already in that mode for
that tracer.

| Mode (number tracer)             | Mode range (radius) | Emitted tracers             | Emission radius | $\sigma$ |
|----------------------------------|:-------------------:|-----------------------------|:---------------:|:--------:|
| NS nucleation soluble            | 0.5-5 nm            | none                        | --              | 1.59     |
| KS Aitken soluble (`KS_N`)       | 5-50 nm             | `POM_KS`, `SO4_KS`          | 0.03 µm         | 1.59     |
| AS accumulation soluble (`AS_N`) | 50-500 nm           | `BC_AS`, `POM_AS`, `SO4_AS` | 0.075 µm        | 1.59     |
| CS coarse soluble (`CS_N`)       | > 500 nm            | `SO4_CS`                    | 0.75 µm         | 2.00     |
| KI Aitken insoluble (`KI_N`)     | 5-50 nm             | `BC_KI`, `POM_KI`           | 0.03 µm         | 1.59     |
| AI accumulation insoluble        | 50-500 nm           | none (\*)                   | --              | 1.59     |
| CI coarse insoluble              | > 500 nm            | none (\*)                   | --              | 2.00     |

(\*) Not emitted by these `.emi` files. Other emissions, for example computed online by
the model, may go to these modes; they are not part of these datasets.

As explained above, the values in the `.emi` files have been checked both against the
code (the HAMM7 Fortran files in OpenIFS, such as `tm5m7_data.F90`) and against the
references. The next table gives the density of the three species emitted, with the
values of the code and of the reference. The density and the size distribution are set
with the parameters `PSD_RADIUS` (number median radius), `PSD_SIGMA` and `MASS_DENSITY`,
which the OpenIFS/IFS emission pre-processor uses to process the emission files created
by `cmip_preemis`.

| Species                                | `MASS_DENSITY` (kg m-3) | Fortran                 | [van Noije et al. (2021)](https://doi.org/10.5194/gmd-14-5637-2021), Table 1 |
|----------------------------------------|:-----------------------:|-------------------------|------------------------------------------------------------------------------|
| BC                                     | 1800                    | `dbc = 1.8` g cm-3      | 1.8                                                                          |
| POM                                    | 1300                    | `doc = 1.3` g cm-3      | 1.3 (POA, SOA)                                                               |
| SO4 (particle density of H2SO4) [^so4] | 1841                    | `dh2so4 = 1.841` g cm-3 | 1.841 (sulfuric acid)                                                        |

## Scaling factors

For each species, tracer and sector, scaling factors are defined to be consistent with the
rationale of [van Noije et al. (2021)](https://doi.org/10.5194/gmd-14-5637-2021), in particular the mode split described in
their Tables 4 and 5. Their logic depends on each case:

- the total emitted mass flux of a species is split among its tracers, for example
  `BC_KI` and `BC_AS`, with split factors that add up to 1 (to the conversion factor when
  there is one, as for OC and SO4);
- for OC, the split also includes the conversion from OC to POM (factor 1.6);
- SO2 gives primary SO4 with the factors explained in the note below;
- additional POM comes from CO and terpene emissions (secondary organic aerosol), with a
  scaling based on estimates of their total emissions and of their conversion into POM
  (0.049 and 0.077, see the note below);
- DMS is converted into SO2 for the simplified chemistry.

| Emission                         | Tracer              | Factor       | Meaning                              |
|----------------------------------|---------------------|:------------:|--------------------------------------|
| BC, biomass burning              | `BC_KI` / `BC_AS`   | 0.05 / 0.95  | 5% insoluble, 95% soluble            |
| BC, other sectors                | `BC_KI`             | 1.00         | all insoluble                        |
| OC, biomass burning              | `POM_KI` / `POM_AS` | 0.08 / 1.52  | 0.05 / 0.95 x 1.6 (OC to POM)        |
| OC, other sectors                | `POM_KI`            | 1.60         | x 1.6                                |
| SO2, biomass burning             | `SO4_AS`            | 0.03757      | 2.5% of sulfur as SO4                |
| SO2, ENE / IND / SHP             | `SO4_AS` + `SO4_CS` | 0.01878 each | 2.5%, half accumulation, half coarse |
| SO2, AGR / RCO / WST / TRA / SLV | `SO4_KS`            | 0.03757      | 2.5%, Aitken                         |
| SO2, volcanic                    | `SO4_AS` + `SO4_KS` | 0.01878 each | 2.5%, half and half                  |
| CO, anthropogenic (SOA)          | `POM_KS`            | 0.049        | SOA from CO                          |
| terpenes, biogenic (SOA)         | `POM_KS`            | 0.077        | SOA from monoterpenes                |
| DMS as SO2                       | `SO2`               | 1.03         | simplified chemistry                 |


:::{admonition} Primary sulphate factor (2.5%)
:class: note

[Van Noije et al. (2021)](https://doi.org/10.5194/gmd-14-5637-2021) write "2.5 % of the emitted SOx mass is assumed to be emitted in
the form of SO4 particles", citing [Dentener et al. (2006)](https://doi.org/10.5194/acp-6-4321-2006), who define it on
sulfur: "2.5% of sulfur should be emitted as particulate SO4", with m(S) = 0.5 m(SO2) =
0.33 m(SO4). The factor on the SO2 mass is therefore 0.025 x 1.5 = 0.0375, as SO4 mass.
The M7 tracer holds SO4 mass (the optics convert it to H2SO4), so SO4 is the right basis.

| Source                                                            | 2.5%    | 1.25%   |
|-------------------------------------------------------------------|:-------:|:-------:|
| [Dentener et al. (2006)](https://doi.org/10.5194/acp-6-4321-2006) | 0.0375  | 0.01875 |
| M7 molar masses (SO4/SO2 = 1.49949)                               | 0.03749 | 0.01874 |
| `.emi` entries                                                    | 0.03757 | 0.01878 |

The entries agree within 0.2%.
:::

:::{admonition} Secondary organic aerosol (SOA) factors
Two sources add POM to `POM_KS` from gas-phase precursors. Each factor is a target total
of SOA divided by the total emission of its precursor:

| Source            | Precursor                                                                            | Factor | Target SOA     | Precursor total                                                                 |
|-------------------|--------------------------------------------------------------------------------------|:------:|----------------|---------------------------------------------------------------------------------|
| Anthropogenic SOA | CO of every anthropogenic sector                                                     | 0.049  | 24.6 Tg/yr     | CO emissions 1990-2020: about 500 Tg/yr (from 570 Tg in 1990 to 414 Tg in 2020) |
| Biogenic SOA      | monoterpenes (alpha-pinene, beta-pinene, others) of CAMS-GLOB-BIO, not part of CMIP7 | 0.077  | about 40 Tg/yr | 521 Tg/yr of terpenes                                                           |

The target SOA totals, 24.6 Tg/yr (anthropogenic) and about 40 Tg/yr (biogenic), were
deduced from the CAMS emissions. For CO, several years were compared (for example
570 Tg in 1990 and 414 Tg in 2020); given the variability and uncertainty of these
emissions, a reference value of 500 Tg/yr was taken to set the factor: 24.6/500 = 0.049.
The `.emi` files use this fixed conversion factor, so the actual anthropogenic SOA follows
the CO emissions of each year (with 0.049: about 28 Tg in 1990 and 20 Tg in 2020).
The 521 Tg/yr of terpenes also come from the CAMS sources, scaled to give the expected
SOA: 40/521 = 0.077.
:::

## Known differences with van Noije et al. (2021)

- **Solid biofuel.** The paper emits biofuel BC and POA like biomass burning (5%
  insoluble, 95% soluble). Here solid biofuel stays in `anthro-surf` and goes 100% to
  `BC_KI`/`POM_KI`: ScenarioMIP provides no solid-biofuel files, so the split is not
  applied, to keep historical and ScenarioMIP consistent.
- **Aviation.** The standard `.emi` emit no aviation aerosol or SO2 (no `paramid` for
  `AVI`). The paper does not specify aircraft BC, SO2 or SO4. A possible implementation
  of aviation aerosols is described in the section below.

## Aviation aerosol emissions

Aircraft soot is much smaller than soot from other sources:

| Source                                                                                                         | Geometric mean diameter | $\sigma$ |
|----------------------------------------------------------------------------------------------------------------|:-----------------------:|:--------:|
| A-PRIDE 4 campaign, 3 engine types ([Lobo et al., 2015](https://doi.org/10.1080/02786826.2015.1047012))        | 20-45 nm                | 1.55-1.9 |
| 42 engines of 19 turbofan types, engine exit ([Durdina et al., 2024](https://doi.org/10.1021/acs.est.4c02538)) | 7-52 nm                 | 1.7-2.5  |
| Global civil aviation inventory ([Zhang et al., 2019](https://doi.org/10.1038/s41467-019-08491-9))             | 32 nm                   | 1.85     |

A diameter of about 32 nm is a radius of about 0.016 µm: Aitken range, half of the
0.03 µm used for other combustion sources. `cmip7_m7_simchem_aviation.emi` (not tested
yet) therefore adds, from `anthro-air`:

| Species              | Tracer      | Factor  | Radius   | paramid |
|----------------------|-------------|:-------:|:--------:|:-------:|
| BC                   | `BC_KI`     | 1.00    | 0.016 µm | 219034  |
| OC                   | `POM_KI`    | 1.60    | 0.016 µm | 219035  |
| SO4 (2.5% of sulfur) | `SO4_KS`    | 0.03757 | 0.016 µm | 219037  |
| SO2                  | `SO2` (gas) | 1.00    | --       | 212230  |

[^so4]: The M7 SO4 tracers hold SO4 mass, so the emission factor of primary sulphate
    uses SO4, not H2SO4 (see the note "Primary sulphate factor" below, with the basis of
    the 2.5% in [van Noije et al. (2021)](https://doi.org/10.5194/gmd-14-5637-2021), who cite [Dentener et al. (2006)](https://doi.org/10.5194/acp-6-4321-2006)). `MASS_DENSITY`,
    which converts the emitted mass flux into a number flux, is the density of H2SO4
    (1841 kg m-3, as in [van Noije et al. (2021)](https://doi.org/10.5194/gmd-14-5637-2021), Table 1): the SO4 mass is implicitly
    reinterpreted as H2SO4. This must be consistent with the rest of the code, so that such
    a conversion is not applied twice: the optical properties, in particular, also convert
    to H2SO4 with `h2so4_factor = xmh2so4/xmso4` (`tm5m7_data.F90`, used in
    `tm5m7_optics_aop_get.F90`). It remains to be checked that this scaling is not applied
    twice; its numerical impact is small (`h2so4_factor` = 1.021, about 2%).
