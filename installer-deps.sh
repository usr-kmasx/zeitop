#!/usr/bin/env bash
# Dependency selection for user-local Zeitop installation. Sourced by the
# installer/uninstaller; never run a package manager merely by sourcing.
# ZEITOP_TEST_OS_RELEASE is for tests with fake package-manager executables.
zeitop_detect_distro() {
  local release_file="${ZEITOP_TEST_OS_RELEASE:-/etc/os-release}"
  local ID="" ID_LIKE=""
  if [[ ! -r "$release_file" ]]; then
    echo "Zeitop: cannot read OS identification: $release_file" >&2
    return 2
  fi
  # os-release is a documented shell-compatible key/value file.
  . "$release_file"
  local id="${ID,,}" family
  case "$id" in
    arch|manjaro|endeavouros|cachyos|garuda) family=arch ;;
    debian|ubuntu|linuxmint|pop|elementary|zorin) family=debian ;;
    fedora|nobara) family=fedora ;;
    opensuse*|suse|sled|sles) family=opensuse ;;
    *)
      # Only recognize known distro families. Do not guess from whichever
      # package-manager binary happens to be on PATH.
      family=""
      local like
      for like in ${ID_LIKE:-}; do
        case "$like" in
          arch) family=arch; break ;;
          debian|ubuntu) family=debian; break ;;
          fedora) family=fedora; break ;;
          opensuse|suse) family=opensuse; break ;;
        esac
      done
      ;;
  esac
  if [[ -z "$family" ]]; then
    echo "Zeitop: unsupported distribution '$id' for automatic dependencies; use --skip-deps after installing the requirements manually." >&2
    return 2
  fi
  printf '%s\n' "$family"
}

zeitop_required_packages() {
  local family=$1
  # Do not install GPU-specific Vulkan ICD drivers; they remain the
  # administrator's responsibility. Both 64- and 32-bit loader/CRT
  # dependencies are required by the native build.
  case "$family" in
    arch)
      zeitop_required=(python python-gobject gtk4 webkitgtk-6.0 gcc lib32-gcc-libs file vulkan-icd-loader lib32-vulkan-icd-loader)
      ;;
    debian)
      zeitop_required=(python3 python3-gi gir1.2-gtk-4.0 gir1.2-webkit-6.0 gcc gcc-multilib libc6-dev-i386 file libvulkan1 libvulkan1:i386)
      ;;
    fedora)
      zeitop_required=(python3 python3-gobject gtk4 webkitgtk6.0 gcc glibc-devel.x86_64 glibc-devel.i686 libgcc.i686 file vulkan-loader.x86_64 vulkan-loader.i686)
      ;;
    opensuse)
      zeitop_required=(python3 python3-gobject typelib-1_0-Gtk-4_0 typelib-1_0-WebKit-6_0 gcc gcc-32bit glibc-devel-32bit file libvulkan1 libvulkan1-32bit)
      ;;
    *) echo "Zeitop: internal error: unknown dependency family." >&2; return 2 ;;
  esac
}

zeitop_install_dependencies() {
  local family=$1 pkg
  zeitop_required_packages "$family"
  zeitop_missing=()
  case "$family" in
    arch)
      command -v pacman >/dev/null 2>&1 || { echo "Zeitop: pacman is required on Arch." >&2; return 2; }
      for pkg in "${zeitop_required[@]}"; do
        pacman -Q "$pkg" >/dev/null 2>&1 || zeitop_missing+=("$pkg")
      done
      if (( ${#zeitop_missing[@]} )); then
        echo "Zeitop: missing Arch dependencies: ${zeitop_missing[*]}"
        sudo pacman -S --needed --asdeps -- "${zeitop_missing[@]}"
      fi
      ;;
    debian)
      command -v dpkg-query >/dev/null 2>&1 && command -v dpkg >/dev/null 2>&1 &&
      command -v apt-get >/dev/null 2>&1 || {
        echo "Zeitop: Debian/Ubuntu requires dpkg, dpkg-query and apt-get." >&2; return 2;
      }
      if [[ "$(dpkg --print-architecture)" != amd64 ]]; then
        echo "Zeitop: this build requires an amd64 Debian/Ubuntu host for both 64- and 32-bit libraries." >&2
        return 2
      fi
      # Enabling a foreign dpkg architecture is a system-wide administrator
      # decision; do not silently change it.
      if ! dpkg --print-foreign-architectures | grep -Fxq i386; then
        echo "Zeitop: Debian/Ubuntu needs i386 multiarch for the 32-bit Vulkan loader." >&2
        echo "Zeitop: enable it explicitly: sudo dpkg --add-architecture i386 && sudo apt-get update" >&2
        return 2
      fi
      for pkg in "${zeitop_required[@]}"; do
        if [[ "$(dpkg-query -W -f='${Status}' "$pkg" 2>/dev/null || true)" != "install ok installed" ]]; then
          zeitop_missing+=("$pkg")
        fi
      done
      if (( ${#zeitop_missing[@]} )); then
        echo "Zeitop: missing Debian/Ubuntu dependencies: ${zeitop_missing[*]}"
        sudo apt-get install --no-install-recommends "${zeitop_missing[@]}"
      fi
      ;;
    fedora|opensuse)
      command -v rpm >/dev/null 2>&1 || { echo "Zeitop: rpm is required for this distribution." >&2; return 2; }
      local manager=dnf
      [[ "$family" == opensuse ]] && manager=zypper
      command -v "$manager" >/dev/null 2>&1 || {
        echo "Zeitop: $manager is required for automatic dependency installation." >&2; return 2;
      }
      for pkg in "${zeitop_required[@]}"; do
        rpm -q "$pkg" >/dev/null 2>&1 || zeitop_missing+=("$pkg")
      done
      if (( ${#zeitop_missing[@]} )); then
        echo "Zeitop: missing $family dependencies: ${zeitop_missing[*]}"
        if [[ "$family" == fedora ]]; then
          sudo dnf install "${zeitop_missing[@]}"
        else
          sudo zypper install --no-recommends "${zeitop_missing[@]}"
        fi
      fi
      ;;
  esac
}
