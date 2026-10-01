"""Benchmark tf-diff on generated plans: time, CPU and peak memory per stage.

Run from the repo root:
  uv run python scripts/bench.py generate mixed 10000 plan.json   # write a plan
  uv run python scripts/bench.py measure plan.json                # one run, JSON on stdout
  uv run python scripts/bench.py matrix --sizes 100,1000,10000    # markdown table, median of runs
  uv run python scripts/bench.py check 10000 --budget 30 --max-mb 1024   # CI gate

Each measured run is a fresh process, so peak memory belongs to that plan alone.
Shapes:
  mixed     modules with for_each, count, cross-module and fan-out references; 70% no-op
  chain     each resource depends on the one before: blast radius walks the whole chain
  fanout    every resource depends on one hub that changes
  findings  every resource is a security group opened to the internet: one finding each
  wide      few resources with megabyte-sized attribute values
"""

import argparse
import ctypes
import gc
import io
import json
import statistics
import subprocess
import sys
import tempfile
import time
from collections.abc import Callable, Iterator
from dataclasses import asdict, dataclass, replace
from functools import partial
from pathlib import Path
from typing import Any

from rich.console import Console

from tfdiff.analysis.engine import analyze
from tfdiff.model.graph import Graph, build
from tfdiff.model.report import Report
from tfdiff.model.settings import Settings
from tfdiff.report import document, markdown, sarif, terminal
from tfdiff.terraform.parser import parse
from tfdiff.terraform.references import read

ROOT = Path(__file__).parents[1]
AWS = "registry.terraform.io/hashicorp/aws"
BUILTIN = "terraform.io/builtin/terraform"
PROD = {"Environment": "production", "Team": "platform", "CostCenter": "cc-1234"}
UNIT = 10  # resources a mixed-shape module instance holds
MODULE_CALLS = 10
POLICY = json.dumps(
    {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Sid": f"Stmt{n}",
                "Effect": "Allow",
                "Action": ["s3:GetObject", "s3:PutObject", "s3:ListBucket"],
                "Resource": [f"arn:aws:s3:::bucket-{n}", f"arn:aws:s3:::bucket-{n}/*"],
            }
            for n in range(8)
        ],
    }
)

# generated plan JSON: nested freely; tf-diff checks it when it reads it
type Json = dict[str, Any]


# ---------------------------------------------------------------------------- plan generation


def _change(  # noqa: PLR0913  - mirrors the fields of a resource change
    address: str,
    kind: str,
    actions: list[str],
    before: Json | None,
    after: Json | None,
    *,
    provider: str = AWS,
    replace_paths: list[list[str]] | None = None,
) -> Json:
    name = address.removesuffix("]").rpartition("[")[0] if address.endswith("]") else address
    change: Json = {
        "actions": actions,
        "before": before,
        "after": after,
        "after_unknown": {"id": True} if actions == ["create"] else {},
        "before_sensitive": {} if before is not None else False,
        "after_sensitive": {} if after is not None else False,
    }
    if replace_paths:
        change["replace_paths"] = replace_paths
    raw: Json = {
        "address": address,
        "mode": "managed",
        "type": kind,
        "name": name.rsplit(".", 1)[1],
        "provider_name": provider,
        "change": change,
    }
    if actions == ["delete"]:
        raw["action_reason"] = "delete_because_no_resource_config"
    return raw


def _resource(kind: str, name: str, expressions: Json, **extra: object) -> Json:
    return {
        "address": f"{kind}.{name}",
        "mode": "managed",
        "type": kind,
        "name": name,
        "provider_config_key": "aws",
        "expressions": expressions,
        "schema_version": 0,
        **extra,
    }


def _refs(*names: str) -> Json:
    return {"references": list(names)}


def _ingress(cidr: str, port: int) -> list[Json]:
    return [
        {
            "cidr_blocks": [cidr],
            "description": "app",
            "from_port": port,
            "to_port": port,
            "ipv6_cidr_blocks": [],
            "prefix_list_ids": [],
            "protocol": "tcp",
            "security_groups": [],
            "self": False,
        }
    ]


def _base(name: str, n: int) -> Json:
    return {
        "id": f"{name}-{n:08x}",
        "arn": f"arn:aws:service:eu-west-1:123456789012:{name}/{n}",
        "tags": PROD,
        "tags_all": PROD,
        "timeouts": None,
    }


