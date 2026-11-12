# Zeitop

**Release:** V12.11.26 (November 12, 2026). See [release notes](docs/RELEASE_NOTES.md).

Zeitop is a compact desktop application (480 × 206 px) with a GTK4/WebKitGTK host and an HTML/CSS/JavaScript interface. Its presentation pacing target is **33.333333 ms** (approximately 30 FPS). No system-wide Vulkan layers, Steam files or game configuration files are modified by Zeitop.

## Start the desktop app

Run:

    cd /absolute/path/to/zeitop
    ./run.sh

The first run compiles 32-bit and 64-bit libraries into the local `runtime/` directory, with the existing system compiler. Zeitop does not install system packages. Keep the desktop window open to see telemetry and change the limiter state.

## Steam games, including Proton

This is a portable example. Replace the placeholder with the path where you cloned Zeitop, or use the app's **Copy** button to generate the exact command automatically (computed from your installation directory):

Steam launch option:

    '/absolute/path/to/zeitop/zeitop-run' %command%

Paste the command into the game's launch options yourself **before starting the game**. The power button then enables or disables pacing without restarting that instrumented game process.

## Games outside Steam

Use the project launcher as a prefix:

    /absolute/path/to/zeitop/zeitop-run /path/to/game arg1 arg2

Or prefix a runner command:

    /absolute/path/to/zeitop/zeitop-run /path/to/runner /path/to/game

The game needs to start through this wrapper. Zeitop cannot attach to a game that is already running without it.

## Frame Generation Settings (external lsfg-vk)

The Settings gear opens a separate window for editing an existing lsfg-vk
version 2 configuration. It supports profiles, a user-owned DLL file picker,
global settings, validation, private backups, and atomic saves.

A separate Frame Generation icon sits immediately to the right of the
limiter toggle. It independently switches Frame Generation for a running
game without restarting it: zeitop-run loads the user's installed lsfg-vk
layer even with FG OFF (multiplier 1x bypass) and the button switches the
generated runtime config between 1x and the user's configured multiplier.

The selected profile is saved with Save Changes, persists when Settings
reopens and is applied at game startup through LSFGVK_PROFILE. Selecting
another profile while the game is open updates its multiplier, flow scale
and performance mode in the generated live config; selecting it does not
switch structural options until the game restarts.

The original lsfg-vk conf.toml remains unchanged by the button, and the
limiter's V12.11.26 pacing algorithm is unchanged. The game still needs
to START through the launcher with a matching profile to initialize the
lsfg-vk layer; it cannot be injected into an already-running process.
The editor does not bundle lsfg-vk or Lossless Scaling. Vulkan Loader
checks show Zeitop before lsfg-vk, while real-game frame-generation cadence
remains to be measured. See
[Frame Generation Settings](docs/FRAME_GENERATION.md) for details and limits.

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
- The production Vulkan layer was verified loaded into a running Mortal Kombat 11 (Proton-CachyOS) process, and the user confirmed that Zeitop and MangoHud behaved as expected. A frame-by-frame MangoHud CSV for that game session was not captured; broad Proton compatibility is not established.
- The actual frame interval may exceed the target even after the more precise timer change. Never clamp telemetry values in the UI.

## Testing

For measured Vulkan workload comparisons, independent MangoHud results, and the Proton game-validation protocol, see `docs/VALIDATION.md`. The experimental controller remains opt-in while game compatibility is unverified.

The project also includes isolated tests using actual Vulkan presentation timestamps and independent MangoHud logging. See `runtime/stage3/RESULTS.md` for the observed driver intervals (16.726 ms without targeting, 33.451 ms when requesting 33.333 ms). This mechanism has **not** been enabled for games by default.

    PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -v
    node --check ui/main.js

Tests cover state toggling, the GTK/WebKit bridge, GUI controls, multiple PIDs, process-launch environment inheritance, 32/64-bit Vulkan layers, real `vkcube` presentation measurements, timer precision, one-second average-display cadence, and English-only GUI strings.

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
