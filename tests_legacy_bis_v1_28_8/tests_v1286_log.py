"""V1.28.7 regression tests for real inline log events (no GUI required)."""
from pathlib import Path
from datetime import datetime
from types import SimpleNamespace, MethodType
import ast
import re
import unittest

ROOT = Path(__file__).resolve().parent
SOURCE = (ROOT / 'app.py').read_text(encoding='utf-8')
TREE = ast.parse(SOURCE)
APP = next(n for n in TREE.body if isinstance(n, ast.ClassDef) and n.name == 'NeonTubeApp')
FUNCTIONS = {n.name: n for n in APP.body if isinstance(n, ast.FunctionDef)}

# Compile only the pure event data methods; no customtkinter package or display needed.
names = ('_log_event','_log_progress_event','_collect_job_log_events','_filtered_log_entries','_log_as_text')
module = ast.Module(body=[FUNCTIONS[n] for n in names], type_ignores=[])
namespace = {'datetime': datetime, 'VERSION': '1.28.7', 're': re}
exec(compile(ast.fix_missing_locations(module), '<log-only>', 'exec'), namespace)

def make_fake():
    obj = SimpleNamespace(log_entries=[], log_filter='Alle Ereignisse',
                          _log_render_pending=False, active_page='download',
                          _log_seen_states={}, _log_progress_deciles={},
                          manager=SimpleNamespace(jobs={}))
    for name in names:
        setattr(obj, name, MethodType(namespace[name], obj))
    return obj

class IntegratedLogTests(unittest.TestCase):
    def test_button_opens_main_page_not_modal(self):
        prog = ast.get_source_segment(SOURCE, FUNCTIONS['_build_progress'])
        body = ast.get_source_segment(SOURCE, FUNCTIONS['_build_body'])
        self.assertIn('lambda: self._switch_page("log")', prog)
        self.assertIn('self.log_page = ctk.CTkFrame', body)
        self.assertNotIn('def open_log_dialog', SOURCE)
        self.assertNotIn('ctk.CTkToplevel(', ast.get_source_segment(SOURCE, FUNCTIONS['_build_log_page']))
        self.assertIn('"log": self.log_page', ast.get_source_segment(SOURCE, FUNCTIONS['_switch_page']))
        self.assertIn('"log": self.log_page', ast.get_source_segment(SOURCE, FUNCTIONS['open_settings']))

    def test_log_controls_and_filter_choices(self):
        src = ast.get_source_segment(SOURCE, FUNCTIONS['_build_log_page'])
        for needle in ['Alle Ereignisse', 'Downloads', 'Fehler',
                       'Kopieren', 'Speichern', 'Leeren', 'Zurück zum Download']:
            self.assertIn(needle, src)
        for needle in ['_copy_log', '_save_log', '_clear_log']:
            self.assertIn('def ' + needle, SOURCE)

    def test_filters_and_text_are_based_on_real_events(self):
        fake = make_fake()
        fake._log_event('info', 'Download-System bereit')
        fake._log_event('download', 'Download gestartet')
        fake._log_event('error', 'Download fehlgeschlagen')
        fake._log_event('success', 'Video fertig')
        self.assertEqual(len(fake._filtered_log_entries()), 4)
        fake.log_filter = 'Downloads'
        self.assertEqual([e['level'] for e in fake._filtered_log_entries()], ['download','success'])
        text = fake._log_as_text()
        self.assertIn('Download gestartet', text)
        self.assertNotIn('Download fehlgeschlagen', text)
        fake.log_filter = 'Fehler'
        self.assertEqual([e['level'] for e in fake._filtered_log_entries()], ['error'])

    def test_transitions_progress_and_errors_are_deduplicated(self):
        fake = make_fake()
        job = SimpleNamespace(id='a', status='downloading', title='Testvideo', total=100,
                              progress=.19, error='')
        fake.manager.jobs[job.id] = job
        fake._collect_job_log_events()
        self.assertEqual([e['level'] for e in fake.log_entries], ['download','download'])
        fake._collect_job_log_events()
        self.assertEqual(len(fake.log_entries), 2)
        job.progress = .23
        fake._collect_job_log_events()
        self.assertEqual(len(fake.log_entries), 2)
        self.assertIn('20%', fake.log_entries[-1]['message'])
        job.status, job.error = 'failed', 'Netzwerkfehler'
        fake._collect_job_log_events()
        self.assertIn('Netzwerkfehler', fake.log_entries[-1]['message'])
        self.assertEqual(fake.log_entries[-1]['level'], 'error')

    def test_bounded_memory_and_private_urls_removed(self):
        fake = make_fake()
        for i in range(520):
            fake._log_event('info', f'Video {i} https://example.com/private?token=abcdef')
        self.assertEqual(len(fake.log_entries), 500)
        self.assertNotIn('token=abcdef', fake._log_as_text())
        self.assertIn('[URL]', fake._log_as_text())

    def test_engine_unchanged_and_no_update_function(self):
        import hashlib
        self.assertEqual(hashlib.sha256((ROOT/'downloader.py').read_bytes()).hexdigest(),
                         'cc7d4b3734a8709e3eb65f54e20596ae4d696e8c3e369ff0bb84bc2e21905695')
        self.assertNotIn('update_checker', SOURCE)

if __name__=='__main__':
    unittest.main()