def _unit(prefix: str, n: int) -> Iterator[Json]:
    """Ten resources of one module instance; `n` picks which ones change."""
    sg = {**_base("sg", n), "name": f"web-{n}", "vpc_id": "vpc-1", "egress": []}
    opened = n % 20 == 0
    yield _change(
        f"{prefix}aws_security_group.web",
        "aws_security_group",
        ["update"] if n % 4 == 0 else ["no-op"],
        {**sg, "ingress": _ingress("10.0.0.0/8", 22)},
        {**sg, "ingress": _ingress("0.0.0.0/0" if opened else "10.0.0.0/8", 22)},
    )
    for key in ("a", "b"):
        vm = {
            **_base("i", n),
            "ami": "ami-0123456789abcdef0",
            "instance_type": "t3.large",
            "subnet_id": f"subnet-{n % 6}",
            "vpc_security_group_ids": [f"sg-{n}"],
            "root_block_device": [{"volume_size": 50, "volume_type": "gp3", "encrypted": True}],
            "metadata_options": [{"http_tokens": "required", "http_endpoint": "enabled"}],
            "user_data": "x" * 400,
        }
        changed = n % 3 == 0
        yield _change(
            f'{prefix}aws_instance.web["{key}"]',
            "aws_instance",
            ["update"] if changed else ["no-op"],
            vm,
            {**vm, "instance_type": "t3.xlarge"} if changed else vm,
        )
    db = {
        **_base("db", n),
        "engine": "postgres",
        "storage_type": "gp2",
        "allocated_storage": 100,
        "skip_final_snapshot": n % 2 == 0,
        "deletion_protection": False,
        "backup_retention_period": 7,
        "publicly_accessible": False,
        "storage_encrypted": True,
    }
    replaced = n % 50 == 0
    yield _change(
        f"{prefix}aws_db_instance.db",
        "aws_db_instance",
        ["delete", "create"] if replaced else ["no-op"],
        db,
        {**db, "storage_type": "io2"} if replaced else db,
        replace_paths=[["storage_type"]] if replaced else None,
    )
    bucket = {**_base("s3", n), "bucket": f"logs-{n}", "force_destroy": n % 2 == 0}
    deleted = n % 100 == 0
    yield _change(
        f"{prefix}aws_s3_bucket.logs",
        "aws_s3_bucket",
        ["delete"] if deleted else ["no-op"],
        bucket,
        None if deleted else bucket,
    )
    asg = {**_base("asg", n), "min_size": 4, "max_size": 8, "desired_capacity": 6}
    shrunk = n % 10 == 0
    yield _change(
        f"{prefix}aws_autoscaling_group.app",
        "aws_autoscaling_group",
        ["update"] if shrunk else ["no-op"],
        asg,
        {**asg, "desired_capacity": 2} if shrunk else asg,
    )
    policy = {**_base("policy", n), "name": f"app-{n}", "policy": POLICY}
    yield _change(f"{prefix}aws_iam_policy.app", "aws_iam_policy", ["no-op"], policy, policy)
    for index in range(3):
        data = {"id": f"td-{n}-{index}", "input": f"v{n}", "output": f"v{n}"}
        created = n % 5 == index
        yield _change(
            f"{prefix}terraform_data.hook[{index}]",
            "terraform_data",
            ["create"] if created else ["no-op"],
            None if created else data,
            data,
            provider=BUILTIN,
        )


def _unit_config() -> Json:
    return {
        "resources": [
            _resource("aws_security_group", "web", {"vpc_id": _refs("var.vpc_id")}),
            _resource(
                "aws_instance",
                "web",
                {
                    "vpc_security_group_ids": _refs(
                        "aws_security_group.web.id", "aws_security_group.web"
                    ),
                    "tags": _refs("each.key"),
                },
                for_each_expression={"constant_value": ["a", "b"]},
            ),
            _resource("aws_db_instance", "db", {"vpc_security_group_ids": _refs("var.vpc_id")}),
            _resource("aws_s3_bucket", "logs", {}),
            _resource(
                "aws_autoscaling_group",
                "app",
                {"launch_template": [{"id": _refs("aws_instance.web")}]},
            ),
            _resource("aws_iam_policy", "app", {"policy": _refs("aws_s3_bucket.logs.arn")}),
            _resource(
                "terraform_data",
                "hook",
                {"input": _refs("aws_db_instance.db.address", "count.index")},
                count_expression={"constant_value": 3},
            ),
        ],
        "outputs": {"sg": {"expression": _refs("aws_security_group.web.id")}},
        "variables": {"vpc_id": {}},
    }


