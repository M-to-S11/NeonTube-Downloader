"""GUI-free checks that V1.14 did not disturb the completed V1.13 layout."""
import ast
import hashlib
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
SOURCE = (HERE / 'app.py').read_text(encoding='utf-8')
TREE = ast.parse(SOURCE)
APP = next(n for n in TREE.body if isinstance(n, ast.ClassDef) and n.name == 'NeonTubeApp')

def method(name):
    return ast.get_source_segment(SOURCE, next(n for n in APP.body
                      if isinstance(n, ast.FunctionDef) and n.name == name))

class V114HistoryTests(unittest.TestCase):
    def test_queue_and_history_sizes_unchanged(self):
        previous = HERE.parents[1] / 'NeonTube_Downloader_V1_13' / 'NeonTube_Downloader' / 'app.py'
        if not previous.exists():
            self.skipTest('Frühere Version zum Vergleich nicht installiert')
        text = previous.read_text(encoding='utf-8')
        for constant in ('QUEUE_PANEL_HEIGHT', 'QUEUE_LIST_HEIGHT', 'QUEUE_CARD_HEIGHT',
                         'QUEUE_ROW_GAP', 'HISTORY_PANEL_HEIGHT', 'HISTORY_ROW_HEIGHT',
                         'HISTORY_ROW_PADY', 'HISTORY_LIST_HEIGHT'):
            import re
            old = re.search(rf'^{constant} = .*$', text, flags=re.M)
            new = re.search(rf'^{constant} = .*$', SOURCE, flags=re.M)
            self.assertIsNotNone(old)
            self.assertEqual(old.group(0), new.group(0))

    def test_engine_remains_byte_identical(self):
        before = HERE.parents[1] / 'NeonTube_Downloader_V1_13' / 'NeonTube_Downloader' / 'downloader.py'
        if not before.exists():
            self.skipTest('Frühere Engine zum Vergleich nicht installiert')
        self.assertEqual(hashlib.sha256(before.read_bytes()).digest(),
                         hashlib.sha256((HERE / 'downloader.py').read_bytes()).digest())

    def test_count_updates_with_actual_persisted_history(self):
        self.assertIn('self.history_count = ctk.CTkLabel(', method('_build_history_summary'))
        self.assertIn('self.history_count.configure(text=str(len(self.history)))',
                      method('_render_history_summary'))
        self.assertIn('self.history[:4]', method('_render_history_summary'))

    def test_full_history_title_resizes_and_retains_tooltip(self):
        s = method('_render_full_history')
        for fragment in ('self._fit_title_label(w, value, 32)',
                         'self._fit_if_visible(w, value, 32)',
                         'HoverTooltip(history_title, full_title)',
                         'compact_history_metadata(entry)',
                         '"<Double-Button-1>"',
                         'self._open_download_directory(directory)'):
            self.assertIn(fragment, s)

    def test_old_tkinter_compatibility_bugs_stay_fixed(self):
        for n in ast.walk(TREE):
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr == 'place':
                self.assertFalse({'height', 'width'} & {keyword.arg for keyword in n.keywords})
        for n in TREE.body:
            if isinstance(n, ast.ClassDef):
                self.assertNotIn('_draw', {item.name for item in n.body if isinstance(item, ast.FunctionDef)})

if __name__ == '__main__':
    unittest.main()
