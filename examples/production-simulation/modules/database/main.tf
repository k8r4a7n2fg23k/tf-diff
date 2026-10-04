variable "subnet_ids" {
  type = list(string)
}

variable "storage_type" {
  type = string
}

variable "password" {
  type      = string
  sensitive = true
}

resource "terraform_data" "primary" {
  triggers_replace = var.storage_type
  input = {
    subnets  = var.subnet_ids
    password = var.password
  }
}

output "endpoint" {
  value = terraform_data.primary.id
}
