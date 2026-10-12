PYTHON ?= python

.PHONY: gates test ratchet mutation

gates:
	$(PYTHON) scripts/gates.py

test:
	$(PYTHON) -m pytest -q

ratchet:
	$(PYTHON) scripts/ratchet.py

mutation:
	$(PYTHON) scripts/mutation_smoke.py
