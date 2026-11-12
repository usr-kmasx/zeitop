#!/bin/sh
set -eu
ROOT=$(CDPATH= cd "$(dirname "$0")" && pwd)
if [ ! -f "$ROOT/runtime/vulkan/libzeitop-vulkan.so" ] ||
   [ ! -f "$ROOT/runtime/vulkan/libzeitop-vulkan32.so" ] ||
   [ ! -f "$ROOT/runtime/libzeitop-gl.so" ] ||
   [ ! -f "$ROOT/runtime/libzeitop-gl32.so" ] ||
   [ "$ROOT/vulkan_layer.c" -nt "$ROOT/runtime/vulkan/libzeitop-vulkan.so" ] ||
   [ "$ROOT/limiter.c" -nt "$ROOT/runtime/libzeitop-gl.so" ]; then
    "$ROOT/build.sh"
fi
export XDG_CACHE_HOME="$ROOT/runtime/cache"
export XDG_CONFIG_HOME="$ROOT/runtime/config"
export XDG_DATA_HOME="$ROOT/runtime/data"
export PYTHONDONTWRITEBYTECODE=1
exec python3 -B "$ROOT/app.py"
