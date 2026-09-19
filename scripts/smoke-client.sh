#!/usr/bin/env bash
set -euo pipefail

mkdir -p ci-output
OUT="ci-output/client-smoke-console.log"
RUN_DIR="smoke/run"
RUN_LOG="$RUN_DIR/logs/latest.log"

rm -rf "$RUN_DIR"
mkdir -p "$RUN_DIR/mods"

LITEMATICA_JAR="$(find forgematica/build/libs -maxdepth 1 -type f -name '*.jar' ! -name '*-sources.jar' ! -name '*-slim.jar' | head -n 1)"
MAFGLIB_JAR="$(find mafglib/build/libs -maxdepth 1 -type f -name '*.jar' ! -name '*-sources.jar' ! -name '*-slim.jar' | head -n 1)"

test -n "$LITEMATICA_JAR"
test -n "$MAFGLIB_JAR"

cp "$LITEMATICA_JAR" "$RUN_DIR/mods/"
cp "$MAFGLIB_JAR" "$RUN_DIR/mods/"

echo "Smoke-testing packaged jars:"
ls -lh "$RUN_DIR/mods"

echo "Verifying required MaLiLib runtime shaders are inside the packaged JAR..."
for shader in   assets/malilib/shaders/legacy_terrain.vsh   assets/malilib/shaders/legacy_terrain.fsh   assets/malilib/shaders/int_position_color.vsh   assets/malilib/shaders/int_position_color.fsh
do
  if ! unzip -l "$MAFGLIB_JAR" | grep -F -q "$shader"; then
    echo "Missing packaged shader: $shader"
    echo "Available MaLiLib shader entries:"
    unzip -l "$MAFGLIB_JAR" | grep -E 'assets/malilib/.+shader|assets/malilib/shaders' || true
    exit 1
  fi
done

echo "Verifying Litematica 26.2 shader layout..."
for shader in \
  assets/litematica/shaders/core/legacy_terrain.vsh \
  assets/litematica/shaders/core/legacy_terrain.fsh
do
  if ! unzip -l "$LITEMATICA_JAR" | grep -F -q "$shader"; then
    echo "Missing packaged shader: $shader"
    exit 1
  fi
done

echo "Launching clean Forge client under Xvfb for a bounded smoke test..."
set +e
timeout --signal=INT --kill-after=20s 180s \
  xvfb-run -a \
  env LIBGL_ALWAYS_SOFTWARE=1 \
  gradle --no-daemon --stacktrace :smoke:runClient \
  >"$OUT" 2>&1
status=$?
set -e

if [[ -f "$RUN_LOG" ]]; then
  cp "$RUN_LOG" ci-output/client-smoke-latest.log
fi

combined="$(mktemp)"
trap 'rm -f "$combined"' EXIT
cat "$OUT" > "$combined"
if [[ -f "$RUN_LOG" ]]; then
  printf '\n===== latest.log =====\n' >> "$combined"
  cat "$RUN_LOG" >> "$combined"
fi

tail -n 800 "$combined" || true

fatal_pattern='MixinTransformerError|InvalidMixinException|Mixin apply failed|Critical injection failure|InjectionError|ModLoadingException|Failed to create mod instance|NoClassDefFoundError|ClassNotFoundException|NoSuchMethodError|NoSuchFieldError|IllegalAccessError|VerifyError|Exception in thread "[^"]+"|java\.lang\.LinkageError|Could not launch|Failed to load mod|EarlyLoadingException|Dependency restrictions were not met'

if grep -E -i "$fatal_pattern" "$combined" >/dev/null; then
  echo "Fatal startup signature detected during packaged-jar Minecraft smoke launch."
  grep -E -i -n "$fatal_pattern" "$combined" | tail -n 120 || true
  exit 1
fi

case "$status" in
  0)
    echo "Minecraft client exited cleanly during smoke test."
    ;;
  124|130|143)
    echo "Minecraft client stayed alive until the bounded timeout; treating that as a successful smoke launch."
    ;;
  *)
    echo "Minecraft client process exited unexpectedly with status $status."
    exit "$status"
    ;;
esac

# Require evidence that Forge found both distribution jars and reached client startup.
for expected in 'litematica-forge-26.2' 'mafglib-forge-26.2'; do
  if ! grep -F -i "$expected" "$combined" >/dev/null; then
    echo "Packaged mod $expected was not discovered by Forge during smoke launch."
    exit 1
  fi
done

if ! grep -E -i 'ModLauncher running|Render thread|Reloading ResourceManager|OpenAL initialized|Created:.*atlas|Setting user:' "$combined" >/dev/null; then
  echo "No evidence that Minecraft reached client startup."
  exit 1
fi

echo "Packaged-jar Minecraft client smoke test PASSED."
