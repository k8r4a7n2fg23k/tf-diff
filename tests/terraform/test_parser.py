import contextlib
import gc
import io
import json

import pytest
from hypothesis import event, given
from hypothesis import strategies as st
from jsonschema import validate  # type: ignore[import-untyped]  # no stubs
from pydantic import JsonValue
from rich.console import Console

from factories import GOLDEN, plan_text, resource_change
from tfdiff.analysis.engine import analyze
from tfdiff.model.errors import CompatibilityError, InputError
from tfdiff.model.plan import Action
from tfdiff.model.settings import Settings
from tfdiff.model.values import Known, Sensitive, Unknown, value_at
from tfdiff.report import document as document_report
from tfdiff.report import markdown, sarif, terminal
from tfdiff.terraform.parser import parse
from tfdiff.terraform.references import MAX_NESTING

RECORDED = GOLDEN / "terraform-1.16" / "plan.json"
REPORT_SCHEMA = json.loads(document_report.schema())


@pytest.fixture(scope="module")
def recorded() -> str:
    return RECORDED.read_text(encoding="utf-8")


def test_recorded_plan_addresses_and_actions(recorded: str) -> None:
    plan = parse(recorded)
    actions = {change.address: change.action for change in plan.changes}
    assert actions['module.network.terraform_data.subnet["zone-c"]'] is Action.DELETE
    assert actions["module.app.terraform_data.worker[2]"] is Action.DELETE
    assert actions["module.database.terraform_data.primary"] is Action.REPLACE
    assert actions["module.network.terraform_data.vpc"] is Action.NOOP
    replaced = next(change for change in plan.changes if change.action is Action.REPLACE)
    assert replaced.actions == ("delete", "create")
    assert replaced.replace_paths == (("triggers_replace",),)


def test_recorded_plan_graph_crosses_modules(recorded: str) -> None:
    graph = parse(recorded).graph
    # module output -> var -> resource, both directions of the module boundary
    assert (
        "module.app.terraform_data.api"
        in graph.dependents["module.database.terraform_data.primary"]
    )
    assert graph.dependencies["module.database.terraform_data.primary"] == frozenset(
        f'module.network.terraform_data.subnet["zone-{zone}"]' for zone in "abc"
    )
    # the bare `module.network` reference must not drag the whole module in
    assert graph.dependencies["terraform_data.cache[0]"] == {"module.network.terraform_data.vpc"}


def test_recorded_plan_values(recorded: str) -> None:
    plan = parse(recorded)
    primary = next(change for change in plan.changes if change.action is Action.REPLACE)
    assert value_at(primary.after, ("id",)) == Unknown()
    assert value_at(primary.after, ("output", "subnets", 0)) == Unknown()
    assert value_at(primary.after, ("triggers_replace",)) == Known("gp3")
    assert isinstance(value_at(primary.before, ("input", "password")), Sensitive)


def test_recorded_plan_configured_attributes(recorded: str) -> None:
    changes = {change.address: change for change in parse(recorded).changes}
    primary = changes["module.database.terraform_data.primary"]
    # `output` is computed: nothing in the configuration sets it
    assert primary.configured == frozenset({"input", "triggers_replace"})
    assert changes['module.network.terraform_data.subnet["zone-a"]'].configured == frozenset(
        {"input"}
    )


def test_configured_attributes_need_the_configuration() -> None:
    raw = resource_change("aws_instance.web", before={"a": 1}, after={"a": 2})
    other = {"address": "aws_x.y", "mode": "managed", "type": "aws_x", "name": "y"}
    bare = {**other, "address": "aws_instance.web", "type": "aws_instance", "name": "web"}

    def configured(configuration: object) -> object:
        (change,) = parse(plan_text(raw, configuration=configuration)).changes
        return change.configured

    assert configured(None) is None
    assert configured({"root_module": {"resources": [other]}}) is None
    assert configured({"root_module": {"resources": [bare]}}) == frozenset()


