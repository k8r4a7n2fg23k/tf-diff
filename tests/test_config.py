from datetime import date

import pytest

from tfdiff.config import ENV_ENVIRONMENT, load
from tfdiff.model.errors import ConfigError
from tfdiff.model.findings import Confidence, Severity
from tfdiff.model.settings import Suppression

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
SUPPRESS = """suppress:
  - rule: replace-resource
    resource: module.cache.main
    reason: rebuilt nightly
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
        ("environment_tags: []\n", "environment_tags: empty"),
        ("environment_tags:\n", "environment_tags: empty"),
        ("production_names: []\n", "production_names: empty"),
        ("environment_tags: [Stage, ' ']\n", "environment_tags.1: blank"),
        ("environment_tags: [env, ENV]\n", "environment_tags.1: ENV repeats an earlier entry"),
        (
            "production_names: [prod, live, Live]\n",
            "production_names.2: Live repeats an earlier entry",
        ),
        ("environment_tags: Stage\n", "environment_tags: Input should be a valid list"),
        (SUPPRESS.replace("replace-resource", "replace-all"), r"suppress.0.rule: unknown rule"),
        (
            SUPPRESS.replace("    reason: rebuilt nightly\n", ""),
            r"suppress.0.reason: Field required",
        ),
        (SUPPRESS.replace("rebuilt nightly", "' '"), r"suppress.0.reason: blank"),
        (SUPPRESS.replace("module.cache.main", "''"), r"suppress.0.resource: blank"),
        (SUPPRESS + SUPPRESS.removeprefix("suppress:\n"), "suppress.1: repeats an earlier entry"),
        (SUPPRESS + "    until: soon\n", "suppress.0.until: Input should be a valid date"),
        (SUPPRESS + "    until: 0\n", "suppress.0.until: Value error, a date like 2027-03-01"),
        (SUPPRESS + "    scope: all\n", "suppress.0.scope: Extra inputs"),
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
        "no-tags",
        "null-tags",
        "no-production-names",
        "blank-tag",
        "duplicate-tag",
        "duplicate-name",
        "tags-not-a-list",
        "suppress-unknown-rule",
        "suppress-no-reason",
        "suppress-blank-reason",
        "suppress-blank-resource",
        "suppress-duplicate",
        "suppress-not-a-date",
        "suppress-unix-time",
        "suppress-typo",
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


def test_environment_lists_replace_the_defaults() -> None:
    defaults = load(None, {})
    assert defaults.environment_tags == ("Environment", "env")
    assert defaults.production_names == {"production", "prod", "prd"}
    settings = load("environment_tags: [' Stage ', env_name]\nproduction_names: [PRD, Live]\n", {})
    assert settings.environment_tags == ("Stage", "env_name")
    assert settings.production_names == {"prd", "live"}


@pytest.mark.parametrize("until", ["2027-03-01", "'2027-03-01'"], ids=["yaml-date", "quoted"])
def test_suppressions_reach_the_model(until: str) -> None:
    text = (
        SUPPRESS.replace("module.cache.main", " module.cache.* ").replace(
            "reason: rebuilt nightly", "reason: |\n      rebuilt\n      nightly"
        )
        + f"    until: {until}\n"
    )
    settings = load(text, {}, today=date(2027, 1, 1))
    assert settings.suppress == (
        Suppression("replace-resource", "module.cache.*", "rebuilt nightly", date(2027, 3, 1)),
    )
    assert settings.today == date(2027, 1, 1)
    assert load("suppress:\n", {}).suppress == ()
