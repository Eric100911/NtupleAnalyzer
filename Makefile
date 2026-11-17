# The Python interface resolves the versioned configuration and delegates to Make.
# Usage: source the LCG setup, then make CONFIG=configs/analysis/jjp.yaml plots
CONFIG ?= configs/analysis/jjp.yaml
PYTHON ?= python3
JOBS ?= 1
export NTUPLE_CONFIG := $(CONFIG)
export NTUPLE_JOBS := $(JOBS)
.PHONY: plan training validation plots acceptance efficiency correction
plan:
	$(PYTHON) -m ntuple_analyzer --config "$$NTUPLE_CONFIG" plan
training validation plots acceptance efficiency correction:
	$(PYTHON) -m ntuple_analyzer --config "$$NTUPLE_CONFIG" run --target $@ --jobs "$$NTUPLE_JOBS"