@pytest.mark.parametrize(
    ("address", "mode", "deposed"),
    [
        ('module.db["blue"].aws_db_instance.main[0]', "managed", None),
        ("module.db.data.aws_ami.base", "data", None),
        ('module.db["blue"].aws_db_instance.main[0]', "managed", "0a1b"),
    ],
    ids=["module-instance", "data-source", "deposed"],
)
def test_configured_attributes_by_config_address(
    address: str, mode: str, deposed: str | None
) -> None:
    kind = "aws_ami" if mode == "data" else "aws_db_instance"
    name = "base" if mode == "data" else "main"
    resource = {
        "address": f"{'data.' if mode == 'data' else ''}{kind}.{name}",
        "mode": mode,
        "type": kind,
        "name": name,
        "expressions": {"password": {"references": ["var.secret"]}},
    }
    configuration = {"root_module": {"module_calls": {"db": {"module": {"resources": [resource]}}}}}
    raw = resource_change(address, actions=("delete",), before={}, mode=mode, deposed=deposed)
    (change,) = parse(plan_text(raw, configuration=configuration)).changes
    assert change.configured == frozenset({"password"})


def test_configured_expressions_must_be_an_object() -> None:
    raw = resource_change("aws_instance.web")
    resource = {
        "address": "aws_instance.web",
        "mode": "managed",
        "type": "aws_instance",
        "name": "web",
        "expressions": ["CANARY-list"],
    }
    configuration = {"root_module": {"resources": [resource]}}
    with pytest.raises(InputError, match=r"aws_instance\.web\.expressions") as caught:
        parse(plan_text(raw, configuration=configuration))
    assert "CANARY" not in str(caught.value)


def test_unknown_fields_are_ignored() -> None:
    raw = resource_change("aws_instance.web", before={"a": 1}, after={"a": 2})
    raw["importing"] = {"id": "i-123"}
    plan = parse(plan_text(raw, from_the_future={"x": 1}))
    assert [change.action for change in plan.changes] == [Action.UPDATE]


def test_newer_minor_format_warns() -> None:
    plan = parse(json.dumps({"format_version": "1.9", "resource_changes": []}))
    assert plan.warnings[0].startswith("plan format 1.9 is newer")


@pytest.mark.parametrize(
    ("document", "error", "message"),
    [
        ({"resource_changes": []}, InputError, "format_version: missing or not a string"),
        ({"format_version": "2.0"}, CompatibilityError, "not supported"),
        ({"format_version": "CANARY-1.2"}, CompatibilityError, "not MAJOR.MINOR"),
        (
            {"format_version": "2.0", "resource_changes": [{"address": "x"}]},
            CompatibilityError,
            "plan format 2.0 is not supported",
        ),
        ({"format_version": "1.2", "errored": True}, InputError, "errors while planning"),
        (
            {"format_version": "1.2", "resource_changes": [{"address": "x"}]},
            InputError,
            "resource_changes.0.change: Field required",
        ),
        (
            json.loads(plan_text(resource_change("aws_x.y", actions=("explode",)))),
            CompatibilityError,
            r"aws_x.y: unsupported action list",
        ),
        (
            json.loads(plan_text(resource_change("aws_x.y"), resource_change("aws_x.y"))),
            InputError,
            "listed twice",
        ),
        (
            json.loads(plan_text(resource_change("aws_x.y", before="CANARY-scalar"))),
            InputError,
            "must be an object",
        ),
    ],
    ids=[
        "no-format",
        "format-2",
        "format-garbage",
        "format-2-reshaped",
        "errored",
        "missing-change",
        "action",
        "duplicate",
        "scalar",
    ],
)
def test_bad_input_is_rejected(document: JsonValue, error: type[Exception], message: str) -> None:
    with pytest.raises(error, match=message) as caught:
        parse(json.dumps(document))
    assert "CANARY" not in str(caught.value)


