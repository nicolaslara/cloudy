# The Pages project's default URL. Cloudflare serves every project at
# https://<project-name>.pages.dev. If a custom domain is configured, prefer it.
output "pages_url" {
  description = "Public URL of the SPA (custom domain if set, else the *.pages.dev subdomain)."
  value       = var.custom_domain != "" ? "https://${var.custom_domain}" : "https://${cloudflare_pages_project.this.name}.pages.dev"
}

output "pages_subdomain" {
  description = "The project's *.pages.dev URL (always available, even with a custom domain)."
  value       = "https://${cloudflare_pages_project.this.name}.pages.dev"
}

output "project_name" {
  description = "Pages project name (echoed for scripting)."
  value       = cloudflare_pages_project.this.name
}
