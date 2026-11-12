import re
from dataclasses import replace

from tfdiff.analysis.diff import diff
from tfdiff.analysis.explain import why
from tfdiff.analysis.score import score
from tfdiff.model.errors import InputError
from tfdiff.model.findings import Finding, order
from tfdiff.model.graph import blast_radius
from tfdiff.model.plan import QUIET, Change, Plan
from tfdiff.model.report import Assessment, Report, Suppressed
from tfdiff.model.settings import Settings, Suppression
from tfdiff.model.text import shortlist
from tfdiff.model.values import Attributes, Known
from tfdiff.rules.registry import RULES, RULES_VERSION
from tfdiff.rules.rule import Context, is_production

# addresses a warning names before it says how many more
EXAMPLES = 3


def analyze(plan: Plan, settings: Settings) -> Report:
    rules = [rule for rule in RULES if rule.id not in settings.disabled]
    fallback, notes = plan_environment(plan, settings)
    patterns = [_glob(pattern) for pattern in settings.ignore]
    muting = [(entry, _glob(entry.resource)) for entry in settings.suppress]
    assessments: list[Assessment] = []
    ignored: list[str] = []
    suppressed: list[Suppressed] = []
    expired: set[Suppression] = set()
    for change in plan.changes:
        if change.action in QUIET:
            continue
        if any(pattern.fullmatch(change.address) for pattern in patterns):
            ignored.append(change.address)
            continue
        attributes = diff(change)
        context = Context(
            change=change,
            attributes=attributes,
            environment=environment(change, settings, fallback),
            blast=blast_radius(plan.graph, change.address),
            settings=settings,
        )
        raised = sorted(
            (_override(found, settings) for rule in rules for found in rule.evaluate(context)),
            key=order,
        )
        kept: list[Finding] = []
        for found in raised:
            entries = _matching(found, muting)
            # the first entry still in force wins; expired ones only speak when none is
            live = next((entry for entry in entries if not _has_expired(entry, settings)), None)
            if live is None:
                expired.update(entries)
                kept.append(found)
            else:
                suppressed.append(Suppressed(found, live.reason, live.until))
        findings = tuple(kept)
        assessments.append(
            Assessment(
                change=change,
                environment=context.environment,
                why=why(change, attributes),
                attributes=attributes,
                dependencies=tuple(sorted(plan.graph.dependencies[change.address])),
                blast=context.blast,
                findings=findings,
                score=score(
                    findings, change.action, context.blast, is_production=context.is_production
                ),
            )
        )
    return Report(
        format_version=plan.format_version,
        terraform_version=plan.terraform_version,
        environment=fallback,
        rules_version=RULES_VERSION,
        inspected=len(plan.changes),
        assessments=tuple(assessments),
        findings=tuple(
            sorted(
                (found for assessment in assessments for found in assessment.findings), key=order
            )
        ),
        ignored=tuple(sorted(ignored)),
        suppressed=tuple(sorted(suppressed, key=lambda muted: order(muted.finding))),
        warnings=(*plan.warnings, *notes, *_expiry(expired)),
    )


def lookup(report: Report, plan: Plan, address: str) -> Assessment | None:
    """Assessment of `address`; None for a no-op or a data source read.

    `address` may also be a label as the report prints it, `X (deposed KEY)`.
    """
    for assessment in report.assessments:
        if address in {assessment.change.address, assessment.change.label}:
            return assessment
    if address in report.ignored:
        raise InputError(f"{address}: skipped by the ignore list in the config")
    if any(address in {change.address, change.label} for change in plan.changes):
        return None
    raise InputError(f"{address}: not in the plan")


def environment(change: Change, settings: Settings, fallback: str | None = None) -> str | None:
    """Pick the environment: settings, then the resource's own tag, then `fallback`."""
    return settings.environment or tagged(change, settings) or fallback


