"""Verifies safe optional code-signing integration without real certificates."""
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import sign_release

class SigningTests(unittest.TestCase):
    def test_thumbprint_accepts_only_40_hex_chars(self):
        t = 'AB' * 20
        self.assertEqual(sign_release.normalize_thumbprint(t.lower()), t)
        self.assertEqual(sign_release.normalize_thumbprint(' '.join([t[:20], t[20:]])), t)
        for value in ('', 'a' * 39, 'z' * 40, '0' * 41):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    sign_release.normalize_thumbprint(value)

    def test_requires_windows(self):
        with patch.object(sign_release.sys, 'platform', 'linux'):
            with self.assertRaises(RuntimeError):
                sign_release.sign_portable(Path('/not-real'), 'A' * 40)

    def test_missing_exe_fails_closed(self):
        with tempfile.TemporaryDirectory() as d, patch.object(sign_release.sys, 'platform', 'win32'):
            with self.assertRaises(RuntimeError):
                sign_release.sign_portable(Path(d), 'A' * 40, signtool=Path('signtool'))

    def test_existing_trusted_signatures_left_unchanged(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            exe = root / 'NeonTubeDownloader.exe'
            dll = root / 'thirdparty.dll'
            exe.write_bytes(b'exe')
            dll.write_bytes(b'dll')
            requests = []
            def fake_run(args, **kw):
                requests.append(args)
                return SimpleNamespace(returncode=0, stderr='', stdout='')
            with patch.object(sign_release.sys, 'platform', 'win32'), patch.object(sign_release, 'run_signtool', side_effect=fake_run):
                result = sign_release.sign_portable(root, '1' * 40, signtool=Path('signtool'))
            self.assertEqual(result['already_trusted'], 2)
            self.assertEqual(result['newly_signed'], 0)
            self.assertTrue(all(req[1] == 'verify' for req in requests))
            self.assertEqual(exe.read_bytes(), b'exe')

    def test_signs_untrusted_and_verifies(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root/'NeonTubeDownloader.exe').write_bytes(b'exe')
            (root/'mod.pyd').write_bytes(b'pyd')
            signed = set()
            def fake_run(args, **kw):
                path = args[-1]
                if args[1] == 'verify':
                    return SimpleNamespace(returncode=0 if path in signed else 1, stderr='', stdout='')
                signed.add(path)
                return SimpleNamespace(returncode=0, stderr='', stdout='')
            with patch.object(sign_release.sys, 'platform', 'win32'), patch.object(sign_release, 'run_signtool', side_effect=fake_run):
                result = sign_release.sign_portable(root, 'F' * 40, signtool=Path('signtool'))
            self.assertEqual(result['newly_signed'], 2)
            self.assertEqual(result['total'], 2)

    def test_signing_failure_prevents_release(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root/'NeonTubeDownloader.exe').write_bytes(b'exe')
            def fake_run(args, **kw):
                if args[1] == 'sign':
                    return SimpleNamespace(returncode=1, stderr='Kein Zertifikat', stdout='')
                return SimpleNamespace(returncode=1, stderr='', stdout='')
            with patch.object(sign_release.sys, 'platform', 'win32'), patch.object(sign_release, 'run_signtool', side_effect=fake_run):
                with self.assertRaisesRegex(RuntimeError, 'Kein Zertifikat'):
                    sign_release.sign_portable(root, 'F' * 40, signtool=Path('signtool'))

if __name__ == '__main__':
    unittest.main()
