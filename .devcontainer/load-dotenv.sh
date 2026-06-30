#!/usr/bin/env bash
# Export the variables defined in the workspace-root .env into the current
# shell, so the backend (uvicorn) and any tooling started inside the dev
# container see AZURE_OPENAI_* and the service-principal vars automatically.
# With the SP vars present, DefaultAzureCredential's EnvironmentCredential can
# authenticate without a separate `az login`.
#
# Sourced from ~/.bashrc (wired up by the dev container postCreateCommand). It
# is a safe no-op when .env is absent so terminals always open. Lines are
# parsed individually (never `source`d) so a secret containing shell
# metacharacters ($, backticks, ...) is never expanded, and `tr -d '\r'`
# tolerates .env files saved with Windows CRLF line endings.

# Resolve the workspace root from this script's location (.devcontainer/..).
__dotenv_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
__dotenv_file="$__dotenv_root/.env"

if [ -f "$__dotenv_file" ]; then
  # Process substitution (not a pipe) keeps the loop in this shell so exports
  # persist. The grep keeps only valid KEY=VALUE assignment lines, skipping
  # blanks and comments.
  while IFS='=' read -r __dotenv_key __dotenv_val; do
    # Strip optional surrounding single or double quotes from the value.
    __dotenv_val="${__dotenv_val%\"}"; __dotenv_val="${__dotenv_val#\"}"
    __dotenv_val="${__dotenv_val%\'}"; __dotenv_val="${__dotenv_val#\'}"
    export "$__dotenv_key=$__dotenv_val"
  done < <(grep -E '^[A-Za-z_][A-Za-z0-9_]*=' "$__dotenv_file" | tr -d '\r')
fi

unset __dotenv_root __dotenv_file __dotenv_key __dotenv_val
