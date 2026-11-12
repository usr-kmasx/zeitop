# Frame Generation settings — external lsfg-vk 2.x

Status: the external config editor is implemented on feature/lsfg-settings.
The original V12.11.26 frame limiter and launcher remain unchanged.
Combined Zeitop + lsfg-vk layer activation is not approved or guaranteed yet.

## License and ownership

Zeitop does not include, modify, patch, or redistribute lsfg-vk's source,
binary layer, Vulkan manifests, or proprietary Lossless Scaling DLL.
Users install lsfg-vk independently and must legally own Lossless Scaling
to obtain its lsfg-vk.dll.

lsfg-vk 2.x is CC BY-NC-ND 4.0. For derivatives or deeper integration,
the author requests contact at derivatives@lsfg-vk.dev.

Authoritative references:
- https://lsfg-vk.dev/docs/configuration/
- https://lsfg-vk.dev/docs/configuration/configuration-options/
- https://lsfg-vk.dev/docs/cli/
- https://lsfg-vk.dev/docs/contributing/

## Using the editor

1. Start Zeitop normally with ./run.sh.
2. Click the Settings gear to open Frame Generation Settings in English.
3. Check the detected lsfg-vk conf.toml; use Browse if necessary.
4. Select your own lsfg-vk.dll using Browse (or leave blank for auto-detection).
5. Select, add, duplicate, or remove profiles in the left column.
6. Edit profile properties on the right, and global settings below.
7. Select Save Changes; the selected ORIGINAL file is validated and written
   atomically. Reload rereads it and discards unsaved edits.

Path discovery considers LSFGVK_CONFIG, existing files under XDG_CONFIG_HOME,
then the conventional ~/.config/lsfg-vk/conf.toml. Zeitop's WebKit private
cache directory is not used to create a new lsfg-vk config.

## Supported version 2 fields

Global: dll, allow_fp16, log_level, log_file.
Profile: name, active_in, multiplier (1 to 1024 in this editor, with 2x/3x/4x presets), flow_scale (0.25 to 1.0),
performance_mode, pacing_mode (only vsync), override_present_mode,
preserve_swapchain_image_count.

The editor follows the v2 sample's pacing_mode field, checked against
lsfg-vk-cli. No unsupported pacing mode is offered.

For changes, Python's tomllib validates TOML and installed lsfg-vk-cli
validates a temporary candidate. Comments and unknown fields in unchanged
sections are retained. A private timestamped backup is saved beside the
original file before an atomic replacement. Conflicting external edits,
invalid DLLs, and unsupported v1 or complex nested profile formats are
rejected rather than being guessed.

The user's absolute config and DLL paths are runtime-only data and are
NEVER hardcoded into project sources or published.

## Combined layer ordering

The settings window edits lsfg-vk only; it does NOT automatically activate
Frame Generation or assert that it works after Zeitop's 30 FPS limiter.
The lsfg-vk implicit layer is managed by the user's separate installation.

Before enabling a combined FG mode we must verify, in a game:
- The exact Vulkan layer and present call order;
- Real frame pacing versus generated output cadence;
- No re-limiting of interpolated frames;
- Proton/DXVK, VSync/FIFO and MangoHud interactions;
- Any required authorization for deeper integration.

Without this evidence, the V12.11.26 limiter stays stable and independent.

### Current read-only Vulkan loader finding

The installed lsfg-vk-cli and layer report version 2.0.0, and
lsfg-vk-cli healthcheck and validate both pass. However, a read-only
Zeitop + vulkaninfo test logged a Vulkan loader error indicating that
the external lsfg-vk layer could not supply vkGetInstanceProcAddr.
This was **not** a game test. The underlying cause and combined layer
ordering therefore remain unverified. Zeitop neither modifies that
external layer nor suppresses this error.

The unmodified loader logs are stored in local ignored runtime files,
not in the Git repository.

## Testing

Run the existing Python unittest suite and JavaScript syntax checks.
Frame Generation tests work only on synthetic temporary TOML files.
A real lsfg-vk-cli test can be done on a temporary copy of the user's
config; the actual config must not change without pressing Save in the UI.