def mixed(resources: int) -> Json:
    units = max(1, resources // UNIT)
    vpc = {**_base("vpc", 0), "cidr_block": "10.0.0.0/16"}
    changes = [
        _change("aws_vpc.main", "aws_vpc", ["update"], vpc, {**vpc, "tags": {**PROD, "v": "2"}})
    ]
    calls: Json = {}
    for call in range(MODULE_CALLS):
        keys = [f"k{n}" for n in range(call, units, MODULE_CALLS)]
        for key in keys:
            n = int(key[1:])
            changes += _unit(f'module.svc{call}["{key}"].', n)
        calls[f"svc{call}"] = {
            "source": "./modules/svc",
            "expressions": {"vpc_id": _refs("aws_vpc.main.id", "aws_vpc.main")},
            "for_each_expression": {"constant_value": keys},
            "module": _unit_config(),
        }
    edge = _resource("terraform_data", "edge", {"input": _refs("module.svc0.sg")})
    edge["provider_config_key"] = "terraform"
    data = {"id": "edge", "input": "a", "output": "a"}
    changes.append(_change("terraform_data.edge", "terraform_data", ["no-op"], data, data))
    root = {
        "resources": [_resource("aws_vpc", "main", {}), edge],
        "module_calls": calls,
    }
    return _plan(changes, root)


def _data(index: int, value: str) -> Json:
    return {"id": f"td-{index}", "input": value, "output": value, "triggers_replace": None}


def chain(resources: int) -> Json:
    changes = [
        _change(
            f"terraform_data.n{index:06d}",
            "terraform_data",
            ["update"],
            _data(index, "a"),
            _data(index, "b"),
            provider=BUILTIN,
        )
        for index in range(resources)
    ]
    config = [
        _resource(
            "terraform_data",
            f"n{index:06d}",
            {"input": _refs(f"terraform_data.n{index - 1:06d}.output")} if index else {},
        )
        for index in range(resources)
    ]
    return _plan(changes, {"resources": config})


def fanout(resources: int) -> Json:
    changes = [
        _change(
            f"terraform_data.n{index:06d}",
            "terraform_data",
            ["update"],
            _data(index, "a"),
            _data(index, "b"),
            provider=BUILTIN,
        )
        for index in range(resources)
    ]
    config = [
        _resource(
            "terraform_data",
            f"n{index:06d}",
            {"input": _refs("terraform_data.n000000.output")} if index else {},
        )
        for index in range(resources)
    ]
    return _plan(changes, {"resources": config})


def findings(resources: int) -> Json:
    changes = []
    for index in range(resources):
        sg = {**_base("sg", index), "name": f"sg-{index}", "egress": []}
        changes.append(
            _change(
                f"aws_security_group.g{index:06d}",
                "aws_security_group",
                ["update"],
                {**sg, "ingress": _ingress("10.0.0.0/8", 22)},
                {**sg, "ingress": _ingress("0.0.0.0/0", 22)},
            )
        )
    config = [_resource("aws_security_group", f"g{index:06d}", {}) for index in range(resources)]
    return _plan(changes, {"resources": config})


def wide(resources: int) -> Json:
    """`resources` IAM policies, each with a 1 MB document that changes in its last statement."""
    statement = {"Effect": "Allow", "Action": ["s3:GetObject"], "Resource": "arn:aws:s3:::b/*"}
    big = [dict(statement, Sid=f"S{n}") for n in range(12_000)]
    changes = []
    for index in range(resources):
        before = {"id": f"p{index}", "name": f"p{index}", "policy": json.dumps(big), "tags": PROD}
        after = {**before, "policy": json.dumps([*big[:-1], dict(statement, Sid="new")])}
        changes.append(
            _change(f"aws_iam_policy.p{index:04d}", "aws_iam_policy", ["update"], before, after)
        )
    config = [_resource("aws_iam_policy", f"p{index:04d}", {}) for index in range(resources)]
    return _plan(changes, {"resources": config})


SHAPES: dict[str, Callable[[int], Json]] = {
    "mixed": mixed,
    "chain": chain,
    "fanout": fanout,
    "findings": findings,
    "wide": wide,
}


def _plan(changes: list[Json], root: Json) -> Json:
    # terraform also writes the values twice more; tf-diff skips them but still decodes them
    planned = [{"address": raw["address"], "values": raw["change"]["after"]} for raw in changes]
    prior = [{"address": raw["address"], "values": raw["change"]["before"]} for raw in changes]
    return {
        "format_version": "1.2",
        "terraform_version": "1.16.0",
        "planned_values": {"root_module": {"resources": planned}},
        "resource_changes": changes,
        "prior_state": {"values": {"root_module": {"resources": prior}}},
        "configuration": {"root_module": root},
        "complete": True,
        "errored": False,
    }


def generate(shape: str, resources: int, out: Path) -> None:
    out.write_text(json.dumps(SHAPES[shape](resources)), encoding="utf-8")


# ---------------------------------------------------------------------------- measurement


class _Counters(ctypes.Structure):
    _fields_ = [
        ("cb", ctypes.c_ulong),
        ("PageFaultCount", ctypes.c_ulong),
        ("PeakWorkingSetSize", ctypes.c_size_t),
        ("WorkingSetSize", ctypes.c_size_t),
        ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
        ("QuotaPagedPoolUsage", ctypes.c_size_t),
        ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
        ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
        ("PagefileUsage", ctypes.c_size_t),
        ("PeakPagefileUsage", ctypes.c_size_t),
    ]


def peak_mb() -> float:
    """Return the peak resident memory of this process so far, in MiB."""
    if sys.platform == "win32":
        counters = _Counters()
        counters.cb = ctypes.sizeof(counters)
        kernel = ctypes.windll.kernel32
        kernel.GetCurrentProcess.restype = ctypes.c_void_p
        kernel.K32GetProcessMemoryInfo.argtypes = [
            ctypes.c_void_p,
            ctypes.POINTER(_Counters),
            ctypes.c_ulong,
        ]
        if not kernel.K32GetProcessMemoryInfo(
            kernel.GetCurrentProcess(), ctypes.byref(counters), counters.cb
        ):
            raise ctypes.WinError()
        peak = int(counters.PeakWorkingSetSize)
    else:
        import resource  # noqa: PLC0415  - POSIX only

        # kilobytes on Linux, bytes on macOS
        scale = 1 if sys.platform == "darwin" else 1024
        peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * scale
    return peak / 2**20


@dataclass(slots=True)
class Stage:
    wall: float
    cpu: float
    # of the process so far, not of this stage alone
    peak_mb: float


@dataclass(slots=True)
class Result:
    shape: str
    plan_mb: float
    resources: int
    changed: int
    findings: int
    edges: int
    output_chars: dict[str, int]
    stages: dict[str, Stage]
    total_wall: float
    peak_mb: float
    runs: int = 1


def _terminal(report: Report) -> str:
    out = io.StringIO()
    terminal.render(Console(file=out, width=120, color_system=None), report)
    return out.getvalue()


RENDERERS: dict[str, Callable[[Report], str]] = {
    "terminal": _terminal,
    "json": document.render,
    "markdown": markdown.render,
    "sarif": lambda report: sarif.render(report, "plan.json"),
}


def measure(plan: Path, shape: str) -> Result:
    """Run every stage once in this process and time it."""
    stages: dict[str, Stage] = {}

    def stage[T](name: str, run: Callable[[], T]) -> T:
        gc.collect()
        wall, cpu = time.perf_counter(), time.process_time()
        result = run()
        stages[name] = Stage(time.perf_counter() - wall, time.process_time() - cpu, peak_mb())
        return result

    started = time.perf_counter()
    text = stage("read", partial(plan.read_text, encoding="utf-8"))
    # the graph alone, as parse builds it, to tell it from the rest of parsing
    stage("graph", partial(_graph, stage("json", partial(json.loads, text))))
    parsed = stage("parse", partial(parse, text))
    text = ""  # parse is done with it: free it before the next stages
    report = stage("analyze", partial(analyze, parsed, Settings()))
    sizes = {
        name: len(stage(f"render-{name}", partial(render, report)))
        for name, render in RENDERERS.items()
    }
    return Result(
        shape=shape,
        plan_mb=plan.stat().st_size / 2**20,
        resources=len(parsed.changes),
        changed=len(report.assessments),
        findings=len(report.findings),
        edges=sum(len(targets) for targets in parsed.graph.dependents.values()),
        output_chars=sizes,
        stages=stages,
        total_wall=time.perf_counter() - started,
        peak_mb=peak_mb(),
    )


def _graph(raw: Json) -> Graph:
    nodes = {change["address"] for change in raw["resource_changes"]}
    return build(nodes, read(raw.get("configuration") or {}, nodes).edges)


class BenchError(Exception):
    pass


def _run(plan: Path, shape: str) -> Result:
    done = subprocess.run(  # noqa: S603  - our own interpreter on our own script
        [sys.executable, __file__, "measure", str(plan), "--shape", shape],
        capture_output=True,
        text=True,
        check=False,
        cwd=ROOT,
    )
    if done.returncode:
        lines = done.stderr.strip().splitlines() or [f"exit code {done.returncode}"]
        raise BenchError(f"{plan.name}: {lines[-1]}")
    return _load(json.loads(done.stdout))


def _load(raw: dict[str, Any]) -> Result:
    stages = {name: Stage(**values) for name, values in raw.pop("stages").items()}
    return Result(**raw, stages=stages)


def _median(runs: list[Result]) -> Result:
    """Return the median run: median time of each stage, highest memory of any run."""
    middle = sorted(runs, key=lambda run: run.total_wall)[len(runs) // 2]
    return replace(
        middle,
        stages={
            name: Stage(
                statistics.median(run.stages[name].wall for run in runs),
                statistics.median(run.stages[name].cpu for run in runs),
                max(run.stages[name].peak_mb for run in runs),
            )
            for name in middle.stages
        },
        total_wall=statistics.median(run.total_wall for run in runs),
        peak_mb=max(run.peak_mb for run in runs),
        runs=len(runs),
    )


def series(shape: str, resources: int, repeat: int, folder: Path) -> Result:
    plan = folder / f"{shape}-{resources}.json"
    if not plan.exists():
        generate(shape, resources, plan)
    return _median([_run(plan, shape) for _ in range(repeat)])


STAGES = ("json", "graph", "parse", "analyze", "render-terminal", "render-json",
          "render-markdown", "render-sarif")  # fmt: skip
HEAD = ("shape", "resources", "changed", "findings", "edges", "plan MB", *STAGES, "total s",
        "peak MB")  # fmt: skip


def row(result: Result | BenchError) -> str:
    if isinstance(result, BenchError):
        return f"| error: {result} |"
    cells = [
        result.shape,
        f"{result.resources:,}",
        f"{result.changed:,}",
        f"{result.findings:,}",
        f"{result.edges:,}",
        f"{result.plan_mb:.1f}",
        *(f"{result.stages[name].wall:.2f}" for name in STAGES),
        f"{result.total_wall:.2f}",
        f"{result.peak_mb:.0f}",
    ]
    return "| " + " | ".join(cells) + " |"


def table(results: list[Result | BenchError]) -> str:
    lines = ["| " + " | ".join(HEAD) + " |", "|" + "---|" * len(HEAD)]
    return "\n".join([*lines, *map(row, results)]) + "\n"


def _attempt(shape: str, resources: int, repeat: int, folder: Path) -> Result | BenchError:
    try:
        return series(shape, resources, repeat, folder)
    except BenchError as error:
        return error


def main() -> None:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    commands = parser.add_subparsers(dest="command", required=True)
    make = commands.add_parser("generate")
    make.add_argument("shape", choices=SHAPES)
    make.add_argument("resources", type=int)
    make.add_argument("out", type=Path)
    one = commands.add_parser("measure")
    one.add_argument("plan", type=Path)
    one.add_argument("--shape", default="?")
    many = commands.add_parser("matrix")
    many.add_argument("--shape", choices=SHAPES, default="mixed")
    many.add_argument("--sizes", default="100,1000,10000,50000")
    many.add_argument("--repeat", type=int, default=3)
    many.add_argument("--dir", type=Path, default=Path(tempfile.gettempdir()) / "tfdiff-bench")
    many.add_argument("--json", type=Path, help="also write the raw results here")
    gate = commands.add_parser("check")
    gate.add_argument("resources", type=int)
    gate.add_argument("--shape", choices=SHAPES, default="mixed")
    gate.add_argument("--budget", type=float, required=True, help="seconds, whole run")
    gate.add_argument("--max-mb", type=float, required=True, help="peak memory, MiB")
    args = parser.parse_args()
    match args.command:
        case "generate":
            generate(args.shape, args.resources, args.out)
        case "measure":
            sys.stdout.write(json.dumps(asdict(measure(args.plan, args.shape))))
        case "matrix":
            args.dir.mkdir(parents=True, exist_ok=True)
            results = [
                _attempt(args.shape, int(size), args.repeat, args.dir)
                for size in args.sizes.split(",")
            ]
            if args.json:
                raw = [asdict(item) if isinstance(item, Result) else str(item) for item in results]
                args.json.write_text(json.dumps(raw, indent=1), encoding="utf-8")
            sys.stdout.write(table(results))
        case "check":
            with tempfile.TemporaryDirectory() as folder:
                result = _attempt(args.shape, args.resources, 1, Path(folder))
            sys.stdout.write(table([result]))
            if isinstance(result, BenchError):
                sys.exit(str(result))
            if result.total_wall > args.budget:
                sys.exit(f"slower than {args.budget} s")
            if result.peak_mb > args.max_mb:
                sys.exit(f"more memory than {args.max_mb} MiB")


if __name__ == "__main__":
    main()
