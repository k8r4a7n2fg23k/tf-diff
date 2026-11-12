"""JSON report, schema `report-v2.json` (shipped next to this module)."""

import json
from importlib import resources
from typing import TypeAlias

from tfdiff import __version__
from tfdiff.model.findings import Finding
from tfdiff.model.graph import BlastRadius
from tfdiff.model.report import Assessment, Report, action_counts, severity_counts
from tfdiff.model.values import Known, Null, Sensitive, Unknown, Value, show_path

# bump on a breaking change to the JSON shape; independent of the app version
SCHEMA_VERSION = "2"

Document: TypeAlias = dict[str, object]


def schema() -> str:
    return resources.files("tfdiff.report").joinpath("report-v2.json").read_text(encoding="utf-8")


def render(report: Report) -> str:
    return dump(build(report))


def dump(document: Document) -> str:
    return json.dumps(document, indent=2, ensure_ascii=False) + "\n"


def build(report: Report) -> Document:
    return {
        "schema_version": SCHEMA_VERSION,
        "tool": {"name": "tf-diff", "version": __version__, "rules_version": report.rules_version},
        "plan": {
            "format_version": report.format_version,
            "terraform_version": report.terraform_version,
        },
        "environment": report.environment,
        "summary": {
            "resources": report.inspected,
            "changed": len(report.assessments),
            "ignored": len(report.ignored),
            "suppressed": len(report.suppressed),
            "actions": {str(action): count for action, count in action_counts(report).items()},
            "risk": {str(level): count for level, count in severity_counts(report).items()},
        },
        "warnings": list(report.warnings),
        "findings": [finding(found) for found in report.findings],
        "suppressed": [
            {
                "finding": finding(muted.finding),
                "reason": muted.reason,
                "until": muted.until.isoformat() if muted.until else None,
            }
            for muted in report.suppressed
        ],
        "changes": [assessment(assessed) for assessed in report.assessments],
        "ignored": list(report.ignored),
    }


def value(marker: Value) -> Document:
    match marker:
        case Known(value=scalar):
            return {"state": "known", "value": scalar}
        case Unknown():
            return {"state": "unknown", "value": None}
        case Sensitive():
            return {"state": "sensitive", "value": None}
        case Null():
            return {"state": "null", "value": None}


def finding(found: Finding) -> Document:
    return {
        "rule": found.rule,
        "severity": str(found.severity),
        "resource": found.address,
        "title": found.title,
        "reason": found.reason,
        "confidence": str(found.confidence),
        "evidence": [
            {"label": evidence.label, "text": evidence.text} for evidence in found.evidence
        ],
    }


def blast(radius: BlastRadius) -> Document:
    return {"direct": list(radius.direct), "indirect": list(radius.indirect)}


def assessment(assessed: Assessment) -> Document:
    change = assessed.change
    return {
        "address": change.address,
        "type": change.resource.type,
        "mode": change.resource.mode,
        "provider": change.resource.provider,
        "deposed": change.deposed,
        "action": str(change.action),
        "actions": list(change.actions),
        "environment": assessed.environment,
        "why": list(assessed.why),
        "attributes": [
            {
                "path": show_path(attribute.path),
                "kind": str(attribute.kind),
                "before": value(attribute.before),
                "after": value(attribute.after),
                "forces_replacement": attribute.is_forcing,
            }
            for attribute in assessed.attributes
        ],
        "dependencies": list(assessed.dependencies),
        "blast_radius": blast(assessed.blast),
        "score": None
        if assessed.score is None
        else {
            "value": assessed.score.value,
            "confidence": str(assessed.score.confidence),
            "factors": list(assessed.score.factors),
        },
        "findings": [found.rule for found in assessed.findings],
    }
