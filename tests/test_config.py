import pytest

from tfdiff.config import ENV_ENVIRONMENT, load
from tfdiff.model.errors import ConfigError
from tfdiff.model.findings import Confidence, Severity

FILE = """
environment: staging
fail_on: medium
fail_on_confidence: low
rules:
  reduce-capacity:
    threshold: 50
  public-database:
    severity: high
  sensitive-value-changed:
    enabled: false
ignore:
  - module.test.*
"""


@pytest.mark.parametrize(
    ("text", "env", "flag", "expected"),
    [
        (None, {}, None, None),
        (FILE, {}, None, "staging"),
        (FILE, {ENV_ENVIRONMENT: "qa"}, None, "qa"),
        (FILE, {ENV_ENVIRONMENT: "qa"}, "production", "production"),
        (FILE, {ENV_ENVIRONMENT: "qa"}, "", None),
        (FILE, {ENV_ENVIRONMENT: ""}, None, "staging"),
        (FILE, {ENV_ENVIRONMENT: "qa"}, "  ", None),
        (FILE, {ENV_ENVIRONMENT: " "}, None, "staging"),
        (None, {ENV_ENVIRONMENT: " prod "}, None, "prod"),
    ],
    ids=[
        "defaults",
        "file",
        "env-over-file",
        "flag-over-env",
        "empty-flag",
        "empty-env",
        "blank-flag",
        "blank-env",
        "padded-env",
    ],
)
def test_environment_precedence(
    text: str | None, env: dict[str, str], flag: str | None, expected: str | None
) -> None:
    assert load(text, env, environment=flag).environment == expected


def test_file_settings_reach_the_model() -> None:
    settings = load(FILE, {})
    assert settings.fail_on is Severity.MEDIUM
    assert settings.fail_on_confidence is Confidence.LOW
    assert settings.thresholds == {"reduce-capacity": 50}
    assert settings.severities == {"public-database": Severity.HIGH}
    assert settings.disabled == {"sensitive-value-changed"}
    assert settings.ignore == ("module.test.*",)
    assert load(FILE, {}, fail_on=Severity.CRITICAL).fail_on is Severity.CRITICAL


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ("rules:\n  no-such-rule: {}\n", "unknown rule"),
        ("rules:\n  public-database:\n    threshold: 3\n", "has no threshold"),
        ("rules:\n  reduce-capacity:\n    threshold: -1\n", "greater than or equal to 0"),
        ("fail_on: catastrophic\n", "fail_on"),
        ("fail_on_confidence: medium\n", "fail_on_confidence"),
        ("enviroment: production\n", "enviroment: Extra inputs"),
        ("- a\n- b\n", "top level must be a mapping"),
        ("a: [unclosed\n", "not valid YAML at line"),
        ("x: !!python/object/apply:os.system ['echo CANARY']\n", "not valid YAML"),
    ],
    ids=[
        "rule",
        "threshold",
        "negative",
        "severity",
        "confidence",
        "typo",
        "list",
        "syntax",
        "python-tag",
    ],
)
def test_bad_config_is_config_error(text: str, message: str) -> None:
    with pytest.raises(ConfigError, match=message) as caught:
        load(text, {})
    assert "CANARY" not in str(caught.value)


def test_sections_with_every_entry_commented_out_are_empty() -> None:
    text = "rules:\n  # reduce-capacity: {}\nignore:\n  # - module.test.*\n"
    settings = load(text, {})
    assert (settings.disabled, settings.ignore) == (frozenset(), ())
