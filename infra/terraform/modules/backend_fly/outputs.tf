# The backend's public HTTPS URL. Fly serves every app at
# https://<app-name>.fly.dev with TLS, so we derive it from the app name rather
# than reading an IP — that's the URL the frontend (VITE_API_URL) targets.
output "backend_url" {
  description = "Public HTTPS base URL of the backend API."
  value       = "https://${fly_app.this.name}.fly.dev"
}

output "app_name" {
  description = "Fly app name (echoed for convenience / scripting)."
  value       = fly_app.this.name
}
