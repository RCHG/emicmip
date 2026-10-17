// ╭────────────────────────────────────────────────────────────────────────────╮
// │ cheatsheet-emicmip.typ                             (updated 2026-10)    │
// │                                                                            │
// │ Author:  Ramiro Checa-Garcia (KNMI)                                        │
// │ Purpose: One-page landscape cheat sheet of the emicmip tools           │
// │          (layout after github.com/OCamlPro/ocaml-cheat-sheets)             │
// │                                                                            │
// │ Build:   typst compile doc/cheatsheet/cheatsheet-emicmip.typ            │
// ╰────────────────────────────────────────────────────────────────────────────╯

#let accent = rgb("#1f5f9e")
#let soft   = rgb("#e8f0f8")
#let note   = rgb("#666666")

#set document(title: "emicmip cheat sheet", author: "Ramiro Checa-Garcia (KNMI)")
#set page(paper: "a4", flipped: true, margin: (x: 0.9cm, top: 0.8cm, bottom: 0.7cm),
  footer: context [
    #set text(6pt, fill: note)
    emicmip cheat sheet #h(1fr) Ramiro Checa-Garcia (KNMI) -- full details in
    `rchg.github.io/emicmip` #h(1fr) #datetime.today().display("[year]-[month]-[day]")
    · page #counter(page).display()
  ])
#set text(font: ("Fira Sans", "DejaVu Sans"), size: 7.0pt)
#set par(leading: 0.42em, spacing: 0.5em)
#show raw: set text(font: ("Fira Code", "DejaVu Sans Mono"), size: 6.5pt)
#set list(indent: 0.2em, body-indent: 0.4em, spacing: 0.35em)

// one section: coloured title strip + body
#let sec(title, body) = block(breakable: false, width: 100%, below: 0.55em,
  stroke: 0.6pt + accent, radius: 2pt, clip: true)[
  #block(width: 100%, fill: accent, inset: (x: 4pt, y: 2.5pt), below: 0pt,
    text(fill: white, weight: "bold", size: 8pt, title))
  #block(width: 100%, inset: 4pt, body)
]

// two-column "what | meaning" rows, zebra-shaded like the OCaml sheets
#let rows(..cells) = table(
  columns: (auto, 1fr), stroke: none, inset: (x: 2pt, y: 1.6pt),
  fill: (_, y) => if calc.odd(y) { soft },
  ..cells)

#let sub(t) = text(weight: "bold", fill: accent, t)
#let gray(t) = text(fill: note, t)

// ─── title ──────────────────────────────────────────────────────────────────
#grid(columns: (1fr, auto), column-gutter: 0.6em, align: (left + bottom, right + bottom),
  text(17pt, weight: "bold", fill: accent)[emicmip #text(11pt, fill: black, weight: "regular")[cheat sheet]],
  text(7pt, fill: note)[CMIP6/CMIP7 input4MIPs emissions #sym.arrow OpenIFS/IFS emission pre-processor \
    `cmip_preemis` · `cmip_check` · `cmip_validate` · `make`])
#v(-0.3em)
#line(length: 100%, stroke: 1.2pt + accent)
#v(0.1em)

// three columns; the validation recipe spans the bottom of columns 1-2, the icon
// is in the bottom-right corner
#grid(columns: (1fr, 1fr, 1fr), column-gutter: 0.8em, row-gutter: 0em,
  [
#sec[Produce the official datasets (`make`)][
  `make [-n] <target> [VAR=value ...]` #gray[(`-n`: dry run, print cmds only)] \
  #sub[Targets] \
  #rows(
    `make`, [help: targets and variables],
    `cmip7-historical`, [CMIP7 historical, with `-e` (also `-ec3` files)],
    [`cmip7-scenariomip-m` #gray[· `-h` · `-l` · `-vl`]], [CMIP7 ScenarioMIP members],
    `cmip6-historical`, [CMIP6 historical],
  )
  #sub[Variables] (all optional) \
  #rows(
    `YEARS=`, [years: `1850,1900` · `1850-1910` · mixed; default all],
    `GROUPS=`, [groups, default `"-a -b -f"`],
    `STORE=`, [tar layout: `year` (default) · `species` · `both`],
    `OPTS=`, [extra `cmip_preemis` flags, e.g. `"--overwrite --verbose"`],
  )
  #sub[Production] #gray[(single run, all groups)] \
  ```
  make cmip7-historical YEARS=1850-1855 OPTS="--nccompress --overwrite"
  ```
]

