.PHONY: reproduce check test check-uotd

reproduce:
	python3 scripts/reproduce_release.py

check:
	python3 scripts/reproduce_release.py --check

test:
	python3 -m unittest discover -s tests -v

check-uotd:
	python3 scripts/build_uotd_inputs.py --check
