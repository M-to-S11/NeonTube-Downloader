"""Regression tests for V1.8's title display and completion states.

These tests use AST only and do not require Windows, Tcl or a network.
"""
import ast
import hashlib
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parent
SOURCE = (ROOT/'app.py').read_text(encoding='utf-8')
TREE = ast.parse(SOURCE)
CLASSES = {n.name: n for n in TREE.body if isinstance(n, ast.ClassDef)}


def method_source(name):
    for node in CLASSES['NeonTubeApp'].body:
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return ast.get_source_segment(SOURCE, node)
    raise AssertionError(name)


class V18PolishTests(unittest.TestCase):
    def test_video_titles_keep_prefix_not_suffix(self):
        method = next(n for n in CLASSES['NeonTubeApp'].body
                      if isinstance(n, ast.FunctionDef) and n.name == '_truncate_title')
        undecorated = ast.FunctionDef(name=method.name, args=method.args,
                                      body=method.body, decorator_list=[],
                                      returns=method.returns, type_comment=None)
        module = ast.fix_missing_locations(ast.Module(body=[undecorated], type_ignores=[]))
        namespace = {}
        exec(compile(module, '<title helper>', 'exec'), namespace)
        shorten = namespace['_truncate_title']
        self.assertEqual(shorten('DJ JACKSON — Balkan Music Mega Mix', 14), 'DJ JACKSON —…')
        self.assertEqual(shorten('Kurz', 20), 'Kurz')
        self.assertEqual(shorten('', 20), '')
        self.assertEqual(shorten('Beispiel', 1), '…')
        for name in ('_render_queue', '_refresh_preview', '_update_queue_progress', '_render_history_summary', '_render_full_history'):
            self.assertIn('_truncate_title', method_source(name))

    def test_full_title_tooltips_are_non_overlay(self):
        tooltip = ast.get_source_segment(SOURCE, CLASSES['HoverTooltip'])
        self.assertIn('wraplength=440', tooltip)
        self.assertIn('"<Leave>"', tooltip)
        self.assertIn('"<Destroy>"', tooltip)
        self.assertIn('self._window.destroy()', tooltip)
        self.assertNotIn('tk.Canvas', tooltip)

    def test_completed_download_controls_are_disabled(self):
        self.assertIn('done = job.status in ("finished", "cancelled")', method_source('_refresh_progress'))
        self.assertIn('state="disabled" if done else "normal"', method_source('_refresh_progress'))
        self.assertIn('self.stats_eta.configure(text="Abgeschlossen")', method_source('_refresh_progress'))
        self.assertIn('if index == 2 and job.status in ("finished", "cancelled"):', method_source('_render_queue'))
        self.assertIn('self.after_idle(self.focus_set)', method_source('start_downloads'))

    def test_existing_engine_and_ctk_regressions(self):
        previous = ROOT.parents[1]/'NeonTube_Downloader_V1_7'/'NeonTube_Downloader'/'downloader.py'
        if previous.exists():
            self.assertEqual(hashlib.sha256(previous.read_bytes()).digest(),
                             hashlib.sha256((ROOT/'downloader.py').read_bytes()).digest())
        for node in ast.walk(TREE):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == 'place':
                self.assertFalse({'height', 'width'} & {k.arg for k in node.keywords})
        for cls in CLASSES.values():
            self.assertNotIn('_draw', {f.name for f in cls.body if isinstance(f, ast.FunctionDef)})

if __name__ == '__main__':
    unittest.main()
