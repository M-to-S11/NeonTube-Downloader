"""Headless clipboard regression tests, without Windows, Tk or network."""
import unittest
from pathlib import Path
from types import SimpleNamespace, MethodType
from unittest.mock import Mock

from clipboard_links import extract_youtube_links, append_unique_links, ClipboardLinkWatcher
from tests_v130_search_ui import app_method

A='dQw4w9WgXcQ'
B='9bZkp7q19f0'
WATCH=f'https://www.youtube.com/watch?v={A}'
SHORT=f'https://youtu.be/{B}'
PLAY='https://www.youtube.com/playlist?list=PL1234abcdef1234'


class ClipboardLinkExtractionTests(unittest.TestCase):
    def test_regular_watch_link(self):
        self.assertEqual(extract_youtube_links(WATCH),[WATCH])

    def test_supported_video_and_playlist_variants(self):
        urls = [f'https://www.youtube.com/shorts/{A}',
                f'https://youtube.com/live/{A}',
                f'https://m.youtube.com/watch?v={A}&t=3',
                f'https://music.youtube.com/watch?v={B}', SHORT, PLAY]
        self.assertEqual(extract_youtube_links(' '.join(urls)),urls)

    def test_video_with_playlist_retains_parameters(self):
        url=f'https://youtube.com/watch?v={A}&list=PL123456abc'
        self.assertEqual(extract_youtube_links(url),[url])

    def test_links_surrounded_by_text_and_punctuation(self):
        self.assertEqual(extract_youtube_links(f'Hier: {WATCH}. Weiter: ({SHORT})'),[WATCH,SHORT])

    def test_mixed_and_repeat_links_deduped(self):
        self.assertEqual(extract_youtube_links(f'{WATCH} {WATCH} https://example.com/ {SHORT}'),[WATCH,SHORT])

    def test_limit_large_and_non_text_are_safe(self):
        self.assertEqual(extract_youtube_links(WATCH+'x'*8200), [])
        self.assertEqual(extract_youtube_links(None), [])
        self.assertEqual(extract_youtube_links(WATCH+' '+SHORT, limit=1), [WATCH])

    def test_lookalike_and_attack_domains_rejected(self):
        invalid=[f'https://youtube.com.evil.invalid/watch?v={A}',
                 f'https://youtube.com@evil.invalid/watch?v={A}',
                 f'https://fake-youtube.com/watch?v={A}',
                 f'https://youtu.be.evil.invalid/{A}',
                 f'https://youtube.com:9999/watch?v={A}',
                 f'https://foo@youtube.com/watch?v={A}',
                 f'https://notyoutube.com/watch?v={A}']
        self.assertEqual(extract_youtube_links(' '.join(invalid)),[])

    def test_arbitrary_youtube_pages_not_treated_as_downloadable(self):
        for path in ('', '/feed', '/results?search_query=a', '/channel/UC123',
                     f'/watch?v={A[:-1]}', '/playlist?list=X'):
            if path=='/playlist?list=X':
                # X is too short to be a plausible playlist identifier.
                pass
            self.assertEqual(extract_youtube_links('https://www.youtube.com'+path),[])

    def test_bad_port_and_malformed_url_safe(self):
        self.assertEqual(extract_youtube_links(f'https://youtube.com:abc/watch?v={A}'), [])
        self.assertEqual(extract_youtube_links(f'http://youtube.com:443/watch?v={A}'),[f'http://youtube.com:443/watch?v={A}'])

    def test_append_preserves_existing_text_and_no_duplicate(self):
        self.assertEqual(append_unique_links(WATCH,[WATCH,SHORT,SHORT]),WATCH+'  '+SHORT)
        self.assertEqual(append_unique_links('eigener Text',[WATCH]),'eigener Text  '+WATCH)
        self.assertEqual(append_unique_links('',[WATCH,SHORT]),WATCH+'  '+SHORT)


