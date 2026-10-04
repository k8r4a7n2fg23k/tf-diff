variable "db_endpoint" {
  type = string
}

variable "release" {
  type = string
}

variable "workers" {
  type = number
}

resource "terraform_data" "api" {
  input = { db = var.db_endpoint, release = var.release }
}

resource "terraform_data" "worker" {
  count = var.workers
  input = { db = var.db_endpoint, release = var.release }
}

resource "terraform_data" "deployment" {
  input = terraform_data.api.id
}

resource "terraform_data" "autoscaler" {
  input = terraform_data.deployment.id
}
