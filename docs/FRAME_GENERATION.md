# Frame Generation settings — external lsfg-vk 2.x

Status: independent Frame Generation toggle and external settings editor
are implemented on feature/lsfg-settings. The V12.11.26 production frame
limiter algorithm and Vulkan/OpenGL hooks remain unchanged. The game launcher
now prepares a private, derived runtime configuration for live bypass.

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

## Independent toggles in the main window

The top bar has two separate icons: the original frame limiter and, directly
to its right, lsfg-vk Frame Generation. Both work with the same existing
Zeitop Steam command:

The Frame Generation button displays the unmodified official lsfg-vk black
duck logo, sourced from https://lsfg-vk.dev/logo.svg (lsfg-vk project,
PancakeTAS). The icon is not drawn or recolored by Zeitop, and its use does
not imply endorsement. The original SVG has a transparent background.

    '/absolute/path/to/zeitop/zeitop-run' %command%

The limiter toggle updates runtime/limit.state and affects intercepted
present calls in an already-running game.

The FG toggle updates runtime/fg.state independently of the limiter.
At game launch, zeitop-run always prepares runtime/fg-live.conf.toml, a
private derived copy of the original user-owned lsfg-vk v2 config, and
passes LSFGVK_CONFIG pointing to that runtime file. It does not set
DISABLE_LSFGVK when the config is usable. Thus the lsfg-vk implicit layer
can initialize when the selected game matches a configured profile.

- FG OFF (default): every runtime profile gets multiplier = 1, which
  the installed lsfg-vk treats as a bypass, without unloading the layer.
- FG ON: runtime profile multipliers are restored directly from the
  original canonical conf.toml (2x, 3x, 4x or other configured values).
- Switching the button regenerates the runtime file atomically, and
  the loaded lsfg-vk detects changes and hot-reloads the multiplier.
- If the canonical configuration cannot be used, the launcher falls
  back to DISABLE_LSFGVK=1 so the original limiter still works.
- When the user edits the canonical conf.toml in Zeitop settings and
  presses Save Changes, the running runtime file is synchronized.

Only the original user-owned conf.toml is editable as the source of
truth. The generated runtime copy is a temporary execution artifact,
never a second user-maintained profile configuration. Files remain inside
ignored runtime/ and are not uploaded to GitHub.

Loading the layer still requires the game to START through zeitop-run.
The FG button cannot inject lsfg-vk into a process already started
without the layer. In a game where it was preloaded at 1x, however, the
toggle can activate or bypass interpolation without restarting.

The FG icon remains available even when the limiter is off; the launcher
always includes Zeitop's hooks but they perform no pacing when the limiter
flag is 0. This preserves the limiter's existing live-toggle behavior.
The settings window does not contain a second FG enable button.

The external lsfg-vk configuration still chooses the profile by active_in
or an existing LSFGVK_PROFILE startup override. Enabling the layer does
not select an arbitrary profile and does not bypass legal DLL ownership.

## Using the editor

1. Start Zeitop normally with ./run.sh.
2. Click the Settings gear to open Frame Generation Settings in English.
3. Check the detected lsfg-vk conf.toml; use Browse if necessary.
4. Select your own lsfg-vk.dll using Browse (or leave blank for auto-detection).
5. Select, add, duplicate, or remove profiles in the left column.
6. Edit profile properties on the right, and global settings below.
7. Select Save Changes; the selected ORIGINAL file is validated and written
   atomically. Reload rereads it and discards unsaved edits.

### Live updates versus profile selection

The profile highlighted on the left is selected only for editing in Zeitop.
It is not a command to switch the profile in a running game. lsfg-vk
chooses the active profile through its game executable match (active_in)
or an existing startup override (LSFGVK_PROFILE).

The official lsfg-vk v2 documentation explicitly supports hot-reloading
multiplier, flow_scale and performance_mode. When you edit these
values in the profile the running game already uses, Save Changes
writes them to conf.toml; lsfg-vk can then apply them without restarting
the game. Selecting another profile in the editor does not itself change
which profile is active in the running process.

Other configuration fields and switching the active profile may require
restarting the game. Live FG operation still requires the external
lsfg-vk Vulkan layer to have loaded successfully into the game.

Reference: https://lsfg-vk.dev/docs/configuration/configuration-options/

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

## Vulkan layer ordering and validation

The existing Vulkan loader chain was observed in four test combinations
using a temporary Zeitop launcher, the user's installed lsfg-vk layer,
an existing profile forced through LSFGVK_PROFILE for the diagnostic, and
vulkaninfo --summary:

| Limiter state | FG state | Loader result |
| --- | --- | --- |
| OFF | OFF | Zeitop then lsfg-vk (1x bypass) |
| ON | OFF | Zeitop then lsfg-vk (1x bypass) |
| OFF | ON | Zeitop then lsfg-vk (configured multiplier) |
| ON | ON | Zeitop then lsfg-vk (configured multiplier) |

The Zeitop layer is still present but does not pace when its live flag is
OFF. The loader logs Zeitop before lsfg-vk in all four states when a valid
profile is selected. With FG OFF, lsfg-vk remains loaded in bypass mode.
This establishes ordering for the tested loader environment, NOT proof that
a game renders more frames or has correct output frametimes.

The wrapper intentionally refuses an explicit/forced lsfg-vk layer in
VK_INSTANCE_LAYERS or VK_LOADER_LAYERS_ENABLE, because a forced layer can
reverse the ordering or bypass the controlled runtime configuration. Leave lsfg-vk installed as
the user's normal implicit layer and configure active_in in conf.toml.

For actual games, still verify:
- The title uses the Vulkan path and the lsfg-vk profile matches.
- Generated output frames are not re-limited by Zeitop.
- VSync/FIFO, Proton/DXVK and third-party overlay behavior.
- The installed 64-bit layer, accessible user-owned DLL and GPU compatibility.

The previous Vulkan Loader message about a missing vkGetInstanceProcAddr
appeared with lsfg-vk's negotiation skipped when no usable profile was
selected; on a read-only test with LSFGVK_PROFILE explicitly selected,
both layers loaded correctly. The Vulkan Loader has a known negotiation
fallback which can produce a misleading diagnostic when a layer declines
loading (Khronos issue #1904, fixed upstream in September 2026).

No code from lsfg-vk, DLL, or private paths is stored in this repository.
No external layer binary, manifest, or system installation was modified.

## Testing

Run the existing Python unittest suite and JavaScript syntax checks.
Frame Generation tests work only on synthetic temporary TOML files.
A real lsfg-vk-cli test can be done on a temporary copy of the user's
config; the actual config must not change without pressing Save in the UI.