@pytest.mark.parametrize(
    "number",
    ["NaN", "Infinity", "-Infinity", "1e999", "1" * 5000],
    ids=["nan", "inf", "-inf", "1e999", "5000-digits"],
)
def test_non_finite_numbers_are_input_error(number: str) -> None:
    # they would reach the JSON report as bare NaN, which is not JSON
    text = plan_text(resource_change("aws_x.y", before={"n": 0}, after={"n": 1}))
    with pytest.raises(InputError, match="plan JSON holds"):
        parse(text.replace('"n": 1', f'"n": {number}'))


def test_validation_error_does_not_echo_plan_keys() -> None:
    deep: JsonValue = 1
    for _ in range(300):
        deep = {"CANARY-key": deep}
    text = plan_text(resource_change("aws_x.y", before={"password": deep}, after={}))
    with pytest.raises(InputError) as caught:
        parse(text)
    assert "CANARY" not in str(caught.value)
    assert len(str(caught.value)) < 300


@pytest.mark.parametrize(
    ("is_unknown", "after"),
    [
        # every attribute of the old object may come back
        (True, ((("a",), Unknown()), (("b",), Unknown()))),
        # a redacted object still shows which attributes it has
        (False, ((("a",), Sensitive(is_changed=True)),)),
    ],
    ids=["unknown", "sensitive"],
)
def test_mask_on_the_whole_object_covers_each_attribute(is_unknown: bool, after: object) -> None:
    raw = resource_change(
        "aws_x.y",
        before={"a": 1, "b": "x"},
        after={"a": 2},
        after_unknown=True if is_unknown else None,
        after_sensitive=None if is_unknown else True,
    )
    (change,) = parse(plan_text(raw)).changes
    assert change.after == after


@pytest.mark.parametrize(
    ("name", "redacted"),
    [
        ("db_password", True),
        ("DB_PASS", True),
        ("apikey", True),
        ("credentials", True),
        ("connection_string", True),
        ("passphrase", True),
        ("bypass", False),
        ("passenger_count", False),
        ("author", False),
    ],
)
def test_secret_looking_names_are_redacted(name: str, redacted: bool) -> None:
    # terraform_data and similar copies lose the provider's sensitive mark
    raw = resource_change(
        "terraform_data.app", before={"output": {name: "v1"}}, after={"output": {name: "v2"}}
    )
    (change,) = parse(plan_text(raw)).changes
    assert isinstance(value_at(change.after, ("output", name)), Sensitive) is redacted


def test_deposed_objects_share_the_address() -> None:
    current = resource_change(
        "aws_instance.web", actions=("no-op",), before={"a": 1}, after={"a": 1}
    )
    old = resource_change("aws_instance.web", actions=("delete",), before={"a": 0}, deposed="00a1")
    plan = parse(plan_text(current, old))
    assert [(change.address, change.deposed) for change in plan.changes] == [
        ("aws_instance.web", None),
        ("aws_instance.web", "00a1"),
    ]


@pytest.mark.parametrize("actions", [("no-op",), ("read",)])
def test_a_quiet_change_keeps_only_its_tags(actions: tuple[str, ...]) -> None:
    state = {"ami": "ami-1", "tags": {"Env": "prod"}, "tags_all": {"Env": "prod"}}
    raw = resource_change(
        "aws_instance.web", actions=actions, before=state, after=state, after_unknown={"id": True}
    )
    (change,) = parse(plan_text(raw)).changes
    tags = ((("tags", "Env"), Known("prod")), (("tags_all", "Env"), Known("prod")))
    assert (change.before, change.after) == (tags, tags)


def test_a_quiet_change_is_still_checked() -> None:
    raw = resource_change("aws_instance.web", actions=("no-op",), before=[1], after=[1])
    with pytest.raises(InputError, match="before/after must be an object"):
        parse(plan_text(raw))


@pytest.mark.parametrize("text", [plan_text(), "not json"])
@pytest.mark.parametrize("collecting", [True, False])
def test_parse_leaves_the_garbage_collector_as_it_was(text: str, collecting: bool) -> None:
    was = gc.isenabled()
    if collecting:
        gc.enable()
    else:
        gc.disable()
    try:
        with contextlib.suppress(InputError):
            parse(text)
        assert gc.isenabled() is collecting
    finally:
        if was:
            gc.enable()
        else:
            gc.disable()


