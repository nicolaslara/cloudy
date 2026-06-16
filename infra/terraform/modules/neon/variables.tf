variable "project_name" {
  description = "Neon project name (and the name shown in the Neon console)."
  type        = string
}

variable "region_id" {
  description = "Neon region, e.g. `aws-eu-central-1`."
  type        = string
}

variable "pg_version" {
  description = "Postgres major version."
  type        = number
}

variable "database_name" {
  description = "Application database name."
  type        = string
  default     = "cloudy"
}

variable "role_name" {
  description = "Application role (owner of the database)."
  type        = string
  default     = "cloudy"
}
