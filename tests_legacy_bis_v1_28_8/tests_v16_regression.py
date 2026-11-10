"""Regression guards for V1.6: compare to stable V1.4 framing.

Works without customtkinter; Python AST tests are structural, not GUI snapshots.
"""
import ast
import hashlib
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SOURCE = (ROOT / 'app.py').read_text(encoding='utf-8')
TREE = ast.parse(SOURCE)
CLASSES = {node.name: node for node in TREE.body if isinstance(node, ast.ClassDef)}

class V16Checks(unittest.TestCase):
    def test_no_full_card_canvas_that_can_obscure_text(self):
        panel = CLASSES['NeonGlassPanel']
        content = ast.get_source_segment(SOURCE, panel)
        self.assertNotIn('_surface_canvas', content)
        self.assertNotIn('_paint_glass_surface', content)
        self.assertNotIn('Image.alpha_composite', content)
        self.assertNotIn('_top_light', content)
        self.assertIn('fg_color=PANEL', content)

    def test_progress_has_no_private_draw_override(self):
        self.assertNotIn('_draw', [n.name for node in CLASSES.values()
                        for n in node.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))])
        progress = CLASSES['NeonGradientProgress']
        names = [n.name for n in progress.body if isinstance(n, ast.FunctionDef)]
        self.assertIn('_draw_progress', names)

    def test_no_height_width_passed_to_place(self):
        for node in ast.walk(TREE):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == 'place':
                attrs = {k.arg for k in node.keywords}
                self.assertFalse({'width', 'height'} & attrs, f'bad .place() near {node.lineno}')

    def test_main_buttons_keep_hover_and_keyboard_actions(self):
        button = ast.get_source_segment(SOURCE, CLASSES['GradientButton'])
        for snippet in ('_hover_enter', '_hover_leave', '<KeyRelease-Return>', '<KeyRelease-space>', '<Button-1>'):
            self.assertIn(snippet, button)

    def test_download_engine_and_assets(self):
        previous = ROOT.parents[1]/'NeonTube_Downloader_V1_5'/'NeonTube_Downloader'/'downloader.py'
        if previous.exists():
            self.assertEqual(hashlib.sha256((ROOT/'downloader.py').read_bytes()).digest(),
                             hashlib.sha256(previous.read_bytes()).digest())
        for name in ('hero_art.png','sidebar_art.png','gradient_hot.png','gradient_purple.png'):
            self.assertTrue((ROOT/'assets'/name).is_file())

if __name__ == '__main__':
    unittest.main()
