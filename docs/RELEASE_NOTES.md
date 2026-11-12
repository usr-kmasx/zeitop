# Zeitop V12-1.11.26

Release date: November 12, 2026.

## Highlights

- **Independent frame-generation control:** a second button controls an externally installed lsfg-vk 2.x layer independently of Zeitop's frame limiter, without restarting an instrumented game.
- **Correct frame pacing with 2× FG:** the Vulkan chain is application → Zeitop → lsfg-vk → driver. The 30 FPS limiter applies to real game frames rather than also limiting the generated output frames.
- **First-present initialization and live switching:** session-scoped, project-local TOML files prepare lsfg-vk at the selected multiplier, then switch to 1× bypass before the first game presentation when FG starts disabled. The button hot-reloads between bypass and the selected multiplier.
- **Proton read-only compatibility:** an authenticated Unix socket allows the running Zeitop GUI to complete the first-present handshake from outside a game's read-only sandbox.
- **Frame Generation settings:** a GTK/WebKit interface for an existing lsfg-vk v2 configuration, including DLL path, profiles, selected profile persistence, and supported live multiplier/flow scale/performance-mode updates. Zeitop does not bundle or redistribute lsfg-vk or the proprietary Lossless Scaling DLL.

## Compatibility and validation

- Cyberpunk 2077 through Proton: the user confirmed FG and limiter operation after the IPC fix.
- A real Vulkan downstream presentation probe measured approximately 30 presented frames/s at 1× with the limiter on and 60 presented frames/s at 2× with the limiter on, without a frame-generation pacing regression.
- Direct native 32-bit Vulkan presentation and Zeitop GUI frame-time telemetry were validated on an AMD Radeon RX 580 after installation of the 32-bit RADV driver. The same wrapper supports native 64-bit Vulkan workloads.
- Mortal Kombat 11 running through Proton-CachyOS was previously inspected with the production Zeitop Vulkan library and MangoHud loaded.
- The automated regression and integration suite passed 108 tests during development of the IPC fix. Repeat the suite for this release.

## Important limitations

- Zeitop remains a presentation-time limiter and telemetry tool, not a way to accelerate frames that are already late; the target interval is 33.333333 ms (approximately 30 FPS). GPU and display timing can differ from CPU-side presentation cadence.
- Applications must start through `zeitop-run` to receive the hooks. The game can be launched directly or via Steam, UMU, Wine, or other compatible launchers.
- A running GUI is required for the read-only Proton first-present IPC path. If it is absent or acknowledgement fails, the bounded failure fallback can temporarily leave FG enabled.
- Frame Generation for directly detected native ELF32 binaries remains intentionally disabled due to the installed lsfg-vk x86 layer's unverified compatibility; the independent 32-bit Vulkan frame limiter and telemetry have been tested.
- Frame Generation requires the user to install lsfg-vk separately and legally obtain the proprietary Lossless Scaling DLL. Zeitop does not patch Steam, Proton, system-wide Vulkan manifests, or the user's lsfg-vk configuration during live FG toggling.
- The alternative experimental Vulkan controller remains opt-in; it is not the production limiter.

## Identification

The canonical version is `V12-1.11.26` in the root `VERSION` file, which supplies the GTK window title. The release Git tag is `V12-1.11.26`. The earlier `V12.11.26` release remains unchanged.
