"""V1.28.5: Only highlighted download controls are reduced in size."""
import ast
import hashlib
import re
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parent
CODE = (ROOT/'app.py').read_text(encoding='utf-8')
TREE = ast.parse(CODE)
APP = next(x for x in TREE.body if isinstance(x, ast.ClassDef) and x.name=='NeonTubeApp')
FUNCS = {n.name:ast.get_source_segment(CODE,n) for n in APP.body if isinstance(n,ast.FunctionDef)}

class CompactControls(unittest.TestCase):
    def test_link_bar_is_smaller(self):
        source=FUNCS['_build_download_page']
        for piece in ('height=46','height=36','height=42, font_size=13','width=145'):
            self.assertIn(piece,source)

    def test_options_are_smaller(self):
        source=FUNCS['_build_options']
        for piece in ('self.panel(parent, 234', 'height=42, font_size=13',
                      'height=36','height=52, font_size=15',
                      'height=51, font_size=12', 'controls.place(x=12, y=164'):
            self.assertIn(piece,source)

    def test_no_unrelated_ui_regression(self):
        s=FUNCS['_build_download_page']
        self.assertNotIn('_build_profile_card',s)
        header=FUNCS['_build_header']
        self.assertNotIn('self.open_settings',header)
        for f in ('_build_preview','_build_progress','_build_queue','_build_history_summary'):
            self.assertIn(f,FUNCS)
        self.assertIn('("settings", "settings", "Einstellungen")',FUNCS['_build_body'])
        self.assertIn('("profiles", "profiles", "Profile")',FUNCS['_build_body'])

    def test_download_engine_identical(self):
        self.assertEqual(hashlib.sha256((ROOT/'downloader.py').read_bytes()).hexdigest(),
                         'cc7d4b3734a8709e3eb65f54e20596ae4d696e8c3e369ff0bb84bc2e21905695')

    def test_ctk_api_safe(self):
        for n in ast.walk(TREE):
            if isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute) and n.func.attr=='place':
                self.assertFalse({'width','height'} & {k.arg for k in n.keywords})
        self.assertNotIn('def _draw(',CODE)

if __name__ == '__main__': unittest.main()
