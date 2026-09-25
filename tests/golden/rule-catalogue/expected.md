<!-- tf-diff:report -->
## Terraform Risk Summary

**Environment:** not set · **Resources:** 54 inspected, 54 changed, 0 ignored
**Changes:** 17 create, 24 update, 4 delete, 8 replace, 1 forget

> warning: resources are tagged for different environments (production, staging): untagged ones get none, set --environment

| Severity | Findings |
|---|---|
| critical | 16 |
| high | 21 |
| medium | 2 |
| low | 7 |
| info | 1 |

### Findings

| Severity | Resource | Finding | Confidence |
|---|---|---|---|
| **CRITICAL** | `aws_db_instance.engine_swap` | Data store replaced (`stateful-data-loss`) | high |
| **CRITICAL** | `aws_db_instance.exposed` | Database becomes publicly accessible (`public-database`) | high |
| **CRITICAL** | `aws_ebs_volume.plain` | Encryption disabled (`encryption-disabled`) | high |
| **CRITICAL** | `aws_efs_file_system.pending` | Encryption may be disabled (`encryption-disabled`) | low |
| **CRITICAL** | `aws_rds_cluster_instance.pending_exposure` | Database may become public (`public-database`) | low |
| **CRITICAL** | `aws_s3_bucket.archive` | Production resource destroyed (`destroy-production-resource`) | high |
| **CRITICAL** | `aws_s3_bucket.archive` | Data store deleted (`stateful-data-loss`) | high |
| **CRITICAL** | `aws_s3_bucket.unexplained_delete` | Production resource destroyed (`destroy-production-resource`) | high |
| **CRITICAL** | `aws_s3_bucket.unexplained_delete` | Data store deleted (`stateful-data-loss`) | high |
| **CRITICAL** | `aws_security_group.mixed_sources` | Ingress opened to the internet (`security-group-wide-open`) | high |
| **CRITICAL** | `aws_security_group.mixed_sources` | Ingress may open to the internet (`security-group-wide-open`) | low |
| **CRITICAL** | `aws_security_group.pending_cidr` | Ingress may open to the internet (`security-group-wide-open`) | low |
| **CRITICAL** | `aws_security_group.web` | Ingress opened to the internet (`security-group-wide-open`) | high |
| **CRITICAL** | `aws_security_group_rule.everything` | Ingress opened to the internet (`security-group-wide-open`) | high |
| **CRITICAL** | `aws_security_group_rule.pending_protocol` | Ingress may open to the internet (`security-group-wide-open`) | low |
| **CRITICAL** | `aws_vpc_security_group_ingress_rule.postgres` | Ingress opened to the internet (`security-group-wide-open`) | high |
| **HIGH** | `aws_autoscaling_group.mixed_capacity` | Capacity may drop (`reduce-capacity`) | low |
| **HIGH** | `aws_autoscaling_group.mixed_capacity` | Capacity reduced (`reduce-capacity`) | high |
| **HIGH** | `aws_autoscaling_group.one_zone` | Redundancy removed (`remove-redundancy`) | high |
| **HIGH** | `aws_autoscaling_group.pending_size` | Capacity may drop (`reduce-capacity`) | low |
| **HIGH** | `aws_autoscaling_group.second_list` | Redundancy removed (`remove-redundancy`) | high |
| **HIGH** | `aws_db_instance.no_backups` | Backups disabled (`backup-disabled`) | high |
| **HIGH** | `aws_db_instance.pending_az` | Multi-AZ may be disabled (`remove-redundancy`) | low |
| **HIGH** | `aws_db_instance.pending_backups` | Backups may be disabled (`backup-disabled`) | low |
| **HIGH** | `aws_db_instance.single_az` | Multi-AZ disabled (`remove-redundancy`) | high |
| **HIGH** | `aws_dynamodb_table.no_pitr` | Backups disabled (`backup-disabled`) | high |
| **HIGH** | `aws_dynamodb_table.tainted` | Data store replaced (`stateful-data-loss`) | high |
| **HIGH** | `aws_ebs_volume.data` | Data store replaced (`stateful-data-loss`) | high |
| **HIGH** | `aws_ecs_service.shrink` | Capacity reduced (`reduce-capacity`) | high |
| **HIGH** | `aws_eks_node_group.pending_subnets` | Redundancy may drop (`remove-redundancy`) | low |
| **HIGH** | `aws_eks_node_group.unknown_then_drop` | Redundancy may drop (`remove-redundancy`) | low |
| **HIGH** | `aws_eks_node_group.unknown_then_drop` | Redundancy removed (`remove-redundancy`) | high |
| **HIGH** | `aws_rds_cluster.no_snapshot` | Backups disabled (`backup-disabled`) | high |
| **HIGH** | `aws_s3_account_public_access_block.pending` | S3 public access block may weaken (`s3-public-access-weakened`) | low |
| **HIGH** | `aws_s3_bucket_public_access_block.flag_off` | S3 public access block weakened (`s3-public-access-weakened`) | high |
| **HIGH** | `aws_s3_bucket_public_access_block.removed` | S3 public access block removed (`s3-public-access-weakened`) | high |
| **HIGH** | `aws_security_group_rule.pending_port` | Ingress may open to the internet (`security-group-wide-open`) | low |
| **MEDIUM** | `aws_db_instance.engine_swap` | Resource replaced (`replace-resource`) | high |
| **MEDIUM** | `aws_vpc.main` | Wide blast radius (`wide-blast-radius`) | high |
| **LOW** | `aws_dynamodb_table.tainted` | Resource replaced (`replace-resource`) | high |
| **LOW** | `aws_ebs_volume.data` | Resource replaced (`replace-resource`) | high |
| **LOW** | `aws_instance.novel` | Resource replaced (`replace-resource`) | high |
| **LOW** | `aws_instance.requested` | Resource replaced (`replace-resource`) | high |
| **LOW** | `aws_instance.unexplained` | Resource replaced (`replace-resource`) | high |
| **LOW** | `aws_lb.computed_subnets` | Resource replaced (`replace-resource`) | high |
| **LOW** | `aws_vpc.main` | Resource replaced (`replace-resource`) | high |
| **INFO** | `aws_db_instance.engine_swap` | Sensitive value changes (`sensitive-value-changed`) | high |

