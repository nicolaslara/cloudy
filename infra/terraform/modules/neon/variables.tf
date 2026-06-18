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

variable "history_retention_seconds" {
  description = <<-EOT
    Point-in-time restore window. Neon's Free plan caps this at 21600s (6h) and
    rejects anything higher; paid plans allow more. The provider's own default
    (86400s) exceeds the free cap, so we set it explicitly. Raise it if the
    project moves to a paid plan and you want a longer restore window.
  EOT
  type        = number
  default     = 21600
}

variable "autoscaling_max_cu" {
  description = <<-EOT
    Maximum compute size (in CUs) the endpoint may autoscale up to under load. The
    minimum is fixed at 0.25 CU and the endpoint scales to zero when idle, so this
    only raises cost while compute is actively busy. Default 0.25 keeps a flat,
    smallest footprint; raise it (e.g. 4) to let bulk work like a historical
    backfill burst, then it settles back down on its own. Free plan allows up to
    2 CU; paid plans allow more.
  EOT
  type        = number
  default     = 0.25
}

variable "org_id" {
  description = <<-EOT
    Neon organization that owns the project. Required for accounts whose API key
    belongs to an organization (Neon's current default); legacy personal accounts
    can leave it empty. Find it under Neon console -> Organization settings, or
    GET /api/v2/users/me/organizations. Empty string = omit (personal account).
  EOT
  type        = string
  default     = ""
}
