"""Regression for the Tk callback ValueError on YouTube API viewCount strings."""
from __future__ import annotations

import ast
import re
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
from tests_v130_search_ui import app_method

APP_FILE = Path(__file__).with_name('app.py')


def function_from_app(name):
    source = ast.parse(APP_FILE.read_text(encoding='utf-8'))
    node = next(n for n in source.body if isinstance(n, ast.FunctionDef) and n.name == name)
    namespace = {'re': re}
    exec(compile(ast.Module(body=[node], type_ignores=[]), str(APP_FILE), 'exec'), namespace)
    return namespace[name]


format_view_count = function_from_app('format_view_count')
clock_text = function_from_app('clock_text')


class ViewCountRegressionTests(unittest.TestCase):
    def test_youtube_data_api_returns_string_count(self):
        self.assertEqual(format_view_count('123456'), '123.456 Aufrufe')

    def test_yt_dlp_returns_integer_count(self):
        self.assertEqual(format_view_count(123456), '123.456 Aufrufe')

    def test_zero_is_not_missing(self):
        self.assertEqual(format_view_count('0'), '0 Aufrufe')
        self.assertEqual(format_view_count(0), '0 Aufrufe')

    def test_thousand_separators_and_whitespace(self):
        self.assertEqual(format_view_count(' 1.234.567 '), '1.234.567 Aufrufe')
        self.assertEqual(format_view_count('1,234,567'), '1.234.567 Aufrufe')

    def test_missing_and_unexpected_values(self):
        for value in (None, '', 'n/a', '1,23', -15, '-15', False, True, {},
                      '123456789012345678901234567890123456789'):
            with self.subTest(value=value):
                self.assertEqual(format_view_count(value), 'Videovorschau')

    def _preview_with_count(self, value):
        ui = SimpleNamespace(
            _selected_job=lambda: None,
            current_meta={'title': 'Beispielvideo', 'uploader': 'Kanal',
                          'view_count': value, 'duration': 150, 'thumbnail_path': ''},
            _set_preview_title=Mock(), _truncate_title=lambda s, length: s[:length],
            preview_channel=Mock(), _bind_preview_title_tooltip=Mock(),
            preview_details=Mock(), preview_duration=Mock(),
            _thumb_image=Mock(return_value='Vorschau-Bild'), preview_image=Mock()
        )
        method = app_method('_refresh_preview', namespace={
            'format_view_count': format_view_count, 'clock_text': clock_text})
        method(ui)
        return ui

    def test_real_callback_method_with_api_string(self):
        ui = self._preview_with_count('123456')
        ui.preview_details.configure.assert_called_once_with(text='123.456 Aufrufe')
        ui.preview_duration.configure.assert_called_once_with(text='02:30')

    def test_real_callback_method_with_yt_dlp_int(self):
        ui = self._preview_with_count(7000)
        ui.preview_details.configure.assert_called_once_with(text='7.000 Aufrufe')

    def test_real_callback_method_without_statistics(self):
        ui = self._preview_with_count(None)
        ui.preview_details.configure.assert_called_once_with(text='Videovorschau')


if __name__ == '__main__':
    unittest.main()
