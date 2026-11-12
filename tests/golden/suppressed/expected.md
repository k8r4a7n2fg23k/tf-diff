<!-- tf-diff:report -->
## Terraform Risk Summary

**Environment:** production · **Resources:** 12 inspected, 10 changed, 0 ignored, 2 findings suppressed
**Changes:** 1 create, 7 update, 1 delete, 1 replace

> warning: 1 resource(s) or module call(s) read locals (aws\_cloudwatch\_log\_group.app): the plan JSON does not say what a local refers to, so dependencies through them are missing and blast radius may be low

| Severity | Findings |
|---|---|
| critical | 5 |
| high | 1 |
| medium | 0 |
| low | 0 |
| info | 1 |

### Findings

| Severity | Resource | Finding | Confidence |
|---|---|---|---|
| **CRITICAL** | `aws_s3_bucket.audit_logs` | Production resource destroyed (`destroy-production-resource`) | high |
| **CRITICAL** | `aws_s3_bucket.audit_logs` | Data store deleted (`stateful-data-loss`) | high |
| **CRITICAL** | `aws_security_group.bastion` | Ingress opened to the internet (`security-group-wide-open`) | high |
| **CRITICAL** | `module.analytics.aws_db_instance.reporting` | Database becomes publicly accessible (`public-database`) | high |
| **CRITICAL** | `module.database.aws_db_instance.primary` | Data store replaced (`stateful-data-loss`) | high |
| **HIGH** | `aws_autoscaling_group.web` | Redundancy removed (`remove-redundancy`) | high |
| **INFO** | `module.database.aws_db_instance.primary` | Sensitive value changes (`sensitive-value-changed`) | high |

<details><summary><code>aws_autoscaling_group.web</code>: update, score 50/100</summary>

- why: 2 attribute(s) change: availability\_zones\[1\], availability\_zones\[2\]
- score factors: +40 high finding (remove-redundancy); +10 production

**Redundancy removed** (`remove-redundancy`): availability\_zones drops from 3 entries to 1
- action: UPDATE
- environment: production
- dependents: 0 direct, 0 indirect
- availability\_zones: 3 -&gt; 1

</details>

<details><summary><code>aws_s3_bucket.audit_logs</code>: delete, score 85/100</summary>

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

<details><summary><code>aws_security_group.bastion</code>: update, score 76/100</summary>

- why: 1 attribute(s) change: ingress\[1\].cidr\_blocks\[0\]
- score factors: +60 critical finding (security-group-wide-open); +10 production; +6 2 dependent resource(s)

**Ingress opened to the internet** (`security-group-wide-open`): 1 ingress rule(s) newly open to 0.0.0.0/0
- action: UPDATE
- environment: production
- dependents: 2 direct, 0 indirect
- ingress: tcp ports 22-22 from 0.0.0.0/0

</details>

<details><summary><code>module.analytics.aws_db_instance.reporting</code>: update, score 70/100</summary>

- why: 1 attribute(s) change: publicly\_accessible
- score factors: +60 critical finding (public-database); +10 production

**Database becomes publicly accessible** (`public-database`): publicly\_accessible turns on: the endpoint resolves to a public IP
- action: UPDATE
- environment: production
- dependents: 0 direct, 0 indirect
- publicly\_accessible: false -&gt; true

</details>

<details><summary><code>module.database.aws_db_instance.primary</code>: replace, score 97/100</summary>

- why: the provider cannot update it in place
- why: storage\_type forces replacement
- why: 1 attribute(s) change: password
- why: 3 attribute(s) known only after apply
- score factors: +60 critical finding (stateful-data-loss); +15 replace: the old object is destroyed; +10 production; +12 4 dependent resource(s)

**Data store replaced** (`stateful-data-loss`): aws\_db\_instance holds data; storage\_type forces a new one, existing data is lost
- action: REPLACE (delete, create)
- environment: production
- dependents: 3 direct, 1 indirect
- storage\_type: "gp2" -&gt; "io2"

**Sensitive value changes** (`sensitive-value-changed`): a secret or credential changes; dependents must pick up the new value
- action: REPLACE (delete, create)
- environment: production
- dependents: 3 direct, 1 indirect
- paths: password

</details>

<details><summary>Suppressed findings (2)</summary>

| Severity | Resource | Finding | Reason | Until |
|---|---|---|---|---|
| high | `module.api.aws_ecs_service.api` | Capacity reduced (`reduce-capacity`) | scaled down for the holiday freeze | - |
| medium | `module.database.aws_db_instance.primary` | Resource replaced (`replace-resource`) | blue/green cutover, approved in CHG-1234 | 2027-03-01 |

</details>

### Other changes

- create: `aws_cloudwatch_log_group.app["api"]`
- update: `aws_lb.public`
- update: `module.api.aws_ecs_service.api`
- update: `module.api.aws_ecs_task_definition.api`
- update: `module.worker.aws_ecs_service.worker`
