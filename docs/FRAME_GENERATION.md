# Frame Generation settings — external lsfg-vk 2.x

Status: included in Zeitop V12-1.11.26 on the main branch. The original
V12.11.26 frame-limiter algorithm remains unchanged. The Vulkan hook adds a
bounded first-present handshake, and each launch gets a private live TOML.

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

The top bar has two independent icons: the frame limiter and, to its
right, lsfg-vk Frame Generation. Both use the same `zeitop-run` wrapper,
regardless of the game launcher. For a direct executable:

    /absolute/path/to/zeitop/zeitop-run /path/to/game

For a separate runner:

    /absolute/path/to/zeitop/zeitop-run /path/to/runner /path/to/game

For Steam launch options only:

    '/absolute/path/to/zeitop/zeitop-run' %command%

The Frame Generation button displays the unmodified official lsfg-vk black
duck logo, sourced from https://lsfg-vk.dev/logo.svg (lsfg-vk project,
PancakeTAS). The icon is not drawn or recolored by Zeitop, and its use does
not imply endorsement. The original SVG has a transparent background.

The limiter toggle updates runtime/limit.state and affects intercepted
present calls in an already-running game.

The FG toggle updates runtime/fg.state independently of the limiter.
The launcher creates a unique lsfg-vk v2 configuration under
runtime/fg-sessions/ for every game launch. LSFGVK_CONFIG points to that
session file, never the user's canonical conf.toml. All writes to the
session use atomic replacement and a shared lock.

- FG ON at launch: lsfg-vk initializes at the configured multiplier.
  A short first-present handshake confirms the session and leaves FG ON.
- FG OFF at launch: the selected multiplier is temporarily kept intact
  so lsfg-vk can initialize its rendering resources. The Zeitop Vulkan
  layer intercepts and holds the FIRST app present and runs the session
  warmup helper. With the GUI running, the helper sends an authenticated
  local Unix datagram to the GUI, which writes multiplier = 1 (bypass)
  to the private session configuration BEFORE the present is forwarded.
  This prevents the later 1x -> 2x freeze reproduced in vkcube.
- FG toggling after the first present hot-reloads the same private
  session configuration, between bypass 1x and the selected multiplier.
- All launched sessions receive GUI toggle and saved profile hot-field
  updates independently, instead of sharing a single global output file.
- If the canonical profile or external lsfg-vk installation cannot be
  used, the launcher falls back to DISABLE_LSFGVK=1; the limiter remains
  available. The experimental stage2 Vulkan backend uses that fallback.
- The first-present helper has a bounded wait. An error or timeout
  releases the game's present with a warning instead of hanging it;
  frame generation may remain temporarily active in that failure path.
  This failure mode remains a limitation; keep the GUI running when
  launching games through read-only containers so IPC is available.

### Read-only game containers (including Proton)

Containerized runners such as Steam Pressure Vessel may expose `runtime/`
to the game as read-only.
The first-present helper therefore sends `ZEITOP_FG_WARMUP1` over the
existing `runtime/zeitop.sock` using an abstract reply address; it does
not write project files from inside Proton. The GUI validates kernel Unix
peer credentials, verifies the presenting process inherited this launch's
random session token, updates the corresponding private TOML with the
existing atomic lock and acknowledges completion. The Vulkan present
only proceeds after that acknowledgement or its bounded failure path.
No Steam, Proton or lsfg-vk files are patched, and the limiter is unchanged.

Without a running GUI, direct native Linux launches use the original
same-process warmup helper. Read-only game containers require the GUI
IPC endpoint; otherwise the timeout/failure warning above applies.
FG and limiter control were confirmed in a game under Proton after the IPC
change; this does not establish universal per-title compatibility.

The actual application-side layer order is:
game -> Zeitop -> lsfg-vk -> driver. Explicit VK_INSTANCE_LAYERS
places Zeitop before lsfg-vk; tracing verified the Zeitop hook receives
one present per source frame, not all generated output frames.

Only the original user-owned conf.toml is editable as the source of
truth. The generated runtime copy is a temporary execution artifact,
never a second user-maintained profile configuration. Files remain inside
ignored runtime/ and are not uploaded to GitHub.

Loading the layer still requires the game to START through zeitop-run.
The FG button cannot inject lsfg-vk into an uninstrumented game.
The first-present handshake primes the lsfg-vk instance before entering
bypass, so subsequent FG toggles can enable interpolation without restarting.

The FG icon remains available even when the limiter is off; the launcher
always includes Zeitop's hooks but they perform no pacing when the limiter
flag is 0. This preserves the limiter's existing live-toggle behavior.
The settings window does not contain a second FG enable button.

