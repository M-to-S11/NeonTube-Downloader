"""V1.22 ambient imagery: pixel tests and UI layout regression checks."""
import ast
import hashlib
import re
import unittest
from pathlib import Path
from PIL import Image, ImageDraw, ImageFilter

HERE = Path(__file__).resolve().parent
PREVIOUS = HERE.parents[1] / 'NeonTube_Downloader_V1_21' / 'NeonTube_Downloader'
SOURCE = (HERE / 'app.py').read_text(encoding='utf-8')
TREE = ast.parse(SOURCE)
CLASSES = {n.name: n for n in TREE.body if isinstance(n, ast.ClassDef)}


def method(cls, name):
    return ast.get_source_segment(SOURCE, next(
        n for n in CLASSES[cls].body if isinstance(n, ast.FunctionDef) and n.name == name))


def pure_compositor():
    node = next(n for n in TREE.body if isinstance(n, ast.FunctionDef) and n.name == 'add_neon_halos')
    local = {}
    exec('from __future__ import annotations\n' + ast.get_source_segment(SOURCE, node),
         {'Image': Image, 'ImageDraw': ImageDraw, 'ImageFilter': ImageFilter}, local)
    return local['add_neon_halos']


class V122AmbientTests(unittest.TestCase):
    def test_version_and_download_engine(self):
        self.assertIn('VERSION = "1.28.8"', SOURCE)
        digest = hashlib.sha256((HERE / 'downloader.py').read_bytes()).hexdigest()
        self.assertEqual(digest, 'cc7d4b3734a8709e3eb65f54e20596ae4d696e8c3e369ff0bb84bc2e21905695')

    def test_pure_compositing_preserves_size_and_transparency(self):
        base = Image.new('RGB', (300, 160), (11, 9, 40))
        lit = pure_compositor()(base, [(.5, .5, .3, .3, (245, 30, 160), 65, .10)])
        self.assertEqual(lit.size, base.size)
        self.assertEqual(lit.mode, 'RGBA')
        self.assertNotEqual(lit.getpixel((150, 80)), base.convert('RGBA').getpixel((150, 80)))
        self.assertEqual(lit.getpixel((1, 1)), base.convert('RGBA').getpixel((1, 1)))

    def test_empty_halos_and_small_images_are_safe(self):
        image = Image.new('RGBA', (1, 1), (40, 20, 50, 255))
        self.assertEqual(pure_compositor()(image, []).getpixel((0, 0)), (40, 20, 50, 255))
        self.assertEqual(pure_compositor()(image, [(.5,.5,.3,.3,(200,0,0),80,.3)]).size, (1,1))

    def test_hero_and_sidebar_have_bitmap_only_lights(self):
        hero = method('NeonHero', '_paint_banner')
        sidebar = method('NeonTubeApp', '_resize_sidebar_art')
        self.assertIn('layer = add_neon_halos(layer, [', hero)
        self.assertIn('picture = add_neon_halos(picture, [', sidebar)
        self.assertIn('ImageTk.PhotoImage(layer)', hero)
        self.assertNotIn('CTkLabel(', hero)
        self.assertNotIn('CTkCanvas(', sidebar)

    def test_widget_dimensions_unchanged(self):
        if not (PREVIOUS / 'app.py').is_file():
            self.skipTest('Previous version not present in standalone archive')
        old = (PREVIOUS / 'app.py').read_text('utf-8')
        for name in ('QUEUE_PANEL_HEIGHT', 'QUEUE_CARD_HEIGHT', 'QUEUE_LIST_HEIGHT',
                     'HISTORY_PANEL_HEIGHT', 'HISTORY_LIST_HEIGHT', 'HISTORY_ROW_HEIGHT'):
            pattern = rf'^{name} = .*'
            self.assertEqual(re.search(pattern, old, re.M).group(), re.search(pattern, SOURCE, re.M).group())

    def test_customtkinter_regressions(self):
        for n in ast.walk(TREE):
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute):
                kwargs = {kw.arg for kw in n.keywords}
                if n.func.attr == 'place':
                    self.assertFalse({'height', 'width'} & kwargs)
                if n.func.attr == 'CTkLabel':
                    self.assertFalse({'border_width', 'border_color'} & kwargs)
        self.assertNotIn('_draw', {n.name for c in CLASSES.values() for n in c.body if isinstance(n, ast.FunctionDef)})


if __name__ == '__main__':
    unittest.main()
