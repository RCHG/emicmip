# Emissions by sector

:::{warning}
Only produced and validated datasets for OpenIFS developments are shown; as soon as more
datasets are produced and validated they will be shown here.
:::

:::{admonition} About this page
:class: tip

One species, one subset and one dataset, split by sector. Zoom the series: the sector
shares and the seasonal cycle are recomputed for the visible years. Click a sector in
the legend to remove it from the three charts. See also
[Emission time series and seasonal cycle](plots_timeseries.md).

ALL and bbALL are the totals for anthropogenic surface emissions, and total (all vegetation types) open biomass burning, and are never stacked on top of the sectors. **Shaded bands**: years not produced yet in that dataset.

**Datasets**: *CMIP7 historical* is `CMIP7hist-2025-04-18d-ec3`, and *ScenarioMIP-h*, *-m*,
*-l*, *-vl* are `ScenarioMIPh-a`, `ScenarioMIPm-a`, `ScenarioMIPl-a`, `ScenarioMIPvl-a`
(see [Choosing a dataset](datasets.md#choosing-a-dataset)). The years produced of each
one are listed in [Years produced](datasets.md#years-produced).

```{raw} html
<p id="splitnote"></p>
```
:::

```{raw} html
<link rel="stylesheet" href="_static/emiviz/emiviz.css">
<div class="emiviz">
<div class="controls">
  <label class="field"><span>Species</span><select id="species"></select></label>
  <label class="field"><span>Subset</span><select id="subset"></select></label>
  <label class="field"><span>Dataset</span><select id="dataset"></select></label>
  <div class="field"><span>View</span>
    <div class="seg" id="view"><button type="button" data-v="stack" aria-pressed="true">Stacked</button><button type="button" data-v="pct" aria-pressed="false">% of total</button><button type="button" data-v="lines" aria-pressed="false">Lines</button></div></div>
  <div class="field"><span>Resolution</span>
    <div class="seg" id="res"><button type="button" data-v="auto" aria-pressed="true">Auto</button><button type="button" data-v="month" aria-pressed="false">Monthly</button><button type="button" data-v="year" aria-pressed="false">Annual</button></div></div>
</div>
<p class="status" id="status"></p>

<section class="grid2">
  <div class="chartbox"><div class="plot" id="e-ts"></div></div>
  <div class="chartbox"><div class="cap" id="cap-sh"></div><div class="plot" id="e-sh"></div></div>
</section>
<section class="chartbox">
  <div class="cap"><span id="cap-sc"></span>
    <span class="seg small" id="scmode"><button type="button" data-v="abs" aria-pressed="true">Tg/month</button><button type="button" data-v="rel" aria-pressed="false">Relative to the mean</button></span></div>
  <div class="plot short" id="e-sc"></div>
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
<script src="_static/emiviz/panel_sectors.js"></script>
```
