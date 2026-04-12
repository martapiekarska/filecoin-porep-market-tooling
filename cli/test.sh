#!/bin/bash

# Testing and development purposes.
# Simple tool that runs all CLI get commands that requires no user input.

set -euo pipefail

# shellcheck disable=SC2155
readonly SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

(
  "${SCRIPT_DIR}"/../porep_tooling_cli.py >/dev/null &&
  "${SCRIPT_DIR}"/../porep_tooling_cli.py info --help >/dev/null &&

  "${SCRIPT_DIR}"/../porep_tooling_cli.py admin --address "0x5CF0365dA2F0a83c70Dfb4b96067c0e3cd2Ea951" info >/dev/null &&
  "${SCRIPT_DIR}"/../porep_tooling_cli.py admin --private-key "b73163861add8c8280f62958432131b7a5e69a9276a3cfa26fcaa92ff356fadc" info >/dev/null &&
  "${SCRIPT_DIR}"/../porep_tooling_cli.py admin get-deals --help>/dev/null &&

  "${SCRIPT_DIR}"/../porep_tooling_cli.py admin get-deals proposed >/dev/null &&
  "${SCRIPT_DIR}"/../porep_tooling_cli.py admin get-devnet-sps >/dev/null &&
  "${SCRIPT_DIR}"/../porep_tooling_cli.py admin get-registered-sps >/dev/null &&
  "${SCRIPT_DIR}"/../porep_tooling_cli.py admin get-db-sps --help >/dev/null &&
  "${SCRIPT_DIR}"/../porep_tooling_cli.py admin register-db-sps --help >/dev/null &&
  "${SCRIPT_DIR}"/../porep_tooling_cli.py admin register-devnet-sps --help >/dev/null &&

  "${SCRIPT_DIR}"/../porep_tooling_cli.py client get-deals rejected >/dev/null &&
  "${SCRIPT_DIR}"/../porep_tooling_cli.py client get-filecoin-pay-account >/dev/null &&
  "${SCRIPT_DIR}"/../porep_tooling_cli.py client init-accepted-deals --help >/dev/null &&
  "${SCRIPT_DIR}"/../porep_tooling_cli.py client deposit-for-all-deals --help >/dev/null &&
  "${SCRIPT_DIR}"/../porep_tooling_cli.py client propose-deal-from-manifest --help >/dev/null &&

  "${SCRIPT_DIR}"/../porep_tooling_cli.py sp get-deals accepted >/dev/null &&
  "${SCRIPT_DIR}"/../porep_tooling_cli.py sp accept-deal --help >/dev/null &&
  "${SCRIPT_DIR}"/../porep_tooling_cli.py sp reject-deal --help >/dev/null &&
  "${SCRIPT_DIR}"/../porep_tooling_cli.py sp manage-proposed-deals --help >/dev/null &&


  echo "All tests passed"
) || {
  echo "Error: CLI test failed"
  exit 1
}
