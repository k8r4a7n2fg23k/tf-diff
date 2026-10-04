terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
  }
}

variable "endpoint" {
  type    = string
  default = "http://127.0.0.1:5555"
}

variable "environment" {
  type = string
}

variable "zones" {
  type = list(string)
}

variable "subnet_bits" {
  type = number
}

variable "db" {
  type = object({
    multi_az       = bool
    encrypted      = bool
    backup_days    = number
    public         = bool
    skip_snapshot  = bool
    instance_class = string
  })
}

variable "web" {
  type = object({
    desired = number
    min     = number
    zones   = number
  })
}

variable "bucket_guarded" {
  type = bool
}

variable "orders_pitr" {
  type = bool
}

variable "volume_encrypted" {
  type = bool
}

variable "admin_cidr" {
  type = string
}

variable "lb_name" {
  type = string
}

provider "aws" {
  region                      = "eu-west-1"
  access_key                  = "moto"
  secret_key                  = "moto"
  skip_credentials_validation = true
  skip_requesting_account_id  = true
  skip_metadata_api_check     = true
  s3_use_path_style           = true

  endpoints {
    autoscaling = var.endpoint
    dynamodb    = var.endpoint
    ec2         = var.endpoint
    elbv2       = var.endpoint
    iam         = var.endpoint
    rds         = var.endpoint
    s3          = var.endpoint
    sts         = var.endpoint
  }

  default_tags {
    tags = { Environment = var.environment }
  }
}

module "network" {
  source      = "./modules/network"
  zones       = var.zones
  subnet_bits = var.subnet_bits
  admin_cidr  = var.admin_cidr
}

module "data" {
  source     = "./modules/data"
  subnet_ids = module.network.subnet_ids
  db_sg      = module.network.db_sg
  db         = var.db
  guarded    = var.bucket_guarded
  pitr       = var.orders_pitr
}

module "compute" {
  source           = "./modules/compute"
  vpc_id           = module.network.vpc_id
  subnet_ids       = module.network.subnet_ids
  web_sg           = module.network.web_sg
  web              = var.web
  db_endpoint      = module.data.db_endpoint
  volume_encrypted = var.volume_encrypted
  lb_name          = var.lb_name
}
