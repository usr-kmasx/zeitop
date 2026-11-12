# Zeitop V12.11.26

Release date: November 12, 2026.

## Included

- Local Vulkan presentation limiter with a 33.333333 ms minimum frame interval target (approximately 30 FPS).
- Process-local Vulkan 64-bit and 32-bit explicit layer integration with Steam/Proton launch options.
- OpenGL GLX/EGL hooks, live enable/disable, and per-process frametime telemetry.
- Compact GTK4/WebKitGTK interface with current, 100-sample average, and history graph.
- Isolated Vulkan workload benchmarks and independent MangoHud measurement scripts.
- Independent candidate controller retained as opt-in for further compatibility testing.

## Release checks

- Mortal Kombat 11 running through Proton-CachyOS was inspected: the production Zeitop Vulkan library and MangoHud were both loaded in the game process.
- The Zeitop runtime enable flag and UI telemetry listener were observed. The user confirmed the in-game operation of Zeitop and MangoHud.
- Automated regression and integration tests cover timing, 32/64-bit Vulkan loading, GUI, telemetry, concurrency, and presentation probes.

## Scope and limitations

- This release uses the original production limiter, not the unapproved acquire-time candidate.
- No complete per-frame MangoHud CSV was collected from the Mortal Kombat 11 session. The release therefore does not claim a measured perfect 33.333333 ms output cadence or universal Proton/DXVK compatibility.
- Frames taking more than 33.333333 ms cannot be accelerated by a limiter.
- The display and driver may present frames at intervals different from CPU-side scheduling.
- No system-wide driver or display changes, system installation or Steam configuration changes are required by Zeitop itself.

## Identification

The canonical version is stored in the root VERSION file, also used for the GTK window title. The corresponding Git tag is V12.11.26.