<details><summary><code>aws_autoscaling_group.mixed_capacity</code>: update, score 40/100</summary>

- why: 3 attribute(s) change: a, desired\_count, min\_size
- why: 1 attribute(s) known only after apply
- score factors: +40 high finding (reduce-capacity)

**Capacity may drop** (`reduce-capacity`): desired\_capacity is unknown until apply
- action: UPDATE
- environment: not set
- dependents: 0 direct, 0 indirect
- desired\_capacity: 4 -&gt; (known after apply)

**Capacity reduced** (`reduce-capacity`): min\_size drops by 80% (threshold 30%)
- action: UPDATE
- environment: not set
- dependents: 0 direct, 0 indirect
- min\_size: 10 -&gt; 2

</details>

<details><summary><code>aws_autoscaling_group.one_zone</code>: update, score 40/100</summary>

- why: 2 attribute(s) change: availability\_zones\[1\], availability\_zones\[2\]
- score factors: +40 high finding (remove-redundancy)

**Redundancy removed** (`remove-redundancy`): availability\_zones drops from 3 entries to 1
- action: UPDATE
- environment: not set
- dependents: 0 direct, 0 indirect
- availability\_zones: 3 -&gt; 1

</details>

<details><summary><code>aws_autoscaling_group.pending_size</code>: update, score 40/100</summary>

- why: 1 attribute(s) known only after apply
- score factors: +40 high finding (reduce-capacity)

**Capacity may drop** (`reduce-capacity`): min\_size is unknown until apply
- action: UPDATE
- environment: not set
- dependents: 0 direct, 0 indirect
- min\_size: 4 -&gt; (known after apply)

