"""V1.31 offline bookmark-storage & headless GUI-path regressions."""
import ast
import json
import queue
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from favorites import FavoriteStore, normalize_favorite
from tests_v130_search_ui import app_method

VIDEO_ID = "dQw4w9WgXcQ"
VIDEO_ID_2 = "9bZkp7q19f0"


def sample(video_id=VIDEO_ID):
    return {"id": video_id, "title": "Da Tweekaz ✨ Neues Video",
            "channel": "Künstler & Co", "duration": "3:42",
            "url": "https://www.youtube.com/watch?v=" + video_id,
            "thumbnail": "https://i.ytimg.com/vi/" + video_id + "/mqdefault.jpg"}


class FavoriteStoreTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.path = Path(self.folder.name) / "favorites.json"
        self.store = FavoriteStore(self.path)

    def test_save_and_reopen_without_api(self):
        self.assertTrue(self.store.add(sample()))
        data = FavoriteStore(self.path).all()
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]["title"], sample()["title"])
        self.assertEqual(data[0]["channel"], sample()["channel"])
        self.assertEqual(data[0]["duration"], "3:42")

    def test_duplicate_no_second_entry(self):
        self.assertTrue(self.store.add(sample()))
        self.assertFalse(self.store.add(sample()))
        self.assertEqual(len(self.store.all()), 1)

    def test_remove_persists(self):
        self.store.add(sample())
        self.assertTrue(self.store.remove(VIDEO_ID))
        self.assertFalse(self.store.remove(VIDEO_ID))
        self.assertFalse(FavoriteStore(self.path).has(VIDEO_ID))

    def test_invalid_ids_rejected(self):
        for candidate in ({"id": ""}, {"id": "short"},
                          {"id": "https://evil.example"}, {"id": 123}, None):
            self.assertIsNone(normalize_favorite(candidate))
        with self.assertRaises(ValueError):
            self.store.add({"id": "invalid"})

    def test_urls_are_formed_from_valid_ids(self):
        item = sample()
        item["url"] = "https://evil.example/query?key=not-a-real-key"
        self.store.add(item)
        self.assertEqual(self.store.all()[0]["url"],
                         "https://www.youtube.com/watch?v=" + VIDEO_ID)

    def test_secrets_and_unspecified_metadata_not_persisted(self):
        item = sample()
        item["api_key"] = "should-not-appear"
        item["thumbnail"] = "https://example.com/private.png"
        self.store.add(item)
        data = self.path.read_text('utf-8')
        self.assertNotIn("should-not-appear", data)
        self.assertNotIn("example.com", data)
        self.assertIn('"version": 1', data)

    def test_bad_json_and_duplicate_legacy_entries(self):
        self.path.write_text('{bad-json', encoding='utf-8')
        self.assertEqual(FavoriteStore(self.path).all(), [])
        self.path.write_text(json.dumps([sample(), sample(), sample(VIDEO_ID_2)]),
                             encoding='utf-8')
        self.assertEqual(len(FavoriteStore(self.path).all()), 2)

    def test_add_rollback_on_disk_failure(self):
        with patch.object(FavoriteStore, 'save', side_effect=OSError("write error")):
            with self.assertRaises(OSError):
                self.store.add(sample())
        self.assertFalse(self.store.has(VIDEO_ID))

    def test_remove_rollback_on_disk_failure(self):
        self.store.add(sample())
        with patch.object(FavoriteStore, 'save', side_effect=OSError("write error")):
            with self.assertRaises(OSError):
                self.store.remove(VIDEO_ID)
        self.assertTrue(self.store.has(VIDEO_ID))

    def test_snapshot_does_not_expose_mutable_state(self):
        self.store.add(sample())
        self.store.all()[0]["title"] = "CHANGED"
        self.assertNotEqual(self.store.all()[0]["title"], "CHANGED")


class FavoriteGuiLogicTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.store = FavoriteStore(Path(self.folder.name) / 'favorites.json')

    def test_heart_toggle_add_and_remove(self):
        toggle = app_method('_toggle_favorite', namespace={'messagebox': Mock()})
        app = SimpleNamespace(favorites=self.store,
                              _refresh_search_favorite_buttons=Mock(),
                              _render_favorites=Mock(), active_page='search')
        toggle(app, sample())
        self.assertTrue(self.store.has(VIDEO_ID))
        self.assertEqual(app._refresh_search_favorite_buttons.call_count, 1)
        toggle(app, sample())
        self.assertFalse(self.store.has(VIDEO_ID))
        self.assertEqual(app._refresh_search_favorite_buttons.call_count, 2)
        app._render_favorites.assert_not_called()

    def test_remove_updates_page_and_buttons(self):
        remove = app_method('_remove_favorite', namespace={'messagebox': Mock()})
        self.store.add(sample())
        app = SimpleNamespace(favorites=self.store,
                              _refresh_search_favorite_buttons=Mock(),
                              _render_favorites=Mock())
        remove(app, VIDEO_ID)
        self.assertFalse(self.store.has(VIDEO_ID))
        app._render_favorites.assert_called_once()

    def test_favorites_page_navigation(self):
        switch = app_method('_switch_page')
        names = ['download', 'search', 'favorites', 'history', 'profiles', 'settings', 'log', 'about']
        pages = {key + '_page': Mock() for key in names}
        buttons = {key: Mock() for key in ('download', 'search', 'favorites', 'history',
                                         'settings', 'profiles', 'about')}
        app = SimpleNamespace(**pages, nav_buttons=buttons, _render_favorites=Mock())
        switch(app, 'favorites')
        self.assertEqual(app.active_page, 'favorites')
        pages['favorites_page'].grid.assert_called_once()
        app._render_favorites.assert_called_once()
        buttons['favorites'].set_selected.assert_called_once_with(True)
        for key in names:
            if key != 'favorites':
                pages[key+'_page'].grid_remove.assert_called_once()

    def test_favorites_reflow_compact_and_large_windows(self):
        reflow = app_method('_reflow_favorites')
        frames = [Mock(), Mock(), Mock(), Mock()]
        titles = [Mock(), Mock(), Mock(), Mock()]
        app = SimpleNamespace(
            favorite_result_cards=frames, favorite_result_titles=titles,
            favorites_list=Mock(), favorites_page=Mock(),
            _favorite_layout_columns=0, _favorite_last_wrap=0,
            _search_grid_columns=lambda width: 3 if width >= 1290 else (2 if width >= 760 else 1))
        for width, expected_col in [(1500, 1), (1000, 1), (680, 0)]:
            reflow(app, width)
            self.assertEqual(frames[1].grid.call_args.kwargs['column'], expected_col)
        self.assertEqual(frames[3].grid.call_args.kwargs['row'], 3)
        self.assertGreaterEqual(titles[0].configure.call_count, 3)

    def test_both_start_buttons_use_existing_download_path(self):
        source = Path(__file__).with_name('app.py').read_text(encoding='utf-8')
        self.assertGreaterEqual(source.count('self._use_search_link(link, download=True)'), 2)
        self.assertIn('def _use_search_link(self, link, download=False):', source)

    def test_local_favorites_do_not_require_api_key(self):
        source = Path(__file__).with_name('app.py').read_text(encoding='utf-8')
        tree = ast.parse(source)
        klass = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'NeonTubeApp')
        render = next(n for n in klass.body if isinstance(n, ast.FunctionDef) and n.name == '_render_favorites')
        names = {n.id for n in ast.walk(render) if isinstance(n, ast.Name)}
        self.assertNotIn('search_videos', names)
        self.assertNotIn('api_request', names)


if __name__ == '__main__':
    unittest.main()
