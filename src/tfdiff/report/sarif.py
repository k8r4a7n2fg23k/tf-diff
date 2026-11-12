"""SARIF 2.1.0 for GitHub code scanning."""

import hashlib

from tfdiff import __version__
from tfdiff.model.findings import Finding, Severity
from tfdiff.model.report import Report
from tfdiff.report.document import Document, dump
from tfdiff.rules.registry import RULES

LEVELS = {
    Severity.CRITICAL: "error",
    Severity.HIGH: "error",
    Severity.MEDIUM: "warning",
    Severity.LOW: "note",
    Severity.INFO: "note",
}
# GitHub maps security-severity >= 9.0 to critical, >= 7.0 high, >= 4.0 medium
SECURITY_SEVERITY = {
    Severity.CRITICAL: "9.5",
    Severity.HIGH: "8.0",
    Severity.MEDIUM: "5.5",
    Severity.LOW: "3.0",
    Severity.INFO: "1.0",
}

# GitHub rejects an upload whose run holds more; findings come most severe first
MAX_RESULTS = 25_000


def _fingerprint(found: Finding) -> str:
    # labels are attribute paths, stable across runs; texts hold values that change
    labels = "\0".join(evidence.label for evidence in found.evidence)
    return hashlib.sha256(f"{found.rule}\0{found.address}\0{labels}".encode()).hexdigest()


def _result(found: Finding, index: int, artifact: str) -> Document:
    return {
        "ruleId": found.rule,
        "ruleIndex": index,
        "level": LEVELS[found.severity],
        "message": {"text": f"{found.address}: {found.title}. {found.reason}"},
        "locations": [
            {
                "physicalLocation": {
                    "artifactLocation": {"uri": artifact},
                    "region": {"startLine": 1},
                },
                "logicalLocations": [{"fullyQualifiedName": found.address, "kind": "resource"}],
            }
        ],
        "partialFingerprints": {"tfdiffFinding/v1": _fingerprint(found)},
        "properties": {
            "severity": str(found.severity),
            "confidence": str(found.confidence),
            "evidence": [f"{evidence.label}: {evidence.text}" for evidence in found.evidence],
        },
    }


def render(report: Report, artifact: str) -> str:
    """SARIF log; `artifact` is the plan path as the user gave it, the only file we can point at."""
    index = {rule.id: position for position, rule in enumerate(RULES)}
    driver: Document = {
        "name": "tf-diff",
        "version": __version__,
        "semanticVersion": __version__,
        "rules": [
            {
                "id": rule.id,
                "name": rule.id,
                "shortDescription": {"text": rule.title},
                "defaultConfiguration": {"level": LEVELS[rule.severity]},
                "properties": {
                    "security-severity": SECURITY_SEVERITY[rule.severity],
                    "tags": ["terraform", "infrastructure"],
                },
            }
            for rule in RULES
        ],
    }
    active = [_result(found, index[found.rule], artifact) for found in report.findings]
    quiet = [
        {
            **_result(muted.finding, index[muted.finding.rule], artifact),
            "suppressions": [{"kind": "external", "justification": muted.reason}],
        }
        for muted in report.suppressed
    ]
    # suppressed ones go last: they are the first to drop at the cap
    results = [*active, *quiet][:MAX_RESULTS]
    run: Document = {"tool": {"driver": driver}, "results": results}
    if left := len(active) + len(quiet) - len(results):
        notice = (
            f"{left} finding(s) left out, suppressed ones first, then the least severe: GitHub "
            "rejects a run of more than "
            f"{MAX_RESULTS} results; the JSON report has them all"
        )
        run["invocations"] = [
            {
                "executionSuccessful": True,
                "toolExecutionNotifications": [{"level": "warning", "message": {"text": notice}}],
            }
        ]
    return dump(
        {
            "$schema": "https://json.schemastore.org/sarif-2.1.0.json",
            "version": "2.1.0",
            "runs": [run],
        }
    )
