variable "primary_region" {
  type    = string
  default = "us-east-1"
}

variable "secondary_regions" {
  type    = list(string)
  default = ["eu-west-1", "ap-southeast-1"]
}

variable "redis_auth_token" {
  type      = string
  sensitive = true
}
