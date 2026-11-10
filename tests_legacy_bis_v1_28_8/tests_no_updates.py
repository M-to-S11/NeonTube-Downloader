"""Regression checks that this release contains no in-app update function."""
from pathlib import Path
import ast
import unittest

HERE = Path(__file__).resolve().parent

class NoUpdateFeatures(unittest.TestCase):
    def test_app_has_no_update_checker(self):
        src = (HERE/'app.py').read_text(encoding='utf-8')
        tree = ast.parse(src)
        defs = {n.name for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
        self.assertFalse({'_check_ytdlp_updates', 'open_program_update_assistant',
                          '_start_ytdlp_update_build', '_check_program_updates'} & defs)
        for name in ('update_checker', 'program_updater', 'github_updater'):
            self.assertNotIn('from '+name+' import', src)
            self.assertFalse((HERE/(name+'.py')).exists())
        for label in ('Programm-Update-Assistent', 'yt-dlp – Versionsprüfung',
                      'yt-dlp aktualisieren und neue EXE erstellen',
                      'NeonTube Update'):
            self.assertNotIn(label, src)

    def test_normal_app_components_present(self):
        source = (HERE/'app.py').read_text(encoding='utf-8')
        for item in ('class NeonTubeApp', 'DownloadManager', 'Warteschlange',
                     'Download-Verlauf', 'VERSION = "1.28.8"'):
            self.assertIn(item, source)

    def test_version_build_metadata(self):
        installer = (HERE/'NeonTubeDownloader_Setup.iss').read_text(encoding='utf-8')
        self.assertIn('AppVersion "1.28.8"',installer)
        self.assertIn('Setup_V1_28_8',installer)

if __name__ == '__main__':
    unittest.main()
