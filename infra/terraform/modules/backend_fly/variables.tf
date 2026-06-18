variable "app_name" {
  description = "Fly app name (the deploy contract fixes this to `cloudy-api`)."
  type        = string
}

variable "org" {
  description = "Fly.io organization slug."
  type        = string
}
