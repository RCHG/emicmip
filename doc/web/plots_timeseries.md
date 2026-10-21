# Emission time series and seasonal cycle

:::{warning}
Only produced and validated datasets for OpenIFS developments are shown; as soon as more
datasets are produced and validated they will be shown here.
:::

:::{admonition} About this page
:class: tip

As part of the outputs produced by `cmip_preemis` and `cmip_validate` are evaluations of
global emissions of the produced datasets. Here it is shown, from those emissions_stats CSVs
produced files, time series of values where you can choose a species and a subset, and tick
the datasets to overlay. Zoom with the mouse wheel, the sliders (bottom: years, right:
values) or the box-zoom icon; the seasonal cycle is recomputed for the visible years. See
also [Emissions by sector](plots_sectors.md).

**Shaded bands**: years not produced yet in that dataset. Isolated years and pairs of years (e.g. 1800, 1850-1851) are drawn as dots in the annual view.

**Datasets**: *CMIP7 historical* is `CMIP7hist-2025-04-18d-ec3`, and *ScenarioMIP-h*, *-m*,
*-l*, *-vl* are `ScenarioMIPh-a`, `ScenarioMIPm-a`, `ScenarioMIPl-a`, `ScenarioMIPvl-a`
(see [Choosing a dataset](datasets.md#choosing-a-dataset)). The years produced of each
one are listed in [Years produced](datasets.md#years-produced).

```{raw} html
<p id="totalnote"></p>
```
:::

```{raw} html
<link rel="stylesheet" href="_static/emiviz/emiviz.css">
<div class="emiviz">
<div class="controls">
  <label class="field"><span>Species</span><select id="species"></select></label>
  <label class="field"><span>Subset</span><select id="subset"></select></label>
  <div class="field"><span>Resolution</span>
    <div class="seg" id="res"><button type="button" data-v="auto" aria-pressed="true">Auto</button><button type="button" data-v="month" aria-pressed="false">Monthly</button><button type="button" data-v="year" aria-pressed="false">Annual</button></div></div>
  <div class="field"><span>Years without data</span>
    <div class="seg" id="gapmode"><button type="button" data-v="break" aria-pressed="true">Break line</button><button type="button" data-v="connect" aria-pressed="false">Connect</button></div></div>
  <button type="button" class="btn" id="season" aria-pressed="true">Seasonal cycle</button>
  <fieldset><legend>Datasets</legend><div class="checks" id="datasets"></div></fieldset>
</div>
<p class="status" id="status"></p>

<section class="grid2" id="pane">
  <div class="chartbox"><div class="plot" id="e-ts"></div></div>
  <div class="chartbox" id="seasonbox"><div class="cap" id="cap-sc"></div><div class="plot" id="e-sc"></div></div>
</section>

<div class="admonition note">
  <p class="admonition-title">License and citation</p>
  <p><b>Figures</b> are distributed under <i>CC BY 4.0, emicmip (KNMI)</i>. Please cite emicmip as
    <a href="https://doi.org/10.5281/zenodo.23440591">doi:10.5281/zenodo.23440591</a>.
    <b>Data sources</b>: CEDS, BB4CMIP7 and ScenarioMIP emissions via
    <a href="https://input4mips-cvs.readthedocs.io/en/latest/">input4MIPs</a>.
    Data plots generated <span id="gen"></span>.</p>
</div>
</div>
<script src="https://cdn.jsdelivr.net/npm/echarts@5.5.1/dist/echarts.min.js"></script>
<script src="_static/emiviz/common.js"></script>
<script>EMI.base = "_static/emiviz/data/";</script>
<script src="_static/emiviz/data/index.js"></script>
<script src="_static/emiviz/panel_timeseries.js"></script>
```
