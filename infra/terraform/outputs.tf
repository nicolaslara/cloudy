# outputs.tf — the three things an operator (or a deploy script) needs after apply.

output "database_url" {
  description = "Neon connection string for the backend (postgresql+psycopg://...), via the pooled host. Sensitive. View with: terraform output -raw database_url"
  value       = module.neon.database_url
  sensitive   = true
}

output "database_url_direct" {
  description = "Neon connection string via the DIRECT (non-pooled) host, for the one-off backfill and other long bulk jobs. Sensitive. View with: terraform output -raw database_url_direct"
  value       = module.neon.database_url_direct
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

output "raw_archive_bucket" {
  description = "Cloudflare R2 bucket that stores the compressed data/raw archive."
  value       = cloudflare_r2_bucket.raw_archive.name
}
