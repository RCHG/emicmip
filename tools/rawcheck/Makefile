# ╭────────────────────────────────────────────────────────────────────────────╮
# │ rawcheck/Makefile                                     (updated 2026-10)    │
# │                                                                            │
# │ Author:  Ramiro Checa-Garcia (KNMI)                                        │
# │ Purpose: Check every raw input4MIPs folder in one go (read-only)           │
# │                                                                            │
# ╰────────────────────────────────────────────────────────────────────────────╯
#
# Copy this rawcheck/ folder next to the raw data folders, e.g.
#   cp -r tools/rawcheck $HPCPERM/raw_emissions/cmip7/historical/
#   cd $HPCPERM/raw_emissions/cmip7/historical/rawcheck
#   make                      # check every sibling folder
#   make REPO=~/emicmip   # ... and which files its etc/*_cmip7.toml configs read
#   make ONLY="BB4CMIP7 CEDS-CMIP" REPO=~/emicmip   # only folders starting so
#   make bytes                # also byte-compare same-size files (slow)
#
# Output: screen + out/rawcheck.log, out/inventory.csv, out/species_versions.csv

RAW    ?= ..
REPO   ?=
ONLY   ?=
TOMLS  ?= $(if $(REPO),$(wildcard $(REPO)/etc/*_cmip7.toml))
OUT    ?= out
PYTHON ?= python3

ARGS = --raw $(RAW) --out $(OUT) $(if $(ONLY),--only $(ONLY)) $(if $(TOMLS),--toml $(TOMLS))

.PHONY: check bytes help

check:
	@mkdir -p $(OUT)
	$(PYTHON) raw_check.py $(ARGS) 2>&1 | tee $(OUT)/rawcheck.log

bytes:
	@mkdir -p $(OUT)
	$(PYTHON) raw_check.py $(ARGS) --bytes 2>&1 | tee $(OUT)/rawcheck.log

help:
	@sed -n '9,17p' $(firstword $(MAKEFILE_LIST))

