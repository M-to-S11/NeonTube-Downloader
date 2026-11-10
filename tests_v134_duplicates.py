"""Headless V1.34.0 regression checks: no GUI, API key or network required."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import MethodType, SimpleNamespace
from unittest.mock import Mock
from urllib.parse import urlparse

from downloader import DownloadJob
from duplicate_guard import (content_key, existing_media, build_download_plan,
                             valid_file_path)
from tests_v130_search_ui import app_method

A = "dQw4w9WgXcQ"
B = "9bZkp7q19f0"
C = "J---aiyznGQ"
video = lambda v: f"https://www.youtube.com/watch?v={v}"


class DuplicateGuardTests(unittest.TestCase):
    def test_same_video_short_live_music_and_watch(self):
        urls = [video(A), f"https://youtu.be/{A}?si=aaa",
                f"https://www.youtube.com/shorts/{A}",
                f"https://music.youtube.com/watch?v={A}",
                f"https://youtube.com/live/{A}"]
        self.assertEqual(len({content_key(x) for x in urls}), 1)
        self.assertEqual(content_key('https://youtube.com/watch?v='+A+'&t=120'), content_key(urls[1]))

    def test_untrusted_hosts_are_not_canonicalized_as_youtube(self):
        fake = 'https://youtube.com.evil.example/watch?v=' + A
        self.assertNotEqual(content_key(fake), content_key(video(A)))

    def test_playlist_is_distinct_from_single_video(self):
        one = video(A) + '&list=PLabcde'
        self.assertEqual(content_key(one, playlist=False), content_key(video(A)))
        self.assertEqual(content_key(one, playlist=True), 'youtube-playlist:PLabcde')
        self.assertEqual(content_key('https://www.youtube.com/playlist?list=PLabcde'),
                         'youtube-playlist:PLabcde')

    def test_duplicate_input_same_video_skips_repeated(self):
        plan = build_download_plan([video(A), f'https://youtu.be/{A}', video(B)],
                                   mode='Video (MP4)', audio_format='MP3', playlist=False,
                                   jobs=[], history=[])
        self.assertEqual(plan.accepted_urls(), [video(A), video(B)])
        self.assertEqual(len(plan.repeated), 1)

    def test_active_job_prevents_second_download(self):
        for status in ('queued', 'downloading', 'retrying', 'paused', 'processing', 'pausing'):
            active = DownloadJob(url=video(A), output_dir='.', status=status)
            plan = build_download_plan([f'https://youtu.be/{A}'],
                                       mode='Video (MP4)', audio_format='MP3',
                                       playlist=False, jobs=[active], history=[])
            self.assertEqual(len(plan.pending), 1, status)
            self.assertEqual(plan.accepted_urls(), [], status)

    def test_failed_and_cancelled_do_not_block(self):
        for status in ('cancelled', 'failed'):
            job = DownloadJob(url=video(A), output_dir='.', status=status)
            plan = build_download_plan([video(A)], mode='Video (MP4)',
                                       audio_format='MP3', playlist=False,
                                       jobs=[job], history=[])
            self.assertEqual(plan.accepted_urls(), [video(A)])

    def test_history_file_must_exist(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory, f'My Video [{A}].mp4')
            record = {'url':video(A), 'mode':'Video (MP4)', 'output_dir':directory,
                      'filename':str(path), 'title':'Alte Aufnahme'}
            kwargs = dict(mode='Video (MP4)', audio_format='MP3', playlist=False,
                          jobs=[], history=[record])
            before = build_download_plan([video(A)], **kwargs)
            self.assertEqual(before.accepted_urls(), [video(A)])
            path.write_bytes(b'not real media, but nonempty file for this unit test')
            after = build_download_plan([video(A)], **kwargs)
            self.assertEqual(after.accepted_urls(), [])
            self.assertEqual(after.accepted_urls(repeat_existing=True), [video(A)])
            self.assertEqual(after.downloaded[0].title, 'Alte Aufnahme')
            path.unlink()
            self.assertEqual(build_download_plan([video(A)], **kwargs).accepted_urls(), [video(A)])

    def test_legacy_partial_filename_finds_final_audio_and_not_part(self):
        with tempfile.TemporaryDirectory() as directory:
            record = {'url': video(A), 'mode':'Nur Audio (MP3)',
                      'audio_format':'MP3','filename':str(Path(directory,'temporary.webm.part')),
                      'output_dir':directory}
            self.assertIsNone(existing_media(record, video_id=A))
            f = Path(directory,f'Artist [{A}].mp3')
            f.write_bytes(b'123')
            self.assertEqual(existing_media(record, video_id=A), f)
            self.assertIsNone(valid_file_path(Path(directory,f'Artist [{A}].mp3.part'),
                                               mode='Nur Audio (MP3)', audio_format='MP3'))

    def test_different_media_formats_are_allowed(self):
        with tempfile.TemporaryDirectory() as directory:
            mp4 = Path(directory, f'Clip [{A}].mp4')
            mp4.write_bytes(b'video')
            record = {'url': video(A), 'mode':'Video (MP4)', 'filename':str(mp4),
                      'output_dir':directory}
            audio_plan = build_download_plan([video(A)],mode='Nur Audio (MP3)',
                         audio_format='MP3',playlist=False,jobs=[],history=[record])
            self.assertEqual(audio_plan.accepted_urls(),[video(A)])
            mp3 = Path(directory,f'Clip [{A}].mp3')
            mp3.write_bytes(b'audio')
            another = {'url':video(A), 'mode':'Nur Audio (MP3)',
                       'audio_format':'MP3','filename':str(mp3),'output_dir':directory}
            flac_plan = build_download_plan([video(A)],mode='Nur Audio (MP3)',
                        audio_format='FLAC',playlist=False,jobs=[],history=[another])
            self.assertEqual(flac_plan.accepted_urls(),[video(A)])
            same_plan = build_download_plan([video(A)],mode='Nur Audio (MP3)',
                        audio_format='MP3',playlist=False,jobs=[],history=[another])
            self.assertEqual(len(same_plan.downloaded),1)

    def test_completed_session_job_found_without_history(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory,'test.mp4')
            path.write_bytes(b'data')
            job=DownloadJob(url=video(A), output_dir=directory,status='finished',
                            filename=str(path))
            plan=build_download_plan([video(A)], mode='Video (MP4)',
                audio_format='MP3', playlist=False, jobs=[job], history=[])
            self.assertEqual(len(plan.downloaded),1)

    def test_a_partial_playlist_is_not_mistaken_for_a_finished_playlist(self):
        with tempfile.TemporaryDirectory() as directory:
            record = {'url':video(A)+'&list=PLabcde', 'playlist':True,
                      'mode':'Video (MP4)','filename':str(Path(directory,'first.mp4')),
                      'output_dir':directory}
            Path(record['filename']).write_bytes(b'data')
            plan=build_download_plan([video(A)+'&list=PLabcde'], mode='Video (MP4)',
                audio_format='MP3',playlist=True,jobs=[],history=[record])
            self.assertEqual(plan.accepted_urls(), [video(A)+'&list=PLabcde'])

    def test_batch_preserves_order_with_mixed_status(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory, f'Test [{B}].mp4')
            path.write_bytes(b'data')
            job=DownloadJob(url=video(A),output_dir=directory,status='paused')
            hist=[{'url':video(B),'mode':'Video (MP4)','title':'B',
                   'output_dir':directory,'filename':str(path)}]
            plan=build_download_plan([video(C),video(A),video(B),f'https://youtu.be/{C}'],
                mode='Video (MP4)',audio_format='MP3',playlist=False,
                jobs=[job],history=hist)
            self.assertEqual(plan.accepted_urls(),[video(C)])
            self.assertEqual(plan.accepted_urls(repeat_existing=True),[video(C),video(B)])
            self.assertEqual(len(plan.pending),1)
            self.assertEqual(len(plan.downloaded),1)
            self.assertEqual(len(plan.repeated),1)


class FakeInput:
    def __init__(self, text): self.text = text
    def get(self): return self.text
    def delete(self, *_): self.text = ''
    def focus_set(self): pass


class UiDuplicateTests(unittest.TestCase):
    def make_app(self, directory, text, history=None, jobs=None, answer=False):
        messages = Mock()
        messages.askyesno.return_value = answer
        class NoNetworkThread:
            def __init__(self, **kwargs): pass
            def start(self): pass
        ui=SimpleNamespace(
            url_input=FakeInput(text),
            _parse_links=lambda data:data.split(),
            output_dir=SimpleNamespace(get=lambda:directory),
            mode=SimpleNamespace(get=lambda:'Video (MP4)'),
            quality=SimpleNamespace(get=lambda:'1080p'),
            audio_format=SimpleNamespace(get=lambda:'MP3'),
            playlist=SimpleNamespace(get=lambda:False),
            manager=SimpleNamespace(add=Mock(),jobs=jobs or {}),
            history=history or [], _log_event=Mock(),_metadata_worker=Mock(),
            _refresh_progress=Mock(),after_idle=Mock(),focus_set=Mock(),
            _switch_page=Mock())
        fn=app_method('start_downloads',namespace={
            'messagebox':messages,'yt_dlp':object(),'Path':Path,
            'urlparse':urlparse,'DownloadJob':DownloadJob,
            'threading':SimpleNamespace(Thread=NoNetworkThread)})
        ui.start_downloads=MethodType(fn,ui)
        return ui, messages

    def test_in_queue_skip_and_fresh_link_is_queued(self):
        with tempfile.TemporaryDirectory() as directory:
            job=DownloadJob(url=video(A),output_dir=directory,status='downloading')
            ui,msg=self.make_app(directory, video(A)+' '+video(B),jobs={job.id:job})
            ui.start_downloads()
            self.assertEqual([c.args[0].url for c in ui.manager.add.call_args_list],[video(B)])
            msg.askyesno.assert_not_called()
            msg.showinfo.assert_called_once()

    def test_already_downloaded_user_declines(self):
        with tempfile.TemporaryDirectory() as directory:
            f=Path(directory,f'Video [{A}].mp4'); f.write_bytes(b'mp4')
            history=[{'url':video(A),'mode':'Video (MP4)','filename':str(f),
                      'output_dir':directory,'title':'Video A'}]
            ui,msg=self.make_app(directory,video(A)+' '+video(B),history=history,answer=False)
            ui.start_downloads()
            self.assertEqual([c.args[0].url for c in ui.manager.add.call_args_list],[video(B)])
            msg.askyesno.assert_called_once()
            self.assertIn('Video A',msg.askyesno.call_args.args[1])

    def test_already_downloaded_user_accepts(self):
        with tempfile.TemporaryDirectory() as directory:
            f=Path(directory,f'Video [{A}].mp4'); f.write_bytes(b'mp4')
            history=[{'url':video(A),'mode':'Video (MP4)','filename':str(f),
                      'output_dir':directory,'title':'Video A'}]
            ui,msg=self.make_app(directory,video(A),history=history,answer=True)
            ui.start_downloads()
            self.assertEqual(len(ui.manager.add.call_args_list),1)
            msg.askyesno.assert_called_once()

    def test_all_pending_keeps_links_and_does_not_enqueue(self):
        with tempfile.TemporaryDirectory() as directory:
            job=DownloadJob(url=video(A),output_dir=directory,status='queued')
            ui,msg=self.make_app(directory,video(A),jobs={job.id:job})
            ui.start_downloads()
            ui.manager.add.assert_not_called()
            self.assertEqual(ui.url_input.text,video(A))
            msg.showinfo.assert_called_once()

    def test_request_duplicate_urls_only_one_new_job(self):
        with tempfile.TemporaryDirectory() as directory:
            ui,msg=self.make_app(directory, video(A)+' '+f'https://youtu.be/{A}')
            ui.start_downloads()
            self.assertEqual(len(ui.manager.add.call_args_list),1)
            msg.askyesno.assert_not_called()


if __name__ == '__main__':
    unittest.main()
