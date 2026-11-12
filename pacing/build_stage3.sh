#!/bin/sh
set -eu
ROOT=$(CDPATH= cd "$(dirname "$0")/.." && pwd)
OUT="$ROOT/runtime/stage3"
mkdir -p "$OUT"
cc -std=gnu11 -O2 -Wall -Wextra -Werror \
  -I"$ROOT/vendor/vulkan" \
  -I"$ROOT/runtime/audit_pacing/source" \
  -I"$OUT" \
  -I"$ROOT/pacing" \
  -o "$OUT/present_probe" \
  "$ROOT/tests/stage3_present_probe.c" \
  "$ROOT/pacing/timed_present_run.c" \
  "$ROOT/pacing/workload.c" \
  "$OUT/xdg-shell-protocol.c" \
  -lvulkan -lwayland-client
printf 'Zeitop isolated presentation probe compiled.\n'
