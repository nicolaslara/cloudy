variable "app_name" {
  description = "Fly app name (the deploy contract fixes this to `cloudy-api`)."
  type        = string
}

variable "org" {
  description = "Fly.io organization slug."
  type        = string
}

variable "region" {
  description = "Primary Fly region code, e.g. `arn` (Stockholm)."
  type        = string
}

variable "fly_api_token" {
  description = "Fly API token, handed to the `flyctl` invocation that builds and pushes the initial image (the same token the fly provider uses). Sensitive."
  type        = string
  sensitive   = true
}

variable "image_label" {
  description = <<-EOT
    Base prefix for the backend image tag. The module appends a content hash of the
    image sources, so the effective tag is `<image_label>-<hash>` and every backend
    change produces a new tag that Terraform rebuilds, pushes, migrates, and rolls
    onto the machine on `terraform apply`. You do NOT bump this per release — the
    hash does that; change it only to namespace builds (e.g. per environment).
  EOT
  type        = string
  default     = "tf-bootstrap"
}

variable "database_url" {
  description = "DATABASE_URL the backend reads (postgresql+psycopg://...). Set as a machine env value; treated as sensitive."
  type        = string
  sensitive   = true
}

variable "cors_allow_origins" {
  description = "Browser origins the API allows (CORS), comma-separated. Set to the Pages origin so only the SPA can call the API; the app reads it as CORS_ALLOW_ORIGINS."
  type        = string
}

variable "internal_port" {
  description = "Port the container listens on. The app binds $PORT; Fly sets PORT to this value. 8080 is Fly's convention and the contract's default."
  type        = number
  default     = 8080
}

variable "min_machines_running" {
  description = "0 = scale-to-zero. (Honored by Fly's proxy autostop config; with a single Terraform-managed machine this is advisory — see note in main.tf.)"
  type        = number
  default     = 0
}

variable "memory_mb" {
  description = "Machine RAM in MB."
  type        = number
  default     = 512
}

variable "cpus" {
  description = "Machine vCPU count."
  type        = number
  default     = 1
}

variable "cpu_type" {
  description = "Fly machine flavor (`shared` is cheapest)."
  type        = string
  default     = "shared"
}
