"""Regression checks for autoscroll without requiring a graphical desktop."""
import ast
import hashlib
from pathlib import Path
from types import SimpleNamespace, MethodType
import unittest

ROOT = Path(__file__).resolve().parent
CODE = (ROOT / 'app.py').read_text('utf-8')
TREE = ast.parse(CODE)
APP = next(x for x in TREE.body if isinstance(x, ast.ClassDef) and x.name == 'NeonTubeApp')
METHODS = {x.name: x for x in APP.body if isinstance(x, ast.FunctionDef)}
HELPER = next(x for x in TREE.body if isinstance(x, ast.FunctionDef)
              and x.name == 'log_scroll_top_fraction')
NAMES = ('_log_canvas', '_log_canvas_geometry', '_track_log_scroll',
         '_update_log_scroll_indicator', '_restore_log_scroll',
         '_schedule_log_scroll_restore')
module = ast.Module(body=[HELPER] + [METHODS[n] for n in NAMES], type_ignores=[])
ns = {"GREEN": "#26eac4", "MUTED": "#a7b8f1"}
exec(compile(ast.fix_missing_locations(module), '<auto-scroll>', 'exec'), ns)

class FakeCanvas:
    def __init__(self, content=1600, viewport=400, start=.2):
        self.content, self.viewport = content, viewport
        self.first = start
        self.moves = []

    def yview(self):
        return self.first, min(1.0, self.first + self.viewport / self.content)

    def bbox(self, *_args):
        return (0, 0, 1000, self.content)

    def winfo_height(self):
        return self.viewport

    def yview_moveto(self, value):
        self.first = value
        self.moves.append(value)

class FakeLabel:
    def __init__(self):
        self.data = {}

    def configure(self, **kwargs):
        self.data.update(kwargs)

def fake_app(canvas=None):
    obj = SimpleNamespace(active_page='log', _log_auto_follow=True,
        _log_scroll_restoring=False, _log_scroll_generation=0,
        log_scroll_status=FakeLabel(),
        log_list=SimpleNamespace(_parent_canvas=canvas or FakeCanvas()), pending=[])
    obj.after = lambda ms, callback: obj.pending.append((ms, callback))
    for name in NAMES:
        setattr(obj, name, MethodType(ns[name], obj))
    return obj

class AutoScrollTests(unittest.TestCase):
    def test_scroll_math_preserves_bottom_offset_on_prepend(self):
        f = ns['log_scroll_top_fraction']
        # Was at y=300 with viewport 400 in a 1600px log: bottom gap 900.
        # Add 100px of new messages above, the old visible content moves to y=400.
        self.assertAlmostEqual(f(1700, 400, 900), 400 / 1700)
        self.assertEqual(f(100, 400, 0), 0)
        self.assertEqual(f(800, 400, 500), 0)
        self.assertAlmostEqual(f(1000, 400, -10), .6)

    def test_manual_scroll_pauses_and_return_to_top_resumes(self):
        canvas=FakeCanvas(start=.22)
        app=fake_app(canvas)
        app._track_log_scroll()
        self.assertFalse(app._log_auto_follow)
        self.assertIn('pausiert', app.log_scroll_status.data['text'])
        canvas.first=0.0
        app._track_log_scroll()
        self.assertTrue(app._log_auto_follow)
        self.assertIn('aktiv', app.log_scroll_status.data['text'])

    def test_auto_scroll_shows_newest_entry(self):
        app=fake_app(FakeCanvas(start=.28))
        app._log_auto_follow=True
        app._log_scroll_generation=4
        app._restore_log_scroll(4, 500)
        self.assertEqual(app.log_list._parent_canvas.moves[-1], 0.0)
        self.assertFalse(app._log_scroll_restoring)

    def test_manual_scroll_preserved_after_new_message(self):
        canvas=FakeCanvas(content=1700, viewport=400, start=.2)
        app=fake_app(canvas)
        app._log_auto_follow=False
        app._log_scroll_generation=7
        # The same 900px gap from the previous 1600px content.
        app._restore_log_scroll(7, 900)
        self.assertAlmostEqual(canvas.moves[-1], 400 / 1700)
        self.assertFalse(app._log_scroll_restoring)

    def test_render_delayed_and_switch_back_follows_latest(self):
        app=fake_app()
        app._schedule_log_scroll_restore(600)
        self.assertTrue(app._log_scroll_restoring)
        self.assertEqual(app.pending[0][0], 65)
        self.assertIn('self._render_log_entries(reset_scroll=True)',
                      ast.get_source_segment(CODE,METHODS['_switch_page']))
        render=ast.get_source_segment(CODE,METHODS['_render_log_entries'])
        self.assertIn('bottom_gap', render)
        self.assertIn('self._schedule_log_scroll_restore(bottom_gap)',render)
        self.assertIn('self._track_log_scroll()',
                      ast.get_source_segment(CODE,METHODS['_poll_events']))
        self.assertNotIn('CTkToplevel(',render)

    def test_unrelated_download_engine_and_design_untouched(self):
        self.assertEqual(hashlib.sha256((ROOT/'downloader.py').read_bytes()).hexdigest(),
                         'cc7d4b3734a8709e3eb65f54e20596ae4d696e8c3e369ff0bb84bc2e21905695')
        self.assertIn('VERSION = "1.28.8"', CODE)
        self.assertNotIn('update_checker', CODE)
        self.assertIn('self.panel(parent, 220',CODE) if 'self.panel(parent, 220' in CODE else self.assertIn('self.panel(parent, 234',CODE)

if __name__=='__main__':
    unittest.main()
