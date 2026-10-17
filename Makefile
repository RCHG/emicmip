# ╭────────────────────────────────────────────────────────────────────────────╮
# │ Makefile                                              (updated 2026-10)    │
# │                                                                            │
# │ Author:  Ramiro Checa-Garcia (KNMI)                                        │
# │ Purpose: Shortcuts to produce the "official" datasets with cmip_preemis    │
# │                                                                            │
# ╰────────────────────────────────────────────────────────────────────────────╯
#
# Usage:
#   make cmip7-historical                        # all years
#   make cmip7-historical YEARS=1850,1900        # selected years
#   make cmip7-historical YEARS=1850-1910        # interval (inclusive)
#   make cmip7-historical YEARS=1850-1860,1900   # both can be mixed
#   make cmip7-scenariomip-m YEARS=2022 OPTS="--overwrite --verbose"
#   make -n cmip7-historical YEARS=1850-1855     # dry-run: print the command only
#   make cmip7-scenariomip-m YEARS=2022-2030 SUBMIT=sbatch                   # as a batch job
#   make cmip7-scenariomip-m YEARS=2022-2030 SUBMIT=sbatch ACCOUNT=nlchecki  # charged to an account

#---[ Variables (override from the command line) ]------------------------------

PREEMIS ?= ./cmip_preemis
GROUPS  ?= -a -b -f
STORE   ?= year
YEARS   ?=
OPTS    ?=
SUBMIT  ?=
ACCOUNT ?=
QOS     ?=
SBATCH_OPTS ?=
LOGDIR  ?= outs/logs
MODULES ?= python3 cdo nco ecmwf-toolbox

# Stop on a misspelled variable (e.g. YAERS=2022): make would otherwise accept
# it silently and run with no --years, i.e. every year of the config.
KNOWN_VARS   := PREEMIS GROUPS STORE YEARS OPTS SUBMIT ACCOUNT QOS SBATCH_OPTS LOGDIR MODULES
UNKNOWN_VARS := $(filter-out $(KNOWN_VARS),$(foreach v,$(.VARIABLES),$(if $(filter command line,$(origin $(v))),$(v))))
ifneq ($(UNKNOWN_VARS),)
$(error Unknown variable(s): $(UNKNOWN_VARS) -- known: $(KNOWN_VARS) (typo?))
endif

# Expand YEARS ("1850,1900", "1850-1910" or a mix) into a space separated list
ifneq ($(strip $(YEARS)),)
YEARS_LIST := $(shell echo '$(YEARS)' | tr ',' '\n' | \
    while IFS=- read a b; do \
        if [ -n "$$b" ]; then seq "$$a" "$$b"; else echo "$$a"; fi; \
    done | tr '\n' ' ')
ifeq ($(strip $(YEARS_LIST)),)
$(error YEARS='$(YEARS)' expands to no years (is the interval reversed?))
endif
YEARS_ARG := --years $(YEARS_LIST)
endif

RUN = $(PREEMIS) $(GROUPS) --store $(STORE) $(YEARS_ARG) $(OPTS)

# SUBMIT=sbatch runs the target as a Slurm batch job instead of in this shell.
#   ACCOUNT  project charged for the job (--account); default: the user's own
#   QOS      queue/service level (--qos); default: the system one (nf on Atos HPCF)
#   SBATCH_OPTS  any other sbatch option, e.g. --time=24:00:00
#   MODULES  modules loaded inside the job, the ones lib/server_env.py checks
#            for (a batch job does not inherit the
#            ones of this shell); empty: none. The job runs in a login shell
#            (bash -l), so that `module` exists there.
# The log goes to $(LOGDIR)/<target>_<jobid>.log; the folder is created first,
# as sbatch fails without a clear message when it is missing. Memory is raised
# to 16G (the default QoS kills jobs above 8000 MiB). Without SUBMIT the command
# runs here, as before.
ifeq ($(strip $(SUBMIT)),)
EXEC = $(1)
else ifeq ($(strip $(SUBMIT)),sbatch)
SBATCH = sbatch --job-name=emi-$@ --mem=16G --output=$(LOGDIR)/$@_%j.log \
         $(if $(strip $(ACCOUNT)),--account=$(ACCOUNT)) $(if $(strip $(QOS)),--qos=$(QOS)) $(SBATCH_OPTS)
EXEC = mkdir -p $(LOGDIR) && $(SBATCH) \
       --wrap="bash -lc '$(if $(strip $(MODULES)),module load $(MODULES) && )$(1)'"
else
$(error SUBMIT='$(SUBMIT)' not supported: use SUBMIT=sbatch (or nothing to run here))
endif

#---[ Official datasets ]-------------------------------------------------------

.PHONY: help cmip7-historical cmip7-scenariomip-m cmip7-scenariomip-h cmip7-scenariomip-l cmip7-scenariomip-vl cmip6-historical

help:
	@sed -n '9,17p' $(firstword $(MAKEFILE_LIST))
	@echo
	@echo "Targets:   cmip7-historical  cmip7-scenariomip-m  cmip7-scenariomip-h  cmip7-scenariomip-l  cmip7-scenariomip-vl  cmip6-historical"
	@echo "Variables: YEARS=$(YEARS) GROUPS=$(GROUPS) STORE=$(STORE) OPTS=$(OPTS)"
	@echo "Batch:     SUBMIT=sbatch ACCOUNT=$(ACCOUNT) QOS=$(QOS) SBATCH_OPTS=$(SBATCH_OPTS) LOGDIR=$(LOGDIR)"
	@echo "           MODULES=$(MODULES)"

# -e (--ecearth3) is safe for the official dataset: it only adds a few extra
# anthro-surf-ecearth files to the tar archives; all other core files are
# bit-identical to a run without it.
cmip7-historical:
	$(call EXEC,$(RUN) -c cmip7 -m historical -e)

cmip7-scenariomip-m:
	$(call EXEC,$(RUN) -c cmip7 -m scenariomip-m)

cmip7-scenariomip-h:
	$(call EXEC,$(RUN) -c cmip7 -m scenariomip-h)

cmip7-scenariomip-l:
	$(call EXEC,$(RUN) -c cmip7 -m scenariomip-l)

cmip7-scenariomip-vl:
	$(call EXEC,$(RUN) -c cmip7 -m scenariomip-vl)

cmip6-historical:
	$(call EXEC,$(RUN) -c cmip6 -m historical)
