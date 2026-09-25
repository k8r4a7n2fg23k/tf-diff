"""Write plan.json: one resource per rule branch, so golden output pins every title and reason.

Run from the repo root: uv run python scripts/catalogue_plan.py
then UPDATE_GOLDEN=1 uv run pytest tests/golden
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / "tests"))

from factories import Raw, plan_text, resource_change  # noqa: E402  - after the sys.path line

PROD = {"tags": {"Environment": "production"}}
STAGING = {"tags_all": {"env": "staging"}}


def update(
    address: str,
    before: dict[str, object],
    after: dict[str, object],
    after_unknown: dict[str, object] | None = None,
) -> Raw:
    return resource_change(address, before=before, after=after, after_unknown=after_unknown)


SUBNETS = 12
changes = [
    # s3-public-access-weakened
    update(
        "aws_s3_bucket_public_access_block.flag_off",
        {"block_public_acls": True, "block_public_policy": True},
        {"block_public_acls": False, "block_public_policy": True},
    ),
    resource_change(
        "aws_s3_bucket_public_access_block.removed",
        actions=("delete",),
        before={"block_public_acls": True},
    ),
    update(
        "aws_s3_account_public_access_block.pending",
        {"restrict_public_buckets": True, "ignore_public_acls": True},
        {"ignore_public_acls": True},
        after_unknown={"restrict_public_buckets": True},
    ),
    # encryption-disabled
    update(
        "aws_ebs_volume.plain",
        {"a_size": 10, "encrypted": True, **PROD},
        {"a_size": 20, "encrypted": False, **PROD},
    ),
    update(
        "aws_efs_file_system.pending",
        {"encrypted": True},
        {},
        after_unknown={"encrypted": True},
    ),
    # backup-disabled
    update(
        "aws_db_instance.no_backups",
        {"backup_retention_period": 7},
        {"backup_retention_period": 0},
    ),
    update(
        "aws_rds_cluster.no_snapshot",
        {"skip_final_snapshot": False},
        {"skip_final_snapshot": True},
    ),
    update(
        "aws_dynamodb_table.no_pitr",
        {"point_in_time_recovery": [{"enabled": True}]},
        {"point_in_time_recovery": [{"enabled": False}]},
    ),
    update(
        "aws_db_instance.pending_backups",
        {"backup_retention_period": 7},
        {},
        after_unknown={"backup_retention_period": True},
    ),
    # reduce-capacity
    update(
        "aws_ecs_service.shrink",
        {"desired_count": 10, **STAGING},
        {"desired_count": 3, **STAGING},
    ),
    update(
        "aws_autoscaling_group.pending_size",
        {"min_size": 4},
        {},
        after_unknown={"min_size": True},
    ),
    # remove-redundancy
    update(
        "aws_autoscaling_group.one_zone",
        {"availability_zones": ["a", "b", "c"]},
        {"availability_zones": ["a"]},
    ),
    update("aws_db_instance.single_az", {"multi_az": True}, {"multi_az": False}),
    update(
        "aws_eks_node_group.pending_subnets",
        {"subnet_ids": ["subnet-1", "subnet-2"]},
        {},
        after_unknown={"subnet_ids": True},
    ),
    # security-group-wide-open
    update(
        "aws_security_group.web",
        {"ingress": []},
        {
            "ingress": [
                {"protocol": "tcp", "from_port": 22, "to_port": 22, "cidr_blocks": ["0.0.0.0/0"]},
                {
                    "protocol": "tcp",
                    "from_port": 8080,
                    "to_port": 8080,
                    "cidr_blocks": [],
                    "ipv6_cidr_blocks": ["::/0"],
                },
            ]
        },
    ),
    resource_change(
        "aws_security_group_rule.everything",
        actions=("create",),
        after={
            "type": "ingress",
            "protocol": "-1",
            "from_port": 0,
            "to_port": 0,
            "cidr_blocks": ["0.0.0.0/0"],
        },
    ),
    resource_change(
        "aws_vpc_security_group_ingress_rule.postgres",
        actions=("create",),
        after={"ip_protocol": "tcp", "from_port": 5432, "to_port": 5432, "cidr_ipv4": "0.0.0.0/0"},
    ),
    resource_change(
        "aws_security_group_rule.pending_protocol",
        actions=("create",),
        after={"type": "ingress", "from_port": 22, "to_port": 22, "cidr_blocks": ["0.0.0.0/0"]},
        after_unknown={"protocol": True},
    ),
    update(
        "aws_security_group.pending_cidr",
        {"ingress": []},
        {"ingress": [{"protocol": "tcp", "from_port": 3389, "to_port": 3389}]},
        after_unknown={"ingress": [{"cidr_blocks": True}]},
    ),
    resource_change(
        "aws_security_group_rule.egress",
        actions=("create",),
        after={
            "type": "egress",
            "protocol": "-1",
            "from_port": 0,
            "to_port": 0,
            "cidr_blocks": ["0.0.0.0/0"],
        },
    ),
    # public-database
    update(
        "aws_db_instance.exposed", {"publicly_accessible": False}, {"publicly_accessible": True}
    ),
    update(
        "aws_rds_cluster_instance.pending_exposure",
        {"publicly_accessible": False},
        {},
        after_unknown={"publicly_accessible": True},
    ),
    # replace-resource, stateful-data-loss, sensitive-value-changed
    resource_change(
        "aws_instance.requested",
        actions=("create", "delete"),
        before={"ami": "ami-1"},
        after={"ami": "ami-1"},
        reason="replace_by_request",
    ),
    resource_change(
        "aws_instance.unexplained",
        actions=("delete", "create"),
        before={"ami": "ami-1"},
        after={"ami": "ami-1"},
    ),
    resource_change(
        "aws_db_instance.engine_swap",
        actions=("delete", "create"),
        before={"api_token": "CANARY-a", "engine": "mysql", "password": "CANARY-old", **PROD},
        after={"api_token": "CANARY-b", "engine": "postgres", "password": "CANARY-new", **PROD},
        replace_paths=[["engine"], ["storage", "type"]],
        reason="replace_because_cannot_update",
    ),
    resource_change(
        "aws_ebs_volume.data",
        actions=("delete", "create"),
        before={"size": 100},
        after={"size": 50},
        replace_paths=[["size"]],
    ),
    # destroy-production-resource, including the deposed cleanup that must stay silent
    resource_change(
        "aws_s3_bucket.archive",
        actions=("delete",),
        before={"bucket": "archive.example.com", **PROD},
        reason="delete_because_no_resource_config",
    ),
    resource_change(
        "aws_s3_bucket.archive",
        actions=("delete",),
        before={"bucket": "archive.example.com", **PROD},
        deposed="0a1b2c3d",
    ),
    resource_change("aws_instance.forgotten", actions=("forget",), before={"ami": "ami-1"}),
    # many plain attribute changes: the why line cuts the list
    update(
        "aws_lb.busy",
        {f"setting_{i}": i for i in range(7)},
        {f"setting_{i}": i + 1 for i in range(7)},
    ),
    # exactly as many changes as the why line lists: no "and N more"
    update(
        "aws_lb.five",
        {f"setting_{i}": i for i in range(5)},
        {f"setting_{i}": i + 1 for i in range(5)},
    ),
    resource_change(
        "aws_s3_bucket.unexplained_delete",
        actions=("delete",),
        before={"bucket": "tmp.example.com", **PROD},
    ),
    resource_change(
        "aws_dynamodb_table.tainted",
        actions=("delete", "create"),
        before={"name": "orders"},
        after={"name": "orders"},
        reason="replace_because_tainted",
    ),
    resource_change(
        "aws_instance.novel",
        actions=("delete", "create"),
        before={"ami": "ami-1"},
        after={"ami": "ami-1"},
        reason="replace_because_of_a_future_terraform_reason",
    ),
    resource_change(
        "aws_security_group_rule.pending_port",
        actions=("create",),
        after={"type": "ingress", "protocol": "tcp", "from_port": 22, "cidr_blocks": ["0.0.0.0/0"]},
        after_unknown={"to_port": True},
    ),
    update(
        "aws_security_group.mixed_sources",
        {"ingress": []},
        {
            "ingress": [
                {"protocol": "tcp", "from_port": 22, "to_port": 22, "ipv6_cidr_blocks": ["::/0"]}
            ]
        },
        after_unknown={"ingress": [{"cidr_blocks": True}]},
    ),
    # several capacity attributes: skipped ones must not stop the scan, and the score takes the
    # lowest confidence among the top findings
    update(
        "aws_autoscaling_group.mixed_capacity",
        {"a": 1, "desired_capacity": 4, "desired_count": 5, "min_size": 10},
        {"a": 2, "min_size": 2},
        after_unknown={"desired_capacity": True},
    ),
    update(
        "aws_autoscaling_group.second_list",
        {"availability_zones": ["a"], "subnet_ids": ["s1", "s2"]},
        {"availability_zones": ["a"], "subnet_ids": ["s1"]},
    ),
    update(
        "aws_eks_node_group.unknown_then_drop",
        {"availability_zones": ["a", "b"], "subnet_ids": ["s1", "s2"]},
        {"subnet_ids": ["s1"]},
        after_unknown={"availability_zones": True},
    ),
    update(
        "aws_db_instance.pending_az",
        {"multi_az": True},
        {},
        after_unknown={"multi_az": True},
    ),
    # computed attributes go unknown on every replace: the configuration does not set them, so
    # no rule may read anything into it
    resource_change(
        "aws_lb.computed_subnets",
        actions=("delete", "create"),
        before={"name": "old", "subnets": ["s1", "s2"], "multi_az": True},
        after={"name": "new"},
        after_unknown={"subnets": True, "multi_az": True},
        replace_paths=[["name"]],
    ),
    # wide-blast-radius: replaced vpc with more dependents than the list shows
    resource_change(
        "aws_vpc.main",
        actions=("delete", "create"),
        before={"cidr_block": "10.0.0.0/16"},
        after={"cidr_block": "10.1.0.0/16"},
        replace_paths=[["cidr_block"]],
    ),
    *(
        resource_change(f"aws_subnet.part[{i}]", actions=("create",), after={"index": i})
        for i in range(SUBNETS)
    ),
]

configuration = {
    "root_module": {
        "resources": [
            {"address": "aws_vpc.main", "mode": "managed", "type": "aws_vpc", "name": "main"},
            {
                "address": "aws_lb.computed_subnets",
                "mode": "managed",
                "type": "aws_lb",
                "name": "computed_subnets",
                "expressions": {"name": {"constant_value": "new"}},
            },
            {
                "address": "aws_subnet.part",
                "mode": "managed",
                "type": "aws_subnet",
                "name": "part",
                "expressions": {"vpc_id": {"references": ["aws_vpc.main.id", "aws_vpc.main"]}},
            },
        ]
    }
}

target = ROOT / "tests" / "golden" / "rule-catalogue" / "plan.json"
document = json.loads(plan_text(*changes, configuration=configuration))
target.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
sys.stdout.write(f"wrote {target} with {len(changes)} resource changes\n")
