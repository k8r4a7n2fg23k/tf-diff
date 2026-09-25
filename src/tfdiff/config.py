"""`.tf-diff.yaml`, environment variables and flags -> model.Settings, in one place.

Precedence: defaults < file < environment < flags.
"""

from collections.abc import Mapping

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, ValidationInfo, field_validator

from tfdiff.model.errors import SHOWN_ERRORS, ConfigError
from tfdiff.model.findings import Confidence, Severity
from tfdiff.model.settings import Settings
from tfdiff.rules.registry import BY_ID

FILENAME = ".tf-diff.yaml"
ENV_ENVIRONMENT = "TF_DIFF_ENVIRONMENT"


class RuleConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    enabled: bool = True
    severity: Severity | None = None
    threshold: int | None = Field(default=None, ge=0)


class FileConfig(BaseModel):
    # our own format, unlike plan JSON: an unknown key is a typo, fail on it
    model_config = ConfigDict(extra="forbid", frozen=True)

    environment: str | None = None
    fail_on: Severity | None = None
    fail_on_confidence: Confidence | None = None
    rules: dict[str, RuleConfig] = {}
    ignore: list[str] = []

    @field_validator("rules", "ignore", mode="before")
    @classmethod
    def _empty_section(cls, value: object, info: ValidationInfo) -> object:
        # `rules:` with every entry commented out is null in YAML
        empty: dict[str, object] | list[str] = {} if info.field_name == "rules" else []
        return empty if value is None else value


def load(  # noqa: PLR0913  - one keyword per flag that overrides the file
    text: str | None,
    env: Mapping[str, str],
    *,
    environment: str | None = None,
    fail_on: Severity | None = None,
    fail_on_confidence: Confidence | None = None,
    source: str = FILENAME,
) -> Settings:
    """Resolve settings; `text` is the config file content, None when there is no file."""
    config = _parse(text, source)
    for rule_id, rule in config.rules.items():
        if rule_id not in BY_ID:
            raise ConfigError(f"{source}: rules.{rule_id}: unknown rule, see `tf-diff rules`")
        if rule.threshold is not None and BY_ID[rule_id].threshold is None:
            raise ConfigError(f"{source}: rules.{rule_id}.threshold: this rule has no threshold")
    if environment is None:
        # blank means unset: `${{ vars.X }}` of a variable nobody defined is empty
        environment = (env.get(ENV_ENVIRONMENT) or "").strip() or config.environment
    return Settings(
        # a blank flag still wins: `--environment ""` leaves it to the resource tags
        environment=environment.strip() or None if environment else None,
        fail_on=fail_on or config.fail_on or Severity.HIGH,
        fail_on_confidence=fail_on_confidence or config.fail_on_confidence or Confidence.HIGH,
        disabled=frozenset(rule_id for rule_id, rule in config.rules.items() if not rule.enabled),
        severities={
            rule_id: rule.severity
            for rule_id, rule in sorted(config.rules.items())
            if rule.severity is not None
        },
        thresholds={
            rule_id: rule.threshold
            for rule_id, rule in sorted(config.rules.items())
            if rule.threshold is not None
        },
        ignore=tuple(config.ignore),
    )


def _parse(text: str | None, source: str) -> FileConfig:
    if text is None:
        return FileConfig()
    try:
        document = yaml.safe_load(text)
    except yaml.YAMLError as error:
        mark = getattr(error, "problem_mark", None)
        where = f" at line {mark.line + 1}" if mark is not None else ""
        raise ConfigError(f"{source}: not valid YAML{where}") from None
    if document is None:
        return FileConfig()
    if not isinstance(document, dict):
        raise ConfigError(f"{source}: top level must be a mapping")
    try:
        return FileConfig.model_validate(document)
    except ValidationError as error:
        problems = dict.fromkeys(
            f"{'.'.join(str(part) for part in issue['loc'])}: {issue['msg']}"
            for issue in error.errors(include_input=False, include_url=False)
        )
        raise ConfigError(f"{source}: " + "; ".join(list(problems)[:SHOWN_ERRORS])) from None
