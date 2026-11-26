# Changelog

`RULES_VERSION` (in `tf-diff version`) changes when a rule's logic or severity changes, and the
JSON report's `schema_version` only on a breaking change to its shape. Both are noted here.

## 0.5.0 (2026-11-26)

- OpenTofu: plans from `tofu show -json` are read the same way as Terraform's. Checked on
  OpenTofu 1.13.
- The report header now says what made the plan, Terraform or OpenTofu. It's taken from the
  provider registry; a plan with built-in providers only shows "Terraform or OpenTofu".

## 0.4.0 (2026-11-16)

- `suppress` in the config mutes one rule on one resource or a group of them, instead of dropping
  the whole resource with `ignore`.
  - `reason` is required, `until` is optional.
  - Suppressed findings don't fail `check`, but stay visible in their own block in the terminal,
    Markdown, JSON and SARIF reports.
  - After `until`, the finding is active again and the report warns about it.
- JSON report schema version 2 (adds `suppressed`).
- Fixed: a date that doesn't exist in the config (say, February 30) is a config error now, not an
  internal one.

## 0.3.0 (2026-11-08)

- `environment_tags` in the config: which tag keys hold the environment, for companies that use
  `Stage` or `env_name`. Before, prod-only checks silently turned off in that case.
- `production_names`: which environments count as production, e.g. to add `live`.
- Defaults are unchanged. An empty list or duplicates are a config error.

## 0.2.0 (2026-11-01)

- Python 3.10 to 3.15. tf-diff used to need 3.14; now it installs on the system Python of
  Ubuntu 22.04 (3.10). No change in behaviour.
- ruff and mypy now check the code against Python 3.10.

## 0.1.0 (2026-10-16)

First version: plan parsing, dependency graph, 12 rules, risk score, terminal / JSON / Markdown /
SARIF reports, `check` for CI.
