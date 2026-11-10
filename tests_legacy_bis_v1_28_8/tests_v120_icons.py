"""V1.20 Icon-Fix: visually correct mode buttons, no engine or geometry changes."""
import ast
import hashlib
import re
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parent
SOURCE = (ROOT / 'app.py').read_text(encoding='utf-8')
TREE = ast.parse(SOURCE)
OLD = ROOT.parents[1] / 'NeonTube_Downloader_V1_19' / 'NeonTube_Downloader'
CLASSES = {node.name: node for node in TREE.body if isinstance(node, ast.ClassDef)}

def method(name, cls='NeonTubeApp'):
    obj = next(node for node in CLASSES[cls].body
               if isinstance(node, ast.FunctionDef) and node.name == name)
    return ast.get_source_segment(SOURCE, obj)

class V120IconTests(unittest.TestCase):
    def test_video_audio_use_drawn_icons(self):
        build = method('_build_options')
        self.assertIn('icon="video"', build)
        self.assertIn('icon="music"', build)
        self.assertIn('"Video (MP4)"', build)
        self.assertIn('"Nur Audio (MP3)"', build)
        self.assertNotIn('▣   Video', build)
        self.assertNotIn('♫   Nur Audio', build)

    def test_gear_icon_has_closed_teeth_and_hole(self):
        icon = ast.get_source_segment(SOURCE,
                    next(n for n in TREE.body if isinstance(n, ast.FunctionDef)
                         and n.name == 'outline_icon'))
        self.assertIn('d.polygon(teeth, fill=c)', icon)
        self.assertIn('fill=(0, 0, 0, 0)', icon)
        self.assertIn('elif kind == "settings"', icon)

    def test_new_mode_icons_are_painted_in_same_canvas(self):
        draw = method('redraw', 'NeonSelectionButton')
        self.assertIn('tk_font.Font(', draw)
        self.assertIn('font.measure(self.text)', draw)
        self.assertIn('self.canvas.create_image(', draw)
        self.assertIn('anchor="w"', draw)
        self.assertNotIn('CTkLabel(', draw)

    def test_screen_layout_is_unchanged(self):
        if not (OLD / 'app.py').exists():
            self.skipTest('V1.19 source not present in standalone ZIP')
        old_code = (OLD / 'app.py').read_text(encoding='utf-8')
        for key in ('QUEUE_PANEL_HEIGHT', 'QUEUE_LIST_HEIGHT', 'QUEUE_CARD_HEIGHT',
                    'QUEUE_FOOTER_TOP', 'HISTORY_PANEL_HEIGHT',
                    'HISTORY_ROW_HEIGHT', 'HISTORY_ROW_PADY'):
            pattern = rf'^{key} = .*'
            self.assertEqual(re.search(pattern, SOURCE, re.M).group(),
                             re.search(pattern, old_code, re.M).group())
        self.assertEqual(method('_build_download_page'),
                         ast.get_source_segment(old_code, next(node for node in
                             ast.parse(old_code).body if isinstance(node, ast.ClassDef)
                             and node.name == 'NeonTubeApp').body[
                             next(i for i, node in enumerate(next(n for n in
                                 ast.parse(old_code).body if isinstance(n, ast.ClassDef)
                                 and n.name == 'NeonTubeApp').body)
                                  if isinstance(node, ast.FunctionDef) and
                                  node.name == '_build_download_page')]))

    def test_download_engine_byte_identical(self):
        actual = hashlib.sha256((ROOT / 'downloader.py').read_bytes()).hexdigest()
        self.assertEqual(actual, 'cc7d4b3734a8709e3eb65f54e20596ae4d696e8c3e369ff0bb84bc2e21905695')

    def test_known_customtkinter_regressions(self):
        for node in ast.walk(TREE):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                if node.func.attr == 'place':
                    self.assertFalse({'height', 'width'} & {arg.arg for arg in node.keywords})
                if node.func.attr == 'CTkLabel':
                    self.assertFalse({'border_width', 'border_color'} & {arg.arg for arg in node.keywords})
        for cls in CLASSES.values():
            self.assertNotIn('_draw', {node.name for node in cls.body
                                     if isinstance(node, ast.FunctionDef)})

if __name__ == '__main__': unittest.main()
