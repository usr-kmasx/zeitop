"""Proton measurement sessions must not modify Steam or global MangoHud config."""
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
SCRIPT=ROOT/"tests/proton_capture.py"

class TestProtonCapture(unittest.TestCase):
    def test_preparation_and_local_report(self):
        with tempfile.TemporaryDirectory(dir=ROOT/"runtime",prefix="zp_proton_test_") as tmp:
            parent=Path(tmp)
            result=subprocess.run(["python3","-B",str(SCRIPT),"prepare",
                "--name","test-new","--controller","new","--output-root",tmp],
                cwd=ROOT,capture_output=True,text=True,timeout=10)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
            folder=parent/"test-new"
            config=(folder/"MangoHud.conf").read_text()
            launch=(folder/"SteamLaunchOptions.txt").read_text()
            self.assertIn("fps_limit=0",config)
            self.assertIn("log_duration=240",config)
            self.assertIn("ZEITOP_VULKAN_STAGE2=1",launch)
            self.assertIn("MANGOHUD_CONFIGFILE=",launch)
            self.assertIn("%command%",launch)
            self.assertTrue((folder/"session.json").is_file())
            csv=folder/"game_sample.csv"
            csv.write_text("frametime,fps\n33.2,30.1\n33.4,29.9\n40.0,25.0\n",
                           encoding="utf-8")
            report=subprocess.run(["python3","-B",str(SCRIPT),"report",
                "--name","test-new","--output-root",tmp],
                cwd=ROOT,capture_output=True,text=True,timeout=10)
            self.assertEqual(report.returncode,0,report.stdout+report.stderr)
            summary=json.loads((folder/"report.json").read_text())
            self.assertEqual(summary["files"][0]["frames"],3)
            self.assertEqual(summary["files"][0]["over_33_5"],1)
            self.assertEqual(summary["files"][0]["p99_ms"],40.0)
