.PHONY: test coverage crap

test:
	python3 -m pytest

coverage.xml:
	python3 -m coverage run --source=. -m pytest
	python3 -m coverage xml -o coverage.xml

coverage: coverage.xml

crap: coverage.xml
	python3 crap/scripts/analyze_crap.py . --languages python --top 20
