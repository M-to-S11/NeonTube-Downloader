"""Headless regression tests for 1.36.0 folder organization and prior features."""
from __future__ import annotations
import os
import queue
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from downloader import (DownloadJob, DownloadManager, FOLDER_ORGANIZATIONS,
                        normalize_folder_organization, output_template, ydl_options)
from duplicate_guard import existing_media, build_download_plan
from tests_v130_search_ui import app_method

VIDEO = 'https://www.youtube.com/watch?v=dQw4w9WgXcQ'
ID = 'dQw4w9WgXcQ'


class FolderOrganizationTests(unittest.TestCase):
    def _job(self, folder='Keine (wie bisher)', **kwargs):
        return DownloadJob(VIDEO, output_dir=os.path.join('C:', 'Downloads'),
                           folder_organization=folder, **kwargs)

    def test_legacy_setting_remains_default(self):
        self.assertEqual(self._job().folder_organization, FOLDER_ORGANIZATIONS[0])
        self.assertEqual(normalize_folder_organization(''), FOLDER_ORGANIZATIONS[0])
        self.assertEqual(normalize_folder_organization(None), FOLDER_ORGANIZATIONS[0])
        self.assertEqual(normalize_folder_organization('../evil'), FOLDER_ORGANIZATIONS[0])
        self.assertEqual(len(set(FOLDER_ORGANIZATIONS)), 4)

    def test_flat_default_retains_original_filename_template(self):
        job = self._job()
        self.assertEqual(output_template(job),
                         os.path.join(job.output_dir, '%(title).160B [%(id)s].%(ext)s'))

    def test_channel_template_has_fallback_and_sanitization(self):
        opts = ydl_options(self._job('Nach Kanal'))
        self.assertIn('%(channel,uploader|Unbekannter Kanal).110S', opts['outtmpl'])
        self.assertIn('%(title).160B [%(id)s].%(ext)s', opts['outtmpl'])
        self.assertTrue(opts['windowsfilenames'])
        self.assertTrue(opts['continuedl'])
        self.assertFalse(opts['nopart'])
        self.assertFalse(opts['overwrites'])

    def test_playlist_template_fallback_for_singles(self):
        for playlist in (False, True):
            name = output_template(self._job('Nach Playlist', playlist=playlist))
            self.assertIn('Einzelvideos', name)
            self.assertIn('playlist_title', name) if playlist else self.assertNotIn('playlist_title', name)

    def test_formats_are_separate_directories(self):
        mp4 = self._job('Nach Dateiformat')
        mp3 = self._job('Nach Dateiformat', mode='Nur Audio (MP3)', audio_format='MP3')
        flac = self._job('Nach Dateiformat', mode='Nur Audio (MP3)', audio_format='FLAC')
        self.assertEqual(Path(output_template(mp4)).parent.name, 'MP4')
        self.assertEqual(Path(output_template(mp3)).parent.name, 'MP3')
        self.assertEqual(Path(output_template(flac)).parent.name, 'FLAC')
        self.assertEqual(Path(output_template(self._job('Nach Dateiformat', mode='Nur Audio (MP3)', audio_format='../bad'))).parent.name, 'Audio')

    def test_old_jobs_keep_layout_when_config_changes(self):
        queued_job = self._job('Nach Kanal')
        new_job = self._job('Nach Playlist')
        self.assertIn('channel', output_template(queued_job))
        self.assertIn('playlist_title', output_template(self._job('Nach Playlist', playlist=True)))

    def test_enqueue_records_current_folder_choice(self):
        """The real queue method passes the chosen setting into the job."""
        from types import SimpleNamespace
        from urllib.parse import urlparse
        from unittest.mock import Mock

        class NoNetworkThread:
            def __init__(self, **kwargs): pass
            def start(self): pass

        start = app_method('start_downloads', namespace={
            'yt_dlp': object(), 'messagebox': Mock(), 'Path': Path,
            'urlparse': urlparse, 'DownloadJob': DownloadJob,
            'threading': SimpleNamespace(Thread=NoNetworkThread)})
        with tempfile.TemporaryDirectory() as dir:
            ui = SimpleNamespace(
                config_data={'folder_organization':'Nach Kanal'},
                url_input=SimpleNamespace(get=lambda:VIDEO,delete=Mock()),
                _parse_links=lambda value:[value],
                mode=SimpleNamespace(get=lambda:'Video (MP4)'),
                quality=SimpleNamespace(get=lambda:'1080p'),
                audio_format=SimpleNamespace(get=lambda:'MP3'),
                playlist=SimpleNamespace(get=lambda:False),
                output_dir=SimpleNamespace(get=lambda:dir),
                manager=SimpleNamespace(add=Mock(),jobs={}),history=[],
                _log_event=Mock(),_metadata_worker=Mock(),
                _switch_page=Mock(),_refresh_progress=Mock(),
                focus_set=Mock(),after_idle=Mock())
            start(ui)
            job = ui.manager.add.call_args.args[0]
            self.assertEqual(job.folder_organization, 'Nach Kanal')
            self.assertIn('%(channel', ydl_options(job)['outtmpl'])

    def test_one_level_nested_fallback_detects_processed_media(self):
        with tempfile.TemporaryDirectory() as dir:
            nested = Path(dir, 'Mein Kanal')
            nested.mkdir()
            output = nested / f'Clip [{ID}].mp3'
            output.write_bytes(b'real media')
            record = {'url':VIDEO, 'mode':'Nur Audio (MP3)', 'audio_format':'MP3',
                      'output_dir':dir, 'filename':str(nested / f'Clip [{ID}].m4a')}
            self.assertEqual(existing_media(record, video_id=ID), output)
            plan = build_download_plan([VIDEO], mode='Nur Audio (MP3)', audio_format='MP3',
                                       playlist=False, jobs=[], history=[record])
            self.assertEqual(len(plan.downloaded), 1)
            output.unlink()
            self.assertEqual(build_download_plan([VIDEO], mode='Nur Audio (MP3)',
                                             audio_format='MP3', playlist=False,
                                             jobs=[], history=[record]).accepted_urls(), [VIDEO])

    def test_record_folder_uses_real_nested_path_and_legacy_root(self):
        method = app_method('_record_folder', namespace={'Path': Path})
        with tempfile.TemporaryDirectory() as dir:
            nested = Path(dir, 'Kanal')
            nested.mkdir()
            file = nested / 'Video.mp4'
            file.write_bytes(b'data')
            info = {'filename':str(file), 'output_dir':dir}
            self.assertEqual(method(info), str(nested))
            info['filename'] = ''
            self.assertEqual(method(info), dir)

    def test_engine_uses_layout_on_retry(self):
        jobs = []
        job = self._job('Nach Kanal')
        def downloader_factory(options):
            jobs.append(options)
            class FakeDL:
                def __enter__(self): return self
                def __exit__(self, *_): return False
                def extract_info(self, url, download=True):
                    if len(jobs) == 1:
                        raise RuntimeError('connection reset')
                    return {'title':'Video', 'id':ID}
            return FakeDL()
        manager = DownloadManager(queue.Queue())
        try:
            with patch('downloader.yt_dlp', SimpleNamespace(YoutubeDL=downloader_factory)), \
                 patch('downloader.time.sleep'):
                manager._worker(job)
        finally:
            manager.close()
        self.assertEqual(job.status, 'finished')
        self.assertEqual(len(jobs), 2)
        self.assertEqual(jobs[0]['outtmpl'], jobs[1]['outtmpl'])
        self.assertTrue(jobs[0]['continuedl'])

    def test_postprocessing_final_output_path_is_not_overwritten(self):
        with tempfile.TemporaryDirectory() as dir:
            final = Path(dir, f'Clip [{ID}].mp3')
            old = Path(dir, f'Clip [{ID}].webm')
            final.write_bytes(b'data')
            job = DownloadJob(VIDEO, dir, mode='Nur Audio (MP3)')
            manager = DownloadManager(queue.Queue())
            class FakeDL:
                def __init__(self, opts): self.options = opts
                def __enter__(self): return self
                def __exit__(self, *_): return False
                def extract_info(self, *_a, **_k):
                    self.options['postprocessor_hooks'][0]({
                        'status':'finished', 'info_dict':{'filepath':str(final)}})
                    return {'title':'Clip','id':ID,
                            'requested_downloads':[{'filepath':str(old)}],
                            'filepath':str(old)}
            try:
                with patch('downloader.yt_dlp',SimpleNamespace(YoutubeDL=FakeDL)):
                    manager._worker(job)
            finally:
                manager.close()
            self.assertEqual(job.status, 'finished')
            self.assertEqual(job.filename, str(final))


if __name__=='__main__':
    unittest.main()
