"""Generated live lsfg-vk configuration for Zeitop-launched games.

The user-owned conf.toml is the canonical source and is NEVER modified by
Frame Generation power toggling. The game reads a derived file in runtime/
and lsfg-vk's own hot reload watches it. No lsfg-vk code is included.
"""
from __future__ import annotations

import fcntl
import json
import os
import secrets
import sys
import tempfile
import time
import tomllib
from pathlib import Path

import fg_config
from core import is_fg_enabled, set_fg_enabled


class LiveConfigError(fg_config.ConfigError):
    pass


def _runtime(root: Path) -> Path:
    return Path(root).resolve() / "runtime"


def source_config(root: Path, *, env=None) -> Path:
    """An explicit user environment override wins over a selected GUI file."""
    env = dict(os.environ if env is None else env)
    if env.get("LSFGVK_CONFIG"):
        provided = fg_config.discover_config(env=env)
        session_dir = (_runtime(root) / "fg-sessions").resolve()
        # An inherited per-launch TOML is never the canonical source.
        if provided.parent.resolve() == session_dir:
            return source_config(root, env={
                key: value for key, value in env.items()
                if key != "LSFGVK_CONFIG"
            })
        # Children of an already-wrapped launcher can inherit our generated
        # runtime path. Never recursively use the bypass copy as the user's
        # canonical profile configuration.
        if provided.resolve() != (_runtime(root) / "fg-live.conf.toml").resolve():
            return provided
    marker = _runtime(root) / "fg.selected-config"
    if marker.exists():
        if marker.is_symlink() or not marker.is_file():
            raise LiveConfigError("Selected lsfg-vk configuration is invalid.")
        path = Path(marker.read_text(encoding="utf-8").strip())
        if not path.is_absolute():
            raise LiveConfigError("Selected lsfg-vk configuration must be an absolute file.")
        return path
    return fg_config.discover_config(env=env)


def _write_atomic(path: Path, content: bytes) -> None:
    """Write without ever exposing partially-written TOML to an active game."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tempname = tempfile.mkstemp(prefix=".fg-toml-", suffix=".tmp", dir=path.parent)
    temp = Path(tempname)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "wb") as out:
            out.write(content)
            out.flush()
            os.fsync(out.fileno())
        os.replace(temp, path)
        dirfd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(dirfd)
        finally:
            os.close(dirfd)
    finally:
        temp.unlink(missing_ok=True)


PRESENTATION_MODES = ("default", "immediate")


def presentation_mode(root: Path) -> str:
    """Zeitop-only next-launch setting; missing or invalid data is safe."""
    path = _runtime(root) / "fg.presentation-mode"
    try:
        if path.is_symlink():
            return "default"
        mode = path.read_text(encoding="ascii").strip()
        return mode if mode in PRESENTATION_MODES else "default"
    except (OSError, UnicodeError):
        return "default"


def remember_presentation_mode(root: Path, mode: str) -> None:
    """Persist independently of the canonical lsfg-vk TOML."""
    if mode not in PRESENTATION_MODES:
        raise LiveConfigError("Unknown Zeitop presentation mode.")
    path = _runtime(root) / "fg.presentation-mode"
    if path.is_symlink():
        raise LiveConfigError("Refusing symlinked presentation-mode setting.")
    if presentation_mode(root) == mode and path.is_file():
        return
    _write_atomic(path, (mode + "\n").encode("ascii"))


def remember_config(root: Path, source: str | Path) -> None:
    """Persist only the config path deliberately selected in the GUI."""
    path = Path(source).expanduser()
    if not path.is_absolute():
        raise LiveConfigError("Choose an absolute lsfg-vk config path.")
    if path.resolve() == (_runtime(root) / "fg-live.conf.toml").resolve():
        raise LiveConfigError("Select the original lsfg-vk conf.toml, not the generated runtime copy.")
    state = fg_config.load_config(path)
    if not state["exists"]:
        raise LiveConfigError("Save the lsfg-vk config before selecting it for games.")
    _write_atomic(_runtime(root) / "fg.selected-config", (str(path) + "\n").encode())


def selected_profile(root: Path, source: Path | None = None) -> str | None:
    """Saved user choice, scoped to its canonical TOML, not the editor cursor."""
    source = Path(source) if source is not None else source_config(root)
    marker = _runtime(root) / "fg.selected-profile.json"
    if not marker.is_file() or marker.is_symlink():
        return None
    try:
        data = json.loads(marker.read_text(encoding="utf-8"))
        if not isinstance(data, dict) or data.get("config") != str(source):
            return None
        name = data.get("name")
        if not isinstance(name, str) or not name:
            return None
        profiles = fg_config.load_config(source)["profiles"]
        if sum(profile["name"] == name for profile in profiles) != 1:
            return None
        return name
    except (ValueError, OSError, fg_config.ConfigError):
        return None


def remember_profile(root: Path, source: Path, name: str) -> None:
    """Validate and persist the choice without editing lsfg-vk's TOML."""
    source = Path(source)
    if (not source.is_absolute() or not isinstance(name, str) or
            not name.strip() or "\n" in name or "\r" in name):
        raise LiveConfigError("Choose a valid named profile.")
    profiles = fg_config.load_config(source)["profiles"]
    if sum(p["name"] == name for p in profiles) != 1:
        raise LiveConfigError("Select one uniquely named profile before saving.")
    marker = _runtime(root) / "fg.selected-profile.json"
    _write_atomic(marker, json.dumps(
        {"config": str(source), "name": name},
        ensure_ascii=False
    ).encode("utf-8") + b"\n")


