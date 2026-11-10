"""V1.12 queue viewport checks. No graphical display or customtkinter needed."""
import ast
import hashlib
import unittest
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).parent
SOURCE = (ROOT / 'app.py').read_text(encoding='utf-8')
TREE = ast.parse(SOURCE)
CONST_NAMES = {
    'QUEUE_PANEL_HEIGHT', 'QUEUE_LIST_TOP', 'QUEUE_LIST_HEIGHT',
    'QUEUE_FOOTER_TOP', 'QUEUE_FOOTER_HEIGHT', 'QUEUE_CARD_HEIGHT',
    'QUEUE_ROW_GAP', 'HISTORY_PANEL_HEIGHT', 'HISTORY_LIST_HEIGHT',
    'HISTORY_ROW_HEIGHT',
}
CONSTANTS = {
    node.targets[0].id: ast.literal_eval(node.value)
    for node in TREE.body
    if isinstance(node, ast.Assign) and len(node.targets) == 1
    and isinstance(node.targets[0], ast.Name) and node.targets[0].id in CONST_NAMES
}
APP = next(n for n in TREE.body
           if isinstance(n, ast.ClassDef) and n.name == 'NeonTubeApp')


def method(name):
    node = next(n for n in APP.body
                if isinstance(n, ast.FunctionDef) and n.name == name)
    return node, ast.get_source_segment(SOURCE, node)


class FakeCanvas:
    def __init__(self, exists=True, fail=False):
        self.exists = exists
        self.fail = fail
        self.positions = []

    def winfo_exists(self):
        if self.fail:
            raise RuntimeError('Canvas was closed')
        return self.exists

    def yview_moveto(self, position):
        self.positions.append(position)


class QueueViewportTests(unittest.TestCase):
    def test_three_cards_fit_without_scrolling(self):
        row_pitch = CONSTANTS['QUEUE_CARD_HEIGHT'] + CONSTANTS['QUEUE_ROW_GAP']
        self.assertGreaterEqual(CONSTANTS['QUEUE_LIST_HEIGHT'], 3 * row_pitch + 8)
        self.assertGreaterEqual(CONSTANTS['QUEUE_CARD_HEIGHT'], 70)

    def test_scroll_area_and_buttons_do_not_overlap(self):
        self.assertGreaterEqual(CONSTANTS['QUEUE_LIST_TOP'], 38)
        self.assertLessEqual(CONSTANTS['QUEUE_LIST_TOP'] + CONSTANTS['QUEUE_LIST_HEIGHT'] + 3,
                             CONSTANTS['QUEUE_FOOTER_TOP'])
        self.assertLessEqual(CONSTANTS['QUEUE_FOOTER_TOP'] + CONSTANTS['QUEUE_FOOTER_HEIGHT'] + 6,
                             CONSTANTS['QUEUE_PANEL_HEIGHT'])

    def test_history_compaction_preserves_three_entries_and_column_height(self):
        self.assertEqual(CONSTANTS['QUEUE_PANEL_HEIGHT'] + CONSTANTS['HISTORY_PANEL_HEIGHT'], 572)
        self.assertGreaterEqual(CONSTANTS['HISTORY_LIST_HEIGHT'], 3 * (CONSTANTS['HISTORY_ROW_HEIGHT'] + 4))
        _, text = method('_render_history_summary')
        self.assertIn('height=HISTORY_ROW_HEIGHT', text)
        self.assertIn('height=16', text)
        self.assertIn('height=15', text)

    def test_queue_rows_have_explicit_short_label_heights(self):
        _, text = method('_render_queue')
        self.assertIn('height=QUEUE_CARD_HEIGHT', text)
        self.assertIn('height=18', text)
        self.assertIn('height=15', text)
        self.assertIn('height=17', text)
        self.assertIn('height=26', text)
        self.assertIn('QUEUE_ROW_GAP', text)
        self.assertIn('self._fit_title_label', text)

    def test_membership_changes_reset_stale_queue_scroll(self):
        _, render = method('_render_queue')
        self.assertIn('new_ids != self._queue_rendered_ids', render)
        self.assertIn('if membership_changed:', render)
        self.assertIn('self.after(60, self._reset_queue_scroll)', render)
        node, _ = method('_reset_queue_scroll')
        namespace = {}
        exec(compile(ast.Module(body=[node], type_ignores=[]), '<queue scroll reset>', 'exec'), namespace)
        reset = namespace['_reset_queue_scroll']
        active = FakeCanvas()
        reset(SimpleNamespace(queue_scroll=SimpleNamespace(_parent_canvas=active)))
        self.assertEqual(active.positions, [0.0])
        gone = FakeCanvas(exists=False)
        reset(SimpleNamespace(queue_scroll=SimpleNamespace(_parent_canvas=gone)))
        self.assertEqual(gone.positions, [])
        # Graceful operation on different CustomTkinter versions / destroyed widget.
        reset(SimpleNamespace(queue_scroll=SimpleNamespace()))
        reset(SimpleNamespace(queue_scroll=SimpleNamespace(_parent_canvas=FakeCanvas(fail=True))))

    def test_downloader_engine_untouched(self):
        expected_sha256 = 'cc7d4b3734a8709e3eb65f54e20596ae4d696e8c3e369ff0bb84bc2e21905695'
        self.assertEqual(hashlib.sha256((ROOT/'downloader.py').read_bytes()).hexdigest(),
                         expected_sha256)
        self.assertIn('VERSION = "1.28.8"', SOURCE)


if __name__ == '__main__':
    unittest.main()
