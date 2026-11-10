"""Network-free regression tests for NeonTube Downloader 1.29.0."""
from __future__ import annotations

import queue
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
from types import SimpleNamespace

from downloader import DownloadJob, DownloadManager, is_transient_network_error, ydl_options
from youtube_api import (YouTubeAPIError, video_id_from_url, readable_duration,
                         seconds_duration, search_videos, get_video_metadata,
                         write_api_key, read_api_key, api_request)


class YoutubeApiUnitTests(unittest.TestCase):
    def test_youtube_url_validation(self):
        good = (
            'https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=15',
            'https://youtu.be/dQw4w9WgXcQ',
            'https://youtube.com/shorts/dQw4w9WgXcQ',
            'https://music.youtube.com/watch?v=dQw4w9WgXcQ',
        )
        for url in good:
            self.assertEqual(video_id_from_url(url), 'dQw4w9WgXcQ')
        for url in ('https://youtube.com.evil.tld/watch?v=dQw4w9WgXcQ',
                    'https://other.com/watch?v=dQw4w9WgXcQ',
                    'https://www.youtube.com/watch?v=short'):
            self.assertIsNone(video_id_from_url(url))

    def test_iso_duration(self):
        self.assertEqual(readable_duration('PT1H02M03S'), '1:02:03')
        self.assertEqual(readable_duration('PT2M04S'), '2:04')
        self.assertEqual(seconds_duration('PT2M04S'), 124)

    @patch('youtube_api.api_request')
    def test_search_and_metadata(self, request):
        request.side_effect = [
            {'items': [{'id': {'videoId': 'dQw4w9WgXcQ'},
                        'snippet': {'title': 'Testvideo', 'channelTitle': 'Testkanal',
                                    'thumbnails': {'medium': {'url': 'https://i.ytimg.com/image.jpg'}}}}],
             'nextPageToken': 'A_PAGE'},
            {'items': [{'id': 'dQw4w9WgXcQ', 'contentDetails': {'duration': 'PT3M20S'}}]},
            {'items': [{'id': 'dQw4w9WgXcQ',
                        'snippet': {'title': 'Testvideo', 'channelTitle': 'Testkanal'},
                        'contentDetails': {'duration': 'PT3M20S'},
                        'statistics': {'viewCount': '42'}}]}
        ]
        result = search_videos('Test', 'test-api-key')
        self.assertEqual(result['next_page_token'], 'A_PAGE')
        self.assertEqual(result['items'][0]['duration'], '3:20')
        meta = get_video_metadata('https://youtu.be/dQw4w9WgXcQ', 'test-api-key')
        self.assertEqual(meta['title'], 'Testvideo')
        self.assertEqual(meta['view_count'], '42')
        self.assertEqual(request.call_count, 3)

    @patch('youtube_api.requests.get')
    def test_errors_do_not_leak_key(self, mocked_get):
        mocked_get.return_value = SimpleNamespace(
            status_code=403,
            json=lambda: {'error': {'errors': [{'reason': 'quotaExceeded'}]}})
        with self.assertRaisesRegex(YouTubeAPIError, 'Limit') as error:
            api_request('search', 'SENSITIVE_KEY', q='test')
        self.assertNotIn('SENSITIVE_KEY', str(error.exception))
        mocked_get.side_effect = Exception('no response')

    @patch('youtube_api.sys.platform', 'linux')
    def test_local_key_storage_outside_project(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict('os.environ', {'YOUTUBE_API_KEY': ''}):
            write_api_key(Path(folder), 'only-user-key')
            self.assertEqual(read_api_key(Path(folder)), 'only-user-key')
            write_api_key(Path(folder), '')
            self.assertEqual(read_api_key(Path(folder)), '')


class DownloadRetryTests(unittest.TestCase):
    def test_retry_categories(self):
        self.assertTrue(is_transient_network_error('SSL: DECRYPTION_FAILED_OR_BAD_RECORD_MAC'))
        self.assertTrue(is_transient_network_error('HTTP Error 503'))
        self.assertFalse(is_transient_network_error('HTTP Error 403 Forbidden'))
        self.assertFalse(is_transient_network_error('This is a private video'))

    def test_options_are_resilient(self):
        job = DownloadJob(url='https://youtu.be/dQw4w9WgXcQ', output_dir='.')
        options = ydl_options(job)
        self.assertGreaterEqual(options['fragment_retries'], 10)
        self.assertLessEqual(options['concurrent_fragment_downloads'], 2)
        self.assertFalse(options.get('nocheckcertificate', False))

    def test_network_error_retries_once(self):
        attempts = []
        class Ydl:
            def __init__(self, opts):
                self.opts = opts
            def __enter__(self): return self
            def __exit__(self, *args): return False
            def extract_info(self, url, download):
                attempts.append(url)
                if len(attempts) == 1:
                    raise Exception('SSL: DECRYPTION_FAILED_OR_BAD_RECORD_MAC')
                return {'title': 'Fertig', 'uploader': 'YouTube', 'duration': 200}

        events = queue.Queue()
        manager = DownloadManager(events, concurrency=1)
        job = DownloadJob(url='https://youtu.be/dQw4w9WgXcQ', output_dir=tempfile.gettempdir())
        manager.jobs[job.id] = job
        with patch('downloader.yt_dlp', SimpleNamespace(YoutubeDL=Ydl)), patch('downloader.time.sleep'):
            manager._worker(job)
        self.assertEqual(job.status, 'finished')
        self.assertEqual(len(attempts), 2)
        self.assertIn('download_retry', [event[0] for event in list(events.queue)])
        manager.close()


if __name__ == '__main__':
    unittest.main()
