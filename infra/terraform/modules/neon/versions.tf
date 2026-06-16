# Declares which provider this module uses. Version is pinned once at the root
# (../../versions.tf) — modules must not re-pin, or the stack can drift.
terraform {
  required_providers {
    neon = {
      source = "kislerdm/neon"
    }
  }
}
