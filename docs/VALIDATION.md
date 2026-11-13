# Zeitop — frame pacing validation

**Status:** The production limiter and independent lsfg-vk Frame Generation
controls are released in V13.11.26. A separate frame-pacing controller
remains experimental and opt-in. The experiments below do not replace the
production limiter or change system-wide graphics settings.

## Verified production behavior (V13.11.26)

The Vulkan call order is `application -> Zeitop pacing -> lsfg-vk -> Zeitop output observer -> driver`.
Zeitop limits source-frame presentations, not interpolated output frames.

| Production test | Observation | Boundary |
|---|---|---|
| Frame limiter ON, FG bypassed (1×) | Approximately 30 downstream presentations/s | Test Vulkan renderer |
| Frame limiter ON, FG active (2×) | Approximately 60 downstream presentations/s | Same renderer, not a guarantee for all games |
| FG OFF -> ON -> OFF | Private per-launch config hot-reloaded from 1× to 2× to 1× | Real Vulkan output probe |
| First-present IPC from read-only container | Acknowledged; pending state cleared; bypass applied | Local read-only and PID-namespace simulation |
| Live FG and limiter through Proton | User-confirmed working after IPC fix | One game; no universal compatibility claim |
| Native 32-bit Vulkan | Real presentations and GUI frame-time samples received | Requires an installed 32-bit Vulkan GPU driver |
| Immediate (Experimental), selected at launch, 3× | Approximately 30 source FPS and 90 downstream output presentations/s | XCB/XWayland Vulkan test; not native Wayland |
| Immediate (Experimental), selected at launch, 4× | Approximately 30 source FPS and 120 downstream output presentations/s | XCB/XWayland Vulkan test; not monitor scan-out |
| Default mode on XCB at 3× | Approximately 20 source FPS and 60 downstream presentations/s | VSync-limited test, not necessarily all compositors |
| Install → launch → reinstall → uninstall | Managed desktop entry/icon and 32/64-bit components verified | Isolated home; shared packages never removed in test |

The 32-bit result validates the **limiter and telemetry**, not lsfg-vk
Frame Generation. Directly detected ELF32 executables intentionally use
the limiter-only fallback. Mixed-architecture runner processes need their
own compatibility checks.

The previous V12-1.11.26 release completed 108 tests; the current
V13.11.26 release ran 127 automated regression tests after the release
metadata update (see release notes). The project stores runtime measurements under ignored
`runtime/` and does not include device-specific logs or user configuration
in the repository. These observations do not prove universal performance.

## Experimental controller research (not the release backend)

### Architecture under test

- Production: vulkan_layer.c and limiter.c, waiting before downstream present.
- Candidate: pacing/vulkan_frame_layer.c with the per-device/swapchain
  controller in pacing/frame_controller.c, pacing before image acquisition.
- The candidate handles both image-acquisition APIs, skipping a wait for
  timeout=0. It is owned source code; it no longer uses a text-replacement
  generator based on production code.
- No-wait telemetry in pacing/present_telemetry.c sends the existing UI's
  ZEITOP1 protocol, without calling the production limiter.
- VK_EXT_present_timing remains in the separate test renderer, not the game layer.

### Workload comparison method

The project-local Wayland/Vulkan renderer runs fixed CPU work AFTER image
acquisition and BEFORE GPU submission: 5, 20, 33, 40 ms, or a deterministic
random sequence of these durations. Old and candidate controllers use the
same random seed, identical render path, and original MangoHud logging.
The pair's run order alternates to limit time-dependent bias.

Original MangoHud CSVs and logs are stored only in ignored project-local
`runtime/` output, not in the repository. P99 uses nearest-rank,
no filtering of nominal intervals. Samples below the 33.333333 ms target
are included in the raw counts.

#### 100 runs: 10 trials per workload per controller (before telemetry integration)

| Workload | Old median P99 (ms) | Candidate median P99 (ms) | Old >33.5 | Candidate >33.5 |
|---|---:|---:|---:|---:|
| 5 ms | 33.40115 | 33.37925 | 2/385 | 1/382 |
| 20 ms | 33.49395 | 33.40695 | 9/381 | 2/386 |
| 33 ms | 33.92600 | 33.80520 | 240/400 | 196/400 |
| 40 ms | 41.41185 | 41.11080 | 440/440 | 440/440 |
| Random | 68.41900 | 68.40955 | 216/406 | 215/406 |

Evidence: runtime/variable_workload/repeated_10x/summary.json, and 100
run directories containing original MangoHud CSV files and stderr/stdout.

For work taking 40 ms, neither limiter added a full 33.333 ms extra wait.
With random work, both show high latency outliers that cannot be accelerated
by a limiter.

#### 30 runs after adding nonblocking telemetry (3 trials per workload/controller)

| Workload | Old median P99 (ms) | Candidate median P99 (ms) |
|---|---:|---:|
| 5 ms | 33.55870 | 33.38350 |
| 20 ms | 33.51130 | 33.49880 |
| 33 ms | 33.81850 | **35.90790** |
| 40 ms | 41.30080 | 41.19970 |
| Random | 68.44040 | 68.40220 |

Evidence: runtime/variable_workload/after_telemetry_3x/summary.json.
The candidate's 33 ms P99 was unfavorable in this shorter run. This is
NOT proof that telemetry caused the change; scheduling and run-to-run
variance may contribute. The candidate should not become default on
the strength of the first 100 runs alone.

### Correctness and concurrency

Eight deterministic controller checks passed with AddressSanitizer and
UndefinedBehaviorSanitizer. They include 8 threads reserving 256 distinct
deadlines and reuse of a destroyed swapchain handle. The same test also
passed under ThreadSanitizer in the test environment.

The telemetry module passed the ZEITOP1 UNIX datagram protocol test and
a real Vulkan test confirmed that the candidate emits UI packets without
executing an additional pacing wait.

### Experimental-controller Proton/DXVK comparison — still outstanding

The historical candidate-versus-production comparison did not launch a
game, change any launch option or modify saves. Installing a Proton runner
does not validate the experimental candidate in a real game. This pending
comparison is separate from the confirmed production FG/limiter behavior
reported above.

Prepare test profiles (all files written under Zeitop/runtime):

    python3 -B tests/proton_capture.py prepare --name game_off --controller disabled
    python3 -B tests/proton_capture.py prepare --name game_old --controller old
    python3 -B tests/proton_capture.py prepare --name game_new --controller new

This optional comparison script targets Steam launch options specifically;
it is **not** required to run Zeitop, which also supports direct and
non-Steam runner commands. Each profile generates a
`SteamLaunchOptions.txt` file. If undertaking that experiment, manually
paste the option into a test game's Steam settings, set the Zeitop
limiter as printed, and record the same scene for 120–180 seconds.
Change only the named experimental condition.

Generate a report for each completed profile:

    python3 -B tests/proton_capture.py report --name game_old

Repeat for the other two profiles and select the game process's CSV rather
than a launcher process CSV. Do not compare dissimilar scenes.

### Experimental controller acceptance criteria

Do not replace the production limiter with the acquisition-time candidate
until representative runner/game comparisons are completed, the unfavorable
33 ms P99 is understood, and double waits, races and UI regressions have
been ruled out. Keep the experimental opt-in and rollback mechanism. The
released V13.11.26 production limiter and FG controls are not this
experimental candidate.