#sec[`cmip_preemis` -- produce a dataset][
  #sub[Groups] (combine freely) \
  #rows(
    `-a`, [`--anthro`: anthropogenic surface (+ speciated VOC, solid biofuel)],
    `-f`, [`--aviation`: aircraft, 3D (`AVI` + levels)],
    `-b`, [`--biomass`: biomass burning (`bburning`)],
  )
  #sub[Config] #gray[(#sym.arrow `etc/<mip>_<cmip>.toml`)] \
  #rows(
    `-c cmip7`, [`--cmip`: cmip6 | cmip7 (default cmip7)],
    `-m historical`, [`--mip`: historical | scenariomip-m | -h | -l | -vl],
    `--toml FILE`, [use this config instead],
    [`--rawpath` `--propath` `--outpath`], [override raw / temp / output paths],
  )
  #sub[Processing] \
  #rows(
    `--years 1850 2022`, [only these years (default: all of the config)],
    `--store year`, [tar per year (also: species, both)],
    `-e`, [`--ecearth3`: extra `anthro-surf-ecearth` (surf #sym.minus biof, BC/OC); tar gets `-ec3`],
    `--nccompress`, [deflate final nc (level 4, lossless) before tar],
    `--forceinterp Y`, [validation: interpolate Y although it exists (needs `--years`, `--outpath`; tar not stored)],
    `--overwrite`, [redo files that already exist],
    `--cleanafter`, [after a safe copy to the store, remove that year's nc + local tar],
    `--noclean`, [keep temp files (debug)],
    `--verbose`, [step-by-step info],
  )
  #sub[Example]
  ```
  ./cmip_preemis -a -b -f -c cmip7 -m historical --years 2022 2023
  ```
  #sub[Info at the end]
  #rows(
  `src=`, [emission specification hint],
  `summary`,[info of missing raw files],
)
]
  ],
  [
#sec[`cmip_validate` -- four modes][
  #rows(
    `--tgz T.tar`, [recreate `emissions_<group>_<year>.csv` (Tg) from a tar],
    `--compare A B`, [diff two tars: A = under test, #strong[B = reference]],
    `--timeseries DIR`, [CSVs #sym.arrow time series PDF (+ joined CSV)],
    `  --seasonal [Y ..]`, [also seasonal-cycle pages for those years],
    `--plotcompare D1 D2..`, [plot several `--compare` outputs (same A)],
  )
  #sub[Compare options] (pick one) \
  #rows(
    `--legacyref`, [B is a legacy tar (`c` or older): name aliases, lone sector paired],
    `--legacyboth`, [both A and B legacy],
    `--historicalref`, [A = ScenarioMIP, B = historical; known differences listed apart],
  )
  #sub[Common] \
  #rows(
    [`--outdir` · `--name`], [default `outs/validation/<name>/`],
    `--ecfs-cache DIR`, [ec:/... tars fetched once, reused],
    `--log`, [log y axis (timeseries, plotcompare)],
    [`--keep` · `--verbose`], [keep extracted nc · chatty],
  )
  #sub[Info] \
  Inputs may be `ec:/...` paths (copied with `ecp`). `--timeseries` and `--plotcompare`
  need no cdo/nco.
]

#sec[`cmip_check` -- what is already produced?][
  #rows(
    `--toml etc/X.toml`, [find the tars made with this toml: per year, in store? plain / `-ec3`, date, size; local files],
    `--years 1850-1900`, [restrict years (make syntax)],
    `--deep --years 2022`, [fetch tar, read bundled toml: command, version, raw data, groups],
    `--tarpath PATH`, [check a tar directly by its full path (no toml needed; with `--toml`, `--deep` compares them)],
    `--ecfs-cache DIR`, [reuse fetched tars across runs],
    [`--outpath DIR` · `--keep`], [other local path · keep temp dir],
  )
  #sub[Info]
  #gray[Nothing is downloaded without `--deep`.]
]

