variable "name" { type = string }
variable "primary_region" { type = string }
variable "private_subnets" { type = list(string) }
variable "redis_security_group_id" { type = string }
variable "auth_token" { type = string sensitive = true }
variable "tags" { type = map(string) default = {} }
