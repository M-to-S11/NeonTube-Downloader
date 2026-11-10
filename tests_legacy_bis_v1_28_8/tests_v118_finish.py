"""V1.18: compatible visual polish, keyboard navigation and regression guards."""
import ast
import hashlib
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SOURCE = (ROOT/'app.py').read_text(encoding='utf8')
TREE = ast.parse(SOURCE)
CLASSES = {n.name: n for n in TREE.body if isinstance(n, ast.ClassDef)}


def cls_source(name):
    return ast.get_source_segment(SOURCE, CLASSES[name])


class Version118Tests(unittest.TestCase):
    def test_version_and_same_downloader_engine(self):
        self.assertIn('VERSION = "1.28.8"', SOURCE)
        self.assertEqual(hashlib.sha256((ROOT/'downloader.py').read_bytes()).hexdigest(),
                         'cc7d4b3734a8709e3eb65f54e20596ae4d696e8c3e369ff0bb84bc2e21905695')

    def test_vector_icons_for_statistics(self):
        self.assertIn('elif kind == "speed":', SOURCE)
        self.assertIn('elif kind == "storage":', SOURCE)
        self.assertIn('self._stat(stats, 1, "Restzeit", "--:--:--", "clock")', SOURCE)
        self.assertIn('small_icon_label(frame, symbol, 16', SOURCE)

    def test_keyboard_access_to_selection(self):
        code = cls_source('NeonSelectionButton')
        self.assertIn('takefocus=1', code)
        self.assertIn('<KeyRelease-Return>', code)
        self.assertIn('<KeyRelease-space>', code)
        self.assertIn('self.canvas.focus_set()', code)
        self.assertIn('self.canvas.focus_get() == self.canvas', code)

    def test_controls_not_reimplemented(self):
        for marker in ('QUEUE_PANEL_HEIGHT = 342','HISTORY_PANEL_HEIGHT = 230',
                       'HISTORY_ROW_HEIGHT = 39', 'QUEUE_CARD_HEIGHT = 76',
                       'header_actions = [("—", self.iconify)'):
            self.assertIn(marker, SOURCE)

    def test_known_ctk_regressions(self):
        for node in ast.walk(TREE):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                if node.func.attr == 'place':
                    self.assertFalse({'width','height'} & {kw.arg for kw in node.keywords})
                if node.func.attr == 'CTkLabel':
                    self.assertFalse({'border_width','border_color'} & {kw.arg for kw in node.keywords})
        for cls in CLASSES.values():
            self.assertNotIn('_draw', {n.name for n in cls.body if isinstance(n, ast.FunctionDef)})


if __name__ == '__main__':
    unittest.main()
