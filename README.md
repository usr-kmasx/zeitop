# Zeitop

**Release:** V13.11.26 (November 13, 2026). See [release notes](docs/RELEASE_NOTES.md).

Zeitop is a compact desktop application (480 × 206 px) with a GTK4/WebKitGTK host and an HTML/CSS/JavaScript interface. Its presentation pacing target is **33.333333 ms** (approximately 30 FPS). No system-wide Vulkan layers, Steam files or game configuration files are modified by Zeitop.

## Start the desktop app

Run:

    cd /absolute/path/to/zeitop
    ./run.sh

The first run compiles 32-bit and 64-bit libraries into the source checkout's local `runtime/` directory. This direct-run option does not install system packages. To install the app and a desktop shortcut, use `./install.sh` below. Keep the GUI open for telemetry and live FG control.

## Install and uninstall (supported Linux distributions)

From the source checkout run `./install.sh`. The script identifies the
distribution from `/etc/os-release`, installs **missing** dependencies using
its native package manager, builds both the 64-bit and 32-bit Vulkan/GL
libraries, and installs the application per-user. These package-manager paths
are implemented:

| Distribution family | Manager | Package preparation |
|---|---|---|
| Arch Linux and Arch-based systems | `pacman` | Multilib packages must be available |
| Debian 13 / Ubuntu 24.04+ and compatible derivatives | `apt-get` | `i386` multiarch must already be enabled |
| Fedora and compatible derivatives | `dnf` | 32-bit `i686` packages must be available |
| openSUSE | `zypper` | 32-bit packages must be available in enabled repos |

On Debian/Ubuntu, if the script reports that `i386` multiarch is disabled,
the administrator must explicitly enable it before retrying:

```sh
sudo dpkg --add-architecture i386
sudo apt-get update
./install.sh
```

The installer **never** enables an architecture, changes distro repositories,
replaces graphics drivers, edits Steam/Proton, or installs system-wide Vulkan
layers. A matching 32-bit and 64-bit Vulkan GPU driver (ICD) is required
separately. WebKitGTK 6.0, PyGObject and the 32-bit build toolchain must be
available through the distribution's configured repositories. Package names
and availability can differ on derivatives. Only the Arch installation has
been tested with the host package manager; the other manager paths have
isolated simulated-package-manager integration tests, **not** real-system
validation.

The app is installed under `$XDG_DATA_HOME/zeitop` (or
`~/.local/share/zeitop` when unset), with `~/.local/bin/zeitop`,
`~/.local/bin/zeitop-run`, an XDG desktop entry and the existing logo.
The GTK/Wayland application ID matches the entry, whose absolute PNG path
works without a theme cache. The Copy button supplies the installed Steam
launch option. On first install, only durable preferences (FG profile/config,
presentation mode and toggle states) are migrated from the checkout;
upgrades keep those from the installed copy. Runtime sockets, logs, compiled
binaries and active game sessions are never migrated.

```sh
./install.sh
# later, from the checkout or the installed app directory:
./uninstall.sh
```

Uninstall removes the managed application, private runtime files, launchers,
desktop entry and icon. It does **not** remove the source checkout, Steam
settings, external lsfg-vk or the proprietary Lossless Scaling DLL. It also
does **not** remove shared distribution packages by default.

On **Arch only**, `./uninstall.sh --remove-deps` additionally removes
packages tracked as newly installed for Zeitop **only if they are currently
pacman orphans**. On Debian, Fedora and openSUSE the same option deliberately
retains all packages; administrators can review/remove them manually. Stop
the application and any games launched with Zeitop before uninstalling.

`./install.sh --skip-deps` avoids all package-manager operations for
isolated tests or installations where prerequisites are already available.
The 32-bit and 64-bit builds and GTK/WebKit import checks still run. External
lsfg-vk 2.x and legally obtained Lossless Scaling are optional and never
downloaded or modified.

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
`game -> Zeitop pacing -> lsfg-vk -> Zeitop output telemetry -> driver` was validated with real Vulkan
presentations; operation through a Proton runner was also confirmed in a
game test. Compatibility still varies by title and runner.
See [Frame Generation Settings](docs/FRAME_GENERATION.md) for details.

## Operation

- **Vulkan:** A process-local explicit Vulkan layer uses the `VK_ADD_LAYER_PATH` (or existing `VK_LAYER_PATH`) and `VK_INSTANCE_LAYERS` environment variables. Both 32-bit and 64-bit layer manifests and libraries are stored inside `runtime/vulkan/`.
- **OpenGL:** A separate GLX/EGL presentation hook is injected through `LD_PRELOAD`. Direct ELF32 launches select a 32-bit hook.
- **Frame pacing:** The limiter reads `runtime/limit.state` before each intercepted present call. It first performs an absolute monotonic sleep ending roughly 0.4 ms before the target, then finishes the deadline with a short precision spin. This removes most of the systematic sleep overshoot at the cost of short CPU busy-wait periods. Scheduler preemption and other delays can still exceed the deadline.
- **Telemetry:** Zeitop measures intervals between intercepted presentation calls. This is **not** the GPU rendering time or an accurate measurement of when a frame reaches the display.
- **FPS card:** The original FPS is calculated from measured source-frame intervals. When FG is enabled and available, a separate Vulkan observer *after* lsfg-vk counts successful output presentations, including generated frames. The indicator shows `source → output` without an `ms` suffix. No multiplier is applied to manufacture an output FPS, and missing data appears as `--`. OpenGL applications retain original FPS only.
- **Presentation mode (Zeitop):** Frame Generation Settings → Global Settings offers `Default` and `Immediate (Experimental)`. Default preserves the original lsfg-vk profile and inherited Mesa settings. Immediate forces `override_present_mode = false` in the per-launch generated TOML and sets `MESA_VK_WSI_PRESENT_MODE=immediate` only for the launched game. This does **not** disable lsfg-vk's internal `pacing_mode = "vsync"`, and it does not alter the user's canonical config. Changes take effect on the **next** game launch, not in already-running games. Immediate was tested on XCB/XWayland; native Wayland may reject it. It can cause tearing and is not guaranteed to improve all games.
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
- `install.sh`, `uninstall.sh`: XDG user-local install/uninstall with Arch dependency detection.
- `vendor/vulkan/`: Khronos headers with Apache-2.0/MIT license.
- `runtime/`: Zeitop's compiled libraries, manifests, socket and local runtime data.
- `tests/`: automated regression and integration tests.

Vulkan loader interface reference: https://github.com/KhronosGroup/Vulkan-Loader/blob/main/docs/LoaderLayerInterface.md
