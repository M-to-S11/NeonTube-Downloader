"""V1.7 GUI safety checks that require no running Windows desktop."""
import ast
import hashlib
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parent
SOURCE = (ROOT / 'app.py').read_text(encoding='utf-8')
TREE = ast.parse(SOURCE)
CLASSES = {n.name: n for n in TREE.body if isinstance(n, ast.ClassDef)}

class V17VisualTests(unittest.TestCase):
    def test_no_card_canvas_or_internal_ctk_draw_override(self):
        panel = ast.get_source_segment(SOURCE, CLASSES['NeonGlassPanel'])
        self.assertNotIn('tk.Canvas', panel)
        self.assertNotIn('_top_light', panel)
        for cls in CLASSES.values():
            methods = [n.name for n in cls.body if isinstance(n, ast.FunctionDef)]
            self.assertNotIn('_draw', methods)

    def test_icons_are_drawn_not_font_glyphs(self):
        self.assertIn('def outline_icon(', SOURCE)
        self.assertIn('def small_icon_label(', SOURCE)
        self.assertIn('Image.Resampling.LANCZOS', SOURCE)
        self.assertIn('small_icon_label(emblem, symbol', SOURCE)
        self.assertIn('self._nav_icon_bitmap', SOURCE)
        self.assertNotIn('make_label(emblem, symbol', SOURCE)

    def test_no_width_or_height_place_regressions(self):
        for node in ast.walk(TREE):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == 'place':
                attrs = {kw.arg for kw in node.keywords}
                self.assertFalse({'height', 'width'} & attrs, f'Invalid place at line {node.lineno}')

    def test_download_engine_preserved(self):
        old = ROOT.parents[1] / 'NeonTube_Downloader_V1_6' / 'NeonTube_Downloader' / 'downloader.py'
        if old.exists():
            self.assertEqual(hashlib.sha256(old.read_bytes()).hexdigest(),
                             hashlib.sha256((ROOT/'downloader.py').read_bytes()).hexdigest())

if __name__ == '__main__':
    unittest.main()
