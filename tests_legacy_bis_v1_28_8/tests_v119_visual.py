"""V1.19 visual refinement safety checks (no Windows GUI required)."""
import ast
import hashlib
import re
from pathlib import Path
import unittest

HERE = Path(__file__).resolve().parent
CODE = (HERE / "app.py").read_text(encoding="utf-8")
TREE = ast.parse(CODE)
PREVIOUS = HERE.parents[1] / "NeonTube_Downloader_V1_18" / "NeonTube_Downloader"
CLASSES = {n.name: n for n in TREE.body if isinstance(n, ast.ClassDef)}

def method(cls, name):
    return ast.get_source_segment(CODE, next(
        n for n in CLASSES[cls].body
        if isinstance(n, ast.FunctionDef) and n.name == name))

class V119VisualSafety(unittest.TestCase):
    def test_engine_is_unchanged(self):
        if not (PREVIOUS / 'downloader.py').exists():
            self.skipTest('Frühere Engine zum Vergleich nicht installiert')
        self.assertEqual(hashlib.sha256((PREVIOUS / "downloader.py").read_bytes()).digest(),
                         hashlib.sha256((HERE / "downloader.py").read_bytes()).digest())

    def test_native_titlebar_remains(self):
        header = method("NeonTubeApp", "_build_header")
        self.assertIn('if sys.platform != "win32":', header)
        self.assertIn('header_actions = [("—", self.iconify)', header)

    def test_hero_glow_is_existing_bitmap_only(self):
        hero = method("NeonHero", "_paint_banner")
        self.assertIn('bottom_light = Image.new(', hero)
        self.assertIn('Image.alpha_composite(layer.convert("RGBA"), bottom_light)', hero)
        self.assertIn('ImageTk.PhotoImage(layer)', hero)
        self.assertNotIn('ctk.CTkLabel', hero)

    def test_native_glass_and_dimensions_preserved(self):
        panel = ast.get_source_segment(CODE, CLASSES['NeonGlassPanel'])
        self.assertIn('border_width=1', panel)
        self.assertNotIn('tk.Canvas', panel)
        if not (PREVIOUS / 'app.py').exists():
            self.skipTest('Frühere Version zum Vergleich nicht installiert')
        prior_code = (PREVIOUS / "app.py").read_text(encoding="utf-8")
        for name in ('QUEUE_PANEL_HEIGHT', 'QUEUE_LIST_TOP', 'QUEUE_LIST_HEIGHT',
                     'QUEUE_FOOTER_TOP', 'QUEUE_CARD_HEIGHT', 'HISTORY_PANEL_HEIGHT',
                     'HISTORY_LIST_HEIGHT', 'HISTORY_ROW_HEIGHT'):
            pat = rf'^{name} = .*$'
            self.assertEqual(re.search(pat, CODE, re.M).group(),
                             re.search(pat, prior_code, re.M).group())

    def test_regressions(self):
        for n in ast.walk(TREE):
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute):
                if n.func.attr == 'place':
                    self.assertFalse({'height', 'width'} & {kw.arg for kw in n.keywords})
                if n.func.attr == 'CTkLabel':
                    self.assertFalse({'border_width', 'border_color'} & {kw.arg for kw in n.keywords})
        for cls in CLASSES.values():
            self.assertNotIn('_draw', {m.name for m in cls.body if isinstance(m, ast.FunctionDef)})

if __name__ == '__main__':
    unittest.main()