def test_too_deep_attributes_are_input_error() -> None:
    deep: JsonValue = "CANARY-leaf"
    for _ in range(MAX_NESTING + 2):
        deep = {"k": deep}
    with pytest.raises(InputError, match="nested deeper") as caught:
        parse(plan_text(resource_change("aws_x.y", before={"a": deep}, after={"a": deep})))
    assert "CANARY" not in str(caught.value)


def test_data_sources_and_depends_on() -> None:
    configuration = {
        "root_module": {
            "resources": [
                {"address": "data.aws_ami.base", "mode": "data", "type": "aws_ami", "name": "base"},
                {
                    "address": "aws_instance.web",
                    "mode": "managed",
                    "type": "aws_instance",
                    "name": "web",
                    "count_expression": {"references": ["data.aws_ami.base.id"]},
                },
                {
                    "address": "aws_eip.web",
                    "mode": "managed",
                    "type": "aws_eip",
                    "name": "web",
                    "depends_on": ["aws_instance.web", "local.ignored"],
                },
            ],
            "module_calls": {
                "dns": {
                    "depends_on": ["aws_eip.web"],
                    "module": {
                        "resources": [
                            {
                                "address": "aws_route53_record.a",
                                "mode": "managed",
                                "type": "aws_route53_record",
                                "name": "a",
                            }
                        ]
                    },
                }
            },
        }
    }
    changes = [
        resource_change("data.aws_ami.base", actions=("read",), mode="data", after={}),
        resource_change("aws_instance.web[0]", actions=("create",), after={}),
        resource_change("aws_instance.web[1]", actions=("create",), after={}),
        resource_change("aws_eip.web", actions=("create",), after={}),
        resource_change("module.dns.aws_route53_record.a", actions=("create",), after={}),
    ]
    graph = parse(plan_text(*changes, configuration=configuration)).graph
    assert graph.dependents["data.aws_ami.base"] == {"aws_instance.web[0]", "aws_instance.web[1]"}
    assert graph.dependencies["aws_eip.web"] == {"aws_instance.web[0]", "aws_instance.web[1]"}
    assert graph.dependencies["module.dns.aws_route53_record.a"] == {"aws_eip.web"}


def _resource(address: str, *refs: str) -> dict[str, JsonValue]:
    kind, name = address.removeprefix("data.").split(".")
    return {
        "address": address,
        "mode": "data" if address.startswith("data.") else "managed",
        "type": kind,
        "name": name,
        "expressions": {"v": {"references": list(refs)}},
    }


def test_dependency_through_data_sources_missing_from_the_plan() -> None:
    # Terraform omits data sources it reads while planning from resource_changes
    configuration = {
        "root_module": {
            "resources": [
                _resource("aws_vpc.main"),
                _resource("data.aws_subnets.x", "aws_vpc.main.id"),
                _resource("data.aws_subnet.each", "data.aws_subnets.x.ids"),
                _resource("aws_instance.app", "data.aws_subnet.each.id"),
            ]
        }
    }
    changes = [
        resource_change("aws_vpc.main", actions=("delete",), before={}),
        resource_change("aws_instance.app", actions=("update",), before={}, after={}),
    ]
    graph = parse(plan_text(*changes, configuration=configuration)).graph
    assert graph.dependents["aws_vpc.main"] == {"aws_instance.app"}


@pytest.mark.parametrize("key", ["for_each_expression", "count_expression"])
def test_module_call_for_each_makes_every_module_resource_a_dependent(key: str) -> None:
    configuration = {
        "root_module": {
            "resources": [_resource("aws_subnet.private")],
            "module_calls": {
                "app": {
                    key: {"references": ["aws_subnet.private"]},
                    "module": {"resources": [_resource("aws_instance.web")]},
                }
            },
        }
    }
    changes = [
        resource_change("aws_subnet.private", actions=("delete", "create"), before={}, after={}),
        resource_change('module.app["a"].aws_instance.web', actions=("create",), after={}),
    ]
    graph = parse(plan_text(*changes, configuration=configuration)).graph
    assert graph.dependents["aws_subnet.private"] == {'module.app["a"].aws_instance.web'}


