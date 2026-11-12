"""`.tf-diff.yaml`, environment variables and flags -> model.Settings, in one place.

Precedence: defaults < file < environment < flags.
"""

from collections.abc import Mapping
from datetime import date

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, ValidationInfo, field_validator

from tfdiff.model.errors import SHOWN_ERRORS, ConfigError
from tfdiff.model.findings import Confidence, Severity
from tfdiff.model.settings import ENVIRONMENT_TAGS, PRODUCTION_NAMES, Settings, Suppression
from tfdiff.rules.registry import BY_ID

FILENAME = ".tf-diff.yaml"
ENV_ENVIRONMENT = "TF_DIFF_ENVIRONMENT"


class RuleConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    enabled: bool = True
    severity: Severity | None = None
    threshold: int | None = Field(default=None, ge=0)


class SuppressConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    rule: str
    resource: str
    reason: str
    until: date | None = None

    @field_validator("until", mode="before")
    @classmethod
    def _no_timestamp(cls, value: object) -> object:
        # pydantic reads a number as unix time: `until: 0` would be 1970-01-01
        if isinstance(value, int | float):
            raise ValueError("a date like 2027-03-01, not a number")  # noqa: TRY004  - pydantic wants ValueError
        return value


class FileConfig(BaseModel):
    # our own format, unlike plan JSON: an unknown key is a typo, fail on it
    model_config = ConfigDict(extra="forbid", frozen=True)

    environment: str | None = None
    # None: left out, the default holds; a list replaces the default
    environment_tags: list[str] | None = None
    production_names: list[str] | None = None
    fail_on: Severity | None = None
    fail_on_confidence: Confidence | None = None
    rules: dict[str, RuleConfig] = {}
    ignore: list[str] = []
    suppress: list[SuppressConfig] = []

    @field_validator(
        "rules", "ignore", "suppress", "environment_tags", "production_names", mode="before"
    )
    @classmethod
    def _empty_section(cls, value: object, info: ValidationInfo) -> object:
        # `rules:` with every entry commented out is null in YAML; an empty list of tags or
        # production names is an error, and null must not slip past it as "left out"
        empty: dict[str, object] | list[str] = {} if info.field_name == "rules" else []
        return empty if value is None else value


def load(  # noqa: PLR0913  - one keyword per flag that overrides the file
    text: str | None,
    env: Mapping[str, str],
    *,
    environment: str | None = None,
    fail_on: Severity | None = None,
    fail_on_confidence: Confidence | None = None,
    today: date | None = None,
    source: str = FILENAME,
) -> Settings:
    """Resolve settings; `text` is the config file content, None when there is no file."""
    config = _parse(text, source)
    for rule_id, rule in config.rules.items():
        if rule_id not in BY_ID:
            raise ConfigError(f"{source}: rules.{rule_id}: unknown rule, see `tf-diff rules`")
        if rule.threshold is not None and BY_ID[rule_id].threshold is None:
            raise ConfigError(f"{source}: rules.{rule_id}.threshold: this rule has no threshold")
    tags = _names(source, "environment_tags", config.environment_tags)
    production = _names(source, "production_names", config.production_names)
    if environment is None:
        # blank means unset: `${{ vars.X }}` of a variable nobody defined is empty
        environment = (env.get(ENV_ENVIRONMENT) or "").strip() or config.environment
    return Settings(
        # a blank flag still wins: `--environment ""` leaves it to the resource tags
        environment=environment.strip() or None if environment else None,
        environment_tags=ENVIRONMENT_TAGS if tags is None else tags,
        production_names=(
            PRODUCTION_NAMES if production is None else frozenset(n.casefold() for n in production)
        ),
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
        suppress=_suppressions(source, config.suppress),
        today=today,
    )


def _suppressions(source: str, entries: list[SuppressConfig]) -> tuple[Suppression, ...]:
    seen: set[tuple[str, str]] = set()
    for index, entry in enumerate(entries):
        where = f"{source}: suppress.{index}"
        if entry.rule not in BY_ID:
            raise ConfigError(f"{where}.rule: unknown rule, see `tf-diff rules`")
        for key, text in (("resource", entry.resource), ("reason", entry.reason)):
            if not text.strip():
                raise ConfigError(f"{where}.{key}: blank; say which resource and why")
        if (entry.rule, entry.resource.strip()) in seen:
            raise ConfigError(f"{where}: repeats an earlier entry for this rule and resource")
        seen.add((entry.rule, entry.resource.strip()))
    return tuple(
        # one line: the reason goes into a Markdown table row and a terminal line
        Suppression(entry.rule, entry.resource.strip(), " ".join(entry.reason.split()), entry.until)
        for entry in entries
    )


def _names(source: str, key: str, names: list[str] | None) -> tuple[str, ...] | None:
    """Check a list that replaces a default; None when the file leaves it out."""
    if names is None:
        return None
    if not names:
        raise ConfigError(f"{source}: {key}: empty; list at least one name or leave the key out")
    stripped = tuple(name.strip() for name in names)
    folded = [name.casefold() for name in stripped]
    for index, name in enumerate(stripped):
        if not name:
            raise ConfigError(f"{source}: {key}.{index}: blank name")
        if folded[index] in folded[:index]:
            raise ConfigError(
                f"{source}: {key}.{index}: {name} repeats an earlier entry (case does not matter)"
            )
    return stripped


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
