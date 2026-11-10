"""V1.28.7 regression tests: compact single-card progress and safety."""
from pathlib import Path
from datetime import datetime
from types import SimpleNamespace, MethodType
import ast
import re
import hashlib
import unittest

ROOT = Path(__file__).resolve().parent
SOURCE = (ROOT / 'app.py').read_text(encoding='utf-8')
TREE = ast.parse(SOURCE)
APP = next(n for n in TREE.body if isinstance(n, ast.ClassDef) and n.name == 'NeonTubeApp')
METHODS = {n.name: n for n in APP.body if isinstance(n, ast.FunctionDef)}
NAMES = ('_log_event', '_log_progress_event', '_collect_job_log_events',
         '_filtered_log_entries', '_log_as_text')
module = ast.Module(body=[METHODS[n] for n in NAMES], type_ignores=[])
ns = {'datetime': datetime, 're': re, 'VERSION': '1.28.7'}
exec(compile(ast.fix_missing_locations(module), '<log-methods>', 'exec'), ns)

def fake_app():
    obj = SimpleNamespace(log_entries=[], log_filter='Alle Ereignisse',
        _log_render_pending=False, active_page='download',
        _log_seen_states={}, _log_progress_deciles={},
        manager=SimpleNamespace(jobs={}))
    for n in NAMES:
        setattr(obj, n, MethodType(ns[n], obj))
    return obj

class PolishedLogTests(unittest.TestCase):
    def test_one_progress_record_per_job_even_after_many_updates(self):
        app = fake_app()
        job = SimpleNamespace(id='a', status='downloading', title='Wunderschönes Testvideo',
                              progress=.14, total=1000, error='')
        app.manager.jobs[job.id] = job
        for fraction in [.14,.24,.33,.43,.56,.66,.72,.84,.99]:
            job.progress = fraction
            app._collect_job_log_events()
        progress = [e for e in app.log_entries if e.get('kind') == 'progress']
        self.assertEqual(len(progress), 1)
        self.assertEqual(progress[0]['job_id'], job.id)
        self.assertIn('90%', progress[0]['message'])
        job.status='finished'; job.progress=1.0
        app._collect_job_log_events()
        self.assertEqual(len([e for e in app.log_entries if e.get('kind') == 'progress']), 1)
        self.assertIn('100%', progress[0]['message'])
        self.assertIn('100%', app._log_as_text())

    def test_progress_records_are_isolated_by_job_and_preserve_complete_titles(self):
        app = fake_app()
        title_a = 'A' * 125
        for ident, title in [('a', title_a), ('b', 'Other video')]:
            app.manager.jobs[ident] = SimpleNamespace(id=ident, title=title,
                status='downloading', progress=.17, total=1500, error='')
        app._collect_job_log_events()
        app.manager.jobs['a'].progress = .55
        app._collect_job_log_events()
        rec = {e['job_id']:e for e in app.log_entries if e.get('kind')=='progress'}
        self.assertEqual(set(rec), {'a','b'})
        self.assertIn('50%', rec['a']['message'])
        self.assertIn('10%', rec['b']['message'])
        self.assertIn(title_a, rec['a']['message'])
        app.log_filter='Downloads'
        self.assertIn(title_a, app._log_as_text())

    def test_sanitizes_urls_and_trimmed_entries(self):
        app=fake_app()
        job=SimpleNamespace(id='secret',title='video https://site.example/?key=private',
                            status='downloading',progress=.2,total=100,error='')
        app._log_progress_event(job,20)
        self.assertIn('[URL]',app._log_as_text())
        self.assertNotIn('private',app._log_as_text())
        for i in range(505): app._log_event('info', str(i))
        self.assertEqual(len(app.log_entries),500)
        job.progress=1.0
        app._log_progress_event(job,100)
        self.assertEqual(len([x for x in app.log_entries if x.get('kind')=='progress']),1)

    def test_compact_layout_hover_icons_and_buttons(self):
        render=ast.get_source_segment(SOURCE,METHODS['_render_log_entries'])
        self.assertIn('HoverTooltip(message_label, full_message)', render)
        self.assertIn('self._fit_if_visible', render)
        self.assertIn('small_icon_label(head, icon_kinds', render)
        self.assertIn('row.pack(fill="x", padx=8, pady=3)', render)
        clear=ast.get_source_segment(SOURCE,METHODS['_clear_log'])
        self.assertIn('self._log_progress_deciles.clear()',clear)
        for action in ('_copy_log','_save_log','_clear_log'):
            self.assertIn(action, METHODS)
        icons=next(n for n in TREE.body if isinstance(n, ast.FunctionDef) and n.name=='outline_icon')
        code=ast.get_source_segment(SOURCE,icons)
        for symbol in ('success','warning','error'):
            self.assertIn(f'kind == "{symbol}"',code)

    def test_download_engine_and_no_updates_unchanged(self):
        self.assertEqual(hashlib.sha256((ROOT/'downloader.py').read_bytes()).hexdigest(),
            'cc7d4b3734a8709e3eb65f54e20596ae4d696e8c3e369ff0bb84bc2e21905695')
        self.assertNotIn('update_checker',SOURCE)
        self.assertIn('VERSION = "1.28.8"',SOURCE)

if __name__=='__main__': unittest.main()
