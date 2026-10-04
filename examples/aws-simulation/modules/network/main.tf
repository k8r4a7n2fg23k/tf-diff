variable "zones" {
  type = list(string)
}

variable "subnet_bits" {
  type = number
}

variable "admin_cidr" {
  type = string
}

resource "aws_vpc" "main" {
  cidr_block = "10.20.0.0/16"
}

resource "aws_subnet" "private" {
  for_each          = { for index, zone in var.zones : zone => index }
  vpc_id            = aws_vpc.main.id
  availability_zone = each.key
  cidr_block        = cidrsubnet(aws_vpc.main.cidr_block, var.subnet_bits, each.value)
}

resource "aws_security_group" "web" {
  name   = "web"
  vpc_id = aws_vpc.main.id

  ingress {
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

resource "aws_security_group" "db" {
  name   = "db"
  vpc_id = aws_vpc.main.id
}

resource "aws_vpc_security_group_ingress_rule" "db_from_web" {
  security_group_id            = aws_security_group.db.id
  referenced_security_group_id = aws_security_group.web.id
  ip_protocol                  = "tcp"
  from_port                    = 5432
  to_port                      = 5432
}

resource "aws_security_group_rule" "ssh" {
  type              = "ingress"
  security_group_id = aws_security_group.web.id
  protocol          = "tcp"
  from_port         = 22
  to_port           = 22
  cidr_blocks       = [var.admin_cidr]
}

output "vpc_id" {
  value = aws_vpc.main.id
}

output "subnet_ids" {
  value = [for zone in var.zones : aws_subnet.private[zone].id]
}

output "web_sg" {
  value = aws_security_group.web.id
}

output "db_sg" {
  value = aws_security_group.db.id
}
