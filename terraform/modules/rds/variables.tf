variable "name" { type = string }
variable "vpc_id" { type = string }
variable "database_subnets" { type = list(string) }
variable "api_security_group_id" { type = string }
variable "kms_key_id" { type = string }
variable "tags" { type = map(string) default = {} }
