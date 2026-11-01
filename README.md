# tf-diff

Reads `terraform show -json` and tells you what a plan actually does: which attribute forces a
replace, what depends on the resource, and whether you're about to lose data in prod.

```
$ tf-diff analyze tfplan.json

Terraform Semantic Diff
────────────────────────────────────────────────────────────────────────
Environment   production
Terraform     1.16.0 (plan format 1.2)
Resources     12 inspected, 10 changed, 0 ignored
Changes       1 create, 7 update, 1 delete, 1 replace
Risk          5 critical, 2 high, 1 medium, 0 low, 1 info
────────────────────────────────────────────────────────────────────────

CRITICAL aws_s3_bucket.audit_logs
  action        DELETE
  why           the resource was removed from configuration
  blast radius  0 direct, 0 indirect
  score         85/100, confidence high
                +60 critical finding (destroy-production-resource)
                +15 delete: the old object is destroyed
                +10 production
```

Read-only: it never runs `apply` and never calls a cloud API.

- Diff without the noise: `"10"` vs `10` is not a change, unknown-after-apply is not "changed",
  secrets are redacted while parsing.
- Dependency graph across modules, `count` and `for_each`; blast radius split into direct and
  indirect dependents.
- 12 rules (generic + AWS), each finding with evidence and a confidence. See
  [docs/rules.md](docs/rules.md).
- Output as terminal, JSON, Markdown (PR comments) or SARIF (code scanning). See
  [docs/outputs.md](docs/outputs.md).
- 10k-resource plan in ~4.5 s and ~220 MB. See [docs/performance.md](docs/performance.md).

What changed between versions: [CHANGELOG.md](CHANGELOG.md).

## Usage

Python 3.10 or newer.

```bash
uv sync
terraform plan -out=tfplan && terraform show -json tfplan > tfplan.json
uv run tf-diff analyze tfplan.json --environment production
```

```
tf-diff analyze PLAN [-f terminal|json|markdown|sarif]     full report, always exits 0
tf-diff check PLAN [--fail-on SEV] [--fail-on-confidence low|high]
                                                           same report, exits 1 on a finding at
                                                           --fail-on (default high)
tf-diff explain PLAN ADDRESS                               one resource in detail
tf-diff graph PLAN [--resource ADDR [--to ADDR]] [-f json]
tf-diff rules | schema | version
```

`check` only fails on high-confidence findings by default. Low-confidence ones (the deciding
value is unknown until apply) are still reported, and stderr says how many were skipped.

`analyze`, `check` and `explain` take `--config PATH` (default `./.tf-diff.yaml`) and
`--environment NAME`. `--environment ""` beats the config and `TF_DIFF_ENVIRONMENT` and leaves it
to resource tags.

Exit codes: `0` ok, `1` check failed, `2` bad input (plan, address or CLI option), `3` bad config,
`4` bug.

## Config

`.tf-diff.yaml`. Precedence: defaults < file < `TF_DIFF_ENVIRONMENT` < flags.

```yaml
environment: production     # otherwise Environment / env tags decide, see docs/rules.md
fail_on: high
fail_on_confidence: high    # low: also fail when the deciding value is unknown until apply
rules:
  reduce-capacity:
    threshold: 50           # percent
  wide-blast-radius:
    threshold: 10           # dependents
  public-database:
    severity: high
  sensitive-value-changed:
    enabled: false
ignore:
  - module.sandbox.*        # full address; * and ? are wildcards, [ ] is literal
```

Unknown keys and rule ids fail with exit 3, so a typo can't quietly turn a rule off.

## CI

```yaml
permissions:
  contents: read
  pull-requests: write     # PR comment
  security-events: write   # code scanning
steps:
  - run: terraform plan -out=tfplan && terraform show -json tfplan > tfplan.json
  - run: tf-diff analyze tfplan.json --format markdown > tf-diff.md
  - id: check
    run: |
      set +e
      tf-diff check tfplan.json --format sarif > tf-diff.sarif
      echo "code=$?" >> "$GITHUB_OUTPUT"
  - uses: github/codeql-action/upload-sarif@v3
    with:
      sarif_file: tf-diff.sarif
      category: tf-diff
  # post tf-diff.md as a PR comment; it starts with <!-- tf-diff:report --> so you can update it
  - if: steps.check.outputs.code != '0'
    run: exit 1
```

`set +e` lets the SARIF upload and the comment go out before the job fails. Code scanning is
free on public repos; private ones need GitHub Code Security.

## How it's built

```
terraform show -json
        │
 terraform/   parser + references, the only code that knows the JSON shape;
        │     sensitive values become markers here
 model/       frozen dataclasses: Change, Attributes, Graph, Finding, Report
        │
 analysis/    diff, blast radius, score; runs rules/ (pure functions of one change)
        │
 report/      terminal, JSON, Markdown, SARIF
        │
 cli.py       files, env, exit codes; config.py turns .tf-diff.yaml into Settings
```

Dependencies only point inward; import-linter checks that.

## Examples

[`examples/production-simulation`](examples/production-simulation) is a stack made of
`terraform_data`, so it runs without a cloud. `dangerous.tfvars` shrinks the zones, replaces the
database, rotates a password and drops workers:

```bash
cd examples/production-simulation
terraform init && terraform apply -var-file=baseline.tfvars -auto-approve
terraform plan -var-file=dangerous.tfvars -out=tfplan && terraform show -json tfplan > tfplan.json
tf-diff analyze tfplan.json --environment production
```

[`examples/aws-simulation`](examples/aws-simulation) uses the real `hashicorp/aws` provider
against [Moto](https://github.com/getmoto/moto) (local AWS emulator, fake keys): VPC across three
zones, security groups, RDS, S3, DynamoDB, an ASG behind a load balancer. Apply `baseline.tfvars`,
then plan one of:

- `baseline.tfvars`: no findings (Moto reports some drift)
- `dangerous.tfvars`: every guard off, one finding per guard
- `rebuild-network.tfvars`: resized subnets, so every id downstream is unknown; low-confidence
  redundancy findings

```bash
pip install "moto[server]" && moto_server -H 127.0.0.1 -p 5555
cd examples/aws-simulation
terraform init && terraform apply -var-file=baseline.tfvars -auto-approve
terraform plan -var-file=dangerous.tfvars -out=tfplan && terraform show -json tfplan > tfplan.json
```

The three plans are recorded in `tests/golden/moto-*`.

## Security

- Secrets don't get past the parser. A test plants `CANARY-...` values and checks every output
  format, `explain` and error messages for them.
- Plan JSON is untrusted: 512 MiB size limit, nesting limit, no `eval` or `pickle`. Config goes
  through `yaml.safe_load`. No plugins.
- Errors name addresses and attribute paths, never values.

## Development

```bash
make check                     # ruff, mypy --strict, import-linter, test gate, pytest + coverage, licenses
uv run pytest -m terraform     # runs the real terraform binary on examples/
UPDATE_GOLDEN=1 uv run pytest tests/integration tests/golden   # re-record plans and golden output
uv run python scripts/catalogue_plan.py   # rebuild the rule-catalogue plan
make mutate                    # mutation testing, Linux or WSL only (mutmut needs fork)
```

## License

Apache 2.0, see [LICENSE](LICENSE).
