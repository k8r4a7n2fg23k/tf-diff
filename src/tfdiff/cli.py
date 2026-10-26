"""Entry point. The only module that touches the filesystem, environment and exit codes."""

import codecs
import errno
import io
import os
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from enum import IntEnum
from pathlib import Path
from typing import Annotated
from urllib.parse import quote

import typer
from rich.console import Console
from typing_extensions import override

from tfdiff import __version__, config
from tfdiff.analysis.engine import analyze as run_analysis
from tfdiff.analysis.engine import lookup
from tfdiff.model import graph as graphs
from tfdiff.model.enums import StrEnum
from tfdiff.model.errors import ConfigError, InputError, TfDiffError
from tfdiff.model.findings import Confidence, Severity
from tfdiff.model.plan import Plan
from tfdiff.model.report import Report
from tfdiff.model.settings import Settings
from tfdiff.report import document, markdown, sarif, terminal
from tfdiff.rules.registry import RULES, RULES_VERSION
from tfdiff.terraform.parser import MAX_SIZE, parse


class Exit(IntEnum):
    """Exit codes are a contract with CI scripts: never renumber."""

    SUCCESS = 0
    POLICY_VIOLATION = 1
    INVALID_INPUT = 2
    CONFIGURATION_ERROR = 3
    INTERNAL_ERROR = 4


class Format(StrEnum):
    TERMINAL = "terminal"
    JSON = "json"
    MARKDOWN = "markdown"
    SARIF = "sarif"


class GraphFormat(StrEnum):
    TERMINAL = "terminal"
    JSON = "json"


# pretty exceptions print locals, and locals hold plan values: off
app = typer.Typer(
    no_args_is_help=True,
    add_completion=False,
    pretty_exceptions_enable=False,
    help="Explain Terraform plans and flag risky infrastructure changes.",
)

PlanArg = Annotated[
    Path, typer.Argument(help="Output of `terraform show -json <planfile>`.", show_default=False)
]
ConfigOpt = Annotated[
    Path | None, typer.Option("--config", "-c", help=f"Config file (default: ./{config.FILENAME}).")
]
EnvironmentOpt = Annotated[
    str | None,
    typer.Option(
        help=f"Environment name, overrides config and ${config.ENV_ENVIRONMENT}; "
        '"" leaves it to resource tags.'
    ),
]
FormatOpt = Annotated[Format, typer.Option("--format", "-f", help="Report format.")]


class _Stdout(Console):
    @override
    def on_broken_pipe(self) -> None:
        # rich exits 1 here, which `check` callers read as a policy violation: let the guard decide
        raise BrokenPipeError(errno.EPIPE, "stdout closed")


def _stdout() -> Console:
    return _Stdout(highlight=False, soft_wrap=True)


def _stderr() -> Console:
    # soft_wrap: a CI log grep for a path or for "check failed" needs it on one line
    return Console(stderr=True, highlight=False, soft_wrap=True)


@contextmanager
def _exit_codes() -> Iterator[None]:
    try:
        yield
    except ConfigError as error:
        _fail(error, Exit.CONFIGURATION_ERROR)
    except InputError as error:
        _fail(error, Exit.INVALID_INPUT)


def _fail(error: TfDiffError, code: Exit) -> None:
    _stderr().print(f"error: {error}", markup=False)
    raise typer.Exit(code)


def _decode(raw: bytes) -> str:
    # Windows PowerShell 5.1 writes `>` redirects as UTF-16 and Out-File as UTF-8 with a BOM
    if raw.startswith((codecs.BOM_UTF16_LE, codecs.BOM_UTF16_BE)):
        return raw.decode("utf-16")
    return raw.decode("utf-8-sig")


def _read_plan(path: Path) -> Plan:
    try:
        if path.is_dir():
            raise InputError(f"{path}: is a directory, expected the plan JSON file")
        if path.stat().st_size > MAX_SIZE:
            raise InputError(f"{path}: larger than {MAX_SIZE} bytes")
        text = _decode(path.read_bytes())
    except FileNotFoundError:
        raise InputError(f"{path}: no such file") from None
    except UnicodeDecodeError:
        raise InputError(f"{path}: not UTF-8 or UTF-16 text") from None
    except OSError as error:
        raise InputError(f"{path}: cannot read ({error.strerror})") from None
    try:
        return parse(text)
    except InputError as error:
        raise type(error)(f"{path}: {error}") from None


