# Tools

emicmip is built around three tools, which share a common library in `lib/`:

| Tool            | Input                                                   | Output                                                                       |
|-----------------|---------------------------------------------------------|------------------------------------------------------------------------------|
| `cmip_preemis`  | raw CMIP files (input4MIPs) and a config (`etc/*.toml`) | one tar per year: NetCDF per species and subset, statistics CSV, config copy |
| `cmip_validate` | tars or their statistics CSV                            | comparisons of two tars, time series and seasonal cycles (PDF)               |
| `cmip_check`    | a config and the store, or one tar by its path          | which years are produced, when, with which options and tool version          |

The tars are then read by the OpenIFS/IFS emission pre-processor (part of OpenIFS, not
of this repository) through an emission-specification file (`.emi`), which writes the
GRIB files read by the model.

| Folder / file | Content                                                                                                                                                                 |
|---------------|-------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| `lib/`        | library used by the three tools                                                                                                                                         |
| `etc/`        | configuration files (TOML) used by the three tools, one per dataset                                                                                                     |
| `tools/`      | stand-alone checks: raw files against a config (`rawcheck/`), interpolation of years (`interp_check.py`), see `tools/INFO.md`                                           |
| `doc/`        | documentation: cheatsheet (`doc/cheatsheet/`), these web pages (`doc/web/`), and the tested emission-specification files (`doc/emis_spec/`) |
| `Makefile`    | production of the datasets, above all those marked as production (see [Producing datasets](producing.md))                                                               |

## Workflow of the tools

### From the raw data to the model

```{mermaid}
flowchart LR
    A["Raw CMIP files<br/>input4MIPs NetCDF<br/>(CEDS, BB4CMIP7, IIASA)"]
    B["One tar per year<br/>NetCDF per species and subset"]
    C["GRIB files<br/>read by the model"]
    A -- "cmip_preemis" --> B
    B -- "OpenIFS/IFS emission pre-processor<br/>(.emi file)" --> C
```

### Checking what has been produced

```{mermaid}
flowchart LR
    A["Raw CMIP files"]
    B["One tar per year"]
    C["Plots (PDF)<br/>comparisons of versions,<br/>time series, seasonal cycles"]
    D["Status of the dataset<br/>years produced, when,<br/>with which options"]
    A -- "cmip_preemis" --> B
    B -- "cmip_validate" --> C
    B -- "cmip_check" --> D
```

`cmip_validate` works only on the tars (or the statistics CSV inside them), never on the
raw data. `cmip_check` compares the years of a config with the tars in the store, or takes
one tar by its path (`--tarpath`), and reads back the header of each tar (emicmip version, command, date) and the raw-data
version of each group.
