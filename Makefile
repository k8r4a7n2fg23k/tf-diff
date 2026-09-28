.PHONY: check fmt lint type arch test licenses mutate

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
