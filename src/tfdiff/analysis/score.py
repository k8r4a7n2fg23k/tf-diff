from tfdiff.model.findings import Finding, Severity
from tfdiff.model.graph import BlastRadius
from tfdiff.model.plan import Action
from tfdiff.model.report import Score

# additive so anyone can redo the sum; the weights are a judgement and top out at
# 60 + 15 + 10 + 15 = 100
SEVERITY_POINTS = {
    Severity.CRITICAL: 60,
    Severity.HIGH: 40,
    Severity.MEDIUM: 25,
    Severity.LOW: 10,
    Severity.INFO: 0,
}
IRREVERSIBLE_POINTS = 15
PRODUCTION_POINTS = 10
DEPENDENT_POINTS = 3
MAX_DEPENDENT_POINTS = 15


def score(
    findings: tuple[Finding, ...], action: Action, blast: BlastRadius, *, is_production: bool
) -> Score | None:
    """Score of a resource with findings; None without findings: no evidence, no score."""
    if not findings:
        return None
    top = max(findings, key=lambda finding: finding.severity.rank)
    factors = [(SEVERITY_POINTS[top.severity], f"{top.severity} finding ({top.rule})")]
    if action in {Action.DELETE, Action.REPLACE}:
        factors.append((IRREVERSIBLE_POINTS, f"{action}: the old object is destroyed"))
    if is_production:
        factors.append((PRODUCTION_POINTS, "production"))
    if blast.total:
        points = min(MAX_DEPENDENT_POINTS, DEPENDENT_POINTS * blast.total)
        factors.append((points, f"{blast.total} dependent resource(s)"))
    confidence = min(
        (finding.confidence for finding in findings if finding.severity is top.severity),
        key=lambda level: level.rank,
    )
    return Score(
        value=sum(points for points, _ in factors),
        confidence=confidence,
        factors=tuple(f"+{points} {text}" for points, text in factors),
    )
