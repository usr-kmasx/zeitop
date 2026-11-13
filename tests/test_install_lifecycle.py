"""User-local install/uninstall integration tests. Never modify the real HOME.

The fake pacman/sudo scripts verify dependency command construction without
executing any host package manager operations or requiring elevated access.
"""
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANAGED = "ZEITOP_MANAGED_INSTALL_V1"
DESKTOP = "X-Zeitop-Managed=true"


class TestInstallLifecycle(unittest.TestCase):
    def setUp(self):
        # The installer explicitly rejects source/destination overlap.
        # Use /tmp rather than the checkout's runtime directory.
        self.temp = tempfile.TemporaryDirectory(prefix="zeitop_install_test_", dir="/tmp")
        self.addCleanup(self.temp.cleanup)
        self.sandbox = Path(self.temp.name)
        self.home = self.sandbox / "home with spaces"
        self.home.mkdir()
        self.data = self.home / ".local/share"
        self.data.mkdir(parents=True)
        self.app = self.data / "zeitop"
        self.bin = self.home / ".local/bin"
        self.desktop = self.data / "applications/io.github.usr_kmasx.Zeitop.desktop"
        self.icon = self.data / "icons/hicolor/128x128/apps/io.github.usr_kmasx.Zeitop.png"
        self.env = os.environ.copy()
        self.env.update({
            "HOME": str(self.home),
            "XDG_DATA_HOME": str(self.data),
            "PYTHONDONTWRITEBYTECODE": "1",
        })
        # Verify that uninstall does not remove unrelated user data.
        (self.home / "keep.txt").write_text("unrelated")

    def run_script(self, name, *args, env=None, timeout=65, success=True):
        proc = subprocess.run(
            [str(ROOT / name), *args],
            cwd=ROOT,
            env=env or self.env,
            text=True, capture_output=True,
            timeout=timeout,
        )
        if success:
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        return proc

    def test_install_launch_reinstall_preserve_preferences_and_uninstall(self):
        a = self.run_script("install.sh", "--skip-deps")
        self.assertIn("installed successfully", a.stdout)
        self.assertEqual((self.app / ".zeitop-managed").read_text().strip(), MANAGED)
        self.assertTrue((self.app / "uninstall.sh").is_file())
        self.assertTrue((self.app / "ui/assets/zeitop-icon.png").is_file())
        self.assertTrue((self.app / "runtime/vulkan/libzeitop-output.so").is_file())
        self.assertTrue((self.app / "runtime/vulkan/libzeitop-output32.so").is_file())
        self.assertFalse((self.app / "tests").exists())
        self.assertFalse((self.app / ".git").exists())
        self.assertFalse((self.app / "logfile").exists())
        self.assertTrue(self.bin.joinpath("zeitop").is_file())
        self.assertTrue(self.bin.joinpath("zeitop-run").is_file())
        self.assertTrue(self.icon.is_file())
        self.assertEqual(
            self.icon.read_bytes(),
            (self.app / "ui/assets/zeitop-icon.png").read_bytes(),
            "GNOME must use the exact existing Zeitop logo",
        )
        self.assertIn(DESKTOP, self.desktop.read_text())
        self.assertIn("Icon=" + str(self.icon), self.desktop.read_text())
        self.assertIn("StartupWMClass=io.github.usr_kmasx.Zeitop", self.desktop.read_text())
        # GNOME/GLib must get a directly loadable FileIcon rather than an
        # unresolved themed icon. The sandbox has no custom icon theme index.
        import gi
        gi.require_version("GioUnix", "2.0")
        from gi.repository import Gio, GioUnix
        registered = GioUnix.DesktopAppInfo.new_from_filename(str(self.desktop))
        self.assertIsNotNone(registered)
        desktop_icon = registered.get_icon()
        self.assertIsInstance(desktop_icon, Gio.FileIcon)
        self.assertEqual(desktop_icon.get_file().get_path(), str(self.icon))
        self.assertTrue(desktop_icon.get_file().query_exists())
        self.assertIn('Exec="', self.desktop.read_text())
        if shutil.which("desktop-file-validate"):
            checked = subprocess.run(
                ["desktop-file-validate", str(self.desktop)],
                capture_output=True, text=True, timeout=5,
            )
            self.assertEqual(checked.returncode, 0, checked.stdout + checked.stderr)
        # The installed Steam launcher resolves ZEITOP_HOME to the new copy,
        # even though ~/.local/bin/zeitop-run is a wrapper, not a symlink.
        proc = subprocess.run(
            [str(self.bin / "zeitop-run"), sys.executable, "-c",
             "import os; print('APP=' + os.environ.get('ZEITOP_HOME', ''))"],
            env=self.env, capture_output=True, text=True, timeout=12,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("APP=" + str(self.app), proc.stdout)
        # Reinstallation/upgrade should keep only durable app preferences.
        for filename, value in [
            ("limit.state", "1\n"), ("fg.state", "0\n"),
            ("fg.presentation-mode", "immediate\n"),
        ]:
            (self.app / "runtime" / filename).write_text(value)
        (self.app / "runtime/cache").mkdir(exist_ok=True)
        (self.app / "runtime/cache/old-log").write_text("private temporary data")
        self.run_script("install.sh", "--skip-deps")
        self.assertEqual((self.app / "runtime/limit.state").read_text(), "1\n")
        self.assertEqual((self.app / "runtime/fg.presentation-mode").read_text(),
                         "immediate\n")
        self.assertFalse((self.app / "runtime/cache/old-log").exists())
        # From the *installed* directory, uninstall is independently usable.
        gone = subprocess.run(
            [str(self.app / "uninstall.sh")],
            cwd=ROOT, env=self.env,
            capture_output=True, text=True, timeout=12,
        )
        self.assertEqual(gone.returncode, 0, gone.stdout + gone.stderr)
        for entry in (self.app, self.desktop, self.icon,
                      self.bin / "zeitop", self.bin / "zeitop-run"):
            self.assertFalse(entry.exists(), str(entry))
        self.assertEqual((self.home / "keep.txt").read_text(), "unrelated")
        self.assertTrue(ROOT.joinpath("README.md").is_file())

    def test_ownership_guards_preserve_unmanaged_files(self):
        self.app.mkdir(parents=True)
        foreign = self.app / "foreign-data"
        foreign.write_text("DO NOT REMOVE")
        installer = self.run_script("install.sh", "--skip-deps", success=False)
        self.assertNotEqual(installer.returncode, 0)
        self.assertIn("not managed", installer.stderr)
        uninstaller = self.run_script("uninstall.sh", success=False)
        self.assertNotEqual(uninstaller.returncode, 0)
        self.assertIn("not owned", uninstaller.stderr)
        self.assertEqual(foreign.read_text(), "DO NOT REMOVE")

    def test_install_and_uninstall_refuse_active_managed_instance(self):
        import fcntl
        self.run_script("install.sh", "--skip-deps")
        lock = self.app / "runtime/zeitop.lock"
        lock.touch()
        with lock.open("rb") as holder:
            fcntl.flock(holder.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            install = self.run_script("install.sh", "--skip-deps", success=False)
            self.assertNotEqual(install.returncode, 0)
            self.assertIn("close the installed application", install.stderr)
            uninstall = self.run_script("uninstall.sh", success=False)
            self.assertNotEqual(uninstall.returncode, 0)
            self.assertIn("close the installed application", uninstall.stderr)
            self.assertTrue(self.app.exists())
            fcntl.flock(holder.fileno(), fcntl.LOCK_UN)
        self.run_script("uninstall.sh")
        self.assertFalse(self.app.exists())

    def test_missing_dependencies_are_recorded_and_only_orphans_removed(self):
        fakebin = self.sandbox / "fakebin"
        fakebin.mkdir()
        log = self.sandbox / "fake-pacman.log"
        pacman = fakebin / "pacman"
        pacman.write_text(
            "#!/bin/sh\n"
            "if [ \"$1\" = -Q ]; then\n"
            "  [ \"$2\" != file ]; exit $?\n"
            "elif [ \"$1\" = -Qdtq ]; then\n"
            "  printf 'file\\n'\n"
            "else exit 17\n"
            "fi\n"
        )
        pacman.chmod(0o755)
        sudo = fakebin / "sudo"
        sudo.write_text(
            "#!/bin/sh\n"
            "printf '%s\\n' \"$*\" >> \"$ZEITOP_FAKE_PACKAGE_LOG\"\n"
            "test \"$1\" = pacman\n"
        )
        sudo.chmod(0o755)
        env = dict(self.env)
        env["PATH"] = str(fakebin) + ":" + env["PATH"]
        env["ZEITOP_FAKE_PACKAGE_LOG"] = str(log)
        self.run_script("install.sh", env=env)
        self.assertEqual((self.app / ".zeitop-installed-deps").read_text(), "file\n")
        self.assertIn("pacman -S --needed --asdeps -- file", log.read_text())
        self.run_script("uninstall.sh", "--remove-deps", env=env)
        self.assertIn("pacman -Rns -- file", log.read_text())
        self.assertFalse(self.app.exists())
        self.assertEqual((self.home / "keep.txt").read_text(), "unrelated")

    def fake_distribution(self, distro, *, like="", multiarch=True):
        """Fake package managers; never run a real sudo/package operation."""
        fakebin = self.sandbox / ("fakebin-" + distro)
        fakebin.mkdir()
        os_release = self.sandbox / ("os-release-" + distro)
        os_release.write_text(f"ID={distro}\nID_LIKE=\"{like}\"\n")
        log = self.sandbox / ("packages-" + distro + ".log")

        def tool(name, code):
            target = fakebin / name
            target.write_text("#!/bin/sh\n" + code)
            target.chmod(0o755)

        tool("sudo", 'printf "%s\n" "$*" >> "$ZEITOP_FAKE_PACKAGE_LOG"\n')
        tool("dpkg", (
            'case "$1" in\n'
            '  --print-architecture) echo amd64 ;;\n'
            '  --print-foreign-architectures) ' +
            ('echo i386' if multiarch else ':') + ' ;;\n'
            '  *) exit 41 ;;\n'
            'esac\n'
        ))
        tool("dpkg-query", (
            'for pkg do :; done\n'
            '[ "$pkg" = file ] && exit 1\n'
            'printf "install ok installed"\n'
        ))
        tool("apt-get", 'echo "Unexpected direct apt-get invocation" >&2; exit 91\n')
        tool("rpm", (
            'test "$1" = -q || exit 41\n'
            '[ "$2" = file ] && exit 1\n'
            'exit 0\n'
        ))
        tool("dnf", 'echo "Unexpected direct dnf invocation" >&2; exit 91\n')
        tool("zypper", 'echo "Unexpected direct zypper invocation" >&2; exit 91\n')
        env = dict(self.env)
        env["ZEITOP_TEST_OS_RELEASE"] = str(os_release)
        env["ZEITOP_FAKE_PACKAGE_LOG"] = str(log)
        env["PATH"] = str(fakebin) + ":" + env["PATH"]
        return env, log

    def test_ubuntu_installs_only_missing_packages_and_retains_shared_deps(self):
        env, log = self.fake_distribution("ubuntu", multiarch=True)
        self.run_script("install.sh", env=env)
        self.assertEqual((self.app / ".zeitop-dependency-manager").read_text().strip(), "debian")
        self.assertEqual((self.app / ".zeitop-installed-deps").read_text(), "file\n")
        self.assertEqual(log.read_text().strip(), "apt-get install --no-install-recommends file")
        self.assertTrue((self.app / "runtime/vulkan/libzeitop-vulkan32.so").is_file())
        self.assertTrue((self.app / "runtime/libzeitop-gl32.so").is_file())
        self.run_script("uninstall.sh", "--remove-deps", env=env)
        self.assertNotIn("remove", log.read_text())
        self.assertFalse(self.app.exists())
        self.assertEqual((self.home / "keep.txt").read_text(), "unrelated")

    def test_ubuntu_requires_explicit_multiarch_before_any_changes(self):
        env, log = self.fake_distribution("ubuntu-no-i386", like="ubuntu", multiarch=False)
        failed = self.run_script("install.sh", env=env, success=False)
        self.assertNotEqual(failed.returncode, 0)
        self.assertIn("sudo dpkg --add-architecture i386", failed.stderr)
        self.assertFalse(self.app.exists())
        self.assertFalse(log.exists())

    def test_fedora_installs_only_missing_packages_and_keeps_deps(self):
        env, log = self.fake_distribution("fedora")
        self.run_script("install.sh", env=env)
        self.assertEqual((self.app / ".zeitop-dependency-manager").read_text().strip(), "fedora")
        self.assertEqual(log.read_text().strip(), "dnf install file")
        self.run_script("uninstall.sh", "--remove-deps", env=env)
        self.assertFalse(self.app.exists())
        self.assertEqual(log.read_text().strip(), "dnf install file")

    def test_opensuse_installs_only_missing_packages_and_keeps_deps(self):
        env, log = self.fake_distribution("opensuse-tumbleweed")
        self.run_script("install.sh", env=env)
        self.assertEqual((self.app / ".zeitop-dependency-manager").read_text().strip(), "opensuse")
        self.assertEqual(log.read_text().strip(), "zypper install --no-recommends file")
        self.run_script("uninstall.sh", "--remove-deps", env=env)
        self.assertFalse(self.app.exists())
        self.assertEqual(log.read_text().strip(), "zypper install --no-recommends file")

    def test_skip_deps_can_install_with_unknown_distro_when_ready(self):
        env, log = self.fake_distribution("unsupported-but-prepared")
        installed = self.run_script("install.sh", "--skip-deps", env=env)
        self.assertIn("installed successfully", installed.stdout)
        self.assertTrue((self.app / "runtime/vulkan/libzeitop-output32.so").is_file())
        self.assertFalse(log.exists())
        self.run_script("uninstall.sh", env=env)
        self.assertFalse(self.app.exists())

    def test_multiarch_packages_and_gui_typelibs_are_explicit(self):
        script = ROOT / "installer-deps.sh"
        for family, required in (
            ("arch", ("webkitgtk-6.0", "lib32-vulkan-icd-loader", "lib32-gcc-libs")),
            ("debian", ("gir1.2-webkit-6.0", "libvulkan1:i386", "gcc-multilib")),
            ("fedora", ("webkitgtk6.0", "vulkan-loader.i686", "glibc-devel.i686")),
            ("opensuse", ("typelib-1_0-WebKit-6_0", "libvulkan1-32bit", "gcc-32bit")),
        ):
            proc = subprocess.run(
                ["bash", "-c",
                 'source "$1"; zeitop_required_packages "$2"; printf "%s\\n" "${zeitop_required[@]}"',
                 "_", str(script), family],
                cwd=ROOT, capture_output=True, text=True, timeout=5,
            )
            self.assertEqual(proc.returncode, 0, proc.stderr)
            for package in required:
                self.assertIn(package, proc.stdout.splitlines(), family)

    def test_unknown_distribution_fails_closed_without_package_changes(self):
        env, log = self.fake_distribution("unknown-linux")
        failed = self.run_script("install.sh", env=env, success=False)
        self.assertNotEqual(failed.returncode, 0)
        self.assertIn("unsupported distribution", failed.stderr)
        self.assertFalse(self.app.exists())
        self.assertFalse(log.exists())

    def test_first_install_migrates_only_durable_checkout_preferences(self):
        source = self.sandbox / "checkout"
        source.mkdir()
        for name in (
            "app.py", "core.py", "fg_config.py", "fg_ipc.py", "fg_live.py",
            "build.sh", "run.sh", "zeitop-run", "install.sh", "uninstall.sh",
            "limiter.c", "vulkan_layer.c", "VERSION", "README.md",
            "installer-deps.sh",
        ):
            shutil.copy2(ROOT / name, source / name)
        for folder in ("ui", "vendor", "docs"):
            shutil.copytree(ROOT / folder, source / folder)
        (source / "runtime").mkdir()
        for name, value in (
            ("fg.state", "1\n"), ("limit.state", "0\n"),
            ("fg.presentation-mode", "immediate\n"),
            ("fg.selected-config", "/tmp/fixture/conf.toml\n"),
        ):
            (source / "runtime" / name).write_text(value)
        (source / "runtime/fg-sessions").mkdir()
        (source / "runtime/fg-sessions/secret.json").write_text("session-data")
        (source / "runtime/private-log").write_text("do not migrate")
        result = subprocess.run(
            [str(source / "install.sh"), "--skip-deps"],
            cwd=source, env=self.env, capture_output=True, text=True, timeout=65,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        for name, expected in (
            ("fg.state", "1\n"), ("limit.state", "0\n"),
            ("fg.presentation-mode", "immediate\n"),
            ("fg.selected-config", "/tmp/fixture/conf.toml\n"),
        ):
            self.assertEqual((self.app / "runtime" / name).read_text(), expected)
        self.assertFalse((self.app / "runtime/fg-sessions").exists())
        self.assertFalse((self.app / "runtime/private-log").exists())
        self.run_script("uninstall.sh")
        self.assertTrue((source / "runtime/private-log").is_file(),
                        "Uninstall must not modify the user's source checkout.")

    def test_installed_gui_can_open_in_sandbox(self):
        if not os.environ.get("WAYLAND_DISPLAY"):
            self.skipTest("Requires a Wayland GUI session")
        self.run_script("install.sh", "--skip-deps")
        env = dict(self.env)
        env["ZEITOP_SMOKE_TEST"] = "1"
        result = subprocess.run(
            [str(self.bin / "zeitop")],
            env=env, cwd=ROOT, capture_output=True, text=True, timeout=15,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("ZEITOP_SMOKE_CLOSE_OK", result.stdout)
        self.assertIn("ZEITOP_SMOKE_ICON_READY", result.stdout, result.stdout + result.stderr)
        self.run_script("uninstall.sh")


if __name__ == "__main__":
    unittest.main()
