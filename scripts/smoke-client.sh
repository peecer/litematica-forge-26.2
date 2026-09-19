#!/usr/bin/env bash
set -euo pipefail

mkdir -p ci-output
OUT="ci-output/client-smoke-console.log"
RUN_LOG="forgematica/run/logs/latest.log"
rm -rf forgematica/run
mkdir -p forgematica/run

echo "Launching Forge development client under Xvfb for a bounded smoke test..."
set +e
timeout --signal=INT --kill-after=20s 150s   xvfb-run -a   env LIBGL_ALWAYS_SOFTWARE=1   gradle --no-daemon --stacktrace :forgematica:runClient   >"$OUT" 2>&1
status=$?
set -e

# Preserve the game log separately if Minecraft created one.
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

# Print the tail into Actions for immediate debugging.
tail -n 500 "$combined" || true

fatal_pattern='MixinTransformerError|InvalidMixinException|Mixin apply failed|Critical injection failure|InjectionError|ModLoadingException|Failed to create mod instance|NoClassDefFoundError|ClassNotFoundException|NoSuchMethodError|NoSuchFieldError|IllegalAccessError|VerifyError|Exception in thread "[^"]+"|java\.lang\.LinkageError|Could not launch|Failed to load mod'

if grep -E -i "$fatal_pattern" "$combined" >/dev/null; then
  echo "Fatal startup signature detected during Minecraft smoke launch."
  grep -E -i -n "$fatal_pattern" "$combined" | tail -n 80 || true
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

# Require evidence that ModLauncher progressed into the actual client, not just Gradle setup.
if ! grep -E -i 'ModLauncher running|Launching target.*forge_client|Render thread|Reloading ResourceManager|OpenAL initialized|Created:.*atlas|Setting user:' "$combined" >/dev/null; then
  echo "No evidence that Minecraft reached client startup."
  exit 1
fi

echo "Minecraft client smoke test PASSED."
