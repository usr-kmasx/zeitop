"""Launch integration: Steam, direct games, child process env propagation."""
import json
import os
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

class TestLaunch(unittest.TestCase):
    def test_direct_process_and_child_see_layer(self):
        code = ('import json,os,subprocess,sys; '
                'keys=["ZEITOP_HOME","VK_INSTANCE_LAYERS","VK_LAYER_PATH","VK_ADD_LAYER_PATH","LD_PRELOAD"]; '
                's=subprocess.run([sys.executable,"-c",'
                '"import json,os; print(json.dumps({k:os.environ.get(k) for k in '+repr(["ZEITOP_HOME","VK_INSTANCE_LAYERS","VK_LAYER_PATH","VK_ADD_LAYER_PATH","LD_PRELOAD"])+ '}))"],capture_output=True,text=True); '
                'print(s.stdout.strip())')
        e = dict(os.environ)
        e["VK_INSTANCE_LAYERS"] = "VK_LAYER_TEST_existing"
        e["VK_ADD_LAYER_PATH"] = "/fake/existing/layers"
        e.pop("VK_LAYER_PATH",None)
        r=subprocess.run([str(ROOT / "zeitop-run"),sys.executable,"-c",code],
                         env=e,capture_output=True,text=True,timeout=8)
        self.assertEqual(r.returncode,0,r.stderr)
        vals=json.loads(r.stdout.strip().splitlines()[-1])
        self.assertEqual(vals["ZEITOP_HOME"],str(ROOT))
        self.assertIn("VK_LAYER_ZEITOP_pacing", vals["VK_INSTANCE_LAYERS"])
        self.assertIn("VK_LAYER_TEST_existing",vals["VK_INSTANCE_LAYERS"])
        self.assertIn(str(ROOT / "runtime" / "vulkan"),vals["VK_ADD_LAYER_PATH"])
        self.assertIn("/fake/existing/layers",vals["VK_ADD_LAYER_PATH"])
        self.assertIn(str(ROOT / "runtime" / "libzeitop-gl.so"),vals["LD_PRELOAD"])

    def test_direct_32bit_program_uses_matching_gl_hook(self):
        binary = ROOT / "runtime" / "zeitop-arch-probe32"
        built = subprocess.run(["gcc","-m32","-O2",
                                str(ROOT/"tests"/"arch_probe.c"),"-o",str(binary)],
                               capture_output=True,text=True,timeout=20)
        self.assertEqual(built.returncode, 0, built.stderr)
        run = subprocess.run([str(ROOT/"zeitop-run"),str(binary)],
                             capture_output=True,text=True,timeout=10)
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertIn(str(ROOT/"runtime"/"libzeitop-gl32.so"),run.stdout)
        self.assertNotIn("wrong ELF class",run.stderr)

    def test_stage2_opt_in_uses_only_local_experimental_layer(self):
        env=dict(os.environ)
        env.pop('VK_LAYER_PATH',None)
        env.pop('VK_ADD_LAYER_PATH',None)
        env['ZEITOP_VULKAN_STAGE2']='1'
        command=[str(ROOT/'zeitop-run'),sys.executable,'-c',
                 'import os; print(os.environ.get("VK_ADD_LAYER_PATH",""))']
        completed=subprocess.run(command,env=env,capture_output=True,text=True,timeout=8)
        self.assertEqual(completed.returncode,0,completed.stderr)
        self.assertIn(str(ROOT/'runtime'/'stage2'),completed.stdout)
        self.assertNotIn(str(ROOT/'runtime'/'vulkan'),completed.stdout)

    def test_wrapper_help_for_missing_executable(self):
        r=subprocess.run([str(ROOT / "zeitop-run")],
                         capture_output=True,text=True,timeout=5)
        self.assertNotEqual(r.returncode,0)
        self.assertIn("Usage",r.stderr)
