"""Properties every rule must hold, run against the whole registry."""

from random import Random

import pytest
from hypothesis import given
from hypothesis import strategies as st

from factories import context, resource_change
from tfdiff.rules.registry import RULES
from tfdiff.rules.rule import Rule

# attribute names the rules key on
NAMES = st.sampled_from(
    [
        "availability_zones",
        "backup_retention_period",
        "block_public_acls",
        "cidr_blocks",
        "desired_count",
        "encrypted",
        "from_port",
        "ingress",
        "multi_az",
        "password",
        "protocol",
        "publicly_accessible",
        "tags",
        "to_port",
    ]
)
LEAVES = st.one_of(
    st.none(),
    st.booleans(),
    st.integers(-5, 70000),
    st.sampled_from(["0.0.0.0/0", "tcp", "-1", "true", "10"]),
)
TREES = st.dictionaries(
    NAMES,
    st.recursive(
        LEAVES,
        lambda inner: st.lists(inner, max_size=3) | st.dictionaries(NAMES, inner, max_size=3),
        max_leaves=8,
    ),
    max_size=6,
)
TYPES = st.sampled_from(
    [
        "aws_autoscaling_group",
        "aws_db_instance",
        "aws_dynamodb_table",
        "aws_rds_cluster",
        "aws_s3_account_public_access_block",
        "aws_s3_bucket_public_access_block",
        "aws_security_group",
        "aws_security_group_rule",
        "aws_vpc_security_group_ingress_rule",
    ]
)
# these judge the action alone (delete, replace): an update with equal sides never reaches them
ATTRIBUTE_RULES = [
    rule
    for rule in RULES
    if rule.id
    not in {
        "destroy-production-resource",
        "replace-resource",
        "stateful-data-loss",
        "wide-blast-radius",
    }
]


@pytest.mark.parametrize("rule", ATTRIBUTE_RULES, ids=[rule.id for rule in ATTRIBUTE_RULES])
@given(tree=TREES, kind=TYPES)
def test_unchanged_resource_yields_nothing(rule: Rule, tree: dict[str, object], kind: str) -> None:
    raw = resource_change(f"{kind}.main", before=tree, after=tree)
    assert list(rule.evaluate(context(raw, environment="production"))) == []


ZONES = ["us-east-1a", "us-east-1b", "us-east-1c"]
INGRESS = st.fixed_dictionaries(
    {
        "from_port": st.sampled_from([22, 443, 8080]),
        "to_port": st.sampled_from([22, 443, 8080]),
        "protocol": st.sampled_from(["tcp", "-1"]),
        "cidr_blocks": st.lists(st.sampled_from(["0.0.0.0/0", "10.0.0.0/8"]), max_size=2),
    }
)
# attributes Terraform plans as sets or as lists whose order means nothing to the rules
UNORDERED = st.fixed_dictionaries(
    {
        "availability_zones": st.lists(st.sampled_from(ZONES), unique=True, max_size=3),
        "subnet_ids": st.lists(st.sampled_from(["s-1", "s-2", "s-3"]), unique=True, max_size=3),
        "ingress": st.lists(INGRESS, max_size=3),
    }
)


def _shuffled(node: object, shuffler: Random) -> object:
    if isinstance(node, list):
        return shuffler.sample([_shuffled(item, shuffler) for item in node], len(node))
    if isinstance(node, dict):
        return {key: _shuffled(value, shuffler) for key, value in node.items()}
    return node


@pytest.mark.parametrize("rule", ATTRIBUTE_RULES, ids=[rule.id for rule in ATTRIBUTE_RULES])
@given(tree=UNORDERED, kind=TYPES, shuffler=st.randoms())
def test_reordered_elements_yield_nothing(
    rule: Rule, tree: dict[str, object], kind: str, shuffler: Random
) -> None:
    raw = resource_change(
        f"{kind}.main", actions=("update",), before=tree, after=_shuffled(tree, shuffler)
    )
    assert list(rule.evaluate(context(raw, environment="production"))) == []
