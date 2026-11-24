<!-- tf-diff:report -->
## Terraform Risk Summary

**Environment:** not set · **Resources:** 12 inspected, 7 changed, 0 ignored
**Changes:** 2 update, 4 delete, 1 replace

> warning: no environment: nothing sets it and no resource has an environment tag (Environment, env), so production-only checks are off; set --environment

| Severity | Findings |
|---|---|
| critical | 0 |
| high | 0 |
| medium | 2 |
| low | 1 |
| info | 1 |

### Findings

| Severity | Resource | Finding | Confidence |
|---|---|---|---|
| **MEDIUM** | `module.database.terraform_data.primary` | Wide blast radius (`wide-blast-radius`) | high |
| **MEDIUM** | `module.network.terraform_data.subnet["zone-c"]` | Wide blast radius (`wide-blast-radius`) | high |
| **LOW** | `module.database.terraform_data.primary` | Resource replaced (`replace-resource`) | high |
| **INFO** | `module.database.terraform_data.primary` | Sensitive value changes (`sensitive-value-changed`) | high |

<details><summary><code>module.database.terraform_data.primary</code>: replace, score 55/100</summary>

- why: the provider cannot update it in place
- why: triggers\_replace forces replacement
- why: 2 attribute(s) change: input.password, input.subnets\[2\]
- why: 2 attribute(s) known only after apply
- score factors: +25 medium finding (wide-blast-radius); +15 replace: the old object is destroyed; +15 6 dependent resource(s)

**Wide blast radius** (`wide-blast-radius`): 6 resources depend on it (threshold 5)
- action: REPLACE (delete, create)
- environment: not set
- dependents: 4 direct, 2 indirect
- affected: module.app.terraform\_data.api, module.app.terraform\_data.worker\[0\], module.app.terraform\_data.worker\[1\], module.app.terraform\_data.worker\[2\], module.app.terraform\_data.autoscaler, module.app.terraform\_data.deployment

**Resource replaced** (`replace-resource`): triggers\_replace cannot be updated in place
- action: REPLACE (delete, create)
- environment: not set
- dependents: 4 direct, 2 indirect
- order: destroy before create: unavailable until the new one is up
- triggers\_replace: "gp2" -&gt; "gp3"

**Sensitive value changes** (`sensitive-value-changed`): a secret or credential changes; dependents must pick up the new value
- action: REPLACE (delete, create)
- environment: not set
- dependents: 4 direct, 2 indirect
- paths: input.password

</details>

<details><summary><code>module.network.terraform_data.subnet[&quot;zone-c&quot;]</code>: delete, score 55/100</summary>

- why: its for\_each key is gone
- score factors: +25 medium finding (wide-blast-radius); +15 delete: the old object is destroyed; +15 7 dependent resource(s)

**Wide blast radius** (`wide-blast-radius`): 7 resources depend on it (threshold 5)
- action: DELETE
- environment: not set
- dependents: 1 direct, 6 indirect
- affected: module.database.terraform\_data.primary, module.app.terraform\_data.api, module.app.terraform\_data.autoscaler, module.app.terraform\_data.deployment, module.app.terraform\_data.worker\[0\], module.app.terraform\_data.worker\[1\], module.app.terraform\_data.worker\[2\]

</details>

### Other changes

- update: `module.app.terraform_data.api`
- update: `module.app.terraform_data.worker[0]`
- delete: `module.app.terraform_data.worker[1]`
- delete: `module.app.terraform_data.worker[2]`
- delete: `terraform_data.cache[0]`
