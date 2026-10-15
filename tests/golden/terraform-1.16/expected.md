<!-- tf-diff:report -->
## Terraform Risk Summary

**Environment:** production · **Resources:** 12 inspected, 7 changed, 0 ignored
**Changes:** 2 update, 4 delete, 1 replace

| Severity | Findings |
|---|---|
| critical | 4 |
| high | 0 |
| medium | 3 |
| low | 0 |
| info | 1 |

### Findings

| Severity | Resource | Finding | Confidence |
|---|---|---|---|
| **CRITICAL** | `module.app.terraform_data.worker[1]` | Production resource destroyed (`destroy-production-resource`) | high |
| **CRITICAL** | `module.app.terraform_data.worker[2]` | Production resource destroyed (`destroy-production-resource`) | high |
| **CRITICAL** | `module.network.terraform_data.subnet["zone-c"]` | Production resource destroyed (`destroy-production-resource`) | high |
| **CRITICAL** | `terraform_data.cache[0]` | Production resource destroyed (`destroy-production-resource`) | high |
| **MEDIUM** | `module.database.terraform_data.primary` | Resource replaced (`replace-resource`) | high |
| **MEDIUM** | `module.database.terraform_data.primary` | Wide blast radius (`wide-blast-radius`) | high |
| **MEDIUM** | `module.network.terraform_data.subnet["zone-c"]` | Wide blast radius (`wide-blast-radius`) | high |
| **INFO** | `module.database.terraform_data.primary` | Sensitive value changes (`sensitive-value-changed`) | high |

<details><summary><code>module.app.terraform_data.worker[1]</code>: delete, score 85/100</summary>

- why: its count index is out of range now
- score factors: +60 critical finding (destroy-production-resource); +15 delete: the old object is destroyed; +10 production

**Production resource destroyed** (`destroy-production-resource`): terraform\_data is deleted in a production environment
- action: DELETE
- environment: production
- dependents: 0 direct, 0 indirect
- terraform reason: delete\_because\_count\_index

</details>

<details><summary><code>module.app.terraform_data.worker[2]</code>: delete, score 85/100</summary>

- why: its count index is out of range now
- score factors: +60 critical finding (destroy-production-resource); +15 delete: the old object is destroyed; +10 production

**Production resource destroyed** (`destroy-production-resource`): terraform\_data is deleted in a production environment
- action: DELETE
- environment: production
- dependents: 0 direct, 0 indirect
- terraform reason: delete\_because\_count\_index

</details>

<details><summary><code>module.database.terraform_data.primary</code>: replace, score 65/100</summary>

- why: the provider cannot update it in place
- why: triggers\_replace forces replacement
- why: 2 attribute(s) change: input.password, input.subnets\[2\]
- why: 2 attribute(s) known only after apply
- score factors: +25 medium finding (replace-resource); +15 replace: the old object is destroyed; +10 production; +15 6 dependent resource(s)

**Resource replaced** (`replace-resource`): triggers\_replace cannot be updated in place
- action: REPLACE (delete, create)
- environment: production
- dependents: 4 direct, 2 indirect
- order: destroy before create: unavailable until the new one is up
- triggers\_replace: "gp2" -&gt; "gp3"

**Wide blast radius** (`wide-blast-radius`): 6 resources depend on it (threshold 5)
- action: REPLACE (delete, create)
- environment: production
- dependents: 4 direct, 2 indirect
- affected: module.app.terraform\_data.api, module.app.terraform\_data.worker\[0\], module.app.terraform\_data.worker\[1\], module.app.terraform\_data.worker\[2\], module.app.terraform\_data.autoscaler, module.app.terraform\_data.deployment

**Sensitive value changes** (`sensitive-value-changed`): a secret or credential changes; dependents must pick up the new value
- action: REPLACE (delete, create)
- environment: production
- dependents: 4 direct, 2 indirect
- paths: input.password

</details>

<details><summary><code>module.network.terraform_data.subnet[&quot;zone-c&quot;]</code>: delete, score 100/100</summary>

- why: its for\_each key is gone
- score factors: +60 critical finding (destroy-production-resource); +15 delete: the old object is destroyed; +10 production; +15 7 dependent resource(s)

**Production resource destroyed** (`destroy-production-resource`): terraform\_data is deleted in a production environment
- action: DELETE
- environment: production
- dependents: 1 direct, 6 indirect
- terraform reason: delete\_because\_each\_key

**Wide blast radius** (`wide-blast-radius`): 7 resources depend on it (threshold 5)
- action: DELETE
- environment: production
- dependents: 1 direct, 6 indirect
- affected: module.database.terraform\_data.primary, module.app.terraform\_data.api, module.app.terraform\_data.autoscaler, module.app.terraform\_data.deployment, module.app.terraform\_data.worker\[0\], module.app.terraform\_data.worker\[1\], module.app.terraform\_data.worker\[2\]

</details>

<details><summary><code>terraform_data.cache[0]</code>: delete, score 85/100</summary>

- why: its count index is out of range now
- score factors: +60 critical finding (destroy-production-resource); +15 delete: the old object is destroyed; +10 production

**Production resource destroyed** (`destroy-production-resource`): terraform\_data is deleted in a production environment
- action: DELETE
- environment: production
- dependents: 0 direct, 0 indirect
- terraform reason: delete\_because\_count\_index

</details>

### Other changes

- update: `module.app.terraform_data.api`
- update: `module.app.terraform_data.worker[0]`
