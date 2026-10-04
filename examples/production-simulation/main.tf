# Simulated production stack: network -> database -> app. terraform_data stands in for cloud
# resources so the plan is real Terraform output without credentials or network access.

variable "zones" {
  type = list(string)
}

variable "storage_type" {
  type = string
}

variable "db_password" {
  type      = string
  sensitive = true
}

variable "release" {
  type = string
}

variable "workers" {
  type = number
}

variable "legacy_cache" {
  type = bool
}

module "network" {
  source = "./modules/network"
  zones  = var.zones
}

module "database" {
  source       = "./modules/database"
  subnet_ids   = module.network.subnet_ids
  storage_type = var.storage_type
  password     = var.db_password
}

module "app" {
  source      = "./modules/app"
  db_endpoint = module.database.endpoint
  release     = var.release
  workers     = var.workers
}

resource "terraform_data" "cache" {
  count = var.legacy_cache ? 1 : 0
  input = module.network.vpc_id
}
