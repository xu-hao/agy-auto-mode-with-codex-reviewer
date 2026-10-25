"""Installer regressions: preserve policy/hooks and never activate failed setup."""
from contextlib import redirect_stdout
import io
import json
import os
from pathlib import Path
import stat
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from scripts import setup
from guardian_bridge import bridge

class SetupTests(unittest.TestCase):
    def setUp(self):
        temporary=tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root=Path(temporary.name)
        self.workspace=self.root/'project with spaces'
        self.workspace.mkdir()
        self.runtime=self.root/'installed runtime'
        self.config=self.root/'operator/config.json'
        self.tools_patch=patch.object(setup,'ensure_account_tools')
        self.tools=self.tools_patch.start();self.addCleanup(self.tools_patch.stop)
        self.builds=[]
        def build(runtime):
            self.builds.append(runtime)
            binary=runtime/'build/debug/guardian-review'
            binary.parent.mkdir(parents=True)
            binary.write_text('fixture build')
        self.build_patch=patch.object(setup,'build_runtime',side_effect=build)
        self.build_patch.start();self.addCleanup(self.build_patch.stop)
        self.probe_patch=patch.object(setup,'probe_runtime')
        self.probe=self.probe_patch.start();self.addCleanup(self.probe_patch.stop)

    def install(self,workspace=None,config=None,model=None):
        with redirect_stdout(io.StringIO()):
            return setup.install(workspace or self.workspace,self.runtime,config or self.config,model)

    def test_defaults_create_separate_private_workspace_configs(self):
        preferences=self.root/'preferences'
        second=self.root/'second';second.mkdir()
        with patch.dict(os.environ,{'XDG_CONFIG_HOME':str(preferences)}),redirect_stdout(io.StringIO()):
            first=setup.install(self.workspace,self.runtime)
            other=setup.install(second,self.runtime)
        self.assertNotEqual(first['config'],other['config'])
        self.assertEqual(bridge.config_load(first['config'])['workspace_roots'],[str(self.workspace)])
        self.assertEqual(bridge.config_load(other['config'])['workspace_roots'],[str(second)])
        self.assertEqual(stat.S_IMODE((preferences/'antigravity-guardian').stat().st_mode),0o700)
        self.assertEqual(len(self.builds),1)

    def test_missing_account_cli_fails_before_build_or_registration(self):
        self.tools.side_effect=setup.SetupError('Missing CLI: codex')
        with self.assertRaises(setup.SetupError):self.install()
        self.assertFalse(self.runtime.exists())
        self.assertFalse((self.workspace/'.agents').exists())
        self.assertEqual(self.builds,[])

    def test_install_creates_private_config_and_usable_hook_command(self):
        result=self.install()
        cfg=bridge.config_load(result['config'])
        self.assertEqual(cfg['workspace_roots'],[str(self.workspace)])
        self.assertEqual(cfg['binary'],str(self.runtime/'build/debug/guardian-review'))
        self.assertEqual(stat.S_IMODE(self.config.stat().st_mode),0o600)
        hooks=json.loads((self.workspace/'.agents/hooks.json').read_text())
        command=hooks[bridge.HOOK_NAME]['PreToolUse'][0]['hooks'][0]['command']
        import shlex
        argv=shlex.split(command)
        self.assertEqual(argv[1],str(self.runtime/'bridge.py'))
        self.assertEqual(argv[-1],'hook')
        self.assertTrue((self.runtime/'uninstall.sh').is_file())
        self.probe.assert_called_once()

    def test_second_workspace_reuses_build_and_preserves_first(self):
        self.install()
        second=self.root/'second project';second.mkdir()
        self.install(second)
        cfg=bridge.config_load(self.config)
        self.assertEqual(cfg['workspace_roots'],[str(self.workspace),str(second)])
        self.assertEqual(len(self.builds),1)
        self.assertEqual(self.probe.call_count,2)
        self.assertTrue((self.workspace/'.agents/hooks.json').exists())

    def test_install_preserves_custom_policy_and_other_hooks(self):
        self.config.parent.mkdir()
        original={'app_data_roots':['/host/logs'],'workspace_roots':[],
                  'permissions':{'denied_paths':['/private']},'native':{'policy':'Custom policy','timeout_ms':1234}}
        setup.private_json(self.config,original)
        hooks=self.workspace/'.agents/hooks.json';hooks.parent.mkdir()
        hooks.write_text('{"other":{"enabled":false}}')
        self.install(model='explicit-reviewer')
        cfg=bridge.config_load(self.config)
        self.assertEqual(cfg['permissions'],original['permissions'])
        self.assertEqual(cfg['native']['policy'],'Custom policy')
        self.assertEqual(cfg['native']['model'],'explicit-reviewer')
        self.assertEqual(json.loads(hooks.read_text())['other'],{'enabled':False})

    def test_default_reinstall_preserves_existing_hook_policy(self):
        self.install()
        cfg=json.loads(self.config.read_text())
        cfg['native']['policy']='Operator policy must survive'
        setup.private_json(self.config,cfg)
        with redirect_stdout(io.StringIO()):
            result=setup.install(self.workspace,self.runtime)
        self.assertEqual(result['config'],str(self.config))
        self.assertEqual(bridge.config_load(self.config)['native']['policy'],'Operator policy must survive')

    def test_custom_existing_hook_is_not_silently_replaced(self):
        path=self.workspace/'.agents/hooks.json';path.parent.mkdir()
        original=json.dumps({bridge.HOOK_NAME:{'PreToolUse':[{'hooks':[{'command':'custom guardian command'}]}]}})
        path.write_text(original)
        with self.assertRaises(setup.SetupError):
            setup.install(self.workspace,self.runtime)
        self.assertEqual(path.read_text(),original)
        self.assertFalse(self.runtime.exists())

    def test_failed_access_check_leaves_config_and_hooks_untouched(self):
        self.install()
        original_config=self.config.read_bytes()
        hooks=self.workspace/'.agents/hooks.json';original_hooks=hooks.read_bytes()
        self.probe.side_effect=setup.SetupError('model unavailable')
        with self.assertRaises(setup.SetupError):self.install(model='unavailable')
        self.assertEqual(self.config.read_bytes(),original_config)
        self.assertEqual(hooks.read_bytes(),original_hooks)
        self.assertEqual(list(self.config.parent.glob('*.install-*')),[])

    def test_refuses_unrelated_install_directory(self):
        self.runtime.mkdir();sentinel=self.runtime/'keep.txt';sentinel.write_text('user file')
        with self.assertRaises(setup.SetupError):self.install()
        self.assertEqual(sentinel.read_text(),'user file')
        self.assertFalse(self.config.exists())

    def test_control_files_must_be_outside_workspace(self):
        with self.assertRaises(setup.SetupError):
            setup.install(self.workspace,self.workspace/'runtime',self.config)
        with self.assertRaises(setup.SetupError):
            setup.install(self.workspace,self.runtime,self.workspace/'config.json')
        self.assertFalse(self.runtime.exists())

    def test_refuses_symlinked_operator_config(self):
        self.config.parent.mkdir();other=self.root/'other.json';other.write_text('{}')
        self.config.symlink_to(other)
        with self.assertRaises(setup.SetupError):self.install()
        self.assertEqual(other.read_text(),'{}')

    def test_uninstall_script_preserves_other_hooks_without_credentials(self):
        self.install()
        self.config.unlink()
        path=self.workspace/'.agents/hooks.json'
        hooks=json.loads(path.read_text());hooks['other']={'enabled':False};path.write_text(json.dumps(hooks))
        process=subprocess.run(['bash',str(self.runtime/'uninstall.sh'),str(self.workspace)],capture_output=True,text=True)
        self.assertEqual(process.returncode,0,process.stderr)
        self.assertTrue(json.loads(process.stdout)['uninstalled'])
        self.assertEqual(json.loads(path.read_text()),{'other':{'enabled':False}})

if __name__=='__main__':unittest.main()
