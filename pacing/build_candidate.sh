#!/bin/sh
# Build only the experimental Stage 2 layer; never overwrite production files.
set -eu
ROOT=$(CDPATH= cd "$(dirname "$0")/.." && pwd)
OUT="$ROOT/runtime/stage2"
mkdir -p "$OUT"
for arch in 64 32; do
  if [ "$arch" = 64 ]; then
    FLAGS=""
    LIB="$OUT/libzeitop-stage2.so"
  else
    FLAGS="-m32"
    LIB="$OUT/libzeitop-stage2-32.so"
  fi
  cc $FLAGS -std=gnu11 -O2 -Wall -Wextra -Werror \
    -fPIC -shared -Wl,-Bsymbolic-functions \
    -I"$ROOT/vendor/vulkan" -I"$ROOT/pacing" \
    -o "$LIB" \
    "$ROOT/pacing/vulkan_frame_layer.c" \
    "$ROOT/pacing/frame_controller.c" \
    "$ROOT/pacing/frame_runtime.c" \
    "$ROOT/pacing/present_telemetry.c" \
    -pthread -ldl
  cat > "$OUT/VkLayer_Zeitop_$arch.json" <<EOF
{
  "file_format_version": "1.2.1",
  "layer": {
    "name": "VK_LAYER_ZEITOP_pacing",
    "type": "GLOBAL",
    "api_version": "1.4.0",
    "library_path": "./$(basename "$LIB")",
    "library_arch": "$arch",
    "implementation_version": "2",
    "description": "Zeitop stage 2 per-swapchain frame pacing experiment"
  }
}
EOF
done
printf 'Stage 2 experimental Vulkan layer built (64 + 32 bit)\n'