def test_recorded_instances_narrow_only_where_the_plan_is_certain() -> None:
    # recorded from Terraform, which updates vm["a"] and attach[0] alone; but `nic[each.key]`
    # and `disk[count.index]` are listed as the whole resource, like `nic[var.peer[each.key]]`
    graph = parse((GOLDEN / "terraform-instances" / "plan.json").read_text(encoding="utf-8")).graph
    whole = {"terraform_data.after", "terraform_data.all"}
    vms = {f'terraform_data.vm["{key}"]' for key in "abc"}
    assert graph.dependents['terraform_data.nic["a"]'] == {*whole, *vms}
    assert graph.dependents['terraform_data.nic["b"]'] == {*whole, *vms, "terraform_data.pinned"}
    assert graph.dependents["terraform_data.disk[0]"] == {
        f"terraform_data.attach[{index}]" for index in range(3)
    }


def _instances(dependent: JsonValue, *addresses: str) -> dict[str, frozenset[str]]:
    configuration = {
        "root_module": {
            "resources": [_resource("aws_x.dep"), dependent],
            "module_calls": {
                "m": {"module": {"resources": [_resource("aws_x.dep"), dependent]}},
            },
        }
    }
    changes = [resource_change(address, actions=("create",), after={}) for address in addresses]
    return parse(plan_text(*changes, configuration=configuration)).graph.dependencies


KEYED = 'aws_x.use["a"]', 'aws_x.use["b"]', 'aws_x.dep["a"]', 'aws_x.dep["b"]'


BOTH = frozenset({'aws_x.dep["a"]', 'aws_x.dep["b"]'})


@pytest.mark.parametrize(
    "refs",
    [
        # dep[each.key] reads the same as dep[var.peer[each.key]] or "every dep but mine"
        ("aws_x.dep", "each.key"),
        ("aws_x.dep", "var.peer", "each.key"),
        ("aws_x.dep", "count.index"),
    ],
)
def test_an_index_computed_from_the_own_key_links_every_instance(refs: tuple[str, ...]) -> None:
    assert _instances(_resource("aws_x.use", *refs), *KEYED)['aws_x.use["a"]'] == BOTH


def test_for_each_over_a_resource_pairs_instances() -> None:
    dependent: JsonValue = {
        **_resource("aws_x.use"),
        "for_each_expression": {"references": ["aws_x.dep"]},
    }
    assert _instances(dependent, *KEYED)['aws_x.use["b"]'] == {'aws_x.dep["b"]'}


@pytest.mark.parametrize(
    "for_each",
    [
        # { for k, v in aws_x.dep : var.peer[k] => v }: keys moved
        {"references": ["aws_x.dep", "var.peer"]},
        {"references": ["aws_x.dep.id"]},
    ],
)
def test_for_each_built_from_a_resource_links_every_instance(for_each: JsonValue) -> None:
    dependent: JsonValue = {**_resource("aws_x.use"), "for_each_expression": for_each}
    assert _instances(dependent, *KEYED)['aws_x.use["b"]'] == BOTH


def test_for_each_keys_missing_on_the_dependency_link_every_instance() -> None:
    dependent: JsonValue = {
        **_resource("aws_x.use"),
        "for_each_expression": {"references": ["aws_x.dep"]},
    }
    addresses = 'aws_x.use["a"]', 'aws_x.dep["A"]', 'aws_x.dep["B"]'
    assert _instances(dependent, *addresses)['aws_x.use["a"]'] == {
        'aws_x.dep["A"]',
        'aws_x.dep["B"]',
    }


