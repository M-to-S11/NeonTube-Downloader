"""V1.11 tests; non-GUI tests work without a display or CTk installation."""
import ast
import hashlib
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
import unittest

ROOT = Path(__file__).resolve().parent
SOURCE = (ROOT / 'app.py').read_text(encoding='utf-8')
TREE = ast.parse(SOURCE)

# Execute only the pure formatting helpers, avoiding Tk imports and startup.
HELPERS = {'bytes_text', 'compact_job_metadata', 'compact_history_metadata'}
selected = [node for node in TREE.body
            if isinstance(node, ast.FunctionDef) and node.name in HELPERS]
space = {'datetime': datetime}
exec(compile(ast.Module(body=selected, type_ignores=[]), '<formatting helpers>', 'exec'), space)


def method_source(name):
    cls = next(n for n in TREE.body if isinstance(n, ast.ClassDef) and n.name == 'NeonTubeApp')
    node = next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == name)
    return ast.get_source_segment(SOURCE, node)


class V111DetailsTests(unittest.TestCase):
    def test_format_size_quality_and_mode_for_video(self):
        job = SimpleNamespace(mode='Video (MP4)', quality='1080p', audio_format='MP3',
                              total=int(3.6 * 1024**2), downloaded=0)
        result = space['compact_job_metadata'](job)
        self.assertIn('MP4 · 1080p', result)
        self.assertIn('3.6 MB', result)

    def test_audio_metadata_does_not_claim_video_resolution(self):
        job = SimpleNamespace(mode='Nur Audio (MP3)', quality='1080p', audio_format='M4A',
                              total=0, downloaded=0)
        self.assertEqual(space['compact_job_metadata'](job), 'M4A · Audio')

    def test_history_details_include_date_and_optional_fields(self):
        entry = dict(mode='Video (MP4)', quality='720p', size=1024**2,
                     date='2026-11-04T08:50')
        self.assertEqual(space['compact_history_metadata'](entry),
                         'MP4 · 720p · 1.0 MB · 04.11. 08:50')
        self.assertEqual(space['compact_history_metadata']({}), 'MP3')
        self.assertIn('MP3', space['compact_history_metadata'](
            dict(mode='Nur Audio (MP3)', audio_format='MP3', size='invalid')))

    def test_queue_has_separate_labels_and_live_updates(self):
        render = method_source('_render_queue')
        progress = method_source('_update_queue_progress')
        self.assertIn('compact_job_metadata(job)', render)
        self.assertIn('height=QUEUE_CARD_HEIGHT', render)
        self.assertIn('"meta": meta', render)
        self.assertIn('refs["meta"].configure(text=compact_job_metadata(job))', progress)
        self.assertIn('GREEN if job.status == "finished" else MUTED', progress)
        self.assertIn('self.open_job_download_folder(k)', render)

    def test_history_preview_uses_compact_metadata(self):
        self.assertIn('compact_history_metadata(entry)', method_source('_render_history_summary'))

    def test_engine_unchanged_and_no_known_ctk_regressions(self):
        prev = ROOT.parents[1] / 'NeonTube_Downloader_V1_10' / 'NeonTube_Downloader' / 'downloader.py'
        if prev.exists():
            self.assertEqual(hashlib.sha256(prev.read_bytes()).digest(),
                             hashlib.sha256((ROOT / 'downloader.py').read_bytes()).digest())
        self.assertIn('VERSION = "1.28.8"', SOURCE)
        for node in ast.walk(TREE):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == 'place':
                self.assertFalse({'width', 'height'} & {kw.arg for kw in node.keywords})
        for node in TREE.body:
            if isinstance(node, ast.ClassDef):
                self.assertNotIn('_draw', {n.name for n in node.body if isinstance(n, ast.FunctionDef)})


if __name__ == '__main__':
    unittest.main()
