"""Regression tests for the four-row history preview (without a GUI display)."""
import ast
import hashlib
import unittest
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parent
SOURCE = (ROOT / 'app.py').read_text(encoding='utf-8')
TREE = ast.parse(SOURCE)
APP = next(node for node in TREE.body if isinstance(node, ast.ClassDef) and node.name == 'NeonTubeApp')


def source(name):
    node = next(n for n in APP.body if isinstance(n, ast.FunctionDef) and n.name == name)
    return node, ast.get_source_segment(SOURCE, node)


def setting(name):
    for node in TREE.body:
        if isinstance(node, ast.Assign):
            if any(isinstance(t, ast.Name) and t.id == name for t in node.targets):
                return ast.literal_eval(node.value)
    raise AssertionError(f'{name} is missing')


class HistoryCardTests(unittest.TestCase):
    def test_four_complete_cards_fit_with_margin(self):
        total = 4 * (setting('HISTORY_ROW_HEIGHT') + 2 * setting('HISTORY_ROW_PADY'))
        self.assertLessEqual(total + 6, setting('HISTORY_LIST_HEIGHT'))
        self.assertGreaterEqual(setting('HISTORY_ROW_HEIGHT'), 37)
        self.assertIn('self.history[:4]', source('_render_history_summary')[1])

    def test_preview_uses_small_thumbnail_and_two_information_rows(self):
        code = source('_render_history_summary')[1]
        self.assertIn('(46, 34)', code)
        self.assertIn('height=16', code)
        self.assertIn('height=15', code)
        self.assertIn('compact_history_metadata(entry)', code)
        self.assertIn('pady=HISTORY_ROW_PADY', code)
        self.assertIn('HoverTooltip(title_widget, title_text)', code)

    def test_status_icon_reserved_before_long_title(self):
        code = source('_render_history_summary')[1]
        check = code.index('make_label(row, "✓"')
        expanding_title = code.index('text_frame.pack(side="left", fill="both", expand=True)')
        self.assertLess(check, expanding_title)

    def test_scroll_position_uses_guarded_canvas_and_reset_is_scheduled(self):
        node, _ = source('_reset_history_preview_scroll')
        ns = {}
        exec(compile(ast.Module(body=[node], type_ignores=[]), '<scroll reset>', 'exec'), ns)
        reset = ns['_reset_history_preview_scroll']
        class Canvas:
            def __init__(self, exists):
                self.exists = exists
                self.calls = []
            def winfo_exists(self):
                return self.exists
            def yview_moveto(self, v):
                self.calls.append(v)
        visible = Canvas(True)
        reset(SimpleNamespace(history_preview_scroll=SimpleNamespace(_parent_canvas=visible)))
        self.assertEqual(visible.calls, [0.0])
        gone = Canvas(False)
        reset(SimpleNamespace(history_preview_scroll=SimpleNamespace(_parent_canvas=gone)))
        self.assertEqual(gone.calls, [])
        reset(SimpleNamespace(history_preview_scroll=SimpleNamespace()))
        self.assertIn('self.after(65, self._reset_history_preview_scroll)', source('_render_history_summary')[1])

    def test_engine_and_queue_dimensions_stay_unchanged(self):
        previous = ROOT.parents[1] / 'NeonTube_Downloader_V1_12' / 'NeonTube_Downloader'
        if not (previous/'downloader.py').exists():
            self.skipTest('Vergleichsdateien aus früherer Version nicht installiert')
        self.assertEqual(hashlib.sha256((ROOT/'downloader.py').read_bytes()).hexdigest(),
                         hashlib.sha256((previous/'downloader.py').read_bytes()).hexdigest())
        for name in ('QUEUE_CARD_HEIGHT','QUEUE_LIST_HEIGHT','QUEUE_PANEL_HEIGHT','QUEUE_FOOTER_TOP'):
            old_source = (previous/'app.py').read_text(encoding='utf-8')
            self.assertIn(f'{name} = {setting(name)}', old_source)

if __name__ == '__main__':
    unittest.main()
