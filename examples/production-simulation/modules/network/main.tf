variable "zones" {
  type = list(string)
}

resource "terraform_data" "vpc" {
  input = "10.0.0.0/16"
}

resource "terraform_data" "subnet" {
  for_each = toset(var.zones)
  input    = { vpc = terraform_data.vpc.id, zone = each.key }
}

output "vpc_id" {
  value = terraform_data.vpc.id
}

output "subnet_ids" {
  value = [for subnet in terraform_data.subnet : subnet.id]
}
