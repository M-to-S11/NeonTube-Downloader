"""V1.28.2: remove ONLY the settings gear in the branded top-right header."""
from pathlib import Path
import ast
import hashlib
import unittest

ROOT = Path(__file__).resolve().parent
CODE = (ROOT / "app.py").read_text(encoding="utf-8")
TREE = ast.parse(CODE)
APP = next(node for node in TREE.body if isinstance(node, ast.ClassDef) and node.name == "NeonTubeApp")
METHODS = {m.name:m for m in APP.body if isinstance(m, ast.FunctionDef)}
HEADER = ast.get_source_segment(CODE, METHODS['_build_header'])
BODY = ast.get_source_segment(CODE, METHODS['_build_body'])

class RemoveTopGearRegression(unittest.TestCase):
    def test_no_top_settings_gear(self):
        self.assertNotIn('("⚙", self.open_settings)', HEADER)
        self.assertNotIn('self.open_settings', HEADER)
        self.assertIn('if sys.platform != "win32":', HEADER)
        self.assertIn('("—", self.iconify)', HEADER)

    def test_left_settings_menu_and_dialog_unchanged(self):
        self.assertIn('("settings", "settings", "Einstellungen")', BODY)
        self.assertIn('self.open_settings()', CODE)
        self.assertIn('open_settings', METHODS)

    def test_bottom_right_profile_still_absent(self):
        self.assertNotIn('_build_profile_card', ast.get_source_segment(CODE, METHODS['_build_download_page']))
        self.assertIn('("profiles", "profiles", "Profile")', BODY)

    def test_no_updates_and_download_engine_unchanged(self):
        self.assertEqual(hashlib.sha256((ROOT/'downloader.py').read_bytes()).hexdigest(),
                         'cc7d4b3734a8709e3eb65f54e20596ae4d696e8c3e369ff0bb84bc2e21905695')
        for name in ('update_checker.py','github_updater.py','program_updater.py'):
            self.assertFalse((ROOT/name).exists())

if __name__=='__main__':
    unittest.main()
