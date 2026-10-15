# Outputs

Every format is deterministic: same plan, byte-identical output, whatever order the resources
come in. Findings sort by severity (desc), address, rule id; everything else by address. No
timestamps.

## Terminal (`-f terminal`, default)

For people. Resources with findings first, worst first, then "Other changes".

## JSON (`-f json`)

For scripts. Schema: [`src/tfdiff/report/report-v1.json`](../src/tfdiff/report/report-v1.json),
or `tf-diff schema`. `schema_version` is `"1"` and only changes on a breaking change, separately
from the app version.

```json
{
  "schema_version": "1",
  "tool": {"name": "tf-diff", "version": "0.1.0", "rules_version": "1"},
  "plan": {"format_version": "1.2", "terraform_version": "1.16.0"},
  "environment": "production",
  "summary": {"resources": 12, "changed": 10, "ignored": 0,
              "actions": {"create": 1, "update": 7, "delete": 1, "replace": 1}, "risk": {"critical": 5, "high": 2, "medium": 1, "low": 0, "info": 1}},
  "warnings": [],
  "findings": [{"rule": "...", "severity": "critical", "resource": "...", "title": "...",
                "reason": "...", "confidence": "high", "evidence": [{"label": "...", "text": "..."}]}],
  "changes": [{"address": "...", "type": "aws_db_instance", "mode": "managed", "provider": "...",
               "deposed": null, "action": "replace", "actions": ["delete", "create"],
               "environment": "production", "why": ["storage_type forces replacement"],
               "attributes": [{"path": "storage_type", "kind": "modified",
                               "before": {"state": "known", "value": "gp2"},
                               "after": {"state": "known", "value": "io2"},
                               "forces_replacement": true}],
               "dependencies": [], "blast_radius": {"direct": [], "indirect": []},
               "score": {"value": 97, "confidence": "high", "factors": ["+60 ..."]}, "findings": ["..."]}],
  "ignored": []
}
```

Trimmed to one finding and one change.

Values are `{"state": "known" | "unknown" | "null" | "sensitive", "value": ...}`. `value` is
`null` unless the state is `known`, so sensitive values never show up.

## Markdown (`-f markdown`)

For PR comments. First line is `<!-- tf-diff:report -->`, so CI can find and update the same
comment. A findings table, then a collapsed `<details>` block with the evidence per resource.

## SARIF (`-f sarif`)

SARIF 2.1.0 for GitHub code scanning, one result per finding. Each result points at the plan file
(line 1) with the resource address as a logical location. Levels: critical/high `error`, medium
`warning`, low/info `note`; rules also carry `security-severity`. `partialFingerprints` hash the
rule id, address and evidence labels (attribute paths, never values), so alerts stay the same
across runs.
