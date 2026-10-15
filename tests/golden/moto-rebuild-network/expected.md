<!-- tf-diff:report -->
## Terraform Risk Summary

**Environment:** production · **Resources:** 18 inspected, 10 changed, 0 ignored
**Changes:** 7 update, 3 replace

| Severity | Findings |
|---|---|
| critical | 0 |
| high | 3 |
| medium | 6 |
| low | 0 |
| info | 0 |

### Findings

| Severity | Resource | Finding | Confidence |
|---|---|---|---|
| **HIGH** | `module.compute.aws_autoscaling_group.web` | Redundancy may drop (`remove-redundancy`) | low |
| **HIGH** | `module.compute.aws_lb.web` | Redundancy may drop (`remove-redundancy`) | low |
| **HIGH** | `module.data.aws_db_subnet_group.main` | Redundancy may drop (`remove-redundancy`) | low |
| **MEDIUM** | `module.network.aws_subnet.private["eu-west-1a"]` | Resource replaced (`replace-resource`) | high |
| **MEDIUM** | `module.network.aws_subnet.private["eu-west-1a"]` | Wide blast radius (`wide-blast-radius`) | high |
| **MEDIUM** | `module.network.aws_subnet.private["eu-west-1b"]` | Resource replaced (`replace-resource`) | high |
| **MEDIUM** | `module.network.aws_subnet.private["eu-west-1b"]` | Wide blast radius (`wide-blast-radius`) | high |
| **MEDIUM** | `module.network.aws_subnet.private["eu-west-1c"]` | Resource replaced (`replace-resource`) | high |
| **MEDIUM** | `module.network.aws_subnet.private["eu-west-1c"]` | Wide blast radius (`wide-blast-radius`) | high |

<details><summary><code>module.compute.aws_autoscaling_group.web</code>: update, score 50/100</summary>

- why: 1 attribute(s) known only after apply
- score factors: +40 high finding (remove-redundancy); +10 production

**Redundancy may drop** (`remove-redundancy`): vpc\_zone\_identifier spans 3 entries now and is unknown until apply
- action: UPDATE
- environment: production
- dependents: 0 direct, 0 indirect
- vpc\_zone\_identifier: 3 -&gt; (known after apply)

</details>

<details><summary><code>module.compute.aws_lb.web</code>: update, score 50/100</summary>

- why: 2 attribute(s) known only after apply
- score factors: +40 high finding (remove-redundancy); +10 production

**Redundancy may drop** (`remove-redundancy`): subnets spans 3 entries now and is unknown until apply
- action: UPDATE
- environment: production
- dependents: 0 direct, 0 indirect
- subnets: 3 -&gt; (known after apply)

</details>

<details><summary><code>module.data.aws_db_subnet_group.main</code>: update, score 59/100</summary>

- why: 1 attribute(s) known only after apply
- score factors: +40 high finding (remove-redundancy); +10 production; +9 3 dependent resource(s)

**Redundancy may drop** (`remove-redundancy`): subnet\_ids spans 3 entries now and is unknown until apply
- action: UPDATE
- environment: production
- dependents: 1 direct, 2 indirect
- subnet\_ids: 3 -&gt; (known after apply)

</details>

<details><summary><code>module.network.aws_subnet.private[&quot;eu-west-1a&quot;]</code>: replace, score 65/100</summary>

- why: the provider cannot update it in place
- why: cidr\_block forces replacement
- why: 7 attribute(s) known only after apply
- score factors: +25 medium finding (replace-resource); +15 replace: the old object is destroyed; +10 production; +15 5 dependent resource(s)

**Resource replaced** (`replace-resource`): cidr\_block cannot be updated in place
- action: REPLACE (delete, create)
- environment: production
- dependents: 3 direct, 2 indirect
- order: destroy before create: unavailable until the new one is up
- cidr\_block: "10.20.0.0/24" -&gt; "10.20.0.0/22"

**Wide blast radius** (`wide-blast-radius`): 5 resources depend on it (threshold 5)
- action: REPLACE (delete, create)
- environment: production
- dependents: 3 direct, 2 indirect
- affected: module.compute.aws\_autoscaling\_group.web, module.compute.aws\_lb.web, module.data.aws\_db\_subnet\_group.main, module.compute.aws\_launch\_template.web, module.data.aws\_db\_instance.orders

</details>

<details><summary><code>module.network.aws_subnet.private[&quot;eu-west-1b&quot;]</code>: replace, score 65/100</summary>

- why: the provider cannot update it in place
- why: cidr\_block forces replacement
- why: 7 attribute(s) known only after apply
- score factors: +25 medium finding (replace-resource); +15 replace: the old object is destroyed; +10 production; +15 5 dependent resource(s)

**Resource replaced** (`replace-resource`): cidr\_block cannot be updated in place
- action: REPLACE (delete, create)
- environment: production
- dependents: 3 direct, 2 indirect
- order: destroy before create: unavailable until the new one is up
- cidr\_block: "10.20.1.0/24" -&gt; "10.20.4.0/22"

**Wide blast radius** (`wide-blast-radius`): 5 resources depend on it (threshold 5)
- action: REPLACE (delete, create)
- environment: production
- dependents: 3 direct, 2 indirect
- affected: module.compute.aws\_autoscaling\_group.web, module.compute.aws\_lb.web, module.data.aws\_db\_subnet\_group.main, module.compute.aws\_launch\_template.web, module.data.aws\_db\_instance.orders

</details>

<details><summary><code>module.network.aws_subnet.private[&quot;eu-west-1c&quot;]</code>: replace, score 65/100</summary>

- why: the provider cannot update it in place
- why: cidr\_block forces replacement
- why: 7 attribute(s) known only after apply
- score factors: +25 medium finding (replace-resource); +15 replace: the old object is destroyed; +10 production; +15 5 dependent resource(s)

**Resource replaced** (`replace-resource`): cidr\_block cannot be updated in place
- action: REPLACE (delete, create)
- environment: production
- dependents: 3 direct, 2 indirect
- order: destroy before create: unavailable until the new one is up
- cidr\_block: "10.20.2.0/24" -&gt; "10.20.8.0/22"

**Wide blast radius** (`wide-blast-radius`): 5 resources depend on it (threshold 5)
- action: REPLACE (delete, create)
- environment: production
- dependents: 3 direct, 2 indirect
- affected: module.compute.aws\_autoscaling\_group.web, module.compute.aws\_lb.web, module.data.aws\_db\_subnet\_group.main, module.compute.aws\_launch\_template.web, module.data.aws\_db\_instance.orders

</details>

### Other changes

- update: `module.compute.aws_launch_template.web`
- update: `module.data.aws_s3_bucket.exports`
- update: `module.network.aws_security_group.web`
- update: `module.network.aws_vpc_security_group_ingress_rule.db_from_web`
