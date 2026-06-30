#!/usr/bin/env bash
# Sign the Azure CLI in as the service principal defined in .env.
#
# Wired to postStartCommand so it runs on every container start. It is a safe
# no-op when the service-principal variables are absent, so it never blocks the
# container from opening. The client secret is never printed.

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="$ROOT/.env"

if [ ! -f "$ENV_FILE" ]; then
  echo "az-login: no .env found; skipping service-principal sign-in."
  exit 0
fi

# Read only the SP variables. We parse instead of sourcing .env so a secret
# containing shell metacharacters ($, backticks, ...) is never expanded.
# tr -d '\r' tolerates .env files saved with Windows CRLF line endings.
AZURE_TENANT_ID=""
AZURE_CLIENT_ID=""
AZURE_CLIENT_SECRET=""
while IFS='=' read -r key val; do
  # Strip optional surrounding single or double quotes.
  val="${val%\"}"; val="${val#\"}"; val="${val%\'}"; val="${val#\'}"
  case "$key" in
    AZURE_TENANT_ID) AZURE_TENANT_ID="$val" ;;
    AZURE_CLIENT_ID) AZURE_CLIENT_ID="$val" ;;
    AZURE_CLIENT_SECRET) AZURE_CLIENT_SECRET="$val" ;;
  esac
done < <(grep -E '^[[:space:]]*AZURE_(TENANT_ID|CLIENT_ID|CLIENT_SECRET)=' "$ENV_FILE" | tr -d '\r' || true)

missing=""
[ -z "$AZURE_TENANT_ID" ] && missing="$missing AZURE_TENANT_ID"
[ -z "$AZURE_CLIENT_ID" ] && missing="$missing AZURE_CLIENT_ID"
[ -z "$AZURE_CLIENT_SECRET" ] && missing="$missing AZURE_CLIENT_SECRET"
if [ -n "$missing" ]; then
  echo "az-login: missing in .env:$missing; skipping az login."
  exit 0
fi

if az login --service-principal \
    --username "$AZURE_CLIENT_ID" \
    --password "$AZURE_CLIENT_SECRET" \
    --tenant "$AZURE_TENANT_ID" \
    --output none 2>/dev/null; then
  echo "az-login: signed in as service principal $AZURE_CLIENT_ID"
else
  echo "az-login: service-principal sign-in failed (continuing)."
fi

exit 0