def active_launch_profile(root: Path, source: Path) -> str | None:
    """Profile identity loaded by the most recently started Zeitop game."""
    marker = _runtime(root) / "fg.active-launch.json"
    if not marker.is_file() or marker.is_symlink():
        return None
    try:
        data = json.loads(marker.read_text(encoding="utf-8"))
        if data.get("config") != str(source):
            return None
        name = data.get("name")
        return name if isinstance(name, str) and name else None
    except (OSError, ValueError, TypeError):
        return None


def _mark_launch(root: Path, source: Path, name: str | None) -> None:
    """Keep the startup identity: changing LSFGVK_PROFILE live is unsupported."""
    path = _runtime(root) / "fg.active-launch.json"
    _write_atomic(path, json.dumps({
        "config": str(source), "name": name
    }, ensure_ascii=False).encode("utf-8") + b"\n")


def _process_start(pid: int) -> str | None:
    """Linux process start tick: protects active sessions from PID reuse."""
    if not isinstance(pid, int) or pid < 1:
        return None
    try:
        stat = (Path("/proc") / str(pid) / "stat").read_text()
        # Field 22 is index 19 after the 2nd field (the parenthesized comm).
        return stat.rsplit(") ", 1)[1].split()[19]
    except (OSError, IndexError, ValueError):
        return None


def _session_dir(root: Path) -> Path:
    return _runtime(root) / "fg-sessions"


def _session_paths(root: Path, token: str):
    if not isinstance(token, str) or len(token) != 24 or any(
        c not in "0123456789abcdef" for c in token
    ):
        raise LiveConfigError("Invalid FG session identifier.")
    folder = _session_dir(root)
    return folder / (token + ".toml"), folder / (token + ".json")


def _session_records(root: Path):
    """Iterate active sessions, dropping only our own stale metadata/files."""
    folder = _session_dir(root)
    if not folder.is_dir() or folder.is_symlink():
        return
    for metadata in folder.glob("*.json"):
        try:
            path, expected = _session_paths(root, metadata.stem)
            if metadata.is_symlink() or path.is_symlink():
                continue
            entry = json.loads(metadata.read_text(encoding="utf-8"))
            if not isinstance(entry, dict) or entry.get("token") != metadata.stem:
                continue
            if entry.get("start") != _process_start(entry.get("pid")):
                # Steam/Proton may hand the Vulkan process to a different
                # PID after the shell launcher exits. Keep an unacknowledged
                # session available for the game's first presentation.
                if entry.get("pending") and (
                    time.time() - metadata.stat().st_mtime < 7200
                ):
                    yield entry, path, metadata
                    continue
                metadata.unlink(missing_ok=True)
                if path.is_file():
                    path.unlink()
                continue
            yield entry, path, metadata
        except (ValueError, TypeError, OSError, LiveConfigError):
            continue


def _session_content(root: Path, entry: dict, enabled: bool) -> bytes:
    canonical = Path(entry["source"])
    content = fg_config._read_existing(canonical)
    if content is None:
        raise LiveConfigError("FG profile configuration no longer exists.")
    selected = selected_profile(root, canonical)
    return render_effective(
        content, enabled=enabled,
        current_profile=entry.get("profile"), selected=selected,
        presentation_mode=entry.get("presentation_mode", "default")
    )


def _sync_sessions_locked(root: Path, enabled: bool) -> None:
    for entry, config, metadata in _session_records(root):
        try:
            # Before the first present, retain the 2x warm configuration
            # even if the GUI requests OFF: the gate will atomically bypass.
            effective_on = enabled or bool(entry.get("pending"))
            generated = _session_content(root, entry, effective_on)
            if not config.is_file() or config.read_bytes() != generated:
                _write_atomic(config, generated)
        except (fg_config.ConfigError, OSError, ValueError):
            # One broken user's source file must not block unrelated sessions.
            continue


