# Zeitop V13.11.26

Release date: November 13, 2026.

## Highlights

- **Source and output FPS:** live telemetry distinguishes real application frames from downstream Vulkan presentations after Frame Generation. The GUI does not estimate generated FPS by multiplying the source rate. Missing output measurements remain unavailable, and original-only output is shown for rendering paths without the observer.
- **Presentation Mode:** a Zeitop-owned `Default` or `Immediate (Experimental)` option saved independently from the user's lsfg-vk configuration. Immediate requests `MESA_VK_WSI_PRESENT_MODE=immediate` in the launched game's environment and disables `override_present_mode` only in that session's temporary TOML. It does **not** alter lsfg-vk's `pacing_mode = "vsync"`, and requires relaunching the game to change.
- **XCB/XWayland experiment:** Vulkan downstream presentation counts reached approximately 30 original → 90 output FPS (3×) and 30 → 120 output FPS (4×). These are measured Vulkan presentations, **not** proof of physical monitor scan-out. Native Wayland can reject IMMEDIATE, and tearing is possible.
- **User-local installation:** `install.sh` checks required Arch packages, compiles Vulkan/OpenGL libraries for both architectures, creates a terminal launcher, XDG desktop entry and icon. `uninstall.sh` removes the managed application and its local data without touching other projects, the user's source checkout, system-wide Vulkan settings, games or external lsfg-vk.
- **Desktop identity and logo:** the GTK application ID, desktop entry ID and logo are aligned. The desktop entry references the installed PNG directly, avoiding missing user-local icon theme indexes.
- **32-bit Vulkan and OpenGL:** separate 32-bit pacing libraries remain supported when suitable drivers and runtimes are installed. Direct native 32-bit FG remains disabled pending external compatibility validation.
- **Independent control:** original frame pacing and Frame Generation can be toggled separately. The first-present IPC handshake and session-scoped bypass are preserved; session configuration changes do not modify the user's original TOML.

## Dependencies and installation

From the source checkout on Arch Linux:

```sh
./install.sh
# Start the app from the desktop menu or with:
zeitop
# To remove the managed installation:
./uninstall.sh
```

For non-Arch environments, the manual `./run.sh` path may work when Python 3, PyGObject, GTK4, WebKitGTK 6, a C compiler with 32-bit support, and suitable Vulkan drivers/loaders are available. The automatic dependency installer currently uses `pacman`. External lsfg-vk 2.x and the legally obtained Lossless Scaling DLL are **not bundled or redistributed**.

## Validation

Release candidates were tested with the real GTK/WebKit interface, the installed XDG desktop entry, the 32/64-bit Vulkan/GL build, the 3× and 4× Vulkan presentation probes, and isolated install/reinstall/uninstall lifecycles. No system packages were installed or removed during isolated tests. See `docs/VALIDATION.md` for methodology, performance limits, and experimental-controller caveats.

Final automated regression result: **127 automated tests, zero functional failures**, including GUI, launch, Frame Generation and 32-bit Vulkan validation, plus JavaScript and shell syntax checks.

## Limitations

- Frame pacing targets approximately 33.333 ms per original frame; it cannot speed up frames that arrive late or guarantee perfectly stable frame times.
- Immediate is explicitly experimental and is applied **only at process launch**; change the mode and restart the game to switch. Use Default if the game or compositor rejects it or tearing is unacceptable.
- Live frame-generation switching requires an external lsfg-vk layer loaded at game startup. Directly detected native 32-bit programs use the independently supported limiter path rather than unvalidated 32-bit FG.
- Source/output frame telemetry is not a measurement of physical display scan-out or complete end-to-end latency.
- Compatibility with Steam/Proton/other runners and desktop environments varies. XDG desktop integration was validated; no universal compatibility is claimed.
- The alternative Vulkan acquisition-time scheduling controller remains experimental and is not the production limiter.

## Privacy and identification

This release contains source code, generic tests, license notices and documentation only. It excludes local configuration, private computer paths, device-specific hardware details, runtime logs, system reports, saved games and test captures. The historical `V12-1.11.26` tag and release remain available.

The canonical version is `V13.11.26` in the root `VERSION` file, read by the GTK application at startup. The corresponding Git release tag is `V13.11.26`.
