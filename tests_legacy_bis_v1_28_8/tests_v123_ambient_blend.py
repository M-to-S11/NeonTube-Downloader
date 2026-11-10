"""V1.23: non-interfering smooth banner fade and regression checks."""
import ast
import hashlib
import unittest
from pathlib import Path
from PIL import Image

HERE = Path(__file__).resolve().parent
SOURCE = (HERE / 'app.py').read_text('utf-8')
TREE = ast.parse(SOURCE)
CLASSES = {node.name: node for node in TREE.body if isinstance(node, ast.ClassDef)}


def get_smooth_left_fade():
    node = next(n for n in TREE.body if isinstance(n, ast.FunctionDef)
                and n.name == 'smooth_left_fade')
    scope = {'Image': Image}
    exec('from __future__ import annotations\n' + ast.get_source_segment(SOURCE, node), scope)
    return scope['smooth_left_fade']


class TestV123AmbientBlend(unittest.TestCase):
    def test_smooth_mask(self):
        mask = get_smooth_left_fade()(500, 120, .30)
        self.assertEqual(mask.mode, 'L')
        self.assertEqual(mask.size, (500, 120))
        self.assertEqual(mask.getpixel((0, 60)), 0)
        self.assertEqual(mask.getpixel((499, 60)), 255)
        samples = [mask.getpixel((x, 60)) for x in range(500)]
        self.assertEqual(samples, sorted(samples))
        # A smoothstep should start and finish gently.
        self.assertLess(samples[10], samples[35])
        self.assertEqual(samples[200], 255)

    def test_tiny_dimensions_and_clamped_fraction(self):
        fn = get_smooth_left_fade()
        self.assertEqual(fn(0, 0).size, (1, 1))
        self.assertEqual(fn(23, 11, 15).size, (23, 11))
        self.assertEqual(fn(23, 11, -1).size, (23, 11))

    def test_existing_canvas_only(self):
        method = next(n for n in CLASSES['NeonHero'].body
                      if isinstance(n, ast.FunctionDef) and n.name == '_paint_banner')
        code = ast.get_source_segment(SOURCE, method)
        self.assertIn('smooth_left_fade(target_w, target_h, .33)', code)
        self.assertIn('ImageChops.multiply', code)
        self.assertIn('ImageTk.PhotoImage(layer)', code)
        self.assertNotIn('CTkLabel(', code)
        self.assertNotIn('CTkCanvas(', code)

    def test_engine_unchanged_and_no_old_ctk_traps(self):
        self.assertEqual(hashlib.sha256((HERE/'downloader.py').read_bytes()).hexdigest(),
                         'cc7d4b3734a8709e3eb65f54e20596ae4d696e8c3e369ff0bb84bc2e21905695')
        for node in ast.walk(TREE):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                args = {kw.arg for kw in node.keywords}
                if node.func.attr == 'place':
                    self.assertFalse({'height', 'width'} & args)
                if node.func.attr == 'CTkLabel':
                    self.assertFalse({'border_width', 'border_color'} & args)
        for cls in CLASSES.values():
            self.assertFalse(any(isinstance(n, ast.FunctionDef) and n.name == '_draw' for n in cls.body))


if __name__ == '__main__':
    unittest.main()