def _settings(
    path: Path | None,
    environment: str | None,
    fail_on: Severity | None = None,
    fail_on_confidence: Confidence | None = None,
) -> Settings:
    candidate = path or Path(config.FILENAME)
    text: str | None = None
    if path is not None or candidate.is_file():
        try:
            text = _decode(candidate.read_bytes())
        except OSError as error:
            raise ConfigError(f"{candidate}: cannot read ({error.strerror})") from None
        except UnicodeDecodeError:
            raise ConfigError(f"{candidate}: not UTF-8 or UTF-16 text") from None
    return config.load(
        text,
        os.environ,
        environment=environment,
        fail_on=fail_on,
        fail_on_confidence=fail_on_confidence,
        source=str(candidate),
    )


@contextmanager
def _pipe_guard() -> Iterator[None]:
    """Let `| head` close the pipe early: not an error, and the verdict still sets the exit code."""
    try:
        yield
        sys.stdout.flush()
    except OSError as error:
        # windows reports a write to a closed pipe as EINVAL, posix as EPIPE
        if error.errno not in {errno.EPIPE, errno.EINVAL}:
            raise
        # the interpreter flushes stdout again at exit; point it at devnull so that flush is quiet
        os.dup2(os.open(os.devnull, os.O_WRONLY), sys.stdout.fileno())


def _emit(report: Report, output: Format, plan: Path) -> None:
    with _pipe_guard():
        match output:
            case Format.TERMINAL:
                terminal.render(_stdout(), report)
            case Format.JSON:
                sys.stdout.write(document.render(report))
            case Format.MARKDOWN:
                sys.stdout.write(markdown.render(report))
            case Format.SARIF:
                # an absolute Windows path as posix reads as a URI with scheme "C"
                location = plan.as_uri() if plan.is_absolute() else quote(plan.as_posix())
                sys.stdout.write(sarif.render(report, location))


@app.command()
def analyze(
    plan: PlanArg,
    output: FormatOpt = Format.TERMINAL,
    config_path: ConfigOpt = None,
    environment: EnvironmentOpt = None,
) -> None:
    """Analyze a plan and print the report. Exits 0 whatever the findings; see `check`."""
    with _exit_codes():
        report = run_analysis(_read_plan(plan), _settings(config_path, environment))
        _emit(report, output, plan)


@app.command()
def check(  # noqa: PLR0913, PLR0917  - Typer: one parameter per option
    plan: PlanArg,
    output: FormatOpt = Format.TERMINAL,
    config_path: ConfigOpt = None,
    environment: EnvironmentOpt = None,
    fail_on: Annotated[
        Severity | None,
        typer.Option(help="Lowest severity that fails the check (default: high)."),
    ] = None,
    fail_on_confidence: Annotated[
        Confidence | None,
        typer.Option(help="Lowest confidence that fails the check (default: high)."),
    ] = None,
) -> None:
    """CI gate: exit 1 when a finding reaches --fail-on, 0 otherwise."""
    with _exit_codes():
        settings = _settings(config_path, environment, fail_on, fail_on_confidence)
        report = run_analysis(_read_plan(plan), settings)
        _emit(report, output, plan)
        severe = [
            found for found in report.findings if found.severity.rank >= settings.fail_on.rank
        ]
        failing = [
            found for found in severe if found.confidence.rank >= settings.fail_on_confidence.rank
        ]
        stderr = _stderr()
        if doubtful := len(severe) - len(failing):
            # unknown until apply: the reviewer should look, but it does not block on its own
            stderr.print(
                f"note: {doubtful} low-confidence finding(s) at {settings.fail_on} or above "
                "not counted; --fail-on-confidence low counts them",
                markup=False,
            )
        if failing:
            stderr.print(
                f"check failed: {len(failing)} finding(s) at {settings.fail_on} or above",
                markup=False,
            )
            raise typer.Exit(Exit.POLICY_VIOLATION)


