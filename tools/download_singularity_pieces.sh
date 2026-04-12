#!/bin/bash

set -euo pipefail

if (( ${BASH_VERSION%%.*} < 4 )); then
   >&2 echo "Requires bash version 4.0.0 or higher, you've got ${BASH_VERSION}"
   exit 1
fi

readonly SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OUTPUT_DIR=$(realpath -m "${SCRIPT_DIR}/pieces")
MANIFEST_FILE=""
MANIFEST_URL=""
HOST=""
JOBS=1
ARIA2C_INPUT_FILE=$(mktemp)
trap 'rm -f "$ARIA2C_INPUT_FILE"' EXIT

print_usage() {
  echo "Usage: $0 [-o output_dir] [-h host_url] [-j number_or_parallel_jobs] <manifest_url_or_file>"
  echo ""
  echo "Example:"
  echo "$0 http://111.22.333.44:7777/api/preparation/1/piece -o ./data -j 4 "
  echo "$0 ./manifest.json -h http://111.22.333.44:9000 "
}

init_args() {
  local manifest_url_or_file

  while [[ ${#} -gt 0 ]]; do
    case "${1}" in
    -o)
      OUTPUT_DIR=$(realpath -m "${2}")
      shift 2
      ;;
    -h)
      HOST="${2}"
      shift 2
      ;;
    -j)
      JOBS="${2}"
      shift 2
      ;;
    *)
      manifest_url_or_file="${1}"
      shift
      ;;
    esac
  done

  if [ -z "${manifest_url_or_file+x}" ]; then
    print_usage
    exit 1
  fi

  if ! test -f "${manifest_url_or_file}"; then
    MANIFEST_URL=${manifest_url_or_file}
    MANIFEST_FILE="${OUTPUT_DIR}/manifest.json"

    if [[ ! "${MANIFEST_URL}" =~ ^https?:// ]]; then
      MANIFEST_URL="http://${MANIFEST_URL}"
    fi

    if [ -z "${HOST+x}" ]; then
      HOST=$(echo "${MANIFEST_URL}" | sed -E 's|(https?://[^/]+).*|\1|')
    fi
  else
    MANIFEST_FILE=${manifest_url_or_file}

    if [ -z "${HOST+x}" ]; then
      echo "Error: host [-h host_url] must be provided when using local manifest file"
      exit 1
    fi
  fi

  MANIFEST_FILE=$(realpath -m "${MANIFEST_FILE}")
}

format_filesize() {
  numfmt --to=iec --suffix=B --format="%.2f" "${1}"
}

_fetch_manifest() {
  curl -fsS --max-time 360 "${1}" -o "${2}" || {
    echo "Error: failed to fetch manifest"
    exit 1
  }
}

fetch_manifest() {
  if [ -z "${MANIFEST_URL+x}" ]; then
    if test -f "${MANIFEST_FILE}"; then
        echo "Reading manifest from ${MANIFEST_FILE}"
    else
        echo "File not found: ${MANIFEST_FILE}"
    fi
  else
    if test -f "${MANIFEST_FILE}"; then
      local temp_manifest_file
      temp_manifest_file=$(mktemp)

      _fetch_manifest "${MANIFEST_URL}" "${temp_manifest_file}"

      if ! cmp -s "${temp_manifest_file}" "${MANIFEST_FILE}"; then
        echo "Error: existing manifest file ${MANIFEST_FILE} differs from fetched manifest"
        rm -f "${temp_manifest_file}"
        exit 1
      fi

      rm -f "${temp_manifest_file}"
    else
      echo "Saving manifest to ${MANIFEST_FILE}"
      _fetch_manifest "${MANIFEST_URL}" "${MANIFEST_FILE}"
    fi
  fi

  MANIFEST_JSON=$(<"${MANIFEST_FILE}")
}

write_aria2c_input_file() {
  local piece_cid storage_path expected_filesize
  local piece_name output_file download_url

  echo "${MANIFEST_JSON}" | jq -c '.[] | .pieces[]' | while IFS= read -r piece; do
    piece_cid=$(echo "${piece}" | jq -r '.pieceCid')
    storage_path=$(echo "${piece}" | jq -r '.storagePath')
    expected_filesize=$(echo "${piece}" | jq -r '.fileSize')
    expected_filesize=$(format_filesize "${expected_filesize}")

    piece_name="${storage_path%.car}"
    output_file="${OUTPUT_DIR}/${storage_path}"
    download_url="${HOST}/piece/${piece_name}"

    mkdir -p "$(dirname "${output_file}")"

    echo "${download_url}" >>"${ARIA2C_INPUT_FILE}"
    echo "  out=$(basename "${output_file}")" >>"${ARIA2C_INPUT_FILE}"
    echo "  dir=$(dirname "${output_file}")" >>"${ARIA2C_INPUT_FILE}"

    echo "${piece_cid}: ${download_url} -> ${output_file}: ${expected_filesize}"
  done
}

run_aria2c() {
  aria2c \
    -i "${ARIA2C_INPUT_FILE}" \
    -j "${JOBS}" \
    -x 4 \
    -s 4 \
    --continue=true \
    --auto-file-renaming=false \
    --summary-interval=1 \
    --console-log-level=warn
}

compare_filesizes() {
  local storage_path expected_filesize actual_filesize file

  echo "${MANIFEST_JSON}" | jq -c '.[] | .pieces[]' | while IFS= read -r piece; do
    storage_path=$(echo "${piece}" | jq -r '.storagePath')
    expected_filesize=$(echo "${piece}" | jq -r '.fileSize')
    expected_filesize=$(format_filesize "${expected_filesize}")
    actual_filesize=0
    file="${OUTPUT_DIR}/${storage_path}"

    if stat -c%s / >/dev/null 2>&1; then
      actual_filesize=$(stat -c%s "${file}")
    else
      actual_filesize=$(stat -f%z "${file}")
    fi

    actual_filesize=$(format_filesize "${actual_filesize}")
    echo "${file} (expected ${expected_filesize}, got ${actual_filesize})"
  done
}

main() {
  echo "Fetching manifest from: ${MANIFEST_URL}"
  echo "Manifest file:          ${MANIFEST_FILE}"
  echo "Using host:             ${HOST}"
  echo "Output dir:             ${OUTPUT_DIR}"
  if ((JOBS > 1)); then
    echo "Jobs:                   ${JOBS}"
  fi
  echo ""

  mkdir -p "${OUTPUT_DIR}"
  fetch_manifest

  write_aria2c_input_file
  echo ""

  run_aria2c
  rm -f "${ARIA2C_INPUT_FILE}"

  echo ""
  compare_filesizes
}

check_dep() {
  if ! command -v "${1}" >/dev/null; then
    echo "Error: ${1} not found"
    return 1
  fi
}

check_dep jq || exit 1
check_dep aria2c || exit 1
check_dep numfmt || exit 1
check_dep curl || exit 1

init_args "${@}"
main "${@}"