</details>

<details><summary><code>aws_autoscaling_group.second_list</code>: update, score 40/100</summary>

- why: 1 attribute(s) change: subnet\_ids\[1\]
- score factors: +40 high finding (remove-redundancy)

**Redundancy removed** (`remove-redundancy`): subnet\_ids drops from 2 entries to 1
- action: UPDATE
- environment: not set
- dependents: 0 direct, 0 indirect
- subnet\_ids: 2 -&gt; 1

</details>

<details><summary><code>aws_db_instance.engine_swap</code>: replace, score 85/100</summary>

- why: the provider cannot update it in place
- why: engine, storage.type forces replacement
- why: 2 attribute(s) change: api\_token, password
- score factors: +60 critical finding (stateful-data-loss); +15 replace: the old object is destroyed; +10 production

**Data store replaced** (`stateful-data-loss`): aws\_db\_instance holds data; engine, storage.type forces a new one, existing data is lost
- action: REPLACE (delete, create)
- environment: production
- dependents: 0 direct, 0 indirect
- engine: "mysql" -&gt; "postgres"

**Resource replaced** (`replace-resource`): engine, storage.type cannot be updated in place
- action: REPLACE (delete, create)
- environment: production
- dependents: 0 direct, 0 indirect
- order: destroy before create: unavailable until the new one is up
- engine: "mysql" -&gt; "postgres"

**Sensitive value changes** (`sensitive-value-changed`): a secret or credential changes; dependents must pick up the new value
- action: REPLACE (delete, create)
- environment: production
- dependents: 0 direct, 0 indirect
- paths: api\_token, password

</details>

<details><summary><code>aws_db_instance.exposed</code>: update, score 60/100</summary>

- why: 1 attribute(s) change: publicly\_accessible
- score factors: +60 critical finding (public-database)

**Database becomes publicly accessible** (`public-database`): publicly\_accessible turns on: the endpoint resolves to a public IP
- action: UPDATE
- environment: not set
- dependents: 0 direct, 0 indirect
- publicly\_accessible: false -&gt; true

</details>

<details><summary><code>aws_db_instance.no_backups</code>: update, score 40/100</summary>

- why: 1 attribute(s) change: backup\_retention\_period
- score factors: +40 high finding (backup-disabled)

**Backups disabled** (`backup-disabled`): backup\_retention\_period removes the way back after data loss
- action: UPDATE
- environment: not set
- dependents: 0 direct, 0 indirect
- backup\_retention\_period: 7 -&gt; 0

</details>

<details><summary><code>aws_db_instance.pending_az</code>: update, score 40/100</summary>

- why: 1 attribute(s) known only after apply
- score factors: +40 high finding (remove-redundancy)

**Multi-AZ may be disabled** (`remove-redundancy`): multi\_az is unknown until apply
- action: UPDATE
- environment: not set
- dependents: 0 direct, 0 indirect
- multi\_az: true -&gt; (known after apply)

</details>

<details><summary><code>aws_db_instance.pending_backups</code>: update, score 40/100</summary>

- why: 1 attribute(s) known only after apply
- score factors: +40 high finding (backup-disabled)

**Backups may be disabled** (`backup-disabled`): backup\_retention\_period is unknown until apply
- action: UPDATE
- environment: not set
- dependents: 0 direct, 0 indirect
- backup\_retention\_period: 7 -&gt; (known after apply)

</details>

<details><summary><code>aws_db_instance.single_az</code>: update, score 40/100</summary>

- why: 1 attribute(s) change: multi\_az
- score factors: +40 high finding (remove-redundancy)

**Multi-AZ disabled** (`remove-redundancy`): multi\_az turns off
- action: UPDATE
- environment: not set
- dependents: 0 direct, 0 indirect
- multi\_az: true -&gt; false

</details>

<details><summary><code>aws_dynamodb_table.no_pitr</code>: update, score 40/100</summary>

- why: 1 attribute(s) change: point\_in\_time\_recovery\[0\].enabled
- score factors: +40 high finding (backup-disabled)

