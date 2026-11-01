# Changelog

`RULES_VERSION` (in `tf-diff version`) changes when a rule's logic or severity changes, and the
JSON report's `schema_version` only on a breaking change to its shape. Both are noted here.

## 0.2.0 (2026-11-01)

- Python 3.10 to 3.15. tf-diff used to need 3.14; now it installs on the system Python of
  Ubuntu 22.04 (3.10). No change in behaviour.
- ruff and mypy now check the code against Python 3.10.

## 0.1.0 (2026-10-16)

First version: plan parsing, dependency graph, 12 rules, risk score, terminal / JSON / Markdown /
SARIF reports, `check` for CI.
