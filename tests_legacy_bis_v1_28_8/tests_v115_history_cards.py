"""Source-level regression checks for the V1.15 full-history layout.

The real Windows GUI must still be inspected locally; no on-screen Tk display
is available to these tests.
"""
import ast
import hashlib
import re
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
SOURCE = (HERE / 'app.py').read_text(encoding='utf-8')
TREE = ast.parse(SOURCE)
APP = next(c for c in TREE.body if isinstance(c, ast.ClassDef) and c.name == 'NeonTubeApp')


def get_method(name):
    return next(m for m in APP.body if isinstance(m, ast.FunctionDef) and m.name == name)


class V115HistoryCards(unittest.TestCase):
    def test_full_history_has_no_transparent_inner_text_frame(self):
        method = get_method('_render_full_history')
        text = ast.get_source_segment(SOURCE, method)
        self.assertNotIn('t = ctk.CTkFrame(p, fg_color="transparent")', text)
        self.assertIn('p.grid_columnconfigure(1, weight=1, minsize=90)', text)
        self.assertIn('history_title.grid(row=0, column=1, sticky="ew"', text)
        self.assertIn('history_info.grid(row=1, column=1, sticky="ew"', text)
        self.assertIn('fg_color=PANEL', text)
        self.assertIn('picture.grid(row=0, column=0, rowspan=2', text)

    def test_title_autofit_and_open_folder_survive(self):
        code = ast.get_source_segment(SOURCE, get_method('_render_full_history'))
        for item in ('self._fit_title_label(w, value, 32)',
                     'self._fit_if_visible(w, value, 32)',
                     'HoverTooltip(history_title, full_title)',
                     'compact_history_metadata(entry)',
                     '"<Double-Button-1>"',
                     '"Ordner öffnen"'):
            self.assertIn(item, code)

    def test_hover_is_visually_separate_from_selected_nav(self):
        cls = next(c for c in TREE.body if isinstance(c, ast.ClassDef)
                   and c.name == 'NeonSelectionButton')
        body = ast.get_source_segment(SOURCE, cls)
        self.assertIn('if self.selected:', body)
        self.assertIn('self.hovered and not self.centered', body)
        self.assertIn('set_selected', body)

    def test_engine_and_compact_cards_are_unchanged(self):
        old = HERE.parents[1] / 'NeonTube_Downloader_V1_14' / 'NeonTube_Downloader'
        if not (old/'downloader.py').exists():
            self.skipTest('Frühere Version zum Vergleich nicht installiert')
        self.assertEqual(hashlib.sha256((old/'downloader.py').read_bytes()).digest(),
                         hashlib.sha256((HERE/'downloader.py').read_bytes()).digest())
        old_code = (old/'app.py').read_text(encoding='utf-8')
        for constant in ('QUEUE_PANEL_HEIGHT', 'QUEUE_LIST_HEIGHT',
                         'QUEUE_CARD_HEIGHT', 'HISTORY_PANEL_HEIGHT',
                         'HISTORY_ROW_HEIGHT', 'HISTORY_LIST_HEIGHT'):
            patt = rf'^{constant} = .*?$'
            self.assertEqual(re.search(patt, old_code, re.M).group(),
                             re.search(patt, SOURCE, re.M).group())

    def test_no_legacy_customtkinter_mistakes(self):
        for node in ast.walk(TREE):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == 'place':
                self.assertFalse({'height','width'} & {kw.arg for kw in node.keywords})
        for node in TREE.body:
            if isinstance(node, ast.ClassDef):
                self.assertNotIn('_draw', {m.name for m in node.body if isinstance(m, ast.FunctionDef)})


if __name__ == '__main__':
    unittest.main()
