"""V1.17 safer glass polish: layout and engine regression checks."""
import ast
import hashlib
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PREVIOUS = ROOT.parents[1] / 'NeonTube_Downloader_V1_16' / 'NeonTube_Downloader'
SOURCE = (ROOT/'app.py').read_text(encoding='utf8')
TREE = ast.parse(SOURCE)
CLASSES = {node.name: node for node in TREE.body if isinstance(node, ast.ClassDef)}
APP = CLASSES['NeonTubeApp']

def method(name):
    return ast.get_source_segment(SOURCE, next(f for f in APP.body if isinstance(f, ast.FunctionDef) and f.name == name))

class GlassPolishTests(unittest.TestCase):
    def test_release_version_and_unmodified_engine(self):
        self.assertIn('VERSION = "1.28.8"', SOURCE)
        if not (PREVIOUS/'downloader.py').exists():
            self.skipTest('Frühere Engine zum Vergleich nicht installiert')
        self.assertEqual(hashlib.sha256((ROOT/'downloader.py').read_bytes()).digest(),
                         hashlib.sha256((PREVIOUS/'downloader.py').read_bytes()).digest())

    def test_core_window_chrome_is_still_native_on_windows(self):
        h = method('_build_header')
        self.assertIn('if sys.platform != "win32":', h)
        self.assertIn('header_actions = [("—", self.iconify)', h)

    def test_no_overlay_layer_on_glass_cards(self):
        glass = ast.get_source_segment(SOURCE, CLASSES['NeonGlassPanel'])
        self.assertNotIn('Canvas', glass)
        self.assertNotIn('pack(', glass)
        self.assertIn('border_width=1', glass)
        self.assertIn('fg_color=PANEL', glass)
        self.assertIn('"pink": "#70458e"', glass)

    def test_soft_glow_is_drawn_into_existing_progress_bitmap(self):
        progress = ast.get_source_segment(SOURCE, CLASSES['NeonGradientProgress'])
        self.assertIn('ImageFilter.GaussianBlur(8)', progress)
        self.assertIn('Image.alpha_composite(layer.convert("RGBA"), glow)', progress)
        self.assertNotIn('def _draw(', progress)

    def test_stats_are_native_cards_and_unchanged_dimensions(self):
        progress=method('_build_progress')
        self.assertIn('height=74',progress)
        self.assertIn('self._stat(stats, 2',progress)
        self.assertIn('fg_color="#111944"', method('_stat'))
        if not (PREVIOUS/'app.py').exists():
            self.skipTest('Frühere Version zum Vergleich nicht installiert')
        for const in ('QUEUE_PANEL_HEIGHT','QUEUE_LIST_HEIGHT', 'QUEUE_CARD_HEIGHT',
                      'HISTORY_PANEL_HEIGHT','HISTORY_LIST_HEIGHT','HISTORY_ROW_HEIGHT'):
            pattern=rf'^{const} = .*?$'
            self.assertEqual(re.search(pattern,SOURCE,re.M).group(),
                             re.search(pattern,(PREVIOUS/'app.py').read_text(encoding='utf8'), re.M).group())

    def test_counter_badges_and_quality_badge_keep_their_controls(self):
        self.assertIn('self.queue_count = ctk.CTkLabel(', method('_build_queue'))
        self.assertIn('self.history_count = ctk.CTkLabel(', method('_build_history_summary'))
        self.assertIn('self.preview_quality = ctk.CTkLabel(', method('_build_preview'))
        self.assertIn('self.queue_count.configure', SOURCE)
        self.assertIn('self.history_count.configure', SOURCE)

    def test_ctk_label_v522_compatibility(self):
        # CustomTkinter 5.2.2 CTkLabel does not accept border_width/color.
        # These are CTkFrame parameters, not portable CTkLabel parameters.
        for node in ast.walk(TREE):
            if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
                continue
            if node.func.attr == 'CTkLabel':
                self.assertFalse({'border_width', 'border_color'} & {k.arg for k in node.keywords},
                                 f'CTkLabel unsupported parameters at line {node.lineno}')

    def test_old_ctk_runtime_regressions_are_blocked(self):
        for node in ast.walk(TREE):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == 'place':
                self.assertFalse({'height','width'} & {k.arg for k in node.keywords})
        for cls in CLASSES.values():
            self.assertNotIn('_draw', {f.name for f in cls.body if isinstance(f, ast.FunctionDef)})

if __name__=='__main__':
    unittest.main()
