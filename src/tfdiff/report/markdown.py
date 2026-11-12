"""Markdown for PR comments. The first line is a stable marker so CI can update one comment."""

import html
from collections import Counter

from tfdiff.model.report import Report, action_counts, severity_counts

MARKER = "<!-- tf-diff:report -->"


def _text(raw: str) -> str:
    # evidence holds plan values: no markup, links, images or @mentions from them in a bot comment
    return (
        raw.replace("&", "&amp;")
        .replace("\\", "\\\\")
        .replace("|", "\\|")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace("*", "\\*")
        .replace("_", "\\_")
        .replace("`", "\\`")
        .replace("[", "\\[")
        .replace("]", "\\]")
        .replace("!", "\\!")
        .replace("@", "&#64;")
    )


def _code(raw: str) -> str:
    # GitHub splits table rows on | even inside a code span
    return "`" + raw.replace("`", "'").replace("|", r"\|") + "`"


def render(report: Report) -> str:
    lines = [MARKER, "## Terraform Risk Summary", ""]
    lines.append(
        f"**Environment:** {_text(report.environment or 'not set')} · "
        f"**Resources:** {report.inspected} inspected, {len(report.assessments)} changed, "
        f"{len(report.ignored)} ignored"
        + (f", {len(report.suppressed)} findings suppressed" if report.suppressed else "")
    )
    actions = ", ".join(f"{count} {action}" for action, count in action_counts(report).items())
    lines += [f"**Changes:** {actions or 'none'}", ""]
    for warning in report.warnings:
        # blank line ends the quote, or the table below joins it
        lines += [f"> warning: {_text(warning)}", ""]
    lines += ["| Severity | Findings |", "|---|---|"]
    lines += [f"| {level} | {count} |" for level, count in severity_counts(report).items()]
    lines.append("")
    if report.findings:
        lines += [
            "### Findings",
            "",
            "| Severity | Resource | Finding | Confidence |",
            "|---|---|---|---|",
        ]
        # one row per distinct line: min_size and desired_capacity both dropping read the same
        # here, and the details below tell them apart
        rows = Counter(
            (found.severity, found.address, found.title, found.rule, found.confidence)
            for found in report.findings
        )
        lines += [
            f"| **{severity.upper()}** | {_code(address)} | {_text(title)} ({_code(rule)})"
            + (f" x{count}" if count > 1 else "")
            + f" | {confidence} |"
            for (severity, address, title, rule, confidence), count in rows.items()
        ]
        lines.append("")
    for assessment in report.assessments:
        if not assessment.findings:
            continue
        lines += [
            # markdown is off inside an HTML block: a code span would show its backticks
            f"<details><summary><code>{html.escape(assessment.change.label)}</code>: "
            f"{assessment.change.action}"
            + (f", score {assessment.score.value}/100" if assessment.score else "")
            + "</summary>",
            "",
        ]
        lines += [f"- why: {_text(line)}" for line in assessment.why]
        if assessment.score:
            lines.append(f"- score factors: {_text('; '.join(assessment.score.factors))}")
        for found in assessment.findings:
            lines += ["", f"**{_text(found.title)}** ({_code(found.rule)}): {_text(found.reason)}"]
            lines += [
                f"- {_text(evidence.label)}: {_text(evidence.text)}" for evidence in found.evidence
            ]
        lines += ["", "</details>", ""]
    if report.suppressed:
        lines += [
            f"<details><summary>Suppressed findings ({len(report.suppressed)})</summary>",
            "",
            "| Severity | Resource | Finding | Reason | Until |",
            "|---|---|---|---|---|",
        ]
        lines += [
            f"| {muted.finding.severity} | {_code(muted.finding.address)} | "
            f"{_text(muted.finding.title)} ({_code(muted.finding.rule)}) | "
            f"{_text(muted.reason)} | {muted.until or '-'} |"
            for muted in report.suppressed
        ]
        lines += ["", "</details>", ""]
    quiet = [assessment for assessment in report.assessments if not assessment.findings]
    if quiet:
        lines += ["### Other changes", ""]
        lines += [
            f"- {assessment.change.action}: {_code(assessment.change.label)}"
            for assessment in quiet
        ]
        lines.append("")
    if not report.assessments:
        lines += ["No changes.", ""]
    return "\n".join(lines)
