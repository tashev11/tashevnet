.PHONY: install check test lint run once doctor

install:
	python3 -m pip install -e ".[dev]"

lint:
	ruff check src tests

test:
	pytest -q

check: lint test
	python3 -m compileall -q src

run:
	tashevnet run

once:
	tashevnet once

doctor:
	tashevnet doctor
