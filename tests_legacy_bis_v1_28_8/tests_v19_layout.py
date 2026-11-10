"""Regressions for the V1.9 link hint and responsive preview title.

Pure Python/AST tests; a full CustomTkinter GUI test must run on Windows.
"""
import ast
import hashlib
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parent
CODE = (ROOT / 'app.py').read_text(encoding='utf-8')
TREE = ast.parse(CODE)
APP = next(n for n in TREE.body if isinstance(n, ast.ClassDef) and n.name == 'NeonTubeApp')


def method(name):
    node = next(n for n in APP.body if isinstance(n, ast.FunctionDef) and n.name == name)
    return ast.get_source_segment(CODE, node)


class V19LayoutTests(unittest.TestCase):
    def test_pixel_ellipsis_fits_measurement_and_keeps_prefix(self):
        helper = next(n for n in TREE.body if isinstance(n, ast.FunctionDef) and n.name == 'ellipsize_to_width')
        namespace = {}
        exec(compile(ast.fix_missing_locations(ast.Module(body=[helper], type_ignores=[])), 'unit', 'exec'), namespace)
        shorten = namespace['ellipsize_to_width']
        measure = lambda text: sum(9 if char != '…' else 7 for char in text)
        title = 'DJ JAKSON — SUPER LONG MIX 2026'
        self.assertEqual(shorten('Hallo', 100, measure), 'Hallo')
        self.assertEqual(shorten('', 100, measure), '')
        self.assertEqual(shorten(title, 0, measure), '')
        self.assertEqual(shorten(title, 3, measure), '')
        for width in (7, 24, 50, 90, 150, 180, 220):
            rendered = shorten(title, width, measure)
            self.assertLessEqual(measure(rendered), width)
            if rendered != title and rendered:
                self.assertTrue(rendered.endswith('…'))
                self.assertTrue(title.startswith(rendered[:-1].rstrip()))

    def test_placeholder_is_observed_not_focus_dependent(self):
        source = method('_build_download_page')
        self.assertIn('self.url_text = ctk.StringVar', source)
        self.assertIn('textvariable=self.url_text', source)
        self.assertIn('self.url_hint = make_label', source)
        self.assertIn('self.url_text.trace_add("write", self._on_url_text_changed)', source)
        self.assertNotIn('placeholder_text=', source)
        self.assertIn('self._update_url_hint()', source)
        self.assertIn('self.url_hint.place_forget()', method('_update_url_hint'))
        self.assertIn('self.url_hint.place(x=8, rely=.5, anchor="w")', method('_update_url_hint'))
        self.assertIn('self.url_input.focus_set()', source)
        self.assertIn('self._url_edited()', method('_on_url_text_changed'))

    def test_preview_title_resizes_and_does_not_cover_quality_badge(self):
        self.assertIn('relwidth=.60', method('_build_preview'))
        self.assertIn('"<Configure>", self._layout_preview_title', method('_build_preview'))
        self.assertIn('ellipsize_to_width(', method('_layout_preview_title'))
        self.assertIn('self._preview_full_title', method('_set_preview_title'))
        for status in ('_refresh_preview', '_fetch_link_preview', '_poll_events'):
            self.assertIn('_set_preview_title(', method(status))
        self.assertIn('HoverTooltip', method('_bind_preview_title_tooltip'))

    def test_no_old_customtkinter_regressions_or_engine_edits(self):
        other = ROOT.parents[1] / 'NeonTube_Downloader_V1_8' / 'NeonTube_Downloader' / 'downloader.py'
        if other.exists():
            self.assertEqual(hashlib.sha256(other.read_bytes()).digest(),
                             hashlib.sha256((ROOT / 'downloader.py').read_bytes()).digest())
        for node in ast.walk(TREE):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == 'place':
                self.assertFalse({'width', 'height'} & {keyword.arg for keyword in node.keywords})
        for node in TREE.body:
            if isinstance(node, ast.ClassDef):
                self.assertNotIn('_draw', {fn.name for fn in node.body if isinstance(fn, ast.FunctionDef)})

if __name__ == '__main__':
    unittest.main()