def launch_session(root: Path, *, pid: int, env=None) -> tuple[Path, str | None, bool]:
    """Create a private lsfg-vk TOML for this launcher and arm first-present.

    The canonical file is never written. A unique session prevents the
    first-present handshake for game A from toggling game B's configuration.
    """
    root = Path(root).resolve()
    start = _process_start(pid)
    if start is None:
        raise LiveConfigError("Launcher PID is not running.")
    environ = dict(os.environ if env is None else env)
    config = source_config(root, env=environ)
    source = fg_config._read_existing(config)
    if source is None:
        raise LiveConfigError("No existing lsfg-vk configuration found.")
    if not fg_config.external_fg_available(env={
        **environ, "LSFGVK_CONFIG": str(config)
    }):
        raise LiveConfigError("lsfg-vk layer, profile or owned DLL is unavailable.")
    doc = fg_config._parse(source)
    profiles = doc.get("profile", [])
    if not profiles:
        raise LiveConfigError("No lsfg-vk profile found.")
    profile = environ.get("LSFGVK_PROFILE") or selected_profile(root, config)
    if profile and sum(p.get("name") == profile for p in profiles) != 1:
        raise LiveConfigError("Selected lsfg-vk profile no longer exists.")
    enabled = is_fg_enabled(root)
    # If no explicit profile was saved, the configured active_in rules can
    # still select a profile. Prewarm on OFF if any profile can generate.
    can_generate = (any(p.get("multiplier", 2) > 1 for p in profiles)
                    if not profile else
                    any(p.get("name") == profile and p.get("multiplier", 2) > 1
                        for p in profiles))
    runtime = _runtime(root)
    runtime.mkdir(parents=True, exist_ok=True)
    lock = runtime / "fg-live.lock"
    with lock.open("a+b") as file:
        os.fchmod(file.fileno(), 0o600)
        fcntl.flock(file.fileno(), fcntl.LOCK_EX)
        # Even launches starting ON must remain primed until their first
        # present: the GUI could switch OFF between exec and Vulkan init.
        enabled = is_fg_enabled(root)
        pending = can_generate
        mode = presentation_mode(root)
        entry = {
            "token": secrets.token_hex(12),
            "pid": pid, "start": start,
            "source": str(config), "profile": profile,
            "presentation_mode": mode, "pending": pending,
        }
        live, meta = _session_paths(root, entry["token"])
        _write_atomic(live, render_effective(
            source, enabled=enabled or pending,
            presentation_mode=mode
        ))
        _write_atomic(meta, (json.dumps(entry) + "\n").encode("utf-8"))
        _mark_launch(root, config, profile)
    return live, profile, pending


def warmup_session(root: Path, token: str, *, pid: int | None = None) -> bool:
    """Complete the first-present handshake, serialized with GUI FG toggles."""
    root = Path(root).resolve()
    live, metadata = _session_paths(root, token)
    lock = _runtime(root) / "fg-live.lock"
    with lock.open("a+b") as file:
        os.fchmod(file.fileno(), 0o600)
        fcntl.flock(file.fileno(), fcntl.LOCK_EX)
        if metadata.is_symlink() or live.is_symlink() or not metadata.is_file():
            raise LiveConfigError("FG warmup session is missing.")
        entry = json.loads(metadata.read_text(encoding="utf-8"))
        if entry.get("token") != token:
            raise LiveConfigError("FG warmup session is invalid.")
        if pid is not None:
            process_start = _process_start(pid)
            if process_start is None:
                raise LiveConfigError("Vulkan presenting process has exited.")
        elif entry.get("start") != _process_start(entry.get("pid")):
            raise LiveConfigError("FG warmup session owner is unavailable.")
        if entry.get("pending"):
            content = _session_content(root, entry, is_fg_enabled(root))
            _write_atomic(live, content)
            entry["pending"] = False
        if pid is not None and (entry.get("pid") != pid or
                                entry.get("start") != process_start):
            entry["pid"] = pid
            entry["start"] = process_start
        _write_atomic(metadata, (json.dumps(entry) + "\n").encode("utf-8"))
    return True


