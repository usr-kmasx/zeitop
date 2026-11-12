# Zeitop V12-1.11.26

Release date: November 12, 2026.

## Highlights

- **Independent frame-generation control:** a second button controls an externally installed lsfg-vk 2.x layer independently of Zeitop's frame limiter, without restarting an instrumented game.
- **Correct frame pacing with 2× FG:** the Vulkan chain is application → Zeitop → lsfg-vk → driver. The 30 FPS limiter applies to real game frames rather than also limiting the generated output frames.
- **First-present initialization and live switching:** session-scoped, project-local TOML files prepare lsfg-vk at the selected multiplier, then switch to 1× bypass before the first game presentation when FG starts disabled. The button hot-reloads between bypass and the selected multiplier.
- **Proton read-only compatibility:** an authenticated Unix socket allows the running Zeitop GUI to complete the first-present handshake from outside a game's read-only sandbox.
- **Frame Generation settings:** a GTK/WebKit interface for an existing lsfg-vk v2 configuration, including DLL path, profiles, selected profile persistence, and supported live multiplier/flow scale/performance-mode updates. Zeitop does not bundle or redistribute lsfg-vk or the proprietary Lossless Scaling DLL.

## Compatibility and validation

- A game tested through Proton was confirmed to support independent FG and limiter control after the IPC change. Compatibility remains dependent on each title and runner.
- A downstream Vulkan presentation probe measured approximately 30 presented frames/s with the limiter enabled and FG bypassed (1×), versus 60 presented frames/s with the limiter enabled and FG active at 2×. Generated frames were not re-limited by Zeitop in that test.
- Direct native 32-bit Vulkan presentations and Zeitop GUI frame-time telemetry were validated with a compatible 32-bit Vulkan GPU driver. This is separate from support for 32-bit FG, which remains unvalidated.
- Release validation completed: **108 automated tests, zero failures, five skips**, plus JavaScript syntax and interface checks. Test counts reflect the release preparation environment; other systems may skip different integration tests.

The release records generic validation findings only. No device identifiers,
personal paths, local configuration, game logs or system reports are included.

## Important limitations

- Zeitop remains a presentation-time limiter and telemetry tool, not a way to accelerate frames that are already late; the target interval is 33.333333 ms (approximately 30 FPS). GPU and display timing can differ from CPU-side presentation cadence.
- Applications must start through `zeitop-run` to receive the hooks. The game can be launched directly or via Steam, UMU, Wine, or other compatible launchers.
- A running GUI is required for the read-only Proton first-present IPC path. If it is absent or acknowledgement fails, the bounded failure fallback can temporarily leave FG enabled.
- Frame Generation for directly detected native ELF32 binaries remains intentionally disabled due to the installed lsfg-vk x86 layer's unverified compatibility; the independent 32-bit Vulkan frame limiter and telemetry have been tested.
- Frame Generation requires the user to install lsfg-vk separately and legally obtain the proprietary Lossless Scaling DLL. Zeitop does not patch Steam, Proton, system-wide Vulkan manifests, or the user's lsfg-vk configuration during live FG toggling.
- The alternative experimental Vulkan controller remains opt-in; it is not the production limiter.

## Identification

The canonical version is `V12-1.11.26` in the root `VERSION` file, which supplies the GTK window title. The release Git tag is `V12-1.11.26`. The earlier `V12.11.26` release remains unchanged.
