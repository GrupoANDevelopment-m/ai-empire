variable "name" { type = string }
variable "image" { type = string }
variable "region" { type = string }
variable "desired_count" { type = number default = 3 }
variable "private_subnets" { type = list(string) }
variable "api_security_group_id" { type = string }
variable "target_group_arn" { type = string }
variable "jwt_secret_arn" { type = string }
variable "nvidia_nim_key_arn" { type = string }
variable "muapi_key_arn" { type = string }
variable "tags" { type = map(string) default = {} }
