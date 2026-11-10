"""Smoke checks for the Windows build-kit files; no GUI required."""
from pathlib import Path
from tempfile import TemporaryDirectory
import ast
import hashlib
import unittest
import build_windows

HERE = Path(__file__).resolve().parent


class ReleaseBuildTests(unittest.TestCase):
    def test_no_updater_modules_and_download_engine_unchanged(self):
        self.assertEqual(hashlib.sha256((HERE/'downloader.py').read_bytes()).hexdigest(),
                         'cc7d4b3734a8709e3eb65f54e20596ae4d696e8c3e369ff0bb84bc2e21905695')
        self.assertIn('VERSION = "1.28.8"', (HERE/'app.py').read_text(encoding='utf-8'))
        for name in ('update_checker.py', 'program_updater.py', 'github_updater.py',
                     'update_und_setup.bat'):
            self.assertFalse((HERE/name).exists(), name)

    def test_validation(self):
        self.assertTrue(build_windows.validate_project())
        self.assertEqual(build_windows.main(['--check-only']), 0)

    def test_pyinstaller_collects_critical_packages_and_runtime(self):
        with TemporaryDirectory() as temp:
            deno=Path(temp)/'deno.exe'
            deno.write_bytes(b'fake - test only')
            args=build_windows.command_for_build(deno, mode='onedir')
            self.assertIn('--onedir', args)
            self.assertIn('--windowed', args)
            self.assertIn('customtkinter',args)
            self.assertIn('yt_dlp', args)
            self.assertIn('yt_dlp_ejs',args)
            self.assertIn('imageio_ffmpeg',args)
            self.assertIn('--add-binary',args)
            self.assertTrue(any('deno.exe' in a for a in args))
            self.assertTrue(any('assets' in a for a in args))
            self.assertIn('--onefile',build_windows.command_for_build(deno,mode='onefile'))

    def test_portable_installer_and_tools_exist(self):
        bat=(HERE/'build_exe.bat').read_text('utf-8')
        iss=(HERE/'NeonTubeDownloader_Setup.iss').read_text('utf-8')
        self.assertIn('build_windows.py --mode onedir',bat)
        self.assertIn('pyinstaller>=6.21',bat)
        self.assertIn('install_deno.ps1',bat)
        self.assertIn('[Files]',iss)
        self.assertIn('recursesubdirs',iss)
        self.assertIn('PrivilegesRequired=lowest',iss)
        self.assertTrue((HERE/'build_setup.bat').exists())
        self.assertTrue((HERE/'WINDOWS_EXE_ANLEITUNG.txt').exists())


if __name__ == '__main__':
    unittest.main()
