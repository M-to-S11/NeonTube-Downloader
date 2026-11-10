"""Regression tests: inline settings, no settings popup, preserved engine."""
import ast
import hashlib
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parent
CODE = (ROOT/'app.py').read_text(encoding='utf-8')
TREE = ast.parse(CODE)
APP = next(node for node in TREE.body if isinstance(node, ast.ClassDef) and node.name=='NeonTubeApp')
FUNCS = {node.name: ast.get_source_segment(CODE,node) for node in APP.body if isinstance(node,ast.FunctionDef)}

class InlineSettings(unittest.TestCase):
    def test_settings_page_is_gridded_and_navigation_preserved(self):
        self.assertIn('self.settings_page = ctk.CTkScrollableFrame', FUNCS['_build_body'])
        self.assertIn('page.grid()', FUNCS['open_settings'])
        self.assertIn('self.open_settings()', FUNCS['_switch_page'])
        self.assertIn('button.set_selected(name == "settings")', FUNCS['open_settings'])
    def test_no_popups_for_settings(self):
        self.assertNotIn('CTkToplevel', FUNCS['open_settings'] + FUNCS['_render_settings_page'])
        self.assertNotIn('grab_set(', FUNCS['open_settings'] + FUNCS['_render_settings_page'])
        self.assertNotIn('settings_window', CODE)
    def test_all_controls_and_save_behavior(self):
        src=FUNCS['_render_settings_page']
        for item in ['Parallele Downloads','Standard-Downloadordner','Cookies-Datei',
                     'Einstellungen speichern','self.manager.set_concurrency',
                     'self.manager.cookiefile = cookies.get()',
                     'self.output_dir.set(folder.get())','save_json(CONFIG_FILE, self.config_data)']:
            self.assertIn(item,src)
    def test_other_ui_preserved(self):
        self.assertIn('("profiles", "profiles", "Profile")', FUNCS['_build_body'])
        self.assertNotIn('_build_profile_card', FUNCS['_build_download_page'])
        self.assertNotIn('self.open_settings', FUNCS['_build_header'])
        self.assertIn('self.panel(parent, 234', FUNCS['_build_options'])
    def test_download_engine_unchanged(self):
        digest=hashlib.sha256((ROOT/'downloader.py').read_bytes()).hexdigest()
        self.assertEqual(digest,'cc7d4b3734a8709e3eb65f54e20596ae4d696e8c3e369ff0bb84bc2e21905695')

if __name__ == '__main__': unittest.main()
