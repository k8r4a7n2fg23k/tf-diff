# Rules

Rules version 1 (`tf-diff version`). Any change to a rule's logic or severity bumps it.

Each finding has the action, environment, direct/indirect dependents, rule-specific evidence and
a confidence. Confidence is `low` when the deciding value is unknown until apply *and* the config
sets that attribute. Computed attributes the config doesn't set (provider defaults, echoes like
`output`) go unknown on every replace, so they don't produce findings at all.

By default `check` only fails on high confidence: an unknown value is worth a look, not a blocked
merge. `--fail-on-confidence low` changes that. Severities and on/off are per rule in
`.tf-diff.yaml`.

## Environment

Production is `production`, `prod` or `prd`, any case. The environment comes from
`--environment`, then `TF_DIFF_ENVIRONMENT`, then the config file; blank counts as unset. If none
is set, the `Environment` / `env` tag of each resource decides:

- `tags_all` first, since it includes the provider's `default_tags`.
- Tags before and after the change both count, production wins. Replacing a prod database with
  one tagged staging still destroys a prod database.
- `Environment` and `env` disagree on a resource: production wins, otherwise `Environment`, and
  the report warns.
- Untagged resources (ASGs, SG rules) get the environment all tagged resources share; `prod` and
  `production` are the same here. Data source tags are skipped, they often point at shared infra.
- Tags disagree or nothing is tagged: untagged resources get no environment and the report warns
  that prod-only checks are off.

## Generic

| Id | Severity | Fires when |
|---|---|---|
| `destroy-production-resource` | critical | A managed resource is deleted in production. Deposed-object cleanup (create_before_destroy) does not count. |
| `replace-resource` | medium in production, low elsewhere | A resource is replaced. Evidence: forcing attributes, and whether the old object goes before or after the new one exists. |
| `reduce-capacity` | high | A capacity attribute (`desired_count`, `desired_capacity`, `min_size`, `replicas`, `node_count`, ...) drops by `threshold` percent or more. Default 30. Unknown after apply: low confidence. |
| `remove-redundancy` | high | A zone or subnet list (`availability_zones`, `subnet_ids`, `subnets`, `vpc_zone_identifier`, `zones`) goes from 2+ entries to 1 or none, or `multi_az` turns off. An update or replace only: deleting the resource is not lost redundancy. Unknown or newly redacted list, or unknown `multi_az`: low confidence. |
| `encryption-disabled` | critical | An encryption flag goes from true to false: `encrypted`, `storage_encrypted`, `kms_encrypted`, `encryption_enabled`, `enable_encryption`, `at_rest_encryption_enabled`, `transit_encryption_enabled`, or `enabled` inside `server_side_encryption`, `encrypt_at_rest` or `node_to_node_encryption`. Unknown after apply: low confidence. |
| `wide-blast-radius` | medium | A deleted or replaced resource has `threshold` or more dependents, direct and indirect. Default 5. |
| `sensitive-value-changed` | info | A sensitive attribute the configuration sets changes. Only the path is reported, never the value. Unknown after apply: low confidence. |

## AWS

| Id | Severity | Types | Fires when |
|---|---|---|---|
| `stateful-data-loss` | critical in production, high elsewhere; high / medium when a guard keeps the data | `aws_db_instance`, `aws_rds_cluster`, `aws_ebs_volume`, `aws_efs_file_system`, `aws_dynamodb_table`, `aws_s3_bucket`, `aws_elasticache_cluster`, `aws_elasticache_replication_group`, `aws_elasticache_serverless_cache`, `aws_docdb_cluster`, `aws_neptune_cluster`, `aws_redshift_cluster`, `aws_opensearch_domain`, `aws_kinesis_stream` | A data store is deleted or replaced, in any environment. Read replicas (`replicate_source_db`, `replication_source_identifier`) and memcached keep no data of their own and are skipped; Redis and Valkey are not. One step lower when the old state shows a guard: `skip_final_snapshot = false` (RDS, DocumentDB, Neptune, Redshift: a final snapshot with `final_snapshot_identifier`, a failed delete without it), `final_snapshot_identifier` (ElastiCache), `deletion_protection` (RDS, DocumentDB, Neptune), `deletion_protection_enabled` (DynamoDB), `force_destroy = false` (S3, refused while the bucket holds objects). Cleanup of a deposed object does not count. |
| `public-database` | critical | `aws_db_instance`, `aws_rds_cluster_instance` | `publicly_accessible` becomes true (update or create). Unknown: low confidence. |
| `backup-disabled` | high | `aws_db_instance`, `aws_rds_cluster`, `aws_docdb_cluster`, `aws_neptune_cluster`, `aws_dynamodb_table` | `backup_retention_period` drops to 0, `skip_final_snapshot` turns on, or DynamoDB point-in-time recovery turns off. Unknown after apply: low confidence. |
| `security-group-wide-open` | critical on all traffic or admin/database ports (22, 3389, 3306, 5432, 6379, ...), high otherwise | `aws_security_group`, `aws_security_group_rule`, `aws_vpc_security_group_ingress_rule` | An ingress rule newly open to `0.0.0.0/0` or `::/0`. Single ports 80 and 443 and ICMP are not reported. Unknown ports, protocol, source, rule direction or whole `ingress` list: low confidence. |
| `s3-public-access-weakened` | high | `aws_s3_bucket_public_access_block`, `aws_s3_account_public_access_block` | A public access guard turns off, or the block is deleted (not deposed-object cleanup). Unknown guard: low confidence. |

## Risk score

Per resource with findings, 0-100. The weights max out at exactly 100, so nothing gets clipped.

| Factor | Points |
|---|---|
| Highest finding: critical / high / medium / low / info | 60 / 40 / 25 / 10 / 0 |
| Action is delete or replace | +15 |
| Production | +10 |
| Dependents | +3 each, at most +15 |

It's a review order, not a probability. Its confidence is the lowest among the top-severity
findings. The report prints the factors, so you can check the sum.
