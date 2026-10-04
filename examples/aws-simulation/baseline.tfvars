environment = "production"
zones       = ["eu-west-1a", "eu-west-1b", "eu-west-1c"]
subnet_bits = 8

db = {
  multi_az       = true
  encrypted      = true
  backup_days    = 7
  public         = false
  skip_snapshot  = false
  instance_class = "db.t3.medium"
}

web = {
  desired = 6
  min     = 3
  zones   = 3
}

bucket_guarded   = true
orders_pitr      = true
volume_encrypted = true
admin_cidr       = "10.0.0.0/8"
lb_name          = "web"
