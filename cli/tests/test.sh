#!/bin/bash

# Simple tool that runs all CLI get commands that requires no user input.
# Expects process exit code and nothing more.
# This is not designed to be a comprehensive test suite.
# Private keys are generated fresh on every run: never commit key material (see .gitleaks.toml).

set -euo pipefail

# shellcheck disable=SC2155
readonly SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly CLI_PATH="${SCRIPT_DIR}/../../porep_tooling_cli.py"

# export all env vars from .env.test
set -a
source "${SCRIPT_DIR}/.env.test"
export DEBUG=true
set +a

# Ephemeral test keys: random, never funded, different on every run
new_key() { python3 -c 'import secrets; print(secrets.token_hex(32))'; }
key_address() { python3 -c 'import sys; from eth_account import Account; print(Account.from_key(sys.argv[1]).address)' "$1"; }

ENV_KEY="0x$(new_key)"  # the role keys normally set in .env
export CLIENT_PRIVATE_KEY="${ENV_KEY}" ADMIN_PRIVATE_KEY="${ENV_KEY}" SP_PRIVATE_KEY="${ENV_KEY}"
readonly ENV_ADDRESS="$(key_address "${ENV_KEY}")"
readonly ADMIN_ARG_KEY="$(new_key)"
readonly TEST_KEY="$(new_key)"
readonly TEST_ADDRESS="$(key_address "${TEST_KEY}")"
readonly OTHER_ADDRESS="$(key_address "$(new_key)")"  # an address none of the keys above matches

(
  # misc tests
  python3 "${CLI_PATH}"               >/dev/null &&
  python3 "${CLI_PATH}" config --help >/dev/null &&

  python3 "${CLI_PATH}" client --address "${ENV_ADDRESS}" info                          >/dev/null &&
  ADMIN_PRIVATE_KEY="${ADMIN_ARG_KEY}" python3 "${CLI_PATH}" admin info >/dev/null &&
  python3 "${CLI_PATH}" sp --organization "${ENV_ADDRESS}" info                         >/dev/null &&
  python3 "${CLI_PATH}" admin get-deals --help                                                                      >/dev/null &&

  # admin tests
  python3 "${CLI_PATH}" admin get-deals proposed         >/dev/null   &&
  python3 "${CLI_PATH}" admin get-sps                    >/dev/null   &&
  python3 "${CLI_PATH}" admin get-db-sps --help          >/dev/null   &&
  python3 "${CLI_PATH}" admin register-db-sps --help     >/dev/null   &&
  python3 "${CLI_PATH}" admin terminate-deal --help      >/dev/null   &&
  python3 "${CLI_PATH}" admin finalize-deal --help       >/dev/null   &&
  ! (python3 "${CLI_PATH}" admin get-deal        4242 >/dev/null 2>&1) &&
  ! (python3 "${CLI_PATH}" admin terminate-deal  4242 >/dev/null 2>&1) &&
  ! (python3 "${CLI_PATH}" admin finalize-deal   4242 >/dev/null 2>&1) &&

  # client tests
  python3 "${CLI_PATH}" client get-deals rejected                >/dev/null &&
  python3 "${CLI_PATH}" client get-filecoinpay-account           >/dev/null &&
  python3 "${CLI_PATH}" client init-deal --help                  >/dev/null &&
  python3 "${CLI_PATH}" client deposit-for-deals --help          >/dev/null &&
  python3 "${CLI_PATH}" client propose-deal --help               >/dev/null &&
  python3 "${CLI_PATH}" client deposit-amount --help             >/dev/null &&
  python3 "${CLI_PATH}" client pay-repair-retrieval --help       >/dev/null &&
  ! (python3 "${CLI_PATH}" client get-deal    4242 >/dev/null 2>&1)         &&

  # sp tests
  python3 "${CLI_PATH}" sp get-deals accepted           >/dev/null &&
  python3 "${CLI_PATH}" sp onboard-data --help         >/dev/null &&
  ! (python3 "${CLI_PATH}" sp get-deal    4242 >/dev/null 2>&1)    &&

  # test keys

  # not matching keys but info command should work
  (CLIENT_PRIVATE_KEY="${TEST_KEY}" \
    python3 "${CLI_PATH}" client --address "${OTHER_ADDRESS}" info >/dev/null) &&

  CLIENT_PRIVATE_KEY="${TEST_KEY}" python3 "${CLI_PATH}" client --address "${OTHER_ADDRESS}" info >/dev/null &&

  # not matching keys but get commands should work
  (CLIENT_PRIVATE_KEY="${TEST_KEY}" \
    python3 "${CLI_PATH}" client --address "${OTHER_ADDRESS}" get-deals >/dev/null) &&  # not matching with env

  CLIENT_PRIVATE_KEY="${TEST_KEY}" python3 "${CLI_PATH}" client --address "${OTHER_ADDRESS}" get-deals >/dev/null &&

  # matching keys
  CLIENT_PRIVATE_KEY="${TEST_KEY}" python3 "${CLI_PATH}" client --address "${TEST_ADDRESS}" info --test-keys >/dev/null &&
  CLIENT_PRIVATE_KEY="${TEST_KEY}" python3 "${CLI_PATH}" client info --test-keys >/dev/null &&

  (CLIENT_PRIVATE_KEY="${TEST_KEY}" \
    python3 "${CLI_PATH}" client --address "${TEST_ADDRESS}" info --test-keys >/dev/null) &&

  (CLIENT_PRIVATE_KEY="${TEST_KEY}" \
    python3 "${CLI_PATH}" client info --test-keys >/dev/null) &&

  # fail when no matching keys
  ! (CLIENT_PRIVATE_KEY="${TEST_KEY}" \
    python3 "${CLI_PATH}" client --address "${OTHER_ADDRESS}" info --test-keys >/dev/null 2>&1) &&

  ! (CLIENT_PRIVATE_KEY="${TEST_KEY}" python3 "${CLI_PATH}" client --address "${OTHER_ADDRESS}" info --test-keys >/dev/null 2>&1) &&

  # keys are never accepted on the command line (shell history, process list)
  ! (python3 "${CLI_PATH}" client --private-key "${TEST_KEY}" info >/dev/null 2>&1) &&

  # dont fail when no keys provided for get commands
  CLIENT_PRIVATE_KEY="" \
    python3 "${CLI_PATH}" client --address "${OTHER_ADDRESS}" get-deals >/dev/null &&

  CLIENT_PRIVATE_KEY="" \
    python3 "${CLI_PATH}" client --address "${OTHER_ADDRESS}" get-deals >/dev/null &&

  ADMIN_PRIVATE_KEY="" \
    python3 "${CLI_PATH}" admin get-deals >/dev/null &&

  echo "All tests passed"
) || {
  echo "Error: CLI test failed: expected different exit code" >&2
  exit 1
}
