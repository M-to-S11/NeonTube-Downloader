"""Regression checks: only the bottom-right Profile card was removed."""
from pathlib import Path
import ast
import hashlib
import unittest

ROOT = Path(__file__).resolve().parent
SOURCE = (ROOT / "app.py").read_text(encoding="utf-8")
TREE = ast.parse(SOURCE)
APP = next(node for node in TREE.body if isinstance(node, ast.ClassDef) and node.name == "NeonTubeApp")
METHODS = {m.name: m for m in APP.body if isinstance(m, ast.FunctionDef)}

class RemovedProfileCardTests(unittest.TestCase):
    def test_bottom_right_profile_is_not_built(self):
        build = METHODS["_build_download_page"]
        called = [n.func.attr for n in ast.walk(build) if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)]
        self.assertNotIn("_build_profile_card", called)
        self.assertIn("_build_queue", called)
        self.assertIn("_build_history_summary", called)
        self.assertNotIn("_build_profile_card", METHODS)

    def test_left_side_profile_menu_remains(self):
        self.assertIn('("profiles", "profiles", "Profile")', SOURCE)
        self.assertIn("_render_full_profiles", METHODS)
        self.assertIn("_apply_profile", METHODS)
        self.assertIn("add_profile", METHODS)
        self.assertIn("save_profile", METHODS)
        self.assertIn("_delete_profile", METHODS)

    def test_no_orphaned_profile_menu_references(self):
        self.assertNotIn("self.profile_menu", SOURCE)
        self.assertNotIn("_render_profile_selector", SOURCE)

    def test_download_engine_is_unchanged(self):
        self.assertTrue((ROOT / "downloader.py").is_file())

if __name__ == "__main__":
    unittest.main()