@app.command()
def explain(
    plan: PlanArg,
    address: Annotated[str, typer.Argument(help="Full resource address.", show_default=False)],
    config_path: ConfigOpt = None,
    environment: EnvironmentOpt = None,
) -> None:
    """Explain one resource: action, reasons, attributes, dependencies, risk."""
    with _exit_codes():
        parsed = _read_plan(plan)
        report = run_analysis(parsed, _settings(config_path, environment))
        assessment = lookup(report, parsed, address)
        with _pipe_guard():
            terminal.explain(_stdout(), address, assessment)


@app.command()
def graph(
    plan: PlanArg,
    resource: Annotated[str | None, typer.Option(help="Show one resource's neighbourhood.")] = None,
    to: Annotated[
        str | None, typer.Option(help="With --resource: dependency path to here.")
    ] = None,
    output: Annotated[GraphFormat, typer.Option("--format", "-f")] = GraphFormat.TERMINAL,
) -> None:
    """Print the dependency graph, or one resource's dependencies and blast radius."""
    with _exit_codes():
        parsed = _read_plan(plan)
        if resource is None and to is not None:
            raise InputError("--to needs --resource")
        for address in (resource, to):
            if address is not None and address not in parsed.graph.dependents:
                raise InputError(f"{address}: not in the plan")
        with _pipe_guard():
            if resource is None:
                _edges(parsed, output)
            else:
                _neighbourhood(parsed, resource, to, output)


def _edges(parsed: Plan, output: GraphFormat) -> None:
    edges = parsed.graph.dependents
    if output is GraphFormat.JSON:
        pairs = [[node, target] for node, targets in edges.items() for target in sorted(targets)]
        sys.stdout.write(document.dump({"nodes": list(edges), "edges": pairs}))
    else:
        terminal.edges(_stdout(), edges)


def _neighbourhood(parsed: Plan, resource: str, to: str | None, output: GraphFormat) -> None:
    ancestors = graphs.ancestors(parsed.graph, resource)
    radius = graphs.blast_radius(parsed.graph, resource)
    chain = None if to is None else graphs.path(parsed.graph, resource, to)
    if output is GraphFormat.JSON:
        view: document.Document = {
            "resource": resource,
            "dependencies": list(ancestors),
            "blast_radius": document.blast(radius),
        }
        if chain is not None:
            view["path"] = list(chain)
        sys.stdout.write(document.dump(view))
    else:
        terminal.graph(_stdout(), resource, ancestors, radius, chain)


@app.command()
def rules() -> None:
    """List built-in rules with their default severity."""
    with _pipe_guard():
        terminal.rules(_stdout(), RULES, RULES_VERSION)


@app.command()
def version() -> None:
    """Print tf-diff, rules and report schema versions."""
    with _pipe_guard():
        sys.stdout.write(
            f"tf-diff {__version__} (rules {RULES_VERSION}, "
            f"report schema {document.SCHEMA_VERSION})\n"
        )


@app.command()
def schema() -> None:
    """Print the JSON Schema of the JSON report."""
    with _pipe_guard():
        sys.stdout.write(document.schema())


def main() -> None:
    # `tf-diff ... >&-` starts us without stdout; writes then go nowhere instead of failing
    if sys.stdout is None:
        sys.stdout = Path(os.devnull).open("w", encoding="utf-8")  # noqa: SIM115  - lives as long as the process
    # reports are UTF-8 with LF whatever the platform (cp1251 cannot print box drawing), so a
    # report saved on Windows is byte for byte the one saved on Linux
    for stream in (sys.stdout, sys.stderr):
        if isinstance(stream, io.TextIOWrapper):
            stream.reconfigure(encoding="utf-8", newline="\n")
    try:
        app()
    except Exception as error:  # noqa: BLE001  - exit 4 is the contract for "our bug"
        # type only: the message of an unexpected error may carry a plan value
        sys.stderr.write(f"internal error: {type(error).__name__}; please report it\n")
        sys.exit(Exit.INTERNAL_ERROR)
