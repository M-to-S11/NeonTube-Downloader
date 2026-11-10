"""V1.21: compact drawn action icons and readable metadata regressions."""
import ast
import hashlib
import re
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
SOURCE = (HERE/'app.py').read_text('utf-8')
TREE = ast.parse(SOURCE)
PRIOR = HERE.parents[1]/'NeonTube_Downloader_V1_20'/'NeonTube_Downloader'
CLASSES = {node.name:node for node in TREE.body if isinstance(node, ast.ClassDef)}

def method(cls, name):
    return ast.get_source_segment(SOURCE, next(
        n for n in CLASSES[cls].body if isinstance(n, ast.FunctionDef) and n.name == name))

class V121ActionIcons(unittest.TestCase):
    def test_version_and_engine(self):
        self.assertIn('VERSION = "1.28.8"',SOURCE)
        self.assertEqual(hashlib.sha256((HERE/'downloader.py').read_bytes()).hexdigest(),
            'cc7d4b3734a8709e3eb65f54e20596ae4d696e8c3e369ff0bb84bc2e21905695')

    def test_painted_pause_resume_cancel_icons(self):
        icon_func = next(n for n in TREE.body if isinstance(n, ast.FunctionDef) and n.name == 'outline_icon')
        code=ast.get_source_segment(SOURCE,icon_func)
        for icon in ('pause','resume','cancel'):
            self.assertIn(f'kind == "{icon}"',code)
        self.assertIn('d.polygon(', code)

    def test_button_has_image_and_reference(self):
        func = next(n for n in TREE.body if isinstance(n, ast.FunctionDef) and n.name == 'set_button_icon')
        code=ast.get_source_segment(SOURCE,func)
        self.assertIn('getattr(button, "_neon_icon_kind", None) == key',code)
        self.assertIn('button.configure(image=photo, compound="left")',code)
        self.assertIn('button._neon_icon_reference = photo',code)

    def test_main_actions_keep_dimensions(self):
        code=method('NeonTubeApp','_build_options')
        for text,icon in [('Pausieren','pause'),('Abbrechen','cancel')]:
            self.assertIn(f'"{text}"',code)
            self.assertIn(f'icon_kind="{icon}"',code)
        self.assertIn('height=51',code)

    def test_state_change_uses_resume_icon_and_finish_disabled(self):
        code=method('NeonTubeApp','_refresh_progress')
        self.assertIn('can_resume = job.status in ("paused", "failed")',code)
        self.assertIn('"resume" if can_resume else "pause"',code)
        self.assertIn('done = job.status in ("finished", "cancelled")',code)
        self.assertIn('state="disabled" if done else "normal"',code)
        self.assertIn('"#8995c0" if done else "#dcdfff"',code)

    def test_metadata_contrast_without_card_resize(self):
        queue=method('NeonTubeApp','_render_queue')
        history=method('NeonTubeApp','_render_history_summary')
        self.assertIn('compact_job_metadata(job), 12, "#c0caff"',queue)
        self.assertIn('11, "#becbff"',history)
        if not (PRIOR/'app.py').exists():
            self.skipTest('Vorherige Version in getrenntem Archiv nicht vorhanden')
        old=(PRIOR/'app.py').read_text('utf-8')
        for symbol in ('QUEUE_PANEL_HEIGHT','QUEUE_CARD_HEIGHT','HISTORY_PANEL_HEIGHT','HISTORY_ROW_HEIGHT'):
            pat=rf'^{symbol} = .*'
            self.assertEqual(re.search(pat,old,re.M).group(),re.search(pat,SOURCE,re.M).group())

    def test_no_known_ctk_start_errors(self):
        for n in ast.walk(TREE):
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute):
                kw={k.arg for k in n.keywords}
                if n.func.attr=='place': self.assertFalse({'height','width'}&kw)
                if n.func.attr=='CTkLabel': self.assertFalse({'border_width','border_color'}&kw)
        self.assertNotIn('_draw', {n.name for c in CLASSES.values() for n in c.body if isinstance(n, ast.FunctionDef)})

if __name__=='__main__': unittest.main()