def render_effective(original: bytes, *, enabled: bool,
                     current_profile: str | None = None,
                     selected: str | None = None,
                     presentation_mode: str = "default") -> bytes:
    """Preserve canonical settings, overriding only hot-reloadable fields.

    A running process retains the LSFGVK_PROFILE chosen at launch. When
    the user saves a different selected profile, copy multiplier, flow_scale
    and performance_mode from that selected profile onto the old startup
    profile only in the runtime file. No structural fields are copied.
    """
    if presentation_mode not in PRESENTATION_MODES:
        raise LiveConfigError("Unknown Zeitop presentation mode.")
    if len(original) > fg_config.MAX_SIZE:
        raise LiveConfigError("The source configuration is too large.")
    doc = fg_config._parse(original)
    profiles = doc.get("profile", [])
    if not profiles:
        raise LiveConfigError("At least one lsfg-vk profile must exist.")
    source_profile = None
    target_profile = None
    if current_profile and selected and current_profile != selected:
        choices = [p for p in profiles if p.get("name") == selected]
        active = [p for p in profiles if p.get("name") == current_profile]
        if len(choices) == len(active) == 1:
            source_profile, target_profile = choices[0], active[0]
    if enabled and source_profile is None and presentation_mode == "default":
        return original
    try:
        source = original.decode("utf-8")
    except UnicodeError as exc:
        raise LiveConfigError("lsfg-vk config is not UTF-8.") from exc
    segments = fg_config._segments(source)
    output = []
    index = 0
    for segment in segments:
        section = segment["name"]
        lines = segment["lines"]
        if section == "[[profile]]":
            if index >= len(profiles):
                raise LiveConfigError("Could not match lsfg-vk profile definitions.")
            original_profile = profiles[index]
            new_fields = {}
            defaults = {}
            if source_profile is not None and original_profile is target_profile:
                for field, default in (
                    ("multiplier", 2), ("flow_scale", 1.0),
                    ("performance_mode", False)
                ):
                    new_fields[field] = source_profile.get(field, default)
                    defaults[field] = default
            if not enabled:
                new_fields["multiplier"] = 1
                defaults["multiplier"] = 2
            if presentation_mode == "immediate":
                # Runtime copy only; never alter the user's source TOML.
                # This does not change lsfg-vk's internal vsync pacing mode.
                new_fields["override_present_mode"] = False
                defaults["override_present_mode"] = True
            output.extend(
                fg_config._rewrite_table(lines, original_profile, new_fields, defaults)
                if new_fields else lines
            )
            index += 1
        elif section.startswith("[profile.") or section.startswith("[[profile."):
            raise LiveConfigError("Nested profile sections cannot be safely overridden.")
        else:
            output.extend(lines)
    if index != len(profiles):
        raise LiveConfigError("Could not locate every lsfg-vk profile.")
    rendered = "".join(output).encode("utf-8")
    parsed = fg_config._parse(rendered)
    if len(parsed.get("profile", [])) != len(profiles):
        raise LiveConfigError("Unexpected profile count in generated config.")
    if not enabled and any(p.get("multiplier", 2) != 1 for p in parsed["profile"]):
        raise LiveConfigError("Failed to disable all multipliers in live config.")
    if presentation_mode == "immediate" and any(
        p.get("override_present_mode", True) is not False
        for p in parsed["profile"]
    ):
        raise LiveConfigError("Failed to disable present-mode override.")
    if source_profile is not None and target_profile is not None:
        target = parsed["profile"][profiles.index(target_profile)]
        for key in ("flow_scale", "performance_mode"):
            if target.get(key, fg_config.PROFILE_DEFAULTS[key]) != source_profile.get(
                key, fg_config.PROFILE_DEFAULTS[key]
            ):
                raise LiveConfigError("Failed to hot-sync profile: " + key)
        expected = source_profile.get("multiplier", 2) if enabled else 1
        if target.get("multiplier", 2) != expected:
            raise LiveConfigError("Failed to hot-sync profile: multiplier")
    return rendered


