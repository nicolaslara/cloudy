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

variable "image" {
  description = "Fully-qualified container image to run (built/pushed by `flyctl deploy`, not Terraform)."
  type        = string
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
