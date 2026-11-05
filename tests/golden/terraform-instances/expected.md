<!-- tf-diff:report -->
## Terraform Risk Summary

**Environment:** not set · **Resources:** 15 inspected, 5 changed, 0 ignored
**Changes:** 3 update, 2 replace

> warning: no environment: nothing sets it and no resource has an environment tag (Environment, env), so production-only checks are off; set --environment

| Severity | Findings |
|---|---|
| critical | 0 |
| high | 0 |
| medium | 1 |
| low | 2 |
| info | 0 |

### Findings

| Severity | Resource | Finding | Confidence |
|---|---|---|---|
| **MEDIUM** | `terraform_data.nic["a"]` | Wide blast radius (`wide-blast-radius`) | high |
| **LOW** | `terraform_data.disk[0]` | Resource replaced (`replace-resource`) | high |
| **LOW** | `terraform_data.nic["a"]` | Resource replaced (`replace-resource`) | high |

<details><summary><code>terraform_data.disk[0]</code>: replace, score 34/100</summary>

- why: replacement was requested with -replace
- why: 2 attribute(s) known only after apply
- score factors: +10 low finding (replace-resource); +15 replace: the old object is destroyed; +9 3 dependent resource(s)

**Resource replaced** (`replace-resource`): Terraform plans replacement (replace\_by\_request)
- action: REPLACE (delete, create)
- environment: not set
- dependents: 3 direct, 0 indirect
- order: destroy before create: unavailable until the new one is up

</details>

<details><summary><code>terraform_data.nic[&quot;a&quot;]</code>: replace, score 55/100</summary>

- why: the provider cannot update it in place
- why: triggers\_replace forces replacement
- why: 1 attribute(s) change: input
- why: 2 attribute(s) known only after apply
- score factors: +25 medium finding (wide-blast-radius); +15 replace: the old object is destroyed; +15 5 dependent resource(s)

**Wide blast radius** (`wide-blast-radius`): 5 resources depend on it (threshold 5)
- action: REPLACE (delete, create)
- environment: not set
- dependents: 5 direct, 0 indirect
- affected: terraform\_data.after, terraform\_data.all, terraform\_data.vm\["a"\], terraform\_data.vm\["b"\], terraform\_data.vm\["c"\]

**Resource replaced** (`replace-resource`): triggers\_replace cannot be updated in place
- action: REPLACE (delete, create)
- environment: not set
- dependents: 5 direct, 0 indirect
- order: destroy before create: unavailable until the new one is up
- triggers\_replace\[0\]: 1 -&gt; 2

</details>

### Other changes

- update: `terraform_data.all`
- update: `terraform_data.attach[0]`
- update: `terraform_data.vm["a"]`
