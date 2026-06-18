#!/usr/bin/env sh
set -eu

# Upload/download the gitignored data/raw archive to Cloudflare R2.
# The archive is operator data: it keeps production ingest jobs from re-fetching
# SMHI history, but it is not part of the application image or git history.

ROOT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
MODE="${1:-}"
BUCKET="${RAW_ARCHIVE_BUCKET:-}"
OBJECT="${RAW_ARCHIVE_OBJECT:-smhi-raw.tar.gz}"
ARCHIVE="${RAW_ARCHIVE_FILE:-$ROOT_DIR/tmp/$OBJECT}"

bucket_name() {
  if [ -n "$BUCKET" ]; then
    printf '%s\n' "$BUCKET"
    return
  fi
  terraform -chdir="$ROOT_DIR/infra/terraform" output -raw raw_archive_bucket
}

wrangler() {
  if command -v wrangler >/dev/null 2>&1; then
    wrangler "$@"
  elif command -v npx >/dev/null 2>&1; then
    npx --yes wrangler "$@"
  else
    echo "wrangler or npx is required for R2 archive sync" >&2
    exit 127
  fi
}

case "$MODE" in
  upload)
    if [ ! -d "$ROOT_DIR/data/raw" ]; then
      echo "missing $ROOT_DIR/data/raw; run local ingest before uploading" >&2
      exit 1
    fi
    mkdir -p "$(dirname "$ARCHIVE")"
    tar -czf "$ARCHIVE" -C "$ROOT_DIR/data" raw
    wrangler r2 object put "$(bucket_name)/$OBJECT" --file "$ARCHIVE"
    ;;
  download)
    mkdir -p "$(dirname "$ARCHIVE")" "$ROOT_DIR/data"
    wrangler r2 object get "$(bucket_name)/$OBJECT" --file "$ARCHIVE"
    tar -xzf "$ARCHIVE" -C "$ROOT_DIR/data"
    ;;
  *)
    echo "usage: scripts/raw-archive.sh [upload|download]" >&2
    exit 2
    ;;
esac
