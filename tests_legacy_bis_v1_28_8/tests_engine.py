"""Offline smoke tests for the download manager (no yt-dlp download needed)."""
import queue
import tempfile
import time
import unittest
from pathlib import Path
import downloader

class FakeYoutubeDL:
    def __init__(self, opts): self.opts = opts
    def __enter__(self): return self
    def __exit__(self, *args): pass
    def extract_info(self, url, download=True):
        for i in range(1, 6):
            time.sleep(0.01)
            self.opts['progress_hooks'][0]({'status':'downloading',
                                            'downloaded_bytes':i*20,
                                            'total_bytes':100, 'speed':128000,
                                            'eta':0})
        self.opts['progress_hooks'][0]({'status':'finished','filename':'result.mp4'})
        return {'title':'Testvideo', 'duration':10}

class FakeModule:
    YoutubeDL = FakeYoutubeDL

class EngineTests(unittest.TestCase):
    def test_queue_completes(self):
        original = downloader.yt_dlp
        downloader.yt_dlp = FakeModule
        try:
            with tempfile.TemporaryDirectory() as folder:
                events=queue.Queue()
                manager=downloader.DownloadManager(events, concurrency=2)
                jobs=[downloader.DownloadJob(url=f'https://youtube.com/watch?v={i}',
                                              output_dir=folder) for i in range(3)]
                for job in jobs:manager.add(job)
                deadline=time.time()+4
                while time.time()<deadline and any(j.status!='finished' for j in jobs):
                    time.sleep(0.03)
                self.assertTrue(all(j.status=='finished' for j in jobs))
                self.assertTrue(any(k=='completed' for k,_,_ in list(events.queue)))
                manager.close()
        finally:
            downloader.yt_dlp = original

    def test_format_options(self):
        job=downloader.DownloadJob('https://example.com', '/tmp', mode='Nur Audio (MP3)')
        opts=downloader.ydl_options(job)
        self.assertEqual(opts['postprocessors'][0]['preferredcodec'], 'mp3')
        job.mode='Video (MP4)';job.quality='720p'
        self.assertIn('height<=720',downloader.ydl_options(job)['format'])

if __name__=='__main__': unittest.main()
