.PHONY: check fmt lint type arch test licenses mutate bench

check: lint type arch test licenses

fmt:
	uv run ruff format .
	uv run ruff check --fix .

lint:
	uv run ruff format --check .
	uv run ruff check .

type:
	uv run mypy

arch:
	uv run lint-imports

test:
	uv run python scripts/check_tests.py
	uv run pytest --cov

licenses:
	uv run pip-licenses --partial-match --ignore-packages tf-diff \
		--allow-only="MIT;BSD;Apache;ISC;PSF;Python Software Foundation;Mozilla Public License 2.0;MPL-2.0"

# Linux or WSL only: mutmut needs fork.
mutate:
	uv run mutmut run
# docs/performance.md: run on an idle machine; the 50k plan needs about 1 GB of memory
bench:
	uv run python scripts/bench.py matrix --sizes 100,1000,10000,50000 --repeat 5
