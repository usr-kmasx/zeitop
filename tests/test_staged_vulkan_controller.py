"""Experiment: Vulkan loader and vkcube run against the staged frame controller."""
import os
import subprocess
import unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
LAYER=ROOT/"runtime"/"stage2"

class TestStagedVulkanController(unittest.TestCase):
    def test_build_and_real_loader(self):
        built=subprocess.run(["sh",str(ROOT/"pacing"/"build_candidate.sh")],
                             cwd=ROOT,capture_output=True,text=True,timeout=30)
        self.assertEqual(built.returncode,0,built.stdout+built.stderr)
        self.assertTrue((LAYER/"libzeitop-stage2.so").is_file())
        self.assertTrue((LAYER/"libzeitop-stage2-32.so").is_file())
        env=os.environ.copy()
        env.update({
            "VK_ADD_LAYER_PATH":str(LAYER),
            "VK_INSTANCE_LAYERS":"VK_LAYER_ZEITOP_pacing",
            "ZEITOP_DEBUG":"1",
            "ZEITOP_HOME":str(ROOT),
            "XDG_CACHE_HOME":str(ROOT/"runtime"/"cache"),
            "XDG_CONFIG_HOME":str(ROOT/"runtime"/"config"),
            "XDG_DATA_HOME":str(ROOT/"runtime"/"data")
        })
        result=subprocess.run(["vulkaninfo","--summary"],env=env,cwd=ROOT,
                              capture_output=True,text=True,timeout=20)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        self.assertIn("ZEITOP_FRAME_CONTROLLER_READY",result.stderr)
