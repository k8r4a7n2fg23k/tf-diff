<!-- tf-diff:report -->
## Terraform Risk Summary

**Environment:** production · **Resources:** 18 inspected, 11 changed, 0 ignored
**Changes:** 7 update, 4 replace

| Severity | Findings |
|---|---|
| critical | 5 |
| high | 9 |
| medium | 4 |
| low | 0 |
| info | 0 |

### Findings

| Severity | Resource | Finding | Confidence |
|---|---|---|---|
| **CRITICAL** | `module.compute.aws_ebs_volume.scratch` | Encryption disabled (`encryption-disabled`) | high |
| **CRITICAL** | `module.compute.aws_ebs_volume.scratch` | Data store replaced (`stateful-data-loss`) | high |
| **CRITICAL** | `module.data.aws_db_instance.orders` | Encryption disabled (`encryption-disabled`) | high |
| **CRITICAL** | `module.data.aws_db_instance.orders` | Database becomes publicly accessible (`public-database`) | high |
| **CRITICAL** | `module.network.aws_security_group_rule.ssh` | Ingress opened to the internet (`security-group-wide-open`) | high |
| **HIGH** | `module.compute.aws_autoscaling_group.web` | Capacity reduced (`reduce-capacity`) x2 | high |
| **HIGH** | `module.compute.aws_autoscaling_group.web` | Redundancy removed (`remove-redundancy`) | high |
| **HIGH** | `module.data.aws_db_instance.orders` | Backups disabled (`backup-disabled`) x2 | high |
| **HIGH** | `module.data.aws_db_instance.orders` | Multi-AZ disabled (`remove-redundancy`) | high |
| **HIGH** | `module.data.aws_db_instance.orders` | Data store replaced (`stateful-data-loss`) | high |
| **HIGH** | `module.data.aws_dynamodb_table.orders` | Backups disabled (`backup-disabled`) | high |
| **HIGH** | `module.data.aws_s3_bucket_public_access_block.exports` | S3 public access block weakened (`s3-public-access-weakened`) | high |
| **MEDIUM** | `module.compute.aws_ebs_volume.scratch` | Resource replaced (`replace-resource`) | high |
| **MEDIUM** | `module.compute.aws_lb.web` | Resource replaced (`replace-resource`) | high |
| **MEDIUM** | `module.data.aws_db_instance.orders` | Resource replaced (`replace-resource`) | high |
| **MEDIUM** | `module.network.aws_security_group_rule.ssh` | Resource replaced (`replace-resource`) | high |

<details><summary><code>module.compute.aws_autoscaling_group.web</code>: update, score 50/100</summary>

- why: 5 attribute(s) change: desired\_capacity, min\_size, vpc\_zone\_identifier\[0\], vpc\_zone\_identifier\[1\], vpc\_zone\_identifier\[2\]
- score factors: +40 high finding (reduce-capacity); +10 production

**Capacity reduced** (`reduce-capacity`): desired\_capacity drops by 67% (threshold 30%)
- action: UPDATE
- environment: production
- dependents: 0 direct, 0 indirect
- desired\_capacity: 6 -&gt; 2

**Capacity reduced** (`reduce-capacity`): min\_size drops by 67% (threshold 30%)
- action: UPDATE
- environment: production
- dependents: 0 direct, 0 indirect
- min\_size: 3 -&gt; 1

**Redundancy removed** (`remove-redundancy`): vpc\_zone\_identifier drops from 3 entries to 1
- action: UPDATE
- environment: production
- dependents: 0 direct, 0 indirect
- vpc\_zone\_identifier: 3 -&gt; 1

</details>

<details><summary><code>module.compute.aws_ebs_volume.scratch</code>: replace, score 85/100</summary>

- why: the provider cannot update it in place
- why: encrypted forces replacement
- why: 8 attribute(s) known only after apply
- score factors: +60 critical finding (encryption-disabled); +15 replace: the old object is destroyed; +10 production

**Encryption disabled** (`encryption-disabled`): encrypted turns off
- action: REPLACE (delete, create)
- environment: production
- dependents: 0 direct, 0 indirect
- encrypted: true -&gt; false

**Data store replaced** (`stateful-data-loss`): aws\_ebs\_volume holds data; encrypted forces a new one, existing data is lost
- action: REPLACE (delete, create)
- environment: production
- dependents: 0 direct, 0 indirect
- encrypted: true -&gt; false

**Resource replaced** (`replace-resource`): encrypted cannot be updated in place
- action: REPLACE (delete, create)
- environment: production
- dependents: 0 direct, 0 indirect
- order: destroy before create: unavailable until the new one is up
- encrypted: true -&gt; false

</details>

<details><summary><code>module.compute.aws_lb.web</code>: replace, score 50/100</summary>

- why: the provider cannot update it in place
- why: name forces replacement
- why: 12 attribute(s) known only after apply
- score factors: +25 medium finding (replace-resource); +15 replace: the old object is destroyed; +10 production

