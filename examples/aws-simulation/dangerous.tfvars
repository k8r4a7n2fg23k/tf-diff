environment = "production"
zones       = ["eu-west-1a", "eu-west-1b", "eu-west-1c"]
subnet_bits = 8

# every guard off; tests/golden/moto-dangerous has one finding per line
db = {
  multi_az       = false
  encrypted      = false
  backup_days    = 0
  public         = true
  skip_snapshot  = true
  instance_class = "db.t3.small"
}

web = {
  desired = 2
  min     = 1
  zones   = 1
}

bucket_guarded   = false
orders_pitr      = false
volume_encrypted = false
admin_cidr       = "0.0.0.0/0"
lb_name          = "web-v2"
