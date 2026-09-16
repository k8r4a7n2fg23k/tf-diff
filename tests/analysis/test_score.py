from tfdiff.analysis.score import score
from tfdiff.model.findings import Confidence, Finding, Severity
from tfdiff.model.graph import BlastRadius
from tfdiff.model.plan import Action


def _finding(severity: Severity, confidence: Confidence) -> Finding:
    return Finding("rule", severity, "aws_x.y", "title", "reason", (), confidence)


def test_confidence_comes_from_the_top_severity_findings_only() -> None:
    # a pending secret (info, low) must not make a certain critical finding look doubtful
    found = (_finding(Severity.CRITICAL, Confidence.HIGH), _finding(Severity.INFO, Confidence.LOW))
    result = score(found, Action.UPDATE, BlastRadius((), ()), is_production=False)
    assert result is not None
    assert (result.value, result.confidence) == (60, Confidence.HIGH)


def test_dependent_points_stop_at_fifteen() -> None:
    blast = BlastRadius(tuple(f"aws_x.d{index}" for index in range(9)), ())
    found = (_finding(Severity.LOW, Confidence.HIGH),)
    result = score(found, Action.UPDATE, blast, is_production=False)
    assert result is not None
    assert result.factors == ("+10 low finding (rule)", "+15 9 dependent resource(s)")
