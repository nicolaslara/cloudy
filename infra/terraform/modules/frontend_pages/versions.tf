# This module manages Cloudflare resources. Version pinned once at the root.
terraform {
  required_providers {
    cloudflare = {
      source = "cloudflare/cloudflare"
    }
  }
}
