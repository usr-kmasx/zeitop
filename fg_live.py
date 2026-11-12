"""Generated live lsfg-vk configuration for Zeitop-launched games.

The user-owned conf.toml is the canonical source and is NEVER modified by
Frame Generation power toggling. The game reads a derived file in runtime/
and lsfg-vk's own hot reload watches it. No lsfg-vk code is included.
"""
from __future__ import annotations

import fcntl
import json
import os
import sys
import tempfile
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


def render_effective(original: bytes, *, enabled: bool,
                     current_profile: str | None = None,
                     selected: str | None = None) -> bytes:
    """Preserve canonical settings, overriding only hot-reloadable fields.

    A running process retains the LSFGVK_PROFILE chosen at launch. When
    the user saves a different selected profile, copy multiplier, flow_scale
    and performance_mode from that selected profile onto the old startup
    profile only in the runtime file. No structural fields are copied.
    """
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
    if enabled and source_profile is None:
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
            current_profile=active_name, selected=selected
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
    if len(sys.argv) != 3 or sys.argv[1] not in ("prepare", "launch"):
        raise SystemExit("Usage: fg_live.py <prepare|launch> <zeitop-root>")
    try:
        if sys.argv[1] == "launch":
            root = Path(sys.argv[2])
            _, launch_name = prepare_live(root, mark_launch=True)
            # Return the exact profile recorded while the launch lock was
            # held. A concurrent Save cannot change this launch's identity.
            print(launch_name or "")
        else:
            print(prepare_live(Path(sys.argv[2])))
    except (fg_config.ConfigError, OSError) as exc:
        print(f"Zeitop: cannot prepare lsfg-vk live config: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(cli())
