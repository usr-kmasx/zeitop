"""Standalone editor for the user's existing lsfg-vk 2.x TOML configuration.

No lsfg-vk source or library is copied, patched, embedded or redistributed.
This module never writes the user's configuration until save_config is called.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import re
import shutil
import stat
import subprocess
import tempfile
import time
import tomllib
from pathlib import Path

MAX_SIZE = 1024 * 1024
GLOBAL_DEFAULTS = {"dll": "", "allow_fp16": True, "log_level": "info", "log_file": ""}
PROFILE_DEFAULTS = {
    "name": "", "active_in": [], "multiplier": 2, "flow_scale": 1.0,
    "performance_mode": False, "pacing_mode": "vsync",
    "override_present_mode": True, "preserve_swapchain_image_count": False,
}
GLOBAL_FIELDS = tuple(GLOBAL_DEFAULTS)
PROFILE_FIELDS = tuple(PROFILE_DEFAULTS)
BLOCK_HEADER = re.compile(r"^\s*(\[\[[\w.-]+\]\]|\[[\w.-]+\])\s*(?:#.*)?$")
ASSIGNMENT = re.compile(r"^(\s*)([A-Za-z_][\w-]*)(\s*=\s*)(.*)$")


class ConfigError(ValueError):
    """User-visible, non-destructive configuration validation failure."""


def discover_config(*, env=None) -> Path:
    """Use an explicit lsfg-vk config first, then existing XDG and HOME files."""
    env = os.environ if env is None else env
    home = Path(env.get("HOME") or str(Path.home())).expanduser()
    explicit = env.get("LSFGVK_CONFIG")
    if explicit:
        candidate = Path(explicit).expanduser()
        if not candidate.is_absolute():
            raise ConfigError("LSFGVK_CONFIG must be an absolute file path.")
        return candidate

    xdg = env.get("XDG_CONFIG_HOME")
    candidates = []
    if xdg and Path(xdg).is_absolute():
        candidates.append(Path(xdg) / "lsfg-vk" / "conf.toml")
    candidates.append(home / ".config" / "lsfg-vk" / "conf.toml")
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    # Some Zeitop launches set XDG_CONFIG_HOME to a private WebKit runtime
    # directory; do not invent an lsfg-vk config there when none exists.
    return candidates[-1]


def _read_existing(path: Path):
    if path.is_symlink():
        raise ConfigError("The configuration is a symbolic link. Select the real file.")
    if not path.exists():
        return None
    if not path.is_file():
        raise ConfigError("Configuration path is not a regular file.")
    if path.stat().st_size > MAX_SIZE:
        raise ConfigError("The configuration file is unexpectedly large.")
    return path.read_bytes()


def _digest(data: bytes | None) -> str:
    return "missing" if data is None else hashlib.sha256(data).hexdigest()


def _parse(data: bytes | None) -> dict:
    try:
        doc = tomllib.loads(data.decode("utf-8")) if data is not None else {"version": 2}
    except (UnicodeError, tomllib.TOMLDecodeError) as exc:
        raise ConfigError("Invalid TOML: " + str(exc)) from exc
    if doc.get("version") != 2 or type(doc.get("version")) is not int:
        raise ConfigError("Only lsfg-vk version 2 configurations are supported.")
    if not isinstance(doc.get("global", {}), dict):
        raise ConfigError("Invalid [global] section.")
    profiles = doc.get("profile", [])
    if not isinstance(profiles, list) or any(not isinstance(p, dict) for p in profiles):
        raise ConfigError("Expected one or more [[profile]] entries.")
    return doc


def load_config(path: Path | str) -> dict:
    path = Path(path).expanduser()
    if not path.is_absolute():
        raise ConfigError("Configuration path must be absolute.")
    data = _read_existing(path)
    parsed = _parse(data)
    global_values = {k: parsed.get("global", {}).get(k, default)
                     for k, default in GLOBAL_DEFAULTS.items()}
    profiles = []
    for i, item in enumerate(parsed.get("profile", [])):
        profile = {"source_index": i}
        profile.update({k: item.get(k, default) for k, default in PROFILE_DEFAULTS.items()})
        profiles.append(profile)
    return {
        "path": str(path), "exists": data is not None,
        "revision": _digest(data), "version": 2,
        "global": global_values, "profiles": profiles,
    }


def _validate_global(global_data: dict) -> dict:
    if not isinstance(global_data, dict):
        raise ConfigError("Invalid global configuration.")
    val = {k: global_data.get(k, default) for k, default in GLOBAL_DEFAULTS.items()}
    for k in ("dll", "log_file", "log_level"):
        if not isinstance(val[k], str) or len(val[k]) > 4096:
            raise ConfigError(f"Invalid {k}.")
    if type(val["allow_fp16"]) is not bool:
        raise ConfigError("Allow FP16 must be enabled or disabled.")
    if val["log_level"] not in ("debug", "info", "warning", "error"):
        raise ConfigError("Log level must be debug, info, warning or error.")
    dll = val["dll"].strip()
    if dll:
        candidate = Path(dll).expanduser()
        if candidate.name.lower() != "lsfg-vk.dll":
            raise ConfigError("lsfg-vk 2.x requires the user-owned lsfg-vk.dll file.")
        if not candidate.is_absolute() or not candidate.is_file():
            raise ConfigError("The selected lsfg-vk.dll does not exist.")
        if not os.access(candidate, os.R_OK):
            raise ConfigError("Cannot read the selected lsfg-vk.dll.")
        val["dll"] = str(candidate)
    if val["log_file"] and not Path(val["log_file"]).is_absolute():
        raise ConfigError("Log file path must be absolute or empty.")
    return val


def _validate_profile(profile: dict, original_count: int) -> dict:
    if not isinstance(profile, dict):
        raise ConfigError("Invalid profile entry.")
    value = {k: profile.get(k, default) for k, default in PROFILE_DEFAULTS.items()}
    src = profile.get("source_index")
    if src is not None and (type(src) is not int or not 0 <= src < original_count):
        raise ConfigError("A profile refers to an invalid original entry.")
    value["source_index"] = src
    if not isinstance(value["name"], str) or not value["name"].strip() or len(value["name"]) > 120:
        raise ConfigError("Every profile needs a name (up to 120 characters).")
    value["name"] = value["name"].strip()
    active = value["active_in"]
    if isinstance(active, str):
        active = active.strip()
    elif isinstance(active, list) and all(isinstance(x, str) for x in active):
        active = [x.strip() for x in active if x.strip()]
    else:
        raise ConfigError("Active In must be a name or a list of names.")
    if isinstance(active, list) and (len(active) > 64 or
                                     any(len(x) > 1024 for x in active)):
        raise ConfigError("Too many or overly long Active In entries.")
    if isinstance(active, str) and len(active) > 1024:
        raise ConfigError("Active In name is too long.")
    value["active_in"] = active
    if type(value["multiplier"]) is not int or not 1 <= value["multiplier"] <= 1024:
        raise ConfigError("Multiplier must be an integer between 1 and 1024.")
    if (type(value["flow_scale"]) not in (int, float) or
            not math.isfinite(value["flow_scale"]) or
            not 0.25 <= value["flow_scale"] <= 1.0):
        raise ConfigError("Flow Scale must be between 0.25 and 1.0.")
    value["flow_scale"] = float(value["flow_scale"])
    for k in ("performance_mode", "override_present_mode", "preserve_swapchain_image_count"):
        if type(value[k]) is not bool:
            raise ConfigError(f"Invalid {k}.")
    if value["pacing_mode"] != "vsync":
        raise ConfigError("Only pacing_mode = vsync is supported in lsfg-vk 2.0.")
    return value


def _normalize_active(active):
    return [active] if isinstance(active, str) and active else (active or [])


def _value_equal(key, a, b):
    if key == "active_in":
        return _normalize_active(a) == _normalize_active(b)
    return a == b


def _encode(value):
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return repr(value)
    if isinstance(value, list):
        return "[ " + ", ".join(_encode(x) for x in value) + " ]" if value else "[ ]"
    raise ConfigError("Unsupported TOML value.")


def _comment_offset(text: str):
    quote = None
    escaped = False
    for i, char in enumerate(text):
        if escaped:
            escaped = False
        elif quote == '"' and char == "\\":
            escaped = True
        elif quote is not None and char == quote:
            quote = None
        elif quote is None and char in ("'", '"'):
            quote = char
        elif char == "#" and quote is None:
            return i
    return None


def _segments(source: str):
    segments = [{"name": "root", "lines": []}]
    for line in source.splitlines(keepends=True):
        m = BLOCK_HEADER.match(line.rstrip("\r\n"))
        if m:
            token = m.group(1)
            segments.append({"name": token, "lines": [line]})
        else:
            segments[-1]["lines"].append(line)
    return segments


def _rewrite_table(lines: list[str], original: dict, desired: dict, defaults: dict):
    changes = {}
    for key, fallback in defaults.items():
        previous = original.get(key, fallback)
        updated = desired[key]
        if not _value_equal(key, previous, updated):
            changes[key] = updated
    if not changes:
        return lines

    out = []
    handled = set()
    for line in lines:
        found = ASSIGNMENT.match(line.rstrip("\r\n"))
        if found and found.group(2) in changes:
            key = found.group(2)
            value = changes[key]
            handled.add(key)
            if (key in ("dll", "log_file", "active_in") and not value):
                continue
            trailing = found.group(4)
            comment_at = _comment_offset(trailing)
            suffix = ""
            if comment_at is not None:
                suffix = " " + trailing[comment_at:]
            # Reject complex multiline syntax instead of accidentally
            # interpreting continuation lines as unrelated config entries.
            parsed_value = trailing[:comment_at].strip() if comment_at is not None else trailing.strip()
            if (parsed_value.startswith("[") and "]" not in parsed_value) or parsed_value.startswith('"""'):
                raise ConfigError(f"Cannot rewrite multiline value for {key}; edit it manually.")
            out.append(found.group(1) + key + found.group(3) +
                       _encode(value) + suffix + "\n")
        else:
            out.append(line)
    for key, value in changes.items():
        if key not in handled and not (key in ("dll", "log_file", "active_in") and not value):
            if out and not out[-1].endswith("\n"):
                out[-1] += "\n"
            out.append(key + " = " + _encode(value) + "\n")
    return out


