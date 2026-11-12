"""Independent Vulkan pacing must report GUI telemetry without double wait."""
import os,socket,subprocess,statistics,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

class TestPresentTelemetry(unittest.TestCase):
    def test_state_machine_and_zeitop1_socket_protocol(self):
        exe=ROOT/"runtime"/"test_present_telemetry"
        built=subprocess.run([
            "cc","-std=gnu11","-O2","-Wall","-Wextra","-Werror",
            "-fsanitize=address,undefined","-fno-omit-frame-pointer",
            "-I"+str(ROOT/"pacing"),str(ROOT/"tests/present_telemetry_test.c"),
            str(ROOT/"pacing/present_telemetry.c"),"-pthread","-o",str(exe)
        ],cwd=ROOT,capture_output=True,text=True,timeout=15)
        self.assertEqual(built.returncode,0,built.stderr)
        with tempfile.TemporaryDirectory(prefix="zp_tel_",dir=ROOT/"runtime") as tmp:
            socket_dir=Path(tmp)/"runtime"
            socket_dir.mkdir()
            address=socket_dir/"zeitop.sock"
            receiver=socket.socket(socket.AF_UNIX,socket.SOCK_DGRAM)
            try:
                receiver.bind(str(address))
                receiver.settimeout(3)
                env=dict(os.environ,ZEITOP_HOME=tmp)
                proc=subprocess.run([str(exe)],env=env,cwd=ROOT,
                                    capture_output=True,text=True,timeout=6)
                self.assertEqual(proc.returncode,0,proc.stdout+proc.stderr)
                packet=receiver.recv(128).decode("ascii")
                self.assertTrue(packet.startswith("ZEITOP1 "),packet)
                self.assertIn("33.333",packet)
            finally:
                receiver.close()

    def test_real_vulkan_candidate_emits_gui_packets(self):
        if not os.environ.get("WAYLAND_DISPLAY"):
            self.skipTest("Wayland is required")
        from core import is_enabled,set_enabled
        receiver_path=ROOT/"runtime"/"zeitop.sock"
        if receiver_path.exists():self.skipTest("Zeitop GUI owns the socket")
        built=subprocess.run(["sh","pacing/build_candidate.sh"],cwd=ROOT,
                             capture_output=True,text=True,timeout=20)
        self.assertEqual(built.returncode,0,built.stdout+built.stderr)
        build_renderer=subprocess.run(["sh","pacing/build_stage3.sh"],cwd=ROOT,
                             capture_output=True,text=True,timeout=20)
        self.assertEqual(build_renderer.returncode,0,build_renderer.stdout+build_renderer.stderr)
        env=dict(os.environ,ZEITOP_VULKAN_STAGE2="1",ZEITOP_DEBUG="1",
                 ZEITOP_TEST_WORK_PATTERN="5",
                 XDG_CACHE_HOME=str(ROOT/"runtime/cache"),
                 XDG_DATA_HOME=str(ROOT/"runtime/data"),
                 XDG_CONFIG_HOME=str(ROOT/"runtime/config"))
        prev=is_enabled(ROOT)
        sock=socket.socket(socket.AF_UNIX,socket.SOCK_DGRAM)
        try:
            sock.bind(str(receiver_path))
            sock.settimeout(.2)
            set_enabled(ROOT,True)
            proc=subprocess.run([str(ROOT/"zeitop-run"),
                str(ROOT/"runtime/stage3/present_probe"),"--untimed-frames","44"],
                cwd=ROOT,env=env,capture_output=True,text=True,timeout=15)
            self.assertEqual(proc.returncode,0,proc.stdout+proc.stderr)
            self.assertIn("ZEITOP_FRAME_CONTROLLER_READY",proc.stderr)
            packets=[]
            while True:
                try:packets.append(sock.recv(128).decode("ascii"))
                except socket.timeout:break
            self.assertGreaterEqual(len(packets),10,packets)
            self.assertTrue(all(p.startswith("ZEITOP1 ") for p in packets))
            values=[float(p.split()[2]) for p in packets]
            self.assertGreater(statistics.median(values),0.0)
        finally:
            set_enabled(ROOT,prev)
            sock.close()
            receiver_path.unlink(missing_ok=True)
