"""Headless regressions for NeonTube 1.30 search page and queue dispatch.

These tests extract genuine methods from app.py's Python AST to validate the
actual application logic without depending on a Windows/Tk display.
"""
from __future__ import annotations

import ast
import queue
import unittest
from pathlib import Path
from types import SimpleNamespace, MethodType
from urllib.parse import urlparse
from downloader import DownloadJob
from unittest.mock import Mock

APP_FILE = Path(__file__).with_name("app.py")


def app_method(name: str, *, namespace: dict | None = None):
    tree = ast.parse(APP_FILE.read_text(encoding="utf-8"))
    klass = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "NeonTubeApp")
    method = next(n for n in klass.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == name)
    method.decorator_list = []
    ns = dict(namespace or {})
    exec(compile(ast.Module(body=[method], type_ignores=[]), str(APP_FILE), "exec"), ns)
    return ns[name]


class SearchInterfaceTests(unittest.TestCase):
    def test_dynamic_grid_columns(self):
        columns = app_method("_search_grid_columns")
        self.assertEqual(columns(650), 1)
        self.assertEqual(columns(1000), 2)
        self.assertEqual(columns(1600), 3)

    def test_queue_dispatch_uses_existing_start_downloads(self):
        use_link = app_method("_use_search_link")
        ui = SimpleNamespace(url_text=Mock(), _switch_page=Mock(),
                             _url_edited=Mock(), start_downloads=Mock())
        url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
        use_link(ui, url, download=False)
        ui.url_text.set.assert_called_once_with(url)
        ui._switch_page.assert_called_once_with("download")
        ui._url_edited.assert_called_once()
        ui.start_downloads.assert_not_called()
        ui.url_text.reset_mock()
        use_link(ui, url, download=True)
        ui.url_text.set.assert_called_once_with(url)
        ui.start_downloads.assert_called_once_with()

    def test_start_button_enqueues_real_download_job(self):
        import tempfile
        from pathlib import Path

        class FakeString:
            value = ""
            def set(self, value): self.value = value
            def get(self): return self.value

        url_var = FakeString()
        inputs = SimpleNamespace(get=url_var.get, delete=Mock())
        use_link = app_method("_use_search_link")
        class NoNetworkThread:
            def __init__(self, **_kwargs): pass
            def start(self): pass
        start = app_method("start_downloads", namespace={
            "messagebox": Mock(), "yt_dlp": object(), "Path": Path,
            "urlparse": urlparse, "DownloadJob": DownloadJob,
            "threading": SimpleNamespace(Thread=NoNetworkThread),
        })
        with tempfile.TemporaryDirectory() as directory:
            app = SimpleNamespace(
                url_text=url_var, url_input=inputs,
                _switch_page=Mock(), _url_edited=Mock(),
                _parse_links=lambda data: [data],
                output_dir=SimpleNamespace(get=lambda: directory),
                mode=SimpleNamespace(get=lambda: "Video (MP4)"),
                quality=SimpleNamespace(get=lambda: "1080p"),
                audio_format=SimpleNamespace(get=lambda: "MP3"),
                playlist=SimpleNamespace(get=lambda: False),
                manager=SimpleNamespace(add=Mock()),
                _log_event=Mock(), _metadata_worker=Mock(),
                _refresh_progress=Mock(), after_idle=Mock(), focus_set=Mock())
            app.start_downloads = MethodType(start, app)
            url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
            use_link(app, url, download=True)
            app.manager.add.assert_called_once()
            job = app.manager.add.call_args.args[0]
            self.assertIsInstance(job, DownloadJob)
            self.assertEqual(job.url, url)
            self.assertEqual(job.mode, "Video (MP4)")

    def test_search_worker_transmits_requested_page_size(self):
        recorded = []

        def fake_search(term, key, **kwargs):
            recorded.append((term, key, kwargs))
            return {"items": [], "next_page_token": ""}

        worker = app_method("_search_worker", namespace={"search_videos": fake_search})
        events = queue.Queue()
        worker(SimpleNamespace(ui_events=events), 3, "Reggaeton", "next", "SECRET", 24)
        self.assertEqual(recorded[0], ("Reggaeton", "SECRET",
                                       {"page_token": "next", "max_results": 24}))
        self.assertEqual(events.get_nowait()[0], "search_results")

    def test_search_execute_forwards_page_size_and_clears_old_cards(self):
        threads = []
        class Thread:
            def __init__(self, **kwargs):
                threads.append(kwargs)
            def start(self):
                pass

        execute = app_method("_search_execute", namespace={"threading": SimpleNamespace(Thread=Thread),
                                                          "MUTED": "muted"})
        destroyed = Mock()
        ui = SimpleNamespace(
            search_text=SimpleNamespace(get=lambda: "Reggaeton"),
            youtube_api_key="SECRET", search_status=Mock(),
            search_input=Mock(), search_more=Mock(),
            search_query_text="", search_counter=0, search_generation=0,
            search_list=SimpleNamespace(winfo_children=lambda: [SimpleNamespace(destroy=destroyed)]),
            search_result_labels={"old": 1}, search_favorite_buttons={"old": 1},
            search_results=[{"id": "old"}],
            search_result_cards=[1, 2], search_result_titles=[3, 4],
            _search_layout_columns=2, _search_last_wrap=200,
            search_next_page="OLD", search_page_size=SimpleNamespace(get=lambda: "24"),
            _search_worker=Mock())
        execute(ui, "")
        self.assertEqual(threads[0]["args"][-1], 24)
        self.assertEqual(ui.search_next_page, "")
        self.assertEqual(ui.search_favorite_buttons, {})
        self.assertEqual(ui.search_result_cards, [])
        self.assertEqual(ui.search_result_titles, [])
        self.assertEqual(ui.search_counter, 1)
        self.assertEqual(ui.search_generation, 1)
        destroyed.assert_called_once()


if __name__ == "__main__":
    unittest.main()
