# Source of plan.json (Terraform 1.16.6, no provider needed):
#   terraform apply
#   terraform plan -out=p -var 'rev={a=2,b=1,c=1}' -replace='terraform_data.disk[0]'
#   terraform show -json p > plan.json
# nic["a"] and disk[0] are replaced; see which instances depend on them.

variable "rev" {
  type    = map(number)
  default = { a = 1, b = 1, c = 1 }
}
resource "terraform_data" "nic" {
  for_each         = var.rev
  input            = each.value
  triggers_replace = [each.value]
}
resource "terraform_data" "vm" {
  for_each = terraform_data.nic
  input    = terraform_data.nic[each.key].id
}
resource "terraform_data" "pinned" {
  input = terraform_data.nic["b"].id
}
resource "terraform_data" "all" {
  input = [for n in terraform_data.nic : n.id]
}
resource "terraform_data" "disk" {
  count = 3
  input = count.index
}
resource "terraform_data" "attach" {
  count = 3
  input = terraform_data.disk[count.index].id
}
resource "terraform_data" "after" {
  depends_on = [terraform_data.nic]
}
