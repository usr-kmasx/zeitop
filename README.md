# Zeitop

**Release:** V12-1.11.26 (November 12, 2026). See [release notes](docs/RELEASE_NOTES.md).

Zeitop is a compact desktop application (480 × 206 px) with a GTK4/WebKitGTK host and an HTML/CSS/JavaScript interface. Its presentation pacing target is **33.333333 ms** (approximately 30 FPS). No system-wide Vulkan layers, Steam files or game configuration files are modified by Zeitop.

## Start the desktop app

Run:

    cd /absolute/path/to/zeitop
    ./run.sh

The first run compiles 32-bit and 64-bit libraries into the local `runtime/` directory, with the existing system compiler. Zeitop does not install system packages. Keep the desktop window open to see telemetry and change the limiter state.

## Launch games with Zeitop

Zeitop is launcher-independent: it can wrap native executables or a game runner. Use the absolute path to the project, not the literal placeholder:

    /absolute/path/to/zeitop/zeitop-run /path/to/game arg1 arg2

For Wine, UMU, Proton or another launcher, place `zeitop-run` before the runner's actual command:

    /absolute/path/to/zeitop/zeitop-run /path/to/runner /path/to/game

The command must start the game through Zeitop. It cannot attach hooks to an already-running game. Keep the GUI open for telemetry and for the frame-generation handshake in read-only game containers.

### Steam launch options (optional)

The app's **Copy** button supplies the exact Steam command (computed from your installation directory). A portable example is:

    '/absolute/path/to/zeitop/zeitop-run' %command%

Paste it into the game's launch options *before* launching. `%command%` is Steam-specific; do not use it for standalone games or other runners.

## Frame Generation Settings (external lsfg-vk)

The Settings gear opens a separate window for editing an existing lsfg-vk
version 2 configuration. It supports profiles, a user-owned DLL file picker,
global settings, validation, private backups, and atomic saves.

A separate Frame Generation icon sits immediately to the right of the
limiter toggle. It independently switches Frame Generation for a running
game without restarting it: zeitop-run loads the user's installed lsfg-vk
layer with application-first Zeitop pacing, and creates a private TOML for
each launch. When FG is OFF, a bounded first-present handshake primes
lsfg-vk at the configured multiplier and switches to 1x bypass before the
app's first present proceeds. The button then hot-reloads 1x vs the saved
multiplier for the tracked game sessions.

The selected profile is saved with Save Changes, persists when Settings
reopens and is applied at game startup through LSFGVK_PROFILE. Selecting
another profile while the game is open updates its multiplier, flow scale
and performance mode in the generated live config; selecting it does not
switch structural options until the game restarts.

Live FG toggling changes only a private per-launch configuration; it does
not edit the user's original lsfg-vk `conf.toml`. The original
V12.11.26 limiter algorithm is unchanged. With a read-only game container,
the first-present helper asks the open Zeitop GUI to update that private
configuration over an authenticated local socket. If the GUI is absent or
the handshake fails, the bounded fallback can temporarily leave FG active.

The wrapper must load the external lsfg-vk layer at game startup; the FG
button cannot inject it into an existing process. The editor does not
bundle lsfg-vk or Lossless Scaling. The ordering
`game -> Zeitop -> lsfg-vk -> driver` was validated with real Vulkan
presentations; operation through a Proton runner was also confirmed in a
game test. Compatibility still varies by title and runner.
See [Frame Generation Settings](docs/FRAME_GENERATION.md) for details.

## Operation

