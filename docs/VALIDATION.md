# Zeitop — frame pacing validation

**Status:** Test renderer verified, experimental controller opt-in only; production unchanged.
No display, driver, Steam, game or system configuration was modified.

## Architecture under test

- Production: vulkan_layer.c and limiter.c, waiting before downstream present.
- Candidate: pacing/vulkan_frame_layer.c with the per-device/swapchain
  controller in pacing/frame_controller.c, pacing before image acquisition.
- The candidate handles both image-acquisition APIs, skipping a wait for
  timeout=0. It is owned source code; it no longer uses a text-replacement
  generator based on production code.
- No-wait telemetry in pacing/present_telemetry.c sends the existing UI's
  ZEITOP1 protocol, without calling the production limiter.
- VK_EXT_present_timing remains in the separate test renderer, not the game layer.

## Workload comparison method

The project-local Wayland/Vulkan renderer runs fixed CPU work AFTER image
acquisition and BEFORE GPU submission: 5, 20, 33, 40 ms, or a deterministic
random sequence of these durations. Old and candidate controllers use the
same random seed, identical render path, and original MangoHud logging.
The pair's run order alternates to limit time-dependent bias.

All raw MangoHud CSVs and logs are retained. P99 values use nearest-rank,
no filtering of nominal intervals. Samples below the 33.333333 ms target
are included in the raw counts.

### 100 runs: 10 trials per workload per controller (before telemetry integration)

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

### 30 runs after adding nonblocking telemetry (3 trials per workload/controller)

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

## Correctness and concurrency

Eight deterministic controller checks passed with AddressSanitizer and
UndefinedBehaviorSanitizer. They include 8 threads reserving 256 distinct
deadlines and reuse of a destroyed swapchain handle. This test also
passed under ThreadSanitizer in the connected Arch Linux environment.

The telemetry module passed the ZEITOP1 UNIX datagram protocol test and
a real Vulkan test confirmed that the candidate emits UI packets without
executing an additional pacing wait.

## Proton/DXVK validation — pending manual game test

No game was launched and no Steam launch option or save was changed.
Installed Proton is not equivalent to testing a real game.

Prepare test profiles (all files written under Zeitop/runtime):

    python3 -B tests/proton_capture.py prepare --name game_off --controller disabled
    python3 -B tests/proton_capture.py prepare --name game_old --controller old
    python3 -B tests/proton_capture.py prepare --name game_new --controller new

Each profile generates a SteamLaunchOptions.txt file. Manually paste
the launch option into one chosen game's Steam launch settings,
set the Zeitop power button as printed by the tool, and play the SAME
scene for 120-180 seconds. Change only the one named test condition.

Generate a report for each completed profile:

    python3 -B tests/proton_capture.py report --name game_old

Repeat for the other two profiles and select the game process's CSV rather
than a launcher process CSV. Do not compare dissimilar scenes.

## Release gate

Do not replace the production limiter until Proton/DXVK data is evaluated,
the 33 ms regression is understood, and no double waits, thread races,
or regressions in the UI are present. Preserve the candidate opt-in
mechanism for rollback. Do not assign an application version number.