def _new_profile_lines(value: dict) -> list[str]:
    lines = ["\n[[profile]]\n"]
    for k in PROFILE_FIELDS:
        v = value[k]
        if k == "active_in" and not v:
            continue
        lines.append(f"{k} = {_encode(v)}\n")
    return lines


def _render(original_text: str, old: dict, new_global: dict, new_profiles: list):
    parts = _segments(original_text)
    old_profiles = old.get("profile", [])
    result = []
    seen_global = False
    old_index = 0
    kept = {p["source_index"]: p for p in new_profiles if p["source_index"] is not None}
    for block in parts:
        name = block["name"]
        if name == "[global]":
            if seen_global:
                raise ConfigError("Duplicate global sections.")
            seen_global = True
            result.extend(_rewrite_table(block["lines"], old.get("global", {}),
                                         new_global, GLOBAL_DEFAULTS))
        elif name == "[[profile]]":
            if old_index in kept:
                result.extend(_rewrite_table(block["lines"], old_profiles[old_index],
                                             kept[old_index], PROFILE_DEFAULTS))
            old_index += 1
        else:
            if name.startswith("[[profile.") or name.startswith("[profile."):
                raise ConfigError("Nested profile sections require manual editing.")
            result.extend(block["lines"])
    if old_index != len(old_profiles):
        raise ConfigError("Cannot match profile sections reliably.")
    if not seen_global:
        # Required global stanza is inserted immediately after the root.
        result = _segments("".join(result))
        result[0]["lines"].append("\n[global]\n")
        result[0]["lines"].extend(_rewrite_table([], {}, new_global, GLOBAL_DEFAULTS))
        result = [line for part in result for line in part["lines"]]
    for profile in new_profiles:
        if profile["source_index"] is None:
            result.extend(_new_profile_lines(profile))
    return "".join(result)


