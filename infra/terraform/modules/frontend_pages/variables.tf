variable "account_id" {
  description = "Cloudflare account ID that owns the Pages project."
  type        = string
}

variable "project_name" {
  description = "Pages project name (the deploy contract fixes this to `cloudy-web`)."
  type        = string
}

variable "production_branch" {
  description = "Git branch Pages treats as production."
  type        = string
  default     = "main"
}

variable "build_command" {
  description = "SPA build command. From frontend/package.json this is `pnpm build` (which runs `tsc --noEmit && vite build`)."
  type        = string
  default     = "pnpm build"
}

variable "destination_dir" {
  description = "Build output directory. Vite's default is `dist` (frontend/vite.config.ts sets no custom outDir)."
  type        = string
  default     = "dist"
}

variable "root_dir" {
  description = "Repo-relative directory the build runs in. The SPA lives in `frontend/`."
  type        = string
  default     = "frontend"
}

variable "api_url" {
  description = "Backend base URL baked into the build as VITE_API_URL (e.g. https://cloudy-api.fly.dev)."
  type        = string
}

variable "compatibility_date" {
  description = "Cloudflare Pages Functions compatibility date. A pure static SPA doesn't use Functions, but the field is required by the deployment config."
  type        = string
  default     = "2025-01-01"
}

variable "custom_domain" {
  description = "Optional custom domain to attach to the Pages project. Empty = skip (the *.pages.dev URL still works)."
  type        = string
  default     = ""
}

variable "dns_zone_id" {
  description = "Cloudflare DNS zone ID for the custom domain. Required only if custom_domain is set AND you want Terraform to create the CNAME record. Empty = create the Pages domain attachment but leave DNS to you."
  type        = string
  default     = ""
}