def plan_environment(plan: Plan, settings: Settings) -> tuple[str | None, tuple[str, ...]]:
    """Return the environment of the whole plan, and warnings about the tags it comes from.

    One plan is one stack, and a stack is one environment; so when every tagged resource agrees,
    the untagged ones (ASG, security group rules, public access blocks: no `tags_all`, no
    provider `default_tags`) are in it too. Data sources only look things up, often in shared
    infrastructure, so their tags say nothing about this stack.
    """
    managed = [change for change in plan.changes if change.resource.mode != "data"]
    notes = _conflicts(managed, settings)
    if settings.environment:
        return settings.environment, notes
    found: dict[str, str] = {}
    for change in managed:
        if tag := tagged(change, settings):
            found.setdefault(_kind(tag, settings), tag)
    if len(found) == 1:
        return next(iter(found.values())), notes
    if all(change.action in QUIET for change in plan.changes):
        return None, notes
    if found:
        names = ", ".join(sorted(found.values()))
        return None, (
            *notes,
            f"resources are tagged for different environments ({names}): untagged ones get "
            "none, set --environment",
        )
    return None, (
        *notes,
        "no environment: nothing sets it and no resource has an environment tag "
        f"({', '.join(settings.environment_tags)}), so production-only checks are off; "
        "set --environment",
    )


def tagged(change: Change, settings: Settings) -> str | None:
    """Return the environment a resource is tagged with: the strictest, when it has several.

    Before and after both count: a replace destroys the object the old tag describes and an
    update changes it while it is still there, so production on either side is production.
    """
    keys = _keys(settings)
    names = [*_side(change.after, keys), *_side(change.before, keys)]
    production = [name for name in names if _kind(name, settings) == "production"]
    return next(iter(production or names), None)


def _kind(name: str, settings: Settings) -> str:
    return "production" if is_production(name, settings) else name.casefold()


def _keys(settings: Settings) -> tuple[str, ...]:
    return tuple(key.casefold() for key in settings.environment_tags)


def _side(attributes: Attributes, keys: tuple[str, ...]) -> list[str]:
    """Environment tag values on one side, in the order of `keys` (casefolded).

    `tags_all` is `tags` with the provider's `default_tags` under it, so it already holds the
    value that wins; `tags` counts only for resources without `tags_all`.
    """
    found: dict[str, dict[str, str]] = {"tags": {}, "tags_all": {}}
    for path, value in attributes:
        match path, value:
            case (("tags" | "tags_all") as block, str(key)), Known(value=str(name)):
                if key.casefold() in keys and name.strip():
                    found[block].setdefault(key.casefold(), name.strip())
    tags = found["tags_all"] or found["tags"]
    return [tags[key] for key in keys if key in tags]


def _conflicts(changes: list[Change], settings: Settings) -> tuple[str, ...]:
    keys = _keys(settings)
    clashing = [
        change.address
        for change in changes
        if any(
            len({_kind(name, settings) for name in _side(side, keys)}) > 1
            for side in (change.before, change.after)
        )
    ]
    if not clashing:
        return ()
    return (
        f"environment tags ({', '.join(settings.environment_tags)}) disagree on "
        f"{len(clashing)} resource(s) ({shortlist(clashing, EXAMPLES)}): production counts if "
        "any says so, else the first listed tag the resource has",
    )


def _glob(pattern: str) -> re.Pattern[str]:
    """Compile `*` / `?` as wildcards; brackets stay literal, addresses are full of them."""
    return re.compile(re.escape(pattern).replace(r"\*", ".*").replace(r"\?", "."))


def _matching(
    found: Finding, muting: list[tuple[Suppression, re.Pattern[str]]]
) -> list[Suppression]:
    """Entries that cover the finding, in config order."""
    return [
        entry
        for entry, pattern in muting
        if entry.rule == found.rule and pattern.fullmatch(found.address)
    ]


def _has_expired(entry: Suppression, settings: Settings) -> bool:
    return entry.until is not None and settings.today is not None and settings.today > entry.until


def _expiry(expired: set[Suppression]) -> list[str]:
    return [
        f"suppression of {entry.rule} on {entry.resource} expired on {entry.until}: "
        "its findings count again"
        for entry in sorted(expired, key=lambda entry: (entry.rule, entry.resource))
    ]


def _override(found: Finding, settings: Settings) -> Finding:
    severity = settings.severities.get(found.rule)
    return found if severity is None else replace(found, severity=severity)
