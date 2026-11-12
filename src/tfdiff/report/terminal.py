"""Human report. Every string goes through rich.Text: addresses like `x["a"]` read as markup."""

from rich.console import Console
from rich.text import Text

from tfdiff.model.findings import Finding, Severity
from tfdiff.model.graph import BlastRadius
from tfdiff.model.report import Assessment, Report, action_counts, severity_counts
from tfdiff.model.values import show, show_path
from tfdiff.rules.rule import Rule

LINE = "─" * 72
STYLES = {
    Severity.CRITICAL: "bold red",
    Severity.HIGH: "red",
    Severity.MEDIUM: "yellow",
    Severity.LOW: "cyan",
    Severity.INFO: "dim",
}
LABEL = 14


def _out(console: Console, *parts: str | tuple[str, str]) -> None:
    console.print(Text.assemble(*parts), markup=False, highlight=False, soft_wrap=True)


def _row(console: Console, label: str, text: str, indent: int = 2) -> None:
    _out(console, " " * indent, (label.ljust(LABEL), "bold"), text)


def _rank(level: Severity) -> int:
    return level.rank


def _severity(level: Severity) -> tuple[str, str]:
    return (level.upper().ljust(9), STYLES[level])


def _count(counts: dict[str, int]) -> str:
    return ", ".join(f"{count} {name}" for name, count in counts.items()) or "none"


def render(console: Console, report: Report) -> None:
    _out(console, ("Terraform Semantic Diff", "bold"))
    _out(console, LINE)
    _row(console, "Environment", report.environment or "not set (resource tags decide)", 0)
    version = report.terraform_version or "unknown"
    _row(console, "Terraform", f"{version} (plan format {report.format_version})", 0)
    _row(
        console,
        "Resources",
        f"{report.inspected} inspected, {len(report.assessments)} changed, "
        f"{len(report.ignored)} ignored"
        + (f", {len(report.suppressed)} findings suppressed" if report.suppressed else ""),
        0,
    )
    _row(
        console,
        "Changes",
        _count({str(action): count for action, count in action_counts(report).items()}),
        0,
    )
    _row(
        console,
        "Risk",
        _count({str(level): count for level, count in severity_counts(report).items()}),
        0,
    )
    for warning in report.warnings:
        _out(console, ("warning: ", "yellow"), warning)
    _out(console, LINE)
    flagged = sorted(
        (
            (max((found.severity for found in assessment.findings), key=_rank), assessment)
            for assessment in report.assessments
            if assessment.findings
        ),
        key=lambda pair: (-pair[0].rank, pair[1].change.address),
    )
    for severity, assessment in flagged:
        _out(console)
        _assessment(console, assessment, severity)
    if report.suppressed:
        _out(console)
        _out(console, ("Suppressed", "bold"))
        width = max(len(muted.finding.rule) for muted in report.suppressed)
        for muted in report.suppressed:
            until = f" (until {muted.until})" if muted.until else ""
            _out(
                console,
                "  ",
                _severity(muted.finding.severity),
                (muted.finding.rule.ljust(width), "bold"),
                "  ",
                f"{muted.finding.address}: {muted.reason}{until}",
            )
    quiet = [assessment for assessment in report.assessments if not assessment.findings]
    if quiet:
        _out(console)
        _out(console, ("Other changes", "bold"))
        for assessment in quiet:
            _out(console, "  ", str(assessment.change.action).ljust(9), assessment.change.label)
    if not report.assessments:
        _out(console)
        _out(console, "No changes.")


def _assessment(console: Console, assessment: Assessment, severity: Severity) -> None:
    change = assessment.change
    _out(console, _severity(severity), (change.label, "bold"))
    _row(console, "action", change.action_label)
    for line in assessment.why:
        _row(console, "why", line)
    _row(
        console,
        "blast radius",
        f"{len(assessment.blast.direct)} direct, {len(assessment.blast.indirect)} indirect",
    )
    if assessment.score is not None:
        _row(
            console,
            "score",
            f"{assessment.score.value}/100, confidence {assessment.score.confidence}",
        )
        for factor in assessment.score.factors:
            _row(console, "", factor)
    for found in assessment.findings:
        _finding(console, found)


def _finding(console: Console, found: Finding) -> None:
    _out(console, "  ", _severity(found.severity), (found.rule, "bold"), "  ", found.title)
    pad = " " * 13
    _out(console, pad, found.reason)
    _out(console, pad, ("confidence ", "dim"), str(found.confidence))
    for evidence in found.evidence:
        _out(console, pad, (f"{evidence.label}: ", "dim"), evidence.text)


def explain(console: Console, address: str, assessment: Assessment | None) -> None:
    _row(console, "RESOURCE", address, 0)
    if assessment is None:
        _row(console, "ACTION", "nothing to assess: no-op or data source read", 0)
        return
    change = assessment.change
    if change.deposed:
        _row(console, "DEPOSED", change.deposed, 0)
    _row(console, "TYPE", change.resource.type, 0)
    _row(console, "ACTION", change.action_label, 0)
    _row(console, "ENVIRONMENT", assessment.environment or "not set", 0)
    for line in assessment.why or ("no reason recorded",):
        _row(console, "WHY", line, 0)
    if assessment.attributes:
        _out(console, ("ATTRIBUTES", "bold"))
        for attribute in assessment.attributes:
            mark = "  (forces replacement)" if attribute.is_forcing else ""
            _out(
                console,
                f"  {show_path(attribute.path)}: ",
                f"{show(attribute.before)} -> {show(attribute.after)}",
                (mark, "red"),
            )
    _listing(console, "DEPENDS ON", assessment.dependencies)
    _listing(console, "DIRECT DEPENDENTS", assessment.blast.direct)
    _listing(console, "INDIRECT DEPENDENTS", assessment.blast.indirect)
    if assessment.severity is None or assessment.score is None:
        _row(console, "RISK", "no findings", 0)
        return
    _out(console, ("RISK".ljust(LABEL), "bold"), _severity(assessment.severity))
    _row(
        console,
        "SCORE",
        f"{assessment.score.value}/100, confidence {assessment.score.confidence}",
        0,
    )
    for factor in assessment.score.factors:
        _out(console, "  ", factor)
    for found in assessment.findings:
        _finding(console, found)


def _listing(console: Console, title: str, addresses: tuple[str, ...]) -> None:
    _out(console, (title, "bold"))
    for address in addresses or ("none",):
        _out(console, "  ", address)


def graph(
    console: Console,
    address: str,
    dependencies: tuple[str, ...],
    radius: BlastRadius,
    chain: tuple[str, ...] | None,
) -> None:
    _row(console, "RESOURCE", address, 0)
    _listing(console, "DEPENDS ON (transitive)", dependencies)
    _listing(console, "DIRECT DEPENDENTS", radius.direct)
    _listing(console, "INDIRECT DEPENDENTS", radius.indirect)
    if chain is not None:
        _listing(console, "PATH", chain)


def edges(console: Console, dependents: dict[str, frozenset[str]]) -> None:
    for node, targets in dependents.items():
        _out(console, (node, "bold"))
        for target in sorted(targets):
            _out(console, "  -> ", target)


def rules(console: Console, registry: tuple[Rule, ...], version: str) -> None:
    _out(console, ("Rules", "bold"), f" (rules version {version})")
    for rule in registry:
        _out(console, _severity(rule.severity), (rule.id.ljust(28), "bold"), rule.title)
