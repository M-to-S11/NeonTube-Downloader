"""NeonTube V1.32: offline regressions for bounded auto repair and cancellation."""
import queue
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import downloader


class FakeYdl:
    def __init__(self, opts, scenario):
        self.opts = opts
        self.scenario = scenario
    def __enter__(self):
        return self
    def __exit__(self, *_):
        return False
    def extract_info(self, url, download=True):
        return self.scenario(self.opts)


class RepairTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.job = downloader.DownloadJob('https://www.youtube.com/watch?v=dQw4w9WgXcQ', self.tmp.name)
        self.events = queue.Queue()
        self.manager = downloader.DownloadManager(self.events, 1)
        self.manager.jobs[self.job.id] = self.job
        self.addCleanup(self.manager.close)

    def run_fake(self, scenario, on_sleep=None):
        opts = []
        def make_dl(options):
            opts.append(options)
            return FakeYdl(options, scenario)
        with patch.object(downloader, 'yt_dlp', SimpleNamespace(YoutubeDL=make_dl)):
            if on_sleep is None:
                with patch.object(downloader.time, 'sleep'):
                    self.manager._worker(self.job)
            else:
                with patch.object(downloader.time, 'sleep', side_effect=on_sleep):
                    self.manager._worker(self.job)
        return opts

    def test_repair_after_ssl_error_and_resume_flag(self):
        counter = [0]
        def scenario(opts):
            counter[0] += 1
            if counter[0] == 1:
                raise RuntimeError('SSL: DECRYPTION_FAILED_OR_BAD_RECORD_MAC')
            return {'title':'Recover', 'filepath':'result.mp4'}
        opts = self.run_fake(scenario)
        self.assertEqual(self.job.status, 'finished')
        self.assertEqual(self.job.title, 'Recover')
        self.assertEqual(self.job.retry_attempt, 2)
        self.assertEqual(self.job.retry_wait, 0)
        self.assertTrue(all(o['continuedl'] and not o['nopart'] for o in opts))
        self.assertEqual([o['concurrent_fragment_downloads'] for o in opts], [2, 1])
        self.assertEqual(sum(kind == 'completed' for kind, *_ in list(self.events.queue)), 1)
        self.assertEqual(sum(kind == 'download_retry' for kind, *_ in list(self.events.queue)), 1)

    def test_second_backoff_exponential_and_three_attempt_ceiling(self):
        counter = [0]
        delays = []
        real_wait = self.manager._wait_for_recovery
        def observed_wait(job, seconds):
            delays.append(seconds)
            return real_wait(job, seconds)
        def scenario(opts):
            counter[0] += 1
            raise RuntimeError('HTTP Error 503: Service unavailable')
        with patch.object(self.manager, '_wait_for_recovery', side_effect=observed_wait):
            self.run_fake(scenario)
        self.assertEqual(self.job.status, 'failed')
        self.assertEqual(counter[0], 3)
        self.assertEqual(delays, [2,5])
        self.assertEqual(self.job.retry_wait, 0)
        self.assertEqual(sum(kind == 'download_retry' for kind, *_ in list(self.events.queue)), 2)
        self.assertEqual(sum(kind == 'completed' for kind, *_ in list(self.events.queue)), 0)

    def test_not_retry_permanent_errors(self):
        for error in ('HTTP Error 403', 'HTTP Error 429', 'private video',
                      'CERTIFICATE_VERIFY_FAILED', 'ffmpeg not found',
                      'Permission denied', 'Requested format is not available'):
            with self.subTest(error=error):
                self.assertFalse(downloader.is_transient_network_error(error + ' connection reset'))
        self.assertTrue(downloader.is_transient_network_error('HTTP Error 504'))
        self.assertTrue(downloader.is_transient_network_error('IncompleteRead'))
        self.assertFalse(downloader.is_transient_network_error('bad file data'))
        counter = [0]
        def scenario(opts):
            counter[0] += 1
            raise RuntimeError('HTTP Error 403: Forbidden')
        self.run_fake(scenario)
        self.assertEqual(counter[0], 1)
        self.assertEqual(self.job.status, 'failed')

    def test_pause_during_backoff_without_another_request(self):
        counter = [0]
        def scenario(opts):
            counter[0] += 1
            raise RuntimeError('Connection reset by peer')
        sleeps = [0]
        def while_sleep(_):
            sleeps[0] += 1
            self.job.pause_requested = True
        self.run_fake(scenario, on_sleep=while_sleep)
        self.assertEqual(self.job.status, 'paused')
        self.assertEqual(counter[0], 1)
        self.assertEqual(self.job.retry_wait, 0)

    def test_cancel_during_backoff_without_another_request(self):
        counter = [0]
        def scenario(opts):
            counter[0] += 1
            raise RuntimeError('Connection timeout')
        def while_sleep(_):
            self.job.cancel_requested = True
        self.run_fake(scenario, on_sleep=while_sleep)
        self.assertEqual(self.job.status, 'cancelled')
        self.assertEqual(counter[0], 1)
        self.assertEqual(self.job.retry_wait, 0)

    def test_no_auto_retry_after_processing_failure(self):
        counter = [0]
        def scenario(opts):
            counter[0] += 1
            opts['postprocessor_hooks'][0]({'status':'started'})
            raise RuntimeError('HTTP Error 503: failure in postprocess')
        self.run_fake(scenario)
        self.assertEqual(self.job.status, 'failed')
        self.assertEqual(counter[0], 1)

    def test_manual_resume_after_failed_attempt_uses_existing_path(self):
        def fail(opts):
            raise RuntimeError('HTTP Error 403: Forbidden')
        self.run_fake(fail)
        self.assertEqual(self.job.status, 'failed')
        # Do not launch a live network download in an offline test.
        with patch.object(self.manager, '_schedule'):
            self.manager.resume(self.job.id)
        self.assertIs(self.manager.jobs[self.job.id], self.job)
        self.assertEqual(self.job.status, 'queued')
        self.assertEqual(self.job.error, '')

    def test_ui_has_retry_label_and_close_guard(self):
        source = (Path(__file__).parent/'app.py').read_text(encoding='utf-8')
        self.assertIn('if job.status == "retrying":', source)
        self.assertIn('"retrying": ("warning",', source)
        self.assertIn('"pausing", "retrying")', source)
        self.assertIn('Neustart in {job.retry_wait} s', source)

if __name__ == '__main__':
    unittest.main()