def save_config(path: Path | str, values: dict, expected_revision: str,
                *, validator: str | None = None) -> dict:
    """Safely update ONLY a user-selected TOML path; never change a game or layer."""
    path = Path(path).expanduser()
    if not path.is_absolute():
        raise ConfigError("Configuration path must be absolute.")
    previous = _read_existing(path)
    if _digest(previous) != expected_revision:
        raise ConfigError("Configuration changed outside Zeitop. Reload before saving.")
    current = _parse(previous)
    if not isinstance(values, dict):
        raise ConfigError("Invalid settings payload.")
    global_data = _validate_global(values.get("global"))
    incoming = values.get("profiles")
    if not isinstance(incoming, list) or not 1 <= len(incoming) <= 100:
        raise ConfigError("Create at least one profile before saving.")
    profiles = [_validate_profile(p, len(current.get("profile", []))) for p in incoming]
    indices = [p["source_index"] for p in profiles if p["source_index"] is not None]
    if len(indices) != len(set(indices)):
        raise ConfigError("Duplicate profile reference.")
    names = [p["name"] for p in profiles]
    if len(names) != len(set(names)):
        raise ConfigError("Profile names must be unique.")
    original = previous.decode("utf-8") if previous is not None else "version = 2\n"
    changed_text = _render(original, current, global_data, profiles)
    parsed = _parse(changed_text.encode("utf-8"))
    if len(parsed.get("profile", [])) != len(profiles):
        raise ConfigError("Generated profile count does not match.")
    if previous is not None and changed_text.encode("utf-8") == previous:
        return {"changed": False, "backup": None, "state": load_config(path)}
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(prefix=".zeitop-edit-", suffix=".toml", dir=path.parent)
    temporary = Path(temporary_name)
    backup = None
    try:
        mode = stat.S_IMODE(path.stat().st_mode) if previous is not None else 0o600
        os.fchmod(fd, mode)
        with os.fdopen(fd, "wb") as f:
            f.write(changed_text.encode("utf-8"))
            f.flush()
            os.fsync(f.fileno())
        if validator is not None:
            try:
                run = subprocess.run([validator, "validate", "-c", str(temporary)],
                                     text=True, capture_output=True, timeout=12)
            except (OSError, subprocess.TimeoutExpired) as exc:
                raise ConfigError("lsfg-vk validation could not run: " + str(exc)) from exc
            if run.returncode:
                raise ConfigError("lsfg-vk validation failed: " +
                                  (run.stderr or run.stdout).strip()[:300])
        if _digest(_read_existing(path)) != expected_revision:
            raise ConfigError("Configuration changed outside Zeitop. Reload before saving.")
        if previous is not None:
            stamp = str(time.time_ns())
            backup = path.with_name(path.name + ".zeitop-bak-" + stamp)
            with backup.open("xb") as f:
                os.fchmod(f.fileno(), 0o600)
                f.write(previous)
                f.flush()
                os.fsync(f.fileno())
        os.replace(temporary, path)
        parentfd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(parentfd)
        finally:
            os.close(parentfd)
    finally:
        temporary.unlink(missing_ok=True)
    return {"changed": True, "backup": str(backup) if backup else None,
            "state": load_config(path)}


def runtime_status(config: Path | str) -> dict:
    """Only observes installed external tools and the selected config file."""
    config = Path(config)
    cli = shutil.which("lsfg-vk-cli")
    if not cli:
        cli_local = Path.home() / ".local/bin/lsfg-vk-cli"
        cli = str(cli_local) if cli_local.is_file() else None
    return {
        "config_path": str(config),
        "config_exists": config.is_file(),
        "cli_path": cli,
        "cli_available": bool(cli),
        "layer_is_separate": True,
        "integration_status": "Config editor only — no lsfg-vk layer is bundled or activated.",
    }
