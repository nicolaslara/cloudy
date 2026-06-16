# outputs.tf — the three things an operator (or a deploy script) needs after apply.

output "database_url" {
  description = "Neon connection string for the backend (postgresql+psycopg://...). Sensitive. View with: terraform output -raw database_url"
  value       = module.neon.database_url
  sensitive   = true
}

output "backend_url" {
  description = "Public HTTPS base URL of the Fly backend (set as the SPA's VITE_API_URL)."
  value       = module.backend_fly.backend_url
}

output "pages_url" {
  description = "Public URL of the deployed SPA."
  value       = module.frontend_pages.pages_url
}