**Resource replaced** (`replace-resource`): name cannot be updated in place
- action: REPLACE (delete, create)
- environment: production
- dependents: 0 direct, 0 indirect
- order: destroy before create: unavailable until the new one is up
- name: "web" -&gt; "web-v2"

</details>

<details><summary><code>module.data.aws_db_instance.orders</code>: replace, score 91/100</summary>

- why: the provider cannot update it in place
- why: storage\_encrypted forces replacement
- why: 5 attribute(s) change: backup\_retention\_period, instance\_class, multi\_az, publicly\_accessible, skip\_final\_snapshot
- why: 41 attribute(s) known only after apply
- score factors: +60 critical finding (encryption-disabled); +15 replace: the old object is destroyed; +10 production; +6 2 dependent resource(s)

**Encryption disabled** (`encryption-disabled`): storage\_encrypted turns off
- action: REPLACE (delete, create)
- environment: production
- dependents: 1 direct, 1 indirect
- storage\_encrypted: true -&gt; false

**Database becomes publicly accessible** (`public-database`): publicly\_accessible turns on: the endpoint resolves to a public IP
- action: REPLACE (delete, create)
- environment: production
- dependents: 1 direct, 1 indirect
- publicly\_accessible: false -&gt; true

**Backups disabled** (`backup-disabled`): backup\_retention\_period removes the way back after data loss
- action: REPLACE (delete, create)
- environment: production
- dependents: 1 direct, 1 indirect
- backup\_retention\_period: 7 -&gt; 0

**Backups disabled** (`backup-disabled`): skip\_final\_snapshot removes the way back after data loss
- action: REPLACE (delete, create)
- environment: production
- dependents: 1 direct, 1 indirect
- skip\_final\_snapshot: false -&gt; true

**Multi-AZ disabled** (`remove-redundancy`): multi\_az turns off
- action: REPLACE (delete, create)
- environment: production
- dependents: 1 direct, 1 indirect
- multi\_az: true -&gt; false

**Data store replaced** (`stateful-data-loss`): aws\_db\_instance holds data; storage\_encrypted forces a new one, but skip\_final\_snapshot = false: the provider refuses to delete it without final\_snapshot\_identifier
- action: REPLACE (delete, create)
- environment: production
- dependents: 1 direct, 1 indirect
- storage\_encrypted: true -&gt; false
- skip\_final\_snapshot: false

**Resource replaced** (`replace-resource`): storage\_encrypted cannot be updated in place
- action: REPLACE (delete, create)
- environment: production
- dependents: 1 direct, 1 indirect
- order: destroy before create: unavailable until the new one is up
- storage\_encrypted: true -&gt; false

</details>

<details><summary><code>module.data.aws_dynamodb_table.orders</code>: update, score 50/100</summary>

- why: 1 attribute(s) change: point\_in\_time\_recovery\[0\].enabled
- score factors: +40 high finding (backup-disabled); +10 production

**Backups disabled** (`backup-disabled`): point\_in\_time\_recovery\[0\].enabled removes the way back after data loss
- action: UPDATE
- environment: production
- dependents: 0 direct, 0 indirect
- point\_in\_time\_recovery\[0\].enabled: true -&gt; false

</details>

<details><summary><code>module.data.aws_s3_bucket_public_access_block.exports</code>: update, score 50/100</summary>

- why: 2 attribute(s) change: block\_public\_policy, restrict\_public\_buckets
- score factors: +40 high finding (s3-public-access-weakened); +10 production

**S3 public access block weakened** (`s3-public-access-weakened`): 2 public access guard(s) turn off
- action: UPDATE
- environment: production
- dependents: 0 direct, 0 indirect
- block\_public\_policy: true -&gt; false
- restrict\_public\_buckets: true -&gt; false

</details>

<details><summary><code>module.network.aws_security_group_rule.ssh</code>: replace, score 85/100</summary>

- why: the provider cannot update it in place
- why: cidr\_blocks forces replacement
- why: 3 attribute(s) known only after apply
- score factors: +60 critical finding (security-group-wide-open); +15 replace: the old object is destroyed; +10 production

**Ingress opened to the internet** (`security-group-wide-open`): 1 ingress rule(s) newly open to 0.0.0.0/0
- action: REPLACE (delete, create)
- environment: production
- dependents: 0 direct, 0 indirect
- ingress: tcp ports 22-22 from 0.0.0.0/0

**Resource replaced** (`replace-resource`): cidr\_blocks cannot be updated in place
- action: REPLACE (delete, create)
- environment: production
- dependents: 0 direct, 0 indirect
- order: destroy before create: unavailable until the new one is up
- cidr\_blocks\[0\]: "10.0.0.0/8" -&gt; "0.0.0.0/0"

</details>

### Other changes

- update: `module.compute.aws_launch_template.web`
- update: `module.data.aws_s3_bucket.exports`
- update: `module.network.aws_security_group.web`
- update: `module.network.aws_vpc_security_group_ingress_rule.db_from_web`
