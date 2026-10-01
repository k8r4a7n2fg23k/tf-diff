"""scripts/bench.py: generated plans stay valid input, so the benchmark measures real work."""

import importlib.util
from pathlib import Path

import pytest

from factories import ROOT
from tfdiff.analysis.engine import analyze
from tfdiff.model.settings import Settings
from tfdiff.terraform.parser import parse

_SPEC = importlib.util.spec_from_file_location("bench", ROOT.parent / "scripts" / "bench.py")
assert _SPEC is not None
assert _SPEC.loader is not None
bench = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(bench)


@pytest.mark.parametrize(
    ("shape", "resources", "changed", "edges", "rules"),
    [
        # one module instance per 10 resources, plus the shared VPC and one root resource
        (
            "mixed",
            100,
            21,
            101,
            {
                "reduce-capacity",
                "security-group-wide-open",
                "stateful-data-loss",
                "destroy-production-resource",
                "replace-resource",
            },
        ),
        ("chain", 30, 30, 29, set()),
        ("fanout", 30, 30, 29, set()),
        ("findings", 30, 30, 0, {"security-group-wide-open"}),
        ("wide", 1, 1, 0, set()),
    ],
)
def test_generated_plans_are_valid_and_risky(  # noqa: PLR0913, PLR0917  - one parameter per column
    tmp_path: Path, shape: str, resources: int, changed: int, edges: int, rules: set[str]
) -> None:
    out = tmp_path / "plan.json"
    bench.generate(shape, resources, out)
    plan = parse(out.read_text(encoding="utf-8"))
    report = analyze(plan, Settings())
    assert (len(report.assessments), sum(map(len, plan.graph.dependents.values()))) == (
        changed,
        edges,
    )
    assert {found.rule for found in report.findings} == rules


def test_chain_puts_every_resource_in_the_blast_radius_of_the_first(tmp_path: Path) -> None:
    out = tmp_path / "plan.json"
    bench.generate("chain", 5, out)
    report = analyze(parse(out.read_text(encoding="utf-8")), Settings())
    first = report.assessments[0]
    assert (len(first.blast.direct), len(first.blast.indirect)) == (1, 3)


def test_measure_times_every_stage(tmp_path: Path) -> None:
    out = tmp_path / "plan.json"
    bench.generate("mixed", 20, out)
    result = bench.measure(out, "mixed")
    assert set(result.stages) == {"read", *bench.STAGES}
    assert (result.resources, result.output_chars["json"] > 0) == (22, True)
    assert result.peak_mb > 0
