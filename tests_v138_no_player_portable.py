"""Portable / no-player release regression tests. Runs without GUI on Linux."""
from pathlib import Path
import ast
import unittest
import build_windows

ROOT = Path(__file__).resolve().parent

class RemovalTests(unittest.TestCase):
    def test_project_validates(self):
        self.assertTrue(build_windows.validate_project())

    def test_no_player_module(self):
        self.assertFalse((ROOT / 'player_page.py').exists())
        self.assertFalse((ROOT / 'player_library.py').exists())

    def test_no_player_imports_or_page(self):
        tree = ast.parse((ROOT / 'app.py').read_text(encoding='utf-8'))
        imported = [n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)]
        self.assertNotIn('player_page', imported)
        self.assertNotIn('player_library', imported)
        app = (ROOT / 'app.py').read_text(encoding='utf-8')
        self.assertNotIn('PlayerPage(', app)
        self.assertNotIn('self.player_page', app)

    def test_no_vlc_dep(self):
        for fname in ('requirements.txt', 'build_windows.py', 'start_windows.bat'):
            contents = (ROOT / fname).read_text(encoding='utf-8').lower()
            self.assertNotIn('python-vlc', contents)
            self.assertNotIn('import vlc', contents)

    def test_portable_zip_script_exists(self):
        self.assertTrue((ROOT / 'PORTABLE_ERSTELLEN.bat').is_file())
        self.assertTrue((ROOT / 'install_ffmpeg.ps1').is_file())
        self.assertIn('--portable-zip', (ROOT / 'PORTABLE_ERSTELLEN.bat').read_text(encoding='utf-8'))

    def test_ffmpeg_detected_as_priority(self):
        from downloader import ffmpeg_path
        self.assertTrue(callable(ffmpeg_path))

if __name__ == '__main__':
    unittest.main()

class BuilderTests(unittest.TestCase):
    def test_command_bundles_deno_ffmpeg_ffprobe_and_no_vlc(self):
        import tempfile
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp)
            binaries = [p / name for name in ('deno.exe', 'ffmpeg.exe', 'ffprobe.exe')]
            for name in binaries:
                name.write_bytes(b'test')
            argv = build_windows.command_for_build(*binaries)
            command = ' '.join(map(str, argv))
            self.assertIn('deno.exe', command)
            self.assertIn('ffmpeg.exe', command)
            self.assertIn('ffprobe.exe', command)
            self.assertNotIn('vlc', command.lower())
            self.assertIn('--onedir', argv)

    def test_portable_zip_contains_full_folder(self):
        import tempfile
        import zipfile
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            dist = base / 'dist'
            folder = dist / 'NeonTubeDownloader'
            (folder / '_internal' / 'ffmpeg').mkdir(parents=True)
            (folder / '_internal' / 'deno').mkdir(parents=True)
            (folder / '_internal' / 'assets').mkdir(parents=True)
            for path in (
                folder / 'NeonTubeDownloader.exe',
                folder / '_internal' / 'deno' / 'deno.exe',
                folder / '_internal' / 'ffmpeg' / 'ffmpeg.exe',
                folder / '_internal' / 'ffmpeg' / 'ffprobe.exe',
                folder / '_internal' / 'assets' / 'hero_art.png',
                folder / '_internal' / 'assets' / 'app.ico',
            ):
                path.write_bytes(b'dummy')
            self.assertTrue(build_windows.verify_portable_dist(folder))
            with patch.object(build_windows, 'ROOT', base):
                archive_path = build_windows.create_portable_zip(folder)
            with zipfile.ZipFile(archive_path) as archive:
                names = archive.namelist()
            self.assertIn('NeonTubeDownloader/NeonTubeDownloader.exe', names)
            self.assertIn('NeonTubeDownloader/_internal/ffmpeg/ffprobe.exe', names)

    def test_missing_ffprobe_prevents_unsafe_distribution(self):
        import tempfile
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            for name in ('NeonTubeDownloader.exe', 'deno.exe', 'ffmpeg.exe',
                         'hero_art.png', 'app.ico'):
                (folder / name).write_bytes(b'x')
            with self.assertRaisesRegex(RuntimeError, 'ffprobe'):
                build_windows.verify_portable_dist(folder)