def test_count_over_a_resource_links_every_instance() -> None:
    dependent: JsonValue = {
        **_resource("aws_x.use"),
        "count_expression": {"references": ["aws_x.dep"]},
    }
    addresses = "aws_x.use[0]", "aws_x.dep[0]", "aws_x.dep[1]"
    assert _instances(dependent, *addresses)["aws_x.use[0]"] == {"aws_x.dep[0]", "aws_x.dep[1]"}


LITERAL = "aws_x.use", 'aws_x.dep["a"]', 'aws_x.dep["b"]', 'aws_x.dep["c"]'


@pytest.mark.parametrize(
    ("refs", "expected"),
    [
        # as Terraform 1.16 lists them: each traversal with its prefixes
        (('aws_x.dep["b"].id', 'aws_x.dep["b"]', "aws_x.dep"), {'aws_x.dep["b"]'}),
        (
            (
                'aws_x.dep["a"].id',
                'aws_x.dep["a"]',
                "aws_x.dep",
                'aws_x.dep["b"].id',
                'aws_x.dep["b"]',
                "aws_x.dep",
            ),
            {'aws_x.dep["a"]', 'aws_x.dep["b"]'},
        ),
        # [dep["b"].id, [for d in dep : d.id]]: the bare address once more, for the whole
        (
            ('aws_x.dep["b"].id', 'aws_x.dep["b"]', "aws_x.dep", "aws_x.dep"),
            {'aws_x.dep["a"]', 'aws_x.dep["b"]', 'aws_x.dep["c"]'},
        ),
    ],
)
def test_literal_indexes_name_their_instances(refs: tuple[str, ...], expected: set[str]) -> None:
    assert _instances(_resource("aws_x.use", *refs), *LITERAL)["aws_x.use"] == expected


def test_a_data_source_depends_on_every_instance_it_names() -> None:
    # Terraform defers the read when any instance of the resource changes
    dependent: JsonValue = {
        **_resource("data.aws_x.use", 'aws_x.dep["b"].id', 'aws_x.dep["b"]', "aws_x.dep"),
        "mode": "data",
    }
    addresses = "data.aws_x.use", 'aws_x.dep["a"]', 'aws_x.dep["b"]'
    changes = [
        resource_change(address, actions=("create",), after={}, mode=mode)
        for address, mode in zip(addresses, ("data", "managed", "managed"), strict=True)
    ]
    configuration = {"root_module": {"resources": [_resource("aws_x.dep"), dependent]}}
    graph = parse(plan_text(*changes, configuration=configuration)).graph
    assert graph.dependencies["data.aws_x.use"] == BOTH


def test_literal_index_with_no_such_instance_links_the_whole_resource() -> None:
    dependent = _resource("aws_x.use", 'aws_x.dep["gone"].id')
    addresses = "aws_x.use", 'aws_x.dep["a"]', 'aws_x.dep["b"]'
    assert _instances(dependent, *addresses)["aws_x.use"] == {'aws_x.dep["a"]', 'aws_x.dep["b"]'}


def test_reference_inside_a_module_stays_in_its_module_instance() -> None:
    dependent = _resource("aws_x.use", "aws_x.dep.id")
    addresses = [f'module.m["{key}"].aws_x.{name}' for key in "ab" for name in ("use", "dep")]
    assert _instances(dependent, "aws_x.dep", *addresses)['module.m["a"].aws_x.use'] == {
        'module.m["a"].aws_x.dep'
    }


def _module_chain(length: int) -> str:
    """root -> module.m0.o -> var.v -> module.m1.o -> ... -> aws_x.base"""
    calls = {
        f"m{i}": {
            "expressions": {
                "v": {"references": [f"module.m{i + 1}.o" if i + 1 < length else "aws_x.base"]}
            },
            "module": {"outputs": {"o": {"expression": {"references": ["var.v"]}}}},
        }
        for i in range(length)
    }
    configuration = {
        "root_module": {
            "resources": [_resource("aws_x.base"), _resource("aws_x.top", "module.m0.o")],
            "module_calls": calls,
        }
    }
    changes = [
        resource_change(f"aws_x.{name}", actions=("create",), after={}) for name in ("base", "top")
    ]
    return plan_text(*changes, configuration=configuration)


