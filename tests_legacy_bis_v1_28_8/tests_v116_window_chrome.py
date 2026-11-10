"""V1.16 window chrome safety checks (without a GUI display)."""
import ast
import hashlib
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SOURCE = (ROOT / 'app.py').read_text(encoding='utf-8')
MODULE = ast.parse(SOURCE)
APP = next(n for n in MODULE.body if isinstance(n, ast.ClassDef) and n.name == 'NeonTubeApp')

def method(name):
    return ast.get_source_segment(SOURCE, next(n for n in APP.body
                       if isinstance(n, ast.FunctionDef) and n.name == name))

class WindowChromeRegression(unittest.TestCase):
    def test_native_windows_titlebar_is_preserved(self):
        init = method('__init__')
        self.assertIn('self.title(APP_NAME)', init)
        self.assertIn('self.minsize(1130, 700)', init)
        self.assertIn('self.protocol("WM_DELETE_WINDOW", self.on_close)', init)
        # Removing the native frame instead would break window management.
        self.assertNotIn('overrideredirect', init)
        self.assertNotIn('overrideredirect', method('_build_header'))

    def test_no_duplicate_windows_minimize_maximize_close_buttons(self):
        code = method('_build_header')
        self.assertNotIn('("⚙", self.open_settings)', code)
        self.assertIn('header_actions = [("—", self.iconify)', code)
        self.assertIn('if sys.platform != "win32":', code)
        self.assertIn('("—", self.iconify)', code)
        self.assertIn('("□", self._toggle_maximize)', code)
        self.assertIn('("×", self.on_close)', code)

    def test_previous_download_engine_is_identical(self):
        previous = ROOT.parents[1] / 'NeonTube_Downloader_V1_15' / 'NeonTube_Downloader'
        if not (previous / 'downloader.py').exists():
            self.skipTest('Frühere Engine zum Vergleich nicht installiert')
        self.assertEqual(hashlib.sha256((previous / 'downloader.py').read_bytes()).digest(),
                         hashlib.sha256((ROOT / 'downloader.py').read_bytes()).digest())

    def test_layout_sizes_are_unchanged(self):
        previous = ROOT.parents[1] / 'NeonTube_Downloader_V1_15' / 'NeonTube_Downloader' / 'app.py'
        if not previous.exists():
            self.skipTest('Frühere Version zum Vergleich nicht installiert')
        old = previous.read_text(encoding='utf-8')
        for constant in ('QUEUE_PANEL_HEIGHT', 'QUEUE_LIST_TOP', 'QUEUE_LIST_HEIGHT',
                         'QUEUE_FOOTER_TOP', 'QUEUE_FOOTER_HEIGHT', 'QUEUE_CARD_HEIGHT',
                         'HISTORY_PANEL_HEIGHT', 'HISTORY_LIST_HEIGHT', 'HISTORY_ROW_HEIGHT'):
            pattern = rf'^{constant} = .*?$'
            self.assertEqual(re.search(pattern, old, re.M).group(),
                             re.search(pattern, SOURCE, re.M).group())

    def test_no_ctk_regressions(self):
        for node in ast.walk(MODULE):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == 'place':
                self.assertFalse({'height', 'width'} & {keyword.arg for keyword in node.keywords})
        for node in MODULE.body:
            if isinstance(node, ast.ClassDef):
                self.assertNotIn('_draw', {m.name for m in node.body if isinstance(m, ast.FunctionDef)})

if __name__ == '__main__':
    unittest.main()