The profile chosen and saved in Zeitop settings is passed to the game
through LSFGVK_PROFILE at launch. An explicitly supplied LSFGVK_PROFILE
from the game's own environment takes precedence over Zeitop's saved
preference; without either, the external lsfg-vk uses active_in matching.
This does not bypass legal DLL ownership.

## Using the editor

1. Start Zeitop normally with ./run.sh.
2. Click the Settings gear to open Frame Generation Settings in English.
3. Check the detected lsfg-vk conf.toml; use Browse if necessary.
4. Select your own lsfg-vk.dll using Browse (or leave blank for auto-detection).
5. Select, add, duplicate, or remove profiles in the left column.
   Clicking a profile enables Save Changes even when fields are untouched.
6. Edit profile properties on the right, and global settings below.
7. Select Save Changes. Zeitop saves the preferred profile name privately
   under runtime/, associated with the chosen source configuration.
   Actual field changes, if any, are validated and atomically saved into
   the original conf.toml with the existing private-backup behavior.
8. Closing/reopening the editor restores the saved highlighted profile.
   Reload discards unsaved field changes and an unsaved profile selection.

### Live updates versus profile selection

Selecting a profile only edits the current UI state until Save Changes is
clicked. Save stores the preference and the next game launched through
zeitop-run uses LSFGVK_PROFILE with that selected name. This works even
without an active_in match, provided the lsfg-vk layer and DLL are usable.

For a game already running with lsfg-vk loaded, its startup profile identity
cannot be changed by updating the environment. Zeitop instead takes ONLY
multiplier, flow_scale and performance_mode from the newly saved profile and
copies these values onto the previously launched profile in the generated
runtime conf.toml. The lsfg-vk v2 hot reload then applies these properties
without restarting the game. Its active_in, pacing mode, swapchain
quirks and other structural settings remain those of the startup profile.
The user-owned canonical config is not edited by selection alone.

Changing other profile properties or the startup profile identity requires
a game restart. Changing a profile's name/removing the one used at launch
also requires restarting. Each launched game has a separate runtime TOML and saved startup profile
identity. FG on/off in the GUI remains a global preference applied to all
tracked sessions. The presenting process claims its session during the
first-present handshake, including when a launcher hands off to a child process.
Only downstream presentation tracing confirms generated output frames.

Live FG operation still requires the external lsfg-vk Vulkan layer to have
loaded successfully into the game.

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

Earlier documentation incorrectly treated Vulkan Loader insertion logs as
the application-to-driver call direction. Caller-address tracing in vkcube
established the actual original order was:
app -> lsfg-vk -> Zeitop -> driver. Zeitop received BOTH the real and
intermediate presents, reducing the FG 2x output from about 60 to 30 FPS
when its 30 FPS limiter was enabled.

The corrected explicit order is:
app -> Zeitop -> lsfg-vk -> driver.
The wrapper builds the controlled prefix
VK_LAYER_ZEITOP_pacing:VK_LAYER_LSFGVK_frame_generation, keeping other
inherited explicit layers afterward without duplicates. With 120 vkcube
source frames, Zeitop now receives 120 presents rather than 240.

A first-present gate is required because merely forcing this corrected
order revealed a separate lsfg-vk hang when starting at bypass 1x and
enabling 2x later. The gate primes 2x and atomically switches the
private runtime TOML to bypass before the first app present continues.
A test-only Vulkan probe downstream of lsfg-vk verifies 1x output while
bypassed, 2x output after enabling, then 1x output after disabling.

The experimental stage2 backend is not FG-enabled. Disabling or
missing the external FG layer falls back to the existing limiter.
Known direct ELF32 launches also fall back to the limiter: the
external lsfg-vk x86 layer failed device enumeration in an earlier test,
and FG has not been validated for that architecture. Native 32-bit Vulkan
presentation and Zeitop GUI telemetry were subsequently verified with a
matching 32-bit Vulkan GPU driver. The wrapper does not automatically
identify the architecture of every child spawned by another runner,
so mixed-architecture launch paths still need separate verification.

For actual games, still verify:
- The title uses the Vulkan path and the lsfg-vk profile matches.
- Generated output frames are not re-limited by Zeitop.
- VSync/FIFO, translation layers (including DXVK) and overlay behavior.
- A compatible external layer for the renderer's architecture, an accessible
  user-owned DLL and a compatible GPU/driver.

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
Tests include isolated synthetic TOML fixtures, first-present IPC tests
and real vkcube + lsfg-vk integration tests with a temporary downstream
probe. Read-only filesystem and PID-namespace simulations validated the
IPC handshake. Direct native 32-bit Vulkan presentation and GUI telemetry
were also tested. No user-owned config/DLL or system Vulkan manifest was
modified. Each additional game and runner still requires verification of
the first-present timeout/failure path and process handoff. See
[validation](VALIDATION.md) for summarized results.
