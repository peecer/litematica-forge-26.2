#!/usr/bin/env bash
set -euo pipefail

FORGEMATICA_PROJECT=912441
FORGEMATICA_SOURCE_FILE=8423902
MAFGLIB_PROJECT=910766
MAFGLIB_SOURCE_FILE=8829584

work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT

fetch_source() {
  local project="$1"
  local file="$2"
  local out="$3"
  local url="https://www.curseforge.com/api/v1/mods/${project}/files/${file}/download"
  echo "Downloading $url"
  curl --fail --location --retry 4 --retry-all-errors --connect-timeout 30 "$url" -o "$out"
  unzip -tq "$out" >/dev/null
}

stage_source() {
  local module="$1"
  local jar="$2"
  local unpack="$work/unpack-$module"
  rm -rf "$module/src/main" "$unpack"
  mkdir -p "$module/src/main/java" "$module/src/main/resources" "$unpack"
  unzip -q "$jar" -d "$unpack"
  while IFS= read -r -d '' f; do
    local rel="${f#${unpack}/}"
    local dest
    if [[ "$rel" == *.java ]]; then
      dest="$module/src/main/java/$rel"
    else
      dest="$module/src/main/resources/$rel"
    fi
    mkdir -p "$(dirname "$dest")"
    cp "$f" "$dest"
  done < <(find "$unpack" -type f -print0)
}

fetch_source "$FORGEMATICA_PROJECT" "$FORGEMATICA_SOURCE_FILE" "$work/forgematica-sources.jar"
fetch_source "$MAFGLIB_PROJECT" "$MAFGLIB_SOURCE_FILE" "$work/mafglib-sources.jar"

stage_source forgematica "$work/forgematica-sources.jar"
stage_source mafglib "$work/mafglib-sources.jar"

cat port/overlay/part*.b64 | tr -d '\r\n' | base64 --decode | gzip --decompress > "$work/forge-port.patch"
git apply --ignore-space-change --ignore-whitespace --recount "$work/forge-port.patch"

echo "Staged Java files:"
printf '  Forgematica: '
find forgematica/src/main/java -type f -name '*.java' | wc -l
printf '  MaFgLib: '
find mafglib/src/main/java -type f -name '*.java' | wc -l

python3 tools/audit_port.py