**Backups disabled** (`backup-disabled`): point\_in\_time\_recovery\[0\].enabled removes the way back after data loss
- action: UPDATE
- environment: not set
- dependents: 0 direct, 0 indirect
- point\_in\_time\_recovery\[0\].enabled: true -&gt; false

</details>

<details><summary><code>aws_dynamodb_table.tainted</code>: replace, score 55/100</summary>

- why: the resource is tainted
- score factors: +40 high finding (stateful-data-loss); +15 replace: the old object is destroyed

**Data store replaced** (`stateful-data-loss`): aws\_dynamodb\_table holds data; Terraform plans a new one, existing data is lost
- action: REPLACE (delete, create)
- environment: not set
- dependents: 0 direct, 0 indirect

**Resource replaced** (`replace-resource`): Terraform plans replacement (replace\_because\_tainted)
- action: REPLACE (delete, create)
- environment: not set
- dependents: 0 direct, 0 indirect
- order: destroy before create: unavailable until the new one is up

</details>

<details><summary><code>aws_ebs_volume.data</code>: replace, score 55/100</summary>

- why: size forces replacement
- score factors: +40 high finding (stateful-data-loss); +15 replace: the old object is destroyed

**Data store replaced** (`stateful-data-loss`): aws\_ebs\_volume holds data; size forces a new one, existing data is lost
- action: REPLACE (delete, create)
- environment: not set
- dependents: 0 direct, 0 indirect
- size: 100 -&gt; 50

**Resource replaced** (`replace-resource`): size cannot be updated in place
- action: REPLACE (delete, create)
- environment: not set
- dependents: 0 direct, 0 indirect
- order: destroy before create: unavailable until the new one is up
- size: 100 -&gt; 50

</details>

<details><summary><code>aws_ebs_volume.plain</code>: update, score 70/100</summary>

- why: 2 attribute(s) change: a\_size, encrypted
- score factors: +60 critical finding (encryption-disabled); +10 production

**Encryption disabled** (`encryption-disabled`): encrypted turns off
- action: UPDATE
- environment: production
- dependents: 0 direct, 0 indirect
- encrypted: true -&gt; false

</details>

<details><summary><code>aws_ecs_service.shrink</code>: update, score 40/100</summary>

- why: 1 attribute(s) change: desired\_count
- score factors: +40 high finding (reduce-capacity)

**Capacity reduced** (`reduce-capacity`): desired\_count drops by 70% (threshold 30%)
- action: UPDATE
- environment: staging
- dependents: 0 direct, 0 indirect
- desired\_count: 10 -&gt; 3

</details>

<details><summary><code>aws_efs_file_system.pending</code>: update, score 60/100</summary>

- why: 1 attribute(s) known only after apply
- score factors: +60 critical finding (encryption-disabled)

**Encryption may be disabled** (`encryption-disabled`): encrypted is unknown until apply
- action: UPDATE
- environment: not set
- dependents: 0 direct, 0 indirect
- encrypted: true -&gt; (known after apply)

</details>

<details><summary><code>aws_eks_node_group.pending_subnets</code>: update, score 40/100</summary>

- why: 1 attribute(s) known only after apply
- score factors: +40 high finding (remove-redundancy)

**Redundancy may drop** (`remove-redundancy`): subnet\_ids spans 2 entries now and is unknown until apply
- action: UPDATE
- environment: not set
- dependents: 0 direct, 0 indirect
- subnet\_ids: 2 -&gt; (known after apply)

</details>

<details><summary><code>aws_eks_node_group.unknown_then_drop</code>: update, score 40/100</summary>

- why: 1 attribute(s) change: subnet\_ids\[1\]
- why: 1 attribute(s) known only after apply
- score factors: +40 high finding (remove-redundancy)

**Redundancy may drop** (`remove-redundancy`): availability\_zones spans 2 entries now and is unknown until apply
- action: UPDATE
- environment: not set
- dependents: 0 direct, 0 indirect
- availability\_zones: 2 -&gt; (known after apply)

