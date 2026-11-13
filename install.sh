#!/usr/bin/env bash
# Install Zeitop for the current Arch Linux user; no system-wide hooks.
set -euo pipefail

source_root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)
if [[ ${1:-} == --help ]]; then
  cat <<'HELP'
Usage: ./install.sh [--skip-deps]
Installs Zeitop into $XDG_DATA_HOME/zeitop (default ~/.local/share/zeitop),
with ~/.local/bin/{zeitop,zeitop-run}, a desktop entry, and an icon.
On Arch Linux, installs missing shared packages via sudo pacman.
--skip-deps: skip pacman operations (for isolated integration tests).
The external lsfg-vk and proprietary Lossless Scaling DLL are never installed.
HELP
  exit 0
fi
skip_deps=0
if [[ ${1:-} == --skip-deps && $# == 1 ]]; then
  skip_deps=1
elif (( $# != 0 )); then
  echo "Zeitop: unknown install argument (try --help)." >&2
  exit 2
fi
if (( EUID == 0 )); then
  echo "Zeitop: install as your normal user, not root." >&2
  exit 2
fi
: "${HOME:?HOME must be set}"
data_home=${XDG_DATA_HOME:-"$HOME/.local/share"}
if [[ "$data_home" != /* || "$HOME" != /* ]]; then
  echo "Zeitop: HOME and XDG_DATA_HOME must be absolute paths." >&2
  exit 2
fi
app_dir="$data_home/zeitop"
bin_dir="$HOME/.local/bin"
desktop_dir="$data_home/applications"
icon_dir="$data_home/icons/hicolor/128x128/apps"
# The desktop filename must match Gtk.Application's Wayland application ID.
app_id="io.github.usr_kmasx.Zeitop"
desktop_file="$desktop_dir/$app_id.desktop"
icon_file="$icon_dir/$app_id.png"
managed_token="ZEITOP_MANAGED_INSTALL_V1"
launcher_token="ZEITOP_MANAGED_LAUNCHER_V1"
required=(python python-gobject gtk4 webkitgtk-6.0 gcc lib32-gcc-libs file vulkan-icd-loader lib32-vulkan-icd-loader)

# Source and destination must never overlap: do not damage a Git checkout.
if [[ "$app_dir" == "$source_root" || "$app_dir" == "$source_root/"* ||
      "$source_root" == "$app_dir/"* || "$app_dir" == / || "$app_dir" == "$HOME" ]]; then
  echo "Zeitop: source and installation directory must be separate." >&2
  exit 2
fi
if [[ -L "$app_dir" ]]; then
  echo "Zeitop: refusing a symlinked application directory." >&2
  exit 2
fi
if [[ -e "$app_dir" ]] && [[ ! -f "$app_dir/.zeitop-managed" ||
       "$(cat "$app_dir/.zeitop-managed")" != "$managed_token" ]]; then
  echo "Zeitop: installation path already exists and is not managed by Zeitop: $app_dir" >&2
  exit 2
fi
if [[ -f "$app_dir/runtime/zeitop.lock" ]]; then
  if ! command -v flock >/dev/null 2>&1; then
    echo "Zeitop: missing flock; cannot safely upgrade a running instance." >&2
    exit 2
  fi
  exec {lockfd}< "$app_dir/runtime/zeitop.lock"
  if ! flock -n "$lockfd"; then
    echo "Zeitop: close the installed application before reinstalling." >&2
    exit 2
  fi
fi
for path in "$bin_dir/zeitop" "$bin_dir/zeitop-run"; do
  if [[ -e "$path" || -L "$path" ]] && ! grep -Fq "$launcher_token" "$path" 2>/dev/null; then
    echo "Zeitop: refusing to replace an unrelated launcher: $path" >&2
    exit 2
  fi
done
if [[ -e "$desktop_file" || -L "$desktop_file" ]] &&
   ! grep -Fq 'X-Zeitop-Managed=true' "$desktop_file" 2>/dev/null; then
  echo "Zeitop: refusing to replace an unrelated desktop entry: $desktop_file" >&2
  exit 2
fi
if [[ -e "$icon_file" || -L "$icon_file" ]] && [[ ! -d "$app_dir" ]]; then
  echo "Zeitop: refusing to replace an existing icon not owned by this installation." >&2
  exit 2
fi

missing=()
if (( ! skip_deps )); then
  if ! command -v pacman >/dev/null 2>&1; then
    echo "Zeitop: automatic dependency installation requires Arch Linux (pacman)." >&2
    exit 2
  fi
  for pkg in "${required[@]}"; do
    if ! pacman -Q "$pkg" >/dev/null 2>&1; then
      missing+=("$pkg")
    fi
  done
  if (( ${#missing[@]} )); then
    echo "Zeitop: missing Arch packages: ${missing[*]}"
    echo "Zeitop: requesting installation of missing dependencies only."
    # --asdeps avoids taking ownership of already-installed explicit packages.
    sudo pacman -S --needed --asdeps -- "${missing[@]}"
  fi
else
  echo "Zeitop: dependency/package-manager operations skipped for testing."
fi
for utility in python3 cc; do
  if ! command -v "$utility" >/dev/null 2>&1; then
    echo "Zeitop: missing required tool: $utility" >&2
    exit 1
  fi
done
# Do not install an app that cannot run its GUI.
if ! python3 - <<'PY'
import gi
gi.require_version("Gtk", "4.0")
gi.require_version("WebKit", "6.0")
from gi.repository import Gtk, WebKit
PY
then
  echo "Zeitop: Python GTK4 / WebKitGTK 6.0 bindings unavailable." >&2
  exit 1
fi

mkdir -p -- "$data_home" "$bin_dir" "$desktop_dir" "$icon_dir"
stage=$(mktemp -d "$data_home/.zeitop-stage.XXXXXXXX")
old_dir=""
published=0
cleanup() {
  result=$?
  trap - EXIT
  if (( result != 0 )) && (( published )); then
    if [[ -f "$app_dir/.zeitop-managed" ]] && [[ "$(cat "$app_dir/.zeitop-managed")" == "$managed_token" ]]; then
      rm -rf -- "$app_dir"
    fi
    if [[ -n "$old_dir" && -d "$old_dir" ]]; then mv -- "$old_dir" "$app_dir"; fi
  fi
  [[ ! -d "$stage" ]] || rm -rf -- "$stage"
  if (( result == 0 )) && [[ -n "$old_dir" ]]; then rm -rf -- "$old_dir"; fi
  exit "$result"
}
trap cleanup EXIT

# Explicit application payload: exclude .git, tests, private config, logs and
# the existing project's runtime (which may contain game session data).
for file in app.py core.py fg_config.py fg_ipc.py fg_live.py \
            build.sh run.sh zeitop-run install.sh uninstall.sh limiter.c vulkan_layer.c VERSION README.md; do
  cp -p -- "$source_root/$file" "$stage/$file"
done
cp -R -- "$source_root/ui" "$source_root/vendor" "$source_root/docs" "$stage/"
printf '%s\n' "$managed_token" > "$stage/.zeitop-managed"
# Preserve only Zeitop's durable preferences: on upgrade they come from
# the previous installed copy, and on first install from the checkout.
# No sockets, session metadata, saved game logs, binaries or cache are moved.
state_source="$source_root/runtime"
if [[ -d "$app_dir" ]]; then state_source="$app_dir/runtime"; fi
if [[ -d "$state_source" && ! -L "$state_source" ]]; then
  mkdir -p -- "$stage/runtime"
  for name in limit.state fg.state fg.presentation-mode fg.selected-config fg.selected-profile.json; do
    prev="$state_source/$name"
    if [[ -f "$prev" && ! -L "$prev" && $(stat -c '%s' "$prev") -le 16384 ]]; then
      cp -p -- "$prev" "$stage/runtime/$name"
    fi
  done
fi
# Rebuild all native 64/32-bit libraries in the staged, self-contained copy.
"$stage/build.sh"
if [[ -d "$app_dir" && -f "$app_dir/.zeitop-installed-deps" ]]; then
  cp -p -- "$app_dir/.zeitop-installed-deps" "$stage/.zeitop-installed-deps"
fi
for pkg in "${missing[@]}"; do printf '%s\n' "$pkg" >> "$stage/.zeitop-installed-deps"; done
if [[ -f "$stage/.zeitop-installed-deps" ]]; then
  sort -u "$stage/.zeitop-installed-deps" -o "$stage/.zeitop-installed-deps"
fi

if [[ -d "$app_dir" ]]; then
  old_dir=$(mktemp -d "$data_home/.zeitop-old.XXXXXXXX")
  rmdir -- "$old_dir"
  mv -- "$app_dir" "$old_dir"
fi
mv -- "$stage" "$app_dir"
published=1

# Only our exact launcher paths are created; they delegate into the installed
# directory so ZEITOP_HOME stays correct for Steam/Proton.
for command in zeitop zeitop-run; do
  entry="$app_dir/run.sh"
  if [[ "$command" == zeitop-run ]]; then entry="$app_dir/zeitop-run"; fi
  printf -v escaped_entry '%q' "$entry"
  target="$bin_dir/$command"
  temp_target=$(mktemp "$bin_dir/.zeitop-launcher.XXXXXXXX")
  printf '#!/usr/bin/env bash\n# %s\nexec %s "$@"\n' "$launcher_token" "$escaped_entry" > "$temp_target"
  chmod 755 "$temp_target"
  mv -f -- "$temp_target" "$target"
done

# The path is quoted according to the Desktop Entry specification; percent
# signs must be doubled and shell-sensitive characters escaped.
desktop_command=$(python3 - "$bin_dir/zeitop" <<'PY'
import sys
s=sys.argv[1]
if '\n' in s or '\r' in s:
    raise SystemExit("Invalid desktop path")
s=s.replace('\\', '\\\\').replace('"', '\\"').replace('$', '\\$').replace('`', '\\`').replace('%', '%%')
print('"' + s + '"')
PY
)
temp_desktop=$(mktemp "$desktop_dir/.zeitop-desktop.XXXXXXXX")
cat > "$temp_desktop" <<DESKTOP
[Desktop Entry]
Type=Application
Name=Zeitop
Comment=Vulkan frame pacing and frame-generation telemetry
Exec=$desktop_command
# GNOME requires a resolvable icon; an absolute managed PNG path also
# works without a user-local hicolor index.theme or fresh icon cache.
Icon=$icon_file
Terminal=false
Categories=Utility;
StartupNotify=true
StartupWMClass=$app_id
X-Zeitop-Managed=true
DESKTOP
chmod 644 "$temp_desktop"
mv -f -- "$temp_desktop" "$desktop_file"
cp -- "$app_dir/ui/assets/zeitop-icon.png" "$icon_file"

echo "Zeitop: installed successfully."
printf '  Application: %s\n  Launcher: %s\n  Steam wrapper: %s\n  Desktop entry: %s\n' \
  "$app_dir" "$bin_dir/zeitop" "$bin_dir/zeitop-run" "$desktop_file"
echo "  Use 'zeitop' (or the GNOME application menu) to open the interface."
echo "  External lsfg-vk and Lossless Scaling are separate, optional dependencies."
