#!/usr/bin/env bash
# Remove only Zeitop-managed per-user files, not shared system packages.
set -euo pipefail
if [[ ${1:-} == --help ]]; then
  cat <<'HELP'
Usage: ./uninstall.sh [--remove-deps]
Removes the managed Zeitop installation, desktop entry, icon, both launchers,
compiled libraries, caches, session files, and Zeitop-local preferences.
Does not touch the Git source tree, Steam settings, or external lsfg-vk.
--remove-deps: on Arch, also remove ONLY packages tracked as installed by
Zeitop that are now pacman orphans. Other distros retain shared packages;
automatic reverse dependency removal is not supported there.
HELP
  exit 0
fi
remove_deps=0
if [[ ${1:-} == --remove-deps && $# == 1 ]]; then
  remove_deps=1
elif (( $# != 0 )); then
  echo "Zeitop: unknown uninstall argument (try --help)." >&2
  exit 2
fi
if (( EUID == 0 )); then
  echo "Zeitop: uninstall as the normal user who installed Zeitop, not root." >&2
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
app_id="io.github.usr_kmasx.Zeitop"
desktop_file="$desktop_dir/$app_id.desktop"
icon_file="$icon_dir/$app_id.png"
managed_token="ZEITOP_MANAGED_INSTALL_V1"
launcher_token="ZEITOP_MANAGED_LAUNCHER_V1"
source_root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)
source "$source_root/installer-deps.sh"
deps=()
deps_family=arch  # Historical installers (without a marker) were Arch-only.
installed=0
if [[ -L "$app_dir" ]]; then
  echo "Zeitop: refusing a symlinked application directory: $app_dir" >&2
  exit 2
fi
if [[ -e "$app_dir" ]]; then
  if [[ ! -f "$app_dir/.zeitop-managed" ||
        "$(cat "$app_dir/.zeitop-managed")" != "$managed_token" ]]; then
    echo "Zeitop: installation path is not owned by this installer: $app_dir" >&2
    exit 2
  fi
  installed=1
  if [[ -f "$app_dir/.zeitop-dependency-manager" && ! -L "$app_dir/.zeitop-dependency-manager" ]]; then
    deps_family=$(cat "$app_dir/.zeitop-dependency-manager")
  fi
  if [[ -e "$app_dir/runtime/zeitop.lock" ]]; then
    if ! command -v flock >/dev/null 2>&1; then
      echo "Zeitop: missing flock; cannot safely check for a running instance." >&2
      exit 2
    fi
    exec {lockfd}< "$app_dir/runtime/zeitop.lock"
    if ! flock -n "$lockfd"; then
      echo "Zeitop: close the installed application before uninstalling." >&2
      exit 2
    fi
  fi
  if [[ -f "$app_dir/.zeitop-installed-deps" && ! -L "$app_dir/.zeitop-installed-deps" ]]; then
    while IFS= read -r pkg; do
      [[ "$pkg" =~ ^[a-z0-9@._+-]+$ ]] && deps+=("$pkg")
    done < "$app_dir/.zeitop-installed-deps"
  fi
fi

# Remove only paths carrying Zeitop's ownership markers.
for path in "$bin_dir/zeitop" "$bin_dir/zeitop-run"; do
  if [[ -f "$path" && ! -L "$path" ]] &&
     grep -Fq "$launcher_token" "$path" 2>/dev/null; then
    rm -f -- "$path"
    echo "Zeitop: removed $path"
  fi
done
if [[ -f "$desktop_file" && ! -L "$desktop_file" ]] &&
   grep -Fxq 'X-Zeitop-Managed=true' "$desktop_file" 2>/dev/null; then
  rm -f -- "$desktop_file"
  echo "Zeitop: removed desktop entry."
fi
if (( installed )); then
  # The icon was installed under an application-specific basename, and
  # is removed only if the managed application directory is present.
  rm -f -- "$icon_file"
  rm -rf -- "$app_dir"
  echo "Zeitop: removed application, all local runtime/cache data and preferences."
else
  echo "Zeitop: managed application is not installed."
fi
# Only remove empty directories we use. Never remove XDG_DATA_HOME, HOME,
# ~/.config/lsfg-vk, Steam launch options, or shared external Vulkan layers.
for folder in "$icon_dir" "$data_home/icons/hicolor/128x128" "$data_home/icons/hicolor" \
              "$data_home/icons" "$desktop_dir" "$bin_dir"; do
  rmdir -- "$folder" 2>/dev/null || :
done

if (( remove_deps && ${#deps[@]} )); then
  current_family=$(zeitop_detect_distro 2>/dev/null || true)
  if [[ "$deps_family" != arch || "$current_family" != arch ]]; then
    echo "Zeitop: shared system dependencies retained on this distribution."
    echo "Zeitop: automatic orphan removal is supported only for Arch pacman."
  elif ! command -v pacman >/dev/null 2>&1; then
    echo "Zeitop: pacman not found; shared dependencies retained."
  else
    mapfile -t orphans < <(pacman -Qdtq 2>/dev/null || true)
    safe=()
    for dep in "${deps[@]}"; do
      for orphan in "${orphans[@]}"; do
        if [[ "$dep" == "$orphan" ]]; then safe+=("$dep"); break; fi
      done
    done
    if (( ${#safe[@]} )); then
      echo "Zeitop: these packages were installed by Zeitop and are now orphans: ${safe[*]}"
      echo "Zeitop: requesting pacman removal (will not remove packages used by others)."
      sudo pacman -Rns -- "${safe[@]}"
    else
      echo "Zeitop: no safely removable Zeitop-installed dependency packages."
    fi
  fi
elif (( ${#deps[@]} )); then
  echo "Zeitop: shared system packages were retained for other applications."
  if [[ "$deps_family" == arch ]]; then
    echo "  On Arch, use --remove-deps during uninstall to check pacman orphan status."
  else
    echo "  On this distribution, dependency removal is intentionally manual."
  fi
fi
echo "Zeitop: uninstall complete. Other apps and external lsfg-vk were left untouched."
