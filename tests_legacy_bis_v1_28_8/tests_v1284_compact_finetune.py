"""Layout regression checks for the user-requested ~5–8% extra compact controls."""
import ast
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parent
NEW=(ROOT/'app.py').read_text(encoding='utf-8')
TREE=ast.parse(NEW)
APP=next(x for x in TREE.body if isinstance(x,ast.ClassDef) and x.name=='NeonTubeApp')
FUNCS={n.name:ast.get_source_segment(NEW,n) for n in APP.body if isinstance(n,ast.FunctionDef)}

class CompactFineTune(unittest.TestCase):
    def test_specific_smaller_controls(self):
        page=FUNCS['_build_download_page']
        for part in ('height=46','height=36','height=42, font_size=13','width=145'):
            self.assertIn(part,page)
        options=FUNCS['_build_options']
        for part in ('self.panel(parent, 234','height=42, font_size=13','height=36',
                     'height=52, font_size=15','height=51, font_size=12',
                     'controls.place(x=12, y=164'):
            self.assertIn(part,options)
    def test_unrequested_ui_untouched(self):
        base=Path(__file__).resolve().parent.parent/'unused_original_app.py'
        # Baseline-independent assertions protecting the earlier removals.
        self.assertNotIn('_build_profile_card',FUNCS['_build_download_page'])
        self.assertNotIn('self.open_settings',FUNCS['_build_header'])
        self.assertIn('("settings", "settings", "Einstellungen")',FUNCS['_build_body'])
        for name in ('_build_preview','_build_progress','_build_queue','_build_history_summary'):
            self.assertIn(name,FUNCS)
    def test_customtkinter_place_safe(self):
        for node in ast.walk(TREE):
            if isinstance(node,ast.Call) and isinstance(node.func,ast.Attribute) and node.func.attr=='place':
                self.assertFalse({'height','width'} & {k.arg for k in node.keywords})
        self.assertNotIn('def _draw(',NEW)

if __name__ == '__main__':
    unittest.main()
