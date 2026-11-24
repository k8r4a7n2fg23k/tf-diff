"""Real terraform and tofu on examples/production-simulation (terraform_data only: no network).

UPDATE_GOLDEN=1 also records the plan as tests/golden/{terraform,opentofu}-<major.minor>/plan.json.
"""

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from factories import GOLDEN, ROOT
from tfdiff.analysis.engine import analyze
from tfdiff.model.settings import Settings
from tfdiff.terraform.parser import parse

EXAMPLE = ROOT.parent / "examples" / "production-simulation"
# binary -> golden directory prefix; both read the same plan JSON (format 1.2)
BINARIES = {"terraform": "terraform", "tofu": "opentofu"}

pytestmark = pytest.mark.terraform


def _run(binary: str, workdir: Path, *args: str) -> str:
    done = subprocess.run(  # noqa: S603  - fixed binary, fixed arguments
        [binary, *args],
        cwd=workdir,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
        env={**os.environ, "TF_IN_AUTOMATION": "1", "CHECKPOINT_DISABLE": "1"},
    )
    assert done.returncode == 0, done.stderr
    return done.stdout


@pytest.fixture(scope="module", params=sorted(BINARIES))
def recorded(request: pytest.FixtureRequest, tmp_path_factory: pytest.TempPathFactory) -> str:
    name: str = request.param
    binary = shutil.which(name)
    if binary is None:
        pytest.skip(f"{name} is not installed")
    workdir = tmp_path_factory.mktemp(name)
    shutil.copytree(EXAMPLE, workdir, dirs_exist_ok=True)
    _run(binary, workdir, "init", "-input=false")
    _run(binary, workdir, "apply", "-input=false", "-auto-approve", "-var-file=baseline.tfvars")
    _run(binary, workdir, "plan", "-input=false", "-var-file=dangerous.tfvars", "-out=tfplan")
    text = _run(binary, workdir, "show", "-json", "tfplan")
    if os.environ.get("UPDATE_GOLDEN"):
        # tofu names its version `terraform_version` too
        version = json.loads(_run(binary, workdir, "version", "-json"))["terraform_version"]
        target = GOLDEN / f"{BINARIES[name]}-{'.'.join(version.split('.')[:2])}" / "plan.json"
        target.parent.mkdir(exist_ok=True)
        target.write_text(json.dumps(json.loads(text), indent=2) + "\n", encoding="utf-8")
    return text


def test_dangerous_change_is_flagged(recorded: str) -> None:
    report = analyze(parse(recorded), Settings(environment="production"))
    found = {(finding.rule, finding.address) for finding in report.findings}
    # no remove-redundancy: the replaced database keeps 2 known subnets in `input`; its computed
    # `output` mirror goes unknown on replace and is no evidence
    assert found == {
        ("destroy-production-resource", "module.app.terraform_data.worker[1]"),
        ("destroy-production-resource", "module.app.terraform_data.worker[2]"),
        ("destroy-production-resource", 'module.network.terraform_data.subnet["zone-c"]'),
        ("destroy-production-resource", "terraform_data.cache[0]"),
        ("replace-resource", "module.database.terraform_data.primary"),
        ("sensitive-value-changed", "module.database.terraform_data.primary"),
        ("wide-blast-radius", "module.database.terraform_data.primary"),
        ("wide-blast-radius", 'module.network.terraform_data.subnet["zone-c"]'),
    }
    assert "CANARY" not in repr(report)