- **Vulkan:** A process-local explicit Vulkan layer uses the `VK_ADD_LAYER_PATH` (or existing `VK_LAYER_PATH`) and `VK_INSTANCE_LAYERS` environment variables. Both 32-bit and 64-bit layer manifests and libraries are stored inside `runtime/vulkan/`.
- **OpenGL:** A separate GLX/EGL presentation hook is injected through `LD_PRELOAD`. Direct ELF32 launches select a 32-bit hook.
- **Frame pacing:** The limiter reads `runtime/limit.state` before each intercepted present call. It first performs an absolute monotonic sleep ending roughly 0.4 ms before the target, then finishes the deadline with a short precision spin. This removes most of the systematic sleep overshoot at the cost of short CPU busy-wait periods. Scheduler preemption and other delays can still exceed the deadline.
- **Telemetry:** Zeitop measures intervals between intercepted presentation calls. This is **not** the GPU rendering time or an accurate measurement of when a frame reaches the display.
- **Current FT:** Refreshed as new presentation samples arrive.
- **Average FT:** The mean of the latest **100 samples** for the selected process, displayed with a **one-second refresh interval**. It resets immediately when the selected process changes or disconnects.
- **Multiple processes:** Tracks telemetry independently per PID, preferring a recently connected process with sustained presentation activity, so a launcher does not constantly clear the game's history.
- **Colors:** Green up to 34.5 ms, yellow from 34.5 to 40 ms, red above 40 ms. These are visual indicators, not guarantees of smooth rendering.

## Practical limitations

- Pacing can delay frames that are ready early. **It cannot accelerate frames that are already late or guarantee that no measured frametime ever exceeds 33.333 ms.** Scheduling, shaders, CPU/GPU load, vsync, and the display can introduce delays.
- Vulkan, Proton, Steam Runtime, and anti-cheat compatibility vary by game. Games whose launchers discard environment variables or whose rendering path bypasses the hooks may not be detected. Avoid anti-cheat games while compatibility is unverified.
- Systems without a matching 32-bit Vulkan GPU driver cannot run 32-bit Vulkan games using that driver, even if the 32-bit Vulkan loader and Zeitop layer are present. Zeitop does not install graphics drivers.
- The Vulkan pacing and FG chain have been tested in a game via Proton, but that does not establish compatibility with every title, graphics API or runner.
- Direct native 32-bit Vulkan applications can use the limiter and frame-time telemetry when a matching 32-bit Vulkan driver is installed. FG remains disabled for directly detected ELF32 executables because the external 32-bit FG layer has not been validated.
- The actual frame interval may exceed the target even after the more precise timer change. Never clamp telemetry values in the UI.

## Testing

For measured Vulkan workload comparisons, independent MangoHud results, and the Proton game-validation protocol, see `docs/VALIDATION.md`. The experimental controller remains opt-in while game compatibility is unverified.

The project also contains separate experimental Vulkan presentation-timing and independent MangoHud measurement tests. Their methodology and limitations are summarized in [validation](docs/VALIDATION.md). Detailed run files stay in ignored `runtime/` and are not shipped with the repository. Experimental driver-targeted presentation scheduling is **not** enabled for games by default.

    PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -v
    node --check ui/main.js
    node --check ui/fg-settings.js

Tests cover state toggling, the GTK/WebKit bridge, GUI controls, multiple PIDs, process-launch environment inheritance, 32/64-bit Vulkan layers, real `vkcube` presentation measurements, first-present IPC, frame-generation output and pacing, timer precision, one-second average-display cadence, and English-only GUI strings. See [validation](docs/VALIDATION.md) for the distinction between production results and the separate experimental controller.

## Project layout

- `app.py` and `core.py`: UI bridge, telemetry state, average-display cadence.
- `ui/`: English-only HTML/CSS/JavaScript desktop interface.
- `limiter.c`: presentation pacing and GLX/EGL interception.
- `vulkan_layer.c`: Vulkan loader interception.
- `build.sh`, `run.sh`, `zeitop-run`: local build, GUI launch and game launcher.
- `vendor/vulkan/`: Khronos headers with Apache-2.0/MIT license.
- `runtime/`: Zeitop's compiled libraries, manifests, socket and local runtime data.
- `tests/`: automated regression and integration tests.

Vulkan loader interface reference: https://github.com/KhronosGroup/Vulkan-Loader/blob/main/docs/LoaderLayerInterface.md