#sec[Output files][
  #rows(
    [local], [`{outputname}_{resol}_{suffix}_{species}_{year}.nc`],
    [in tar], [prefix #sym.arrow `tar_common` (`+ -ec3` with `-e`)],
    [tar], [`{tar_common}[-ec3]_{year}.tar` in `tar_store`],
    [stats], [`emissions_<group>_<year>.csv` (Tg, monthly/annual) inside the tar],
  )
  #sub[Suffixes] \
  #rows(
    `anthro-surf`, [CEDS surface + speciated VOC (NMVOC = their sum)],
    `anthro-biof`, [solid biofuel (BC, OC), historical only],
    `anthro-surf-ecearth`, [surf #sym.minus biof (with `-e`)],
    `anthro-air`, [aviation, 3D],
    `bburning`, [biomass burning: read `bbALL`; `bbPEAT` = CO2 peat part, never add it #gray[(legacy: `bb4-2-0`)]],
  )
  #sub[Resolutions] \
  - Historical:  `05x05` anthro/air, `025x025` bburning;
  - ScenarioMIP: `05x05` everywhere.
]
  ],
  [
#sec[Stores and datasets][
  #rows(
    [hist.], [`ec:/nldac/emissions/cmip7hist/`],
    [scen.], [`ec:/nldac/emissions/cmip7scenariomip/`],
    [CMIP6], [`ec:/nldac/emissions/cmip6hist/` (`not produced`)],
  )
  #sub[CMIP7 historical versions] \
  #rows(
    [#strong[`d-ec3`]], [#strong[use this] -- + NMVOC, N2O, CH4 aviation, `bbALL`+`bbPEAT`],
    `c`, [previous tool; CO2 bburning = peat only (scaled in place)],
    `c-ec3`, [#text(fill: red)[obsolete]: wrong peat scaling (CO2 only)],
  )
  #sub[CMIP7 ScenarioMIP versions] \
  #rows(
    [#strong[`ScenarioMIP{h,m,l,vl}-a`]], [#strong[use this]: aviation from IIASA 1-1-2],
  )
  #sub[Info]
  #gray[ECFS yearly tars also include the run's toml and stats CSV files.]
]

#sec[Config `etc/*.toml` (`[CMIP7]`)][
  #rows(
    `rawpath propath outpath`, [raw / temp / output roots; `{user}` = who runs the tool],
    `tar_store`, [`{cmd="ecp", path="ec:/..."}` (or `cp`)],
    [`tar_common` · `outputname`], [tar prefix (version letter) · local prefix],
    [`origin` `category` `target_mip`], [parts of the raw file names (`input4MIPs`, `emissions`, `CMIP`/`ScenarioMIP`)],
  )
  #sub[Per group] `[CMIP7.anthro|aviation|bburning]` \
  #rows(
    `version`, [list, tried in order],
    [`path` `resol` `years` `sectors`], [raw subfolder, grid, raw periods, sectors],
    `aggregate`, [`{target="ALL", from=[...]}` new summed sector],
    `remove_sectors`, [drop sectors after creation],
    `subsets.<name>`, [`suffix`, `species`, `species_filename_map`],
    `  extra_years`, [`[{period, species}]`: extra raw period only for those species (e.g. CH4, N2O 1970-1999)],
    `[[...scaling]]`, [`target from species file`: e.g. `bbPEAT`],
    `[[...derivespecies]]`, [`target suffix from only_if_missing`: e.g. NMVOC = #sym.Sigma 23 VOC],
    `interpolate_years`, [`true`: a year missing in its raw file is interpolated month by month from the file's neighbouring years (never extrapolated)],
  )
  #gray[Species lists = all available in raw data, not only `.emi` used.]
]
  ],
  grid.cell(colspan: 2, align: bottom + left)[
#sec[Validation recipe: new `d` vs legacy `c`][
  ```
  S=ec:/nldac/emissions/cmip7hist
  for y in 1850 1990 2022; do
    ./cmip_validate --compare $S/CMIP7hist-2025-04-18d-ec3_$y.tar $S/CMIP7hist-2025-04-18c_$y.tar \
                    --legacyref --ecfs-cache ~/ecfs_cache
  done
  ./cmip_validate --plotcompare --log outs/validation/*d-ec3_vs_*c
  ./cmip_validate --timeseries outs/validation/CMIP7-historical --seasonal 2022
  ```
  Verdicts (`plotcompare_summary.csv`): equal · close (< 0.01 %) · different ·
  only_in_A · only_in_B. Expected against `c`: only CO2 aviation differs (new source),
  plus the species new in `d` (NMVOC, N2O, CH4 aviation, ...).
]
  ],
  grid.cell(align: bottom + right)[
    #image("emicmip-icon.png", height: 2.4cm)   // symlink to doc/png/emicmip-icon.png
  ],
)