def test_long_module_chain_resolves() -> None:
    assert parse(_module_chain(40)).graph.dependents["aws_x.base"] == {"aws_x.top"}


def test_endless_module_chain_is_input_error() -> None:
    # each hop recurses: without a bound Python stops it with RecursionError, exit 4
    with pytest.raises(InputError, match="chained through more than"):
        parse(_module_chain(200))


def test_cycle_in_configuration_is_input_error() -> None:
    def node(name: str, ref: str) -> JsonValue:
        return {
            "address": f"aws_x.{name}",
            "mode": "managed",
            "type": "aws_x",
            "name": name,
            "expressions": {"v": {"references": [ref]}},
        }

    configuration = {"root_module": {"resources": [node("a", "aws_x.b"), node("b", "aws_x.a")]}}
    changes = [resource_change(f"aws_x.{name}", actions=("create",), after={}) for name in "ab"]
    with pytest.raises(InputError, match="dependency cycle"):
        parse(plan_text(*changes, configuration=configuration))


JSON = st.recursive(
    st.none() | st.booleans() | st.integers() | st.floats() | st.text(max_size=8),
    lambda inner: (
        st.lists(inner, max_size=4) | st.dictionaries(st.text(max_size=8), inner, max_size=4)
    ),
    max_leaves=30,
)
CHANGE = st.fixed_dictionaries(
    {},
    optional={
        "address": st.text(max_size=12) | JSON,
        "mode": st.sampled_from(["managed", "data"]) | JSON,
        "type": st.text(max_size=8),
        "name": st.text(max_size=8),
        "provider_name": st.text(max_size=8),
        "index": JSON,
        "change": st.fixed_dictionaries(
            {},
            optional={
                "actions": st.lists(
                    st.sampled_from(["create", "delete", "update", "no-op", "read"]), max_size=2
                )
                | JSON,
                "before": JSON,
                "after": JSON,
                "after_unknown": JSON,
                "before_sensitive": JSON,
                "after_sensitive": JSON,
                "replace_paths": JSON,
            },
        ),
    },
)
DOCUMENTS = st.fixed_dictionaries(
    {"format_version": st.sampled_from(["1.0", "1.2", "0.1", "x"]) | JSON},
    optional={"resource_changes": st.lists(CHANGE, max_size=3) | JSON, "configuration": JSON},
)


def assert_parses_or_rejects(text: str) -> None:
    """Any exception other than InputError escapes and fails the test."""
    with contextlib.suppress(InputError):
        parse(text)


@given(DOCUMENTS)
def test_fuzzed_structures_raise_only_input_error(document: JsonValue) -> None:
    assert_parses_or_rejects(json.dumps(document))


def assert_strict_json(text: str, schema: object = None) -> None:
    def refuse(constant: str) -> object:
        raise AssertionError(f"report holds {constant}, which is not JSON")

    loaded = json.loads(text, parse_constant=refuse)
    if schema is not None:
        validate(loaded, schema)


OBJECTS = st.none() | st.dictionaries(st.sampled_from(["password", "multi_az", "tags", "x"]), JSON)
MASKS = st.booleans() | OBJECTS
# a valid skeleton with random values and masks: most of these parse, so later steps get fuzzed
PLANS = st.fixed_dictionaries(
    {
        "format_version": st.just("1.2"),
        "resource_changes": st.lists(
            st.fixed_dictionaries(
                {
                    "address": st.sampled_from(["aws_db_instance.a", "aws_x.b", 'aws_x.c["k|<"]']),
                    "mode": st.just("managed"),
                    "type": st.sampled_from(["aws_db_instance", "aws_security_group"]),
                    "provider_name": st.just("aws"),
                    "change": st.fixed_dictionaries(
                        {
                            "actions": st.sampled_from(
                                [["update"], ["delete"], ["delete", "create"]]
                            ),
                            "before": OBJECTS,
                            "after": OBJECTS,
                            "after_unknown": MASKS,
                            "before_sensitive": MASKS,
                            "after_sensitive": MASKS,
                        }
                    ),
                },
                optional={"deposed": st.just("0a1b")},
            ),
            max_size=3,
        ),
    }
)


