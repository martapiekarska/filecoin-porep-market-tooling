#!/bin/bash
# Usage: source cli/tests/e2e/load-env.sh
# Loads the public e2e config (.env.e2e), then local secrets (.env.e2e.local), then a Lotus API token, which is never
# committed: read from cli/tests/e2e/.lotus-token, or freshly created with lotus and stored there (owner-only).

E2E_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

set -a
# shellcheck source=/dev/null
source "${E2E_DIR}/.env.e2e"
# shellcheck source=/dev/null
[[ -f "${E2E_DIR}/.env.e2e.local" ]] && source "${E2E_DIR}/.env.e2e.local"
set +a

if [[ -z "${LOTUS_TOKEN:-}" ]]; then
    LOTUS_TOKEN_FILE="${E2E_DIR}/.lotus-token"

    if [[ ! -s "${LOTUS_TOKEN_FILE}" ]] && command -v lotus >/dev/null 2>&1; then
        (umask 077 && lotus auth create-token --perm sign > "${LOTUS_TOKEN_FILE}")
    fi

    if [[ -s "${LOTUS_TOKEN_FILE}" ]]; then
        LOTUS_TOKEN="$(< "${LOTUS_TOKEN_FILE}")"
        export LOTUS_TOKEN
    else
        echo "load-env.sh: no Lotus token; put one in ${LOTUS_TOKEN_FILE} or install lotus" >&2
    fi
fi
