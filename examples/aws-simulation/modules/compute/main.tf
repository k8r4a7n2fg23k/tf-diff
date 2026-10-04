variable "vpc_id" {
  type = string
}

variable "subnet_ids" {
  type = list(string)
}

variable "web_sg" {
  type = string
}

variable "web" {
  type = object({
    desired = number
    min     = number
    zones   = number
  })
}

variable "db_endpoint" {
  type = string
}

variable "volume_encrypted" {
  type = bool
}

variable "lb_name" {
  type = string
}

resource "aws_launch_template" "web" {
  name          = "web"
  image_id      = "ami-12c6146b"
  instance_type = "t3.micro"
  user_data     = base64encode("DB_HOST=${var.db_endpoint}")
}

resource "aws_autoscaling_group" "web" {
  name                = "web"
  min_size            = var.web.min
  max_size            = 10
  desired_capacity    = var.web.desired
  vpc_zone_identifier = slice(var.subnet_ids, 0, var.web.zones)

  launch_template {
    id      = aws_launch_template.web.id
    version = "$Latest"
  }
}

resource "aws_lb" "web" {
  name               = var.lb_name
  load_balancer_type = "application"
  internal           = true
  security_groups    = [var.web_sg]
  subnets            = var.subnet_ids
}

resource "aws_lb_target_group" "web" {
  name     = "web"
  port     = 80
  protocol = "HTTP"
  vpc_id   = var.vpc_id
}

resource "aws_ebs_volume" "scratch" {
  availability_zone = "eu-west-1a"
  size              = 20
  encrypted         = var.volume_encrypted
}