@given(DOCUMENTS | PLANS)
def test_a_parsed_plan_always_renders(document: JsonValue) -> None:
    # parse accepting a plan is a promise that every later step copes with it
    try:
        plan = parse(json.dumps(document))
    except InputError:
        return
    event("parsed")
    report = analyze(plan, Settings())
    terminal.render(Console(file=io.StringIO(), width=100), report)
    markdown.render(report)
    assert_strict_json(document_report.render(report), REPORT_SCHEMA)
    assert_strict_json(sarif.render(report, "plan.json"))


@given(st.text(max_size=200) | st.binary(max_size=200).map(lambda raw: raw.decode("latin-1")))
def test_fuzzed_text_raises_only_input_error(text: str) -> None:
    assert_parses_or_rejects(text)


def test_pathological_nesting_is_input_error() -> None:
    with pytest.raises(InputError):
        parse("[" * 100_000 + "]" * 100_000)


def test_reading_locals_is_a_warning() -> None:
    configuration = {
        "root_module": {
            "resources": [
                _resource("aws_x.a", "local.ids"),
                _resource("aws_x.b", "aws_x.a.id"),
                _resource("aws_x.c", "local.name"),
            ],
            "module_calls": {
                "m": {
                    "expressions": {"v": {"references": ["local.v"]}},
                    "module": {"resources": [_resource("aws_x.d", "local.d")]},
                }
            },
        }
    }
    changes = [resource_change(f"aws_x.{name}", actions=("create",), after={}) for name in "abc"]
    plan = parse(plan_text(*changes, configuration=configuration))
    assert plan.warnings == (
        "4 resource(s) or module call(s) read locals (aws_x.a, aws_x.c, module.m and 1 more): the "
        "plan JSON does not say what a local refers to, so dependencies through them are missing "
        "and blast radius may be low",
    )


def test_no_locals_no_warning() -> None:
    configuration = {"root_module": {"resources": [_resource("aws_x.a", "var.v")]}}
    raw = resource_change("aws_x.a", actions=("create",), after={})
    assert parse(plan_text(raw, configuration=configuration)).warnings == ()


@pytest.mark.parametrize(
    ("providers", "tool"),
    [
        (["registry.opentofu.org/hashicorp/aws"], "OpenTofu"),
        (["registry.terraform.io/hashicorp/aws"], "Terraform"),
        # registry.opentofu.org shows up by default only under tofu; an explicit source fools it
        (
            ["registry.terraform.io/hashicorp/aws", "registry.opentofu.org/hashicorp/aws"],
            "OpenTofu",
        ),
        (["terraform.io/builtin/terraform"], None),
        ([], None),
    ],
    ids=["opentofu", "terraform", "mixed", "builtin", "empty"],
)
def test_the_provider_registry_tells_the_tool(providers: list[str], tool: str | None) -> None:
    changes = [
        {**resource_change(f"aws_instance.n{index}"), "provider_name": provider}
        for index, provider in enumerate(providers)
    ]
    assert parse(plan_text(*changes)).tool == tool


def test_recorded_opentofu_plan_parses_like_terraform() -> None:
    tofu = parse((GOLDEN / "opentofu-1.13" / "plan.json").read_text(encoding="utf-8"))
    terraform = parse((GOLDEN / "terraform-1.17" / "plan.json").read_text(encoding="utf-8"))
    assert tofu.terraform_version == "1.13.10"
    assert [change.address for change in tofu.changes] == [
        change.address for change in terraform.changes
    ]
    assert [change.action for change in tofu.changes] == [
        change.action for change in terraform.changes
    ]