**Redundancy removed** (`remove-redundancy`): subnet\_ids drops from 2 entries to 1
- action: UPDATE
- environment: not set
- dependents: 0 direct, 0 indirect
- subnet\_ids: 2 -&gt; 1

</details>

<details><summary><code>aws_instance.novel</code>: replace, score 25/100</summary>

- why: replace\_because\_of\_a\_future\_terraform\_reason
- score factors: +10 low finding (replace-resource); +15 replace: the old object is destroyed

**Resource replaced** (`replace-resource`): Terraform plans replacement (replace\_because\_of\_a\_future\_terraform\_reason)
- action: REPLACE (delete, create)
- environment: not set
- dependents: 0 direct, 0 indirect
- order: destroy before create: unavailable until the new one is up

</details>

<details><summary><code>aws_instance.requested</code>: replace, score 25/100</summary>

- why: replacement was requested with -replace
- why: create\_before\_destroy: the new object exists before the old one goes
- score factors: +10 low finding (replace-resource); +15 replace: the old object is destroyed

**Resource replaced** (`replace-resource`): Terraform plans replacement (replace\_by\_request)
- action: REPLACE (create, delete)
- environment: not set
- dependents: 0 direct, 0 indirect
- order: create before destroy

</details>

<details><summary><code>aws_instance.unexplained</code>: replace, score 25/100</summary>

- score factors: +10 low finding (replace-resource); +15 replace: the old object is destroyed

**Resource replaced** (`replace-resource`): Terraform plans replacement (no reason given)
- action: REPLACE (delete, create)
- environment: not set
- dependents: 0 direct, 0 indirect
- order: destroy before create: unavailable until the new one is up

</details>

<details><summary><code>aws_lb.computed_subnets</code>: replace, score 25/100</summary>

- why: name forces replacement
- why: 2 attribute(s) known only after apply
- score factors: +10 low finding (replace-resource); +15 replace: the old object is destroyed

**Resource replaced** (`replace-resource`): name cannot be updated in place
- action: REPLACE (delete, create)
- environment: not set
- dependents: 0 direct, 0 indirect
- order: destroy before create: unavailable until the new one is up
- name: "old" -&gt; "new"

</details>

<details><summary><code>aws_rds_cluster.no_snapshot</code>: update, score 40/100</summary>

- why: 1 attribute(s) change: skip\_final\_snapshot
- score factors: +40 high finding (backup-disabled)

**Backups disabled** (`backup-disabled`): skip\_final\_snapshot removes the way back after data loss
- action: UPDATE
- environment: not set
- dependents: 0 direct, 0 indirect
- skip\_final\_snapshot: false -&gt; true

</details>

<details><summary><code>aws_rds_cluster_instance.pending_exposure</code>: update, score 60/100</summary>

- why: 1 attribute(s) known only after apply
- score factors: +60 critical finding (public-database)

**Database may become public** (`public-database`): publicly\_accessible is unknown until apply
- action: UPDATE
- environment: not set
- dependents: 0 direct, 0 indirect
- publicly\_accessible: false -&gt; (known after apply)

</details>

<details><summary><code>aws_s3_account_public_access_block.pending</code>: update, score 40/100</summary>

- why: 1 attribute(s) known only after apply
- score factors: +40 high finding (s3-public-access-weakened)

**S3 public access block may weaken** (`s3-public-access-weakened`): 1 public access guard(s) unknown until apply
- action: UPDATE
- environment: not set
- dependents: 0 direct, 0 indirect
- restrict\_public\_buckets: true -&gt; (known after apply)

</details>

<details><summary><code>aws_s3_bucket.archive</code>: delete, score 85/100</summary>

- why: the resource was removed from configuration
- score factors: +60 critical finding (destroy-production-resource); +15 delete: the old object is destroyed; +10 production

