#!/bin/sh
set -eu
ROOT=$(CDPATH= cd "$(dirname "$0")" && pwd)
mkdir -p "$ROOT/runtime/vulkan"

cc -std=gnu11 -O2 -Wall -Wextra -fPIC -shared -DZEITOP_GL_ONLY \
  -o "$ROOT/runtime/libzeitop-gl.so" "$ROOT/limiter.c" -ldl
cc -m32 -std=gnu11 -O2 -Wall -Wextra -fPIC -shared -DZEITOP_GL_ONLY \
  -o "$ROOT/runtime/libzeitop-gl32.so" "$ROOT/limiter.c" -ldl
cc -std=gnu11 -O2 -Wall -Wextra -fPIC -shared -Wl,-Bsymbolic-functions -DZEITOP_PACING_ONLY \
  -I"$ROOT/vendor/vulkan" \
  -o "$ROOT/runtime/vulkan/libzeitop-vulkan.so" \
  "$ROOT/vulkan_layer.c" "$ROOT/limiter.c" -pthread -ldl
cc -m32 -std=gnu11 -O2 -Wall -Wextra -fPIC -shared -Wl,-Bsymbolic-functions -DZEITOP_PACING_ONLY \
  -I"$ROOT/vendor/vulkan" \
  -o "$ROOT/runtime/vulkan/libzeitop-vulkan32.so" \
  "$ROOT/vulkan_layer.c" "$ROOT/limiter.c" -pthread -ldl

# A second, read-only Vulkan observer sits downstream of lsfg-vk.
# It is a separate library so the generated frames are never paced again.
cc -std=gnu11 -O2 -Wall -Wextra -fPIC -shared -Wl,-Bsymbolic-functions \
  -DZEITOP_PACING_ONLY -DZEITOP_OUTPUT_TELEMETRY \
  -I"$ROOT/vendor/vulkan" \
  -o "$ROOT/runtime/vulkan/libzeitop-output.so" \
  "$ROOT/vulkan_layer.c" "$ROOT/limiter.c" -pthread -ldl
cc -m32 -std=gnu11 -O2 -Wall -Wextra -fPIC -shared -Wl,-Bsymbolic-functions \
  -DZEITOP_PACING_ONLY -DZEITOP_OUTPUT_TELEMETRY \
  -I"$ROOT/vendor/vulkan" \
  -o "$ROOT/runtime/vulkan/libzeitop-output32.so" \
  "$ROOT/vulkan_layer.c" "$ROOT/limiter.c" -pthread -ldl

cat > "$ROOT/runtime/vulkan/VkLayer_ZeitopOutput_64.json" <<'EOF'
{
  "file_format_version": "1.2.1",
  "layer": {
    "name": "VK_LAYER_ZEITOP_output",
    "type": "GLOBAL",
    "api_version": "1.4.0",
    "library_path": "./libzeitop-output.so",
    "library_arch": "64",
    "implementation_version": "1",
    "description": "Zeitop downstream frame-output telemetry"
  }
}
EOF
cat > "$ROOT/runtime/vulkan/VkLayer_ZeitopOutput_32.json" <<'EOF'
{
  "file_format_version": "1.2.1",
  "layer": {
    "name": "VK_LAYER_ZEITOP_output",
    "type": "GLOBAL",
    "api_version": "1.4.0",
    "library_path": "./libzeitop-output32.so",
    "library_arch": "32",
    "implementation_version": "1",
    "description": "Zeitop downstream frame-output telemetry"
  }
}
EOF

cat > "$ROOT/runtime/vulkan/VkLayer_Zeitop_64.json" <<'EOF'
{
  "file_format_version": "1.2.1",
  "layer": {
    "name": "VK_LAYER_ZEITOP_pacing",
    "type": "GLOBAL",
    "api_version": "1.4.0",
    "library_path": "./libzeitop-vulkan.so",
    "library_arch": "64",
    "implementation_version": "1",
    "description": "Zeitop 64-bit frame presentation pacing"
  }
}
EOF
cat > "$ROOT/runtime/vulkan/VkLayer_Zeitop_32.json" <<'EOF'
{
  "file_format_version": "1.2.1",
  "layer": {
    "name": "VK_LAYER_ZEITOP_pacing",
    "type": "GLOBAL",
    "api_version": "1.4.0",
    "library_path": "./libzeitop-vulkan32.so",
    "library_arch": "32",
    "implementation_version": "1",
    "description": "Zeitop 32-bit frame presentation pacing"
  }
}
EOF
# Remove only the retired project-local manifest, so it cannot shadow the arch variants.
rm -f "$ROOT/runtime/vulkan/VkLayer_Zeitop.json"
printf 'Zeitop: built Vulkan, output telemetry and GL integration for 64-bit and 32-bit.\n'