def prepare_live(root: Path, *, enabled: bool | None = None,
                 source: Path | None = None, env=None,
                 validator: str | None = None,
                 commit_state: bool = False,
                 mark_launch: bool = False) -> Path:
    """Safely regenerate the hot-reload file for currently running games.

    Call both at launch and whenever the GUI changes FG state or source
    settings. Uses flock across launcher processes and GUI to avoid races.
    """
    root = Path(root).resolve()
    runtime = _runtime(root)
    runtime.mkdir(parents=True, exist_ok=True)
    lock = runtime / "fg-live.lock"
    with lock.open("a+b") as file:
        os.fchmod(file.fileno(), 0o600)
        fcntl.flock(file.fileno(), fcntl.LOCK_EX)
        config = Path(source) if source is not None else source_config(root, env=env)
        if not config.is_absolute():
            raise LiveConfigError("Source configuration must be absolute.")
        state = fg_config.load_config(config)
        if not state["exists"]:
            raise LiveConfigError("No existing lsfg-vk conf.toml found.")
        if enabled is None:
            enabled = is_fg_enabled(root)
        content = fg_config._read_existing(config)
        if content is None:
            raise LiveConfigError("Source configuration disappeared.")
        selected = selected_profile(root, config)
        environ = dict(os.environ if env is None else env)
        inherited = environ.get("LSFGVK_PROFILE")
        launch_name = inherited or selected
        active_name = launch_name if mark_launch else active_launch_profile(root, config)
        generated = render_effective(
            content, enabled=enabled,
            current_profile=active_name, selected=selected,
            presentation_mode=presentation_mode(root)
        )
        if validator:
            # The underlying parser is the same one validated for v2 and
            # the temporary candidate is checked with the installed CLI.
            import subprocess
            fd, candidate_name = tempfile.mkstemp(prefix=".fg-validate-",
                                                  suffix=".toml", dir=runtime)
            candidate = Path(candidate_name)
            try:
                with os.fdopen(fd, "wb") as out:
                    out.write(generated)
                result = subprocess.run([validator, "validate", "-c", str(candidate)],
                                        capture_output=True, text=True, timeout=12)
                if result.returncode:
                    raise LiveConfigError("Invalid live lsfg-vk config: " +
                                          (result.stderr or result.stdout).strip()[:250])
            except (OSError, subprocess.TimeoutExpired) as exc:
                raise LiveConfigError("lsfg-vk validation failed: " + str(exc)) from exc
            finally:
                candidate.unlink(missing_ok=True)
        destination = runtime / "fg-live.conf.toml"
        try:
            if destination.is_file() and not destination.is_symlink() and destination.read_bytes() == generated:
                if commit_state:
                    set_fg_enabled(root, enabled)
                _sync_sessions_locked(root, enabled)
                if mark_launch:
                    _mark_launch(root, config, launch_name)
                    return destination, launch_name
                return destination
        except OSError:
            pass
        if destination.is_symlink():
            raise LiveConfigError("Refusing to overwrite a symlinked live config.")
        _write_atomic(destination, generated)
        if commit_state:
            set_fg_enabled(root, enabled)
        _sync_sessions_locked(root, enabled)
        if mark_launch:
            _mark_launch(root, config, launch_name)
            return destination, launch_name
        return destination


def switch_live(root: Path, enabled: bool) -> Path:
    """Update live config first; don't change GUI state if update fails."""
    source = source_config(root)
    env = dict(os.environ)
    env["LSFGVK_CONFIG"] = str(source)
    if enabled and not fg_config.external_fg_available(env=env):
        raise LiveConfigError("lsfg-vk layer, profile, or DLL is unavailable.")
    # Hold the same lock as the launcher until BOTH the live TOML and
    # the persisted toggle state have been committed. A simultaneous
    # game launch cannot restore a stale multiplier between these writes.
    return prepare_live(root, enabled=enabled, source=source, commit_state=True)


def cli():
    if len(sys.argv) < 3:
        raise SystemExit("Usage: fg_live.py <prepare|launch|session|warmup> <root> [pid|token]")
    op = sys.argv[1]
    root = Path(sys.argv[2])
    try:
        if op == "session" and len(sys.argv) == 4:
            live, profile, pending = launch_session(root, pid=int(sys.argv[3]))
            print(live)
            print(profile or "")
            print("1" if pending else "0")
            # The session snapshots the option before its first present.
            # Never re-read a concurrently modified global preference here.
            entry = json.loads(live.with_suffix(".json").read_text(encoding="utf-8"))
            print(entry["presentation_mode"])
        elif op == "warmup" and len(sys.argv) in (4, 5):
            from fg_ipc import request_warmup
            token = sys.argv[3]
            pid = int(sys.argv[4]) if len(sys.argv) == 5 else None
            if request_warmup(root, token):
                if os.environ.get("ZEITOP_DEBUG"):
                    print("ZEITOP_FG_IPC_ACK", file=sys.stderr)
            else:
                # Direct Linux without a running Zeitop GUI retains the
                # original synchronous helper path for existing use/tests.
                warmup_session(root, token, pid=pid)
        elif op == "launch" and len(sys.argv) == 3:
            _, name = prepare_live(root, mark_launch=True)
            print(name or "")
        elif op == "prepare" and len(sys.argv) == 3:
            print(prepare_live(root))
        else:
            raise LiveConfigError("Invalid FG operation arguments.")
    except (fg_config.ConfigError, OSError, ValueError) as exc:
        print(f"Zeitop: FG configuration failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(cli())
