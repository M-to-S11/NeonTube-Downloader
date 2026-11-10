"""V1.10 GUI behaviour assertions, without requiring a Windows display."""
import ast
import hashlib
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parent
CODE = (ROOT/'app.py').read_text(encoding='utf-8')
TREE = ast.parse(CODE)
APP = next(n for n in TREE.body if isinstance(n, ast.ClassDef) and n.name == 'NeonTubeApp')

def method(name):
    node = next(n for n in APP.body if isinstance(n, ast.FunctionDef) and n.name == name)
    return ast.get_source_segment(CODE, node)

class V110QueueTests(unittest.TestCase):
    def test_queue_text_responds_to_real_width(self):
        self.assertIn('"<Configure>"', method('_render_queue'))
        self.assertIn('self._fit_title_label(w, j.title, 32)', method('_render_queue'))
        self.assertIn('"shown_title": job.title', method('_render_queue'))
        self.assertIn('ellipsize_to_width(text, available', method('_fit_title_label'))
        self.assertIn('label.winfo_width()', method('_fit_title_label'))
        self.assertIn('self._fit_title_label(refs["title"], job.title, 32)', method('_update_queue_progress'))

    def test_history_preview_title_reflows_on_resize(self):
        render = method('_render_history_summary')
        self.assertIn('title_widget.pack(fill="x"', render)
        self.assertIn('"<Configure>"', render)
        self.assertIn('self._fit_title_label(w, t, 35)', render)

    def test_queue_folder_action_and_double_click(self):
        self.assertIn('"Ordner öffnen", self.open_selected_download_folder', method('_build_queue'))
        self.assertIn('"<Double-Button-1>"', method('_render_queue'))
        self.assertIn('self.open_job_download_folder(k)', method('_render_queue'))
        self.assertIn('self._open_download_directory(job.output_dir)', method('open_job_download_folder'))
        self.assertIn('Path(directory).is_dir()', method('_open_download_directory'))
        self.assertIn('open_path(directory)', method('_open_download_directory'))
        self.assertIn('"<Double-Button-1>"', method('_render_history_summary'))

    def test_selecting_job_keeps_widget_for_double_click(self):
        select = method('select_job')
        self.assertNotIn('self._render_queue()', select)
        self.assertIn('refs["frame"].configure(', select)
        self.assertIn('"frame": frame', method('_render_queue'))

    def test_engine_remains_exactly_identical_to_v19(self):
        before = ROOT.parents[1] / 'NeonTube_Downloader_V1_9' / 'NeonTube_Downloader' / 'downloader.py'
        if before.exists():
            self.assertEqual(hashlib.sha256(before.read_bytes()).digest(),
                             hashlib.sha256((ROOT / 'downloader.py').read_bytes()).digest())
        self.assertRegex(CODE, r'VERSION = "1\.(?:10|11|12|13|14|15|16|17|18|19|20|21|22|23|28)\.(?:0|1|2|3|4|5|6|7|8)"')

    def test_ctk_known_regressions(self):
        for node in ast.walk(TREE):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == 'place':
                self.assertFalse({'width', 'height'} & {key.arg for key in node.keywords})
        for node in TREE.body:
            if isinstance(node, ast.ClassDef):
                self.assertNotIn('_draw', {n.name for n in node.body if isinstance(n, ast.FunctionDef)})

if __name__ == '__main__':
    unittest.main()
