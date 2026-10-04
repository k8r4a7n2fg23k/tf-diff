variable "subnet_ids" {
  type = list(string)
}

variable "db_sg" {
  type = string
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

variable "guarded" {
  type = bool
}

variable "pitr" {
  type = bool
}

resource "aws_db_subnet_group" "main" {
  name       = "main"
  subnet_ids = var.subnet_ids
}

resource "aws_db_instance" "orders" {
  identifier              = "orders"
  engine                  = "postgres"
  engine_version          = "16.3"
  instance_class          = var.db.instance_class
  allocated_storage       = 50
  username                = "app"
  password                = "CANARY-db-password"
  db_subnet_group_name    = aws_db_subnet_group.main.name
  vpc_security_group_ids  = [var.db_sg]
  multi_az                = var.db.multi_az
  storage_encrypted       = var.db.encrypted
  backup_retention_period = var.db.backup_days
  publicly_accessible     = var.db.public
  skip_final_snapshot     = var.db.skip_snapshot
}

resource "aws_s3_bucket" "exports" {
  bucket = "orders-exports"
}

resource "aws_s3_bucket_public_access_block" "exports" {
  bucket                  = aws_s3_bucket.exports.id
  block_public_acls       = true
  ignore_public_acls      = true
  block_public_policy     = var.guarded
  restrict_public_buckets = var.guarded
}

resource "aws_dynamodb_table" "orders" {
  name         = "orders"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "id"

  attribute {
    name = "id"
    type = "S"
  }

  point_in_time_recovery {
    enabled = var.pitr
  }
}

output "db_endpoint" {
  value = aws_db_instance.orders.address
}