class ClipboardWatcherTests(unittest.TestCase):
    def test_old_clipboard_is_ignored_on_start(self):
        watcher=ClipboardLinkWatcher(WATCH)
        self.assertEqual(watcher.observe(WATCH,foreground=True),[])

    def test_background_waits_until_focus_then_prompts_once(self):
        watcher=ClipboardLinkWatcher('')
        self.assertEqual(watcher.observe(WATCH,foreground=False),[])
        self.assertEqual(watcher.observe(WATCH,foreground=False),[])
        self.assertEqual(watcher.observe(WATCH,foreground=True),[WATCH])
        self.assertEqual(watcher.observe(WATCH,foreground=True),[])

    def test_non_youtube_copy_removes_old_offer(self):
        watcher=ClipboardLinkWatcher('')
        watcher.observe(WATCH,foreground=False)
        watcher.observe('Hallo',foreground=False)
        self.assertEqual(watcher.observe('Hallo',foreground=True),[])

    def test_copying_again_after_change_is_new_offer(self):
        watcher=ClipboardLinkWatcher('')
        self.assertEqual(watcher.observe(WATCH,foreground=True),[WATCH])
        watcher.observe('other', foreground=True)
        self.assertEqual(watcher.observe(WATCH,foreground=True),[WATCH])

    def test_manual_paste_suppresses_prompt(self):
        watcher=ClipboardLinkWatcher('')
        watcher.observe(' '+WATCH+' ',foreground=False)
        watcher.dismiss(' '+WATCH+' ')
        self.assertEqual(watcher.observe(' '+WATCH+' ',foreground=True),[])

    def test_no_clipboard_data_is_stored_except_valid_urls(self):
        watcher=ClipboardLinkWatcher('SECRET_PASSWORD_CONTENT')
        self.assertNotIn('SECRET_PASSWORD_CONTENT',repr(watcher.__dict__))
        watcher.observe('other secret text', foreground=False)
        self.assertFalse(watcher.pending)


class ClipboardUIBridgeTests(unittest.TestCase):
    def make_ui(self, *, focused=True, accepted=True, initial=''):
        user_text=SimpleNamespace(value=initial)
        user_text.get=lambda: user_text.value
        user_text.set=lambda s: setattr(user_text,'value',s)
        question=Mock(return_value=accepted)
        ui=SimpleNamespace(
            _clipboard_watcher=ClipboardLinkWatcher(''),
            _clipboard_watch_after=None, state=lambda:'normal',
            focus_get=lambda: object() if focused else None,
            _clipboard_text_safely=Mock(return_value=WATCH),
            _switch_page=Mock(), url_input=SimpleNamespace(get=user_text.get,focus_set=Mock()),
            url_text=user_text, winfo_exists=lambda:True, after=Mock(return_value='jobId'))
        ui._clipboard_watch_tick=MethodType(app_method('_clipboard_watch_tick',namespace={
            'messagebox':SimpleNamespace(askyesno=question),
            'append_unique_links':append_unique_links}),ui)
        return ui,question

    def test_acknowledged_link_populates_input_not_download(self):
        ui,question=self.make_ui()
        ui._clipboard_watch_tick()
        question.assert_called_once()
        ui._switch_page.assert_called_once_with('download')
        self.assertEqual(ui.url_text.get(),WATCH)
        self.assertEqual(ui._clipboard_watch_after,'jobId')

    def test_declined_link_never_populates_and_does_not_prompt_again(self):
        ui,question=self.make_ui(accepted=False)
        ui._clipboard_watch_tick()
        ui._clipboard_watch_tick()
        self.assertEqual(question.call_count,1)
        self.assertEqual(ui.url_text.get(),'')
        ui._switch_page.assert_not_called()

    def test_window_unfocused_delays_prompt_until_focus(self):
        ui,question=self.make_ui(focused=False)
        ui._clipboard_watch_tick()
        question.assert_not_called()
        ui.focus_get=lambda: object()
        ui._clipboard_watch_tick()
        question.assert_called_once()

    def test_existing_entry_not_overwritten(self):
        ui,question=self.make_ui(initial=SHORT)
        ui._clipboard_watch_tick()
        self.assertEqual(ui.url_text.get(),SHORT+'  '+WATCH)

    def test_manual_paste_disables_second_auto_offer(self):
        pasted=' '+WATCH+' '
        class Input:
            def __init__(self): self.value=''
            def get(self): return self.value
            def delete(self,*a):self.value=''
            def insert(self,idx,text):self.value=text
        ui=SimpleNamespace(_clipboard_watcher=ClipboardLinkWatcher(''),
                           clipboard_get=lambda:pasted,url_input=Input(),_url_edited=Mock())
        method=app_method('paste_link', namespace={'re':__import__('re'),
                     'messagebox':Mock()})
        method(ui)
        self.assertEqual(ui.url_input.value,WATCH)
        self.assertEqual(ui._clipboard_watcher.observe(pasted, foreground=True),[])


if __name__=='__main__':unittest.main()