**Production resource destroyed** (`destroy-production-resource`): aws\_s3\_bucket is deleted in a production environment
- action: DELETE
- environment: production
- dependents: 0 direct, 0 indirect
- terraform reason: delete\_because\_no\_resource\_config

**Data store deleted** (`stateful-data-loss`): aws\_s3\_bucket holds data; it is removed, existing data is lost
- action: DELETE
- environment: production
- dependents: 0 direct, 0 indirect
- terraform reason: delete\_because\_no\_resource\_config

</details>

<details><summary><code>aws_s3_bucket.unexplained_delete</code>: delete, score 85/100</summary>

- score factors: +60 critical finding (destroy-production-resource); +15 delete: the old object is destroyed; +10 production

**Production resource destroyed** (`destroy-production-resource`): aws\_s3\_bucket is deleted in a production environment
- action: DELETE
- environment: production
- dependents: 0 direct, 0 indirect

**Data store deleted** (`stateful-data-loss`): aws\_s3\_bucket holds data; it is removed, existing data is lost
- action: DELETE
- environment: production
- dependents: 0 direct, 0 indirect

</details>

<details><summary><code>aws_s3_bucket_public_access_block.flag_off</code>: update, score 40/100</summary>

- why: 1 attribute(s) change: block\_public\_acls
- score factors: +40 high finding (s3-public-access-weakened)

**S3 public access block weakened** (`s3-public-access-weakened`): 1 public access guard(s) turn off
- action: UPDATE
- environment: not set
- dependents: 0 direct, 0 indirect
- block\_public\_acls: true -&gt; false

</details>

<details><summary><code>aws_s3_bucket_public_access_block.removed</code>: delete, score 55/100</summary>

- score factors: +40 high finding (s3-public-access-weakened); +15 delete: the old object is destroyed

**S3 public access block removed** (`s3-public-access-weakened`): deleting the block lets bucket policies and ACLs make data public
- action: DELETE
- environment: not set
- dependents: 0 direct, 0 indirect
- resource: aws\_s3\_bucket\_public\_access\_block

</details>

<details><summary><code>aws_security_group.mixed_sources</code>: update, score 60/100</summary>

- why: 4 attribute(s) change: ingress\[0\].from\_port, ingress\[0\].ipv6\_cidr\_blocks\[0\], ingress\[0\].protocol, ingress\[0\].to\_port
- why: 1 attribute(s) known only after apply
- score factors: +60 critical finding (security-group-wide-open)

**Ingress opened to the internet** (`security-group-wide-open`): 1 ingress rule(s) newly open to ::/0
- action: UPDATE
- environment: not set
- dependents: 0 direct, 0 indirect
- ingress: tcp ports 22-22 from ::/0

**Ingress may open to the internet** (`security-group-wide-open`): 1 ingress rule(s) newly open to (known after apply)
- action: UPDATE
- environment: not set
- dependents: 0 direct, 0 indirect
- ingress: tcp ports 22-22 from (known after apply)

</details>

<details><summary><code>aws_security_group.pending_cidr</code>: update, score 60/100</summary>

- why: 3 attribute(s) change: ingress\[0\].from\_port, ingress\[0\].protocol, ingress\[0\].to\_port
- why: 1 attribute(s) known only after apply
- score factors: +60 critical finding (security-group-wide-open)

**Ingress may open to the internet** (`security-group-wide-open`): 1 ingress rule(s) newly open to (known after apply)
- action: UPDATE
- environment: not set
- dependents: 0 direct, 0 indirect
- ingress: tcp ports 3389-3389 from (known after apply)

</details>

<details><summary><code>aws_security_group.web</code>: update, score 60/100</summary>

- why: 8 attribute(s) change: ingress\[0\].cidr\_blocks\[0\], ingress\[0\].from\_port, ingress\[0\].protocol, ingress\[0\].to\_port, ingress\[1\].from\_port and 3 more
- score factors: +60 critical finding (security-group-wide-open)

**Ingress opened to the internet** (`security-group-wide-open`): 2 ingress rule(s) newly open to 0.0.0.0/0, ::/0
- action: UPDATE
- environment: not set
- dependents: 0 direct, 0 indirect
- ingress: tcp ports 22-22 from 0.0.0.0/0
- ingress: tcp ports 8080-8080 from ::/0

</details>

<details><summary><code>aws_security_group_rule.everything</code>: create, score 60/100</summary>

- why: new resource
- score factors: +60 critical finding (security-group-wide-open)

**Ingress opened to the internet** (`security-group-wide-open`): 1 ingress rule(s) newly open to 0.0.0.0/0
- action: CREATE
- environment: not set
- dependents: 0 direct, 0 indirect
- ingress: -1 ports all from 0.0.0.0/0

</details>

<details><summary><code>aws_security_group_rule.pending_port</code>: create, score 40/100</summary>

- why: new resource
- score factors: +40 high finding (security-group-wide-open)

**Ingress may open to the internet** (`security-group-wide-open`): 1 ingress rule(s) newly open to 0.0.0.0/0
- action: CREATE
- environment: not set
- dependents: 0 direct, 0 indirect
- ingress: tcp ports 22-? from 0.0.0.0/0

</details>

<details><summary><code>aws_security_group_rule.pending_protocol</code>: create, score 60/100</summary>

- why: new resource
- score factors: +60 critical finding (security-group-wide-open)

**Ingress may open to the internet** (`security-group-wide-open`): 1 ingress rule(s) newly open to 0.0.0.0/0
- action: CREATE
- environment: not set
- dependents: 0 direct, 0 indirect
- ingress: ? ports 22-22 from 0.0.0.0/0

</details>

<details><summary><code>aws_vpc.main</code>: replace, score 55/100</summary>

- why: cidr\_block forces replacement
- score factors: +25 medium finding (wide-blast-radius); +15 replace: the old object is destroyed; +15 12 dependent resource(s)

**Wide blast radius** (`wide-blast-radius`): 12 resources depend on it (threshold 5)
- action: REPLACE (delete, create)
- environment: not set
- dependents: 12 direct, 0 indirect
- affected: aws\_subnet.part\[0\], aws\_subnet.part\[10\], aws\_subnet.part\[11\], aws\_subnet.part\[1\], aws\_subnet.part\[2\], aws\_subnet.part\[3\], aws\_subnet.part\[4\], aws\_subnet.part\[5\], aws\_subnet.part\[6\], aws\_subnet.part\[7\] and 2 more

**Resource replaced** (`replace-resource`): cidr\_block cannot be updated in place
- action: REPLACE (delete, create)
- environment: not set
- dependents: 12 direct, 0 indirect
- order: destroy before create: unavailable until the new one is up
- cidr\_block: "10.0.0.0/16" -&gt; "10.1.0.0/16"

</details>

<details><summary><code>aws_vpc_security_group_ingress_rule.postgres</code>: create, score 60/100</summary>

- why: new resource
- score factors: +60 critical finding (security-group-wide-open)

**Ingress opened to the internet** (`security-group-wide-open`): 1 ingress rule(s) newly open to 0.0.0.0/0
- action: CREATE
- environment: not set
- dependents: 0 direct, 0 indirect
- ingress: tcp ports 5432-5432 from 0.0.0.0/0

</details>

### Other changes

- forget: `aws_instance.forgotten`
- update: `aws_lb.busy`
- update: `aws_lb.five`
- delete: `aws_s3_bucket.archive (deposed 0a1b2c3d)`
- create: `aws_security_group_rule.egress`
- create: `aws_subnet.part[0]`
- create: `aws_subnet.part[10]`
- create: `aws_subnet.part[11]`
- create: `aws_subnet.part[1]`
- create: `aws_subnet.part[2]`
- create: `aws_subnet.part[3]`
- create: `aws_subnet.part[4]`
- create: `aws_subnet.part[5]`
- create: `aws_subnet.part[6]`
- create: `aws_subnet.part[7]`
- create: `aws_subnet.part[8]`
- create: `aws_subnet.part[9]`
