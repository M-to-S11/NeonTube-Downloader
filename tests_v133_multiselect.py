"""V1.33 regression tests for bulk selection and queued downloads (no network)."""
from __future__ import annotations

import re
import tempfile
import unittest
from pathlib import Path
from types import MethodType, SimpleNamespace
from unittest.mock import Mock
from urllib.parse import urlparse

from downloader import DownloadJob
from search_batch import selected_video_links
from tests_v130_search_ui import app_method

A = 'dQw4w9WgXcQ'
B = '9bZkp7q19f0'
C = 'J---aiyznGQ'
url = lambda video_id: 'https://www.youtube.com/watch?v=' + video_id
video = lambda video_id: {'id':video_id,'url':url(video_id),'title':'Test'}

class FakeVar:
    def __init__(self, value=False): self.value = value
    def get(self): return self.value
    def set(self, value): self.value = value


def make_ui(items=None):
    items = items or [video(A), video(B), video(C)]
    return SimpleNamespace(
        search_results=list(items), search_selected_ids=set(),
        search_select_vars={v['id']:FakeVar() for v in items},
        search_result_frames={v['id']:Mock() for v in items},
        search_selected_count=Mock(), search_batch_button=Mock(),
        search_select_all_button=Mock(), search_clear_button=Mock())


def bind_select(ui):
    for name in ['_toggle_search_selection','_select_all_search_results',
                 '_clear_search_selection','_update_search_selection_controls',
                 '_enqueue_selected_search_results']:
        setattr(ui, name, MethodType(app_method(name,
                       namespace={'GREEN':'#0f0', 'MUTED':'#888',
                                  'selected_video_links':selected_video_links}),ui))
    return ui


class SelectedVideoLinksTests(unittest.TestCase):
    def test_only_selected_current_results_in_display_order(self):
        links = selected_video_links([video(A),video(B),video(C)], [C,A,'UNKNOWN'])
        self.assertEqual(links, [url(A), url(C)])

    def test_repeated_results_do_not_create_duplicate_queue_jobs(self):
        links = selected_video_links([video(A),video(A),video(B)], [A,B])
        self.assertEqual(links, [url(A),url(B)])

    def test_never_follow_untrusted_urls_or_stale_ids(self):
        results = [dict(video(A), url='https://evil.example/track'),
                   {'id':'BAD', 'url':'https://evil.example'},
                   {'id':'<script>', 'url':'https://evil.example'}, None]
        self.assertEqual(selected_video_links(results, [A,'BAD','<script>',C]),[url(A)])
        self.assertEqual(selected_video_links([], [A]),[])


class SelectionControlsTests(unittest.TestCase):
    def test_single_checkbox_toggles_selection_count_and_border(self):
        ui=bind_select(make_ui())
        ui.search_select_vars[A].set(True)
        ui._toggle_search_selection(A)
        self.assertEqual(ui.search_selected_ids, {A})
        ui.search_selected_count.configure.assert_called_with(text='1 Videos ausgewählt',text_color='#0f0')
        ui.search_result_frames[A].configure.assert_called_with(border_color='#9c4cf4')
        ui.search_batch_button.configure.assert_called_with(text='Zur Warteschlange (1)',state='normal')
        ui.search_select_vars[A].set(False)
        ui._toggle_search_selection(A)
        self.assertEqual(ui.search_selected_ids,set())
        ui.search_batch_button.configure.assert_called_with(text='Zur Warteschlange (0)',state='disabled')

    def test_select_all_and_clear_keep_checkboxes_in_sync(self):
        ui=bind_select(make_ui())
        ui._select_all_search_results()
        self.assertEqual(ui.search_selected_ids,{A,B,C})
        self.assertTrue(all(v.get() for v in ui.search_select_vars.values()))
        ui._clear_search_selection()
        self.assertEqual(ui.search_selected_ids,set())
        self.assertTrue(all(not v.get() for v in ui.search_select_vars.values()))

    def test_new_page_preserves_old_selection(self):
        ui=bind_select(make_ui([video(A),video(B)]))
        ui.search_selected_ids.add(A)
        ui.search_results.extend([video(C)])  # as after next-page API response
        ui.search_select_vars[C]=FakeVar()
        ui.search_result_frames[C]=Mock()
        ui._update_search_selection_controls()
        self.assertEqual(ui.search_selected_ids,{A})
        ui._select_all_search_results()
        self.assertEqual(ui.search_selected_ids,{A,B,C})

    def test_stale_selection_dropped(self):
        ui=bind_select(make_ui([video(A)]))
        ui.search_selected_ids={A,B}
        ui._update_search_selection_controls()
        self.assertEqual(ui.search_selected_ids,{A})

    def test_batch_calls_existing_path_once_and_resets(self):
        ui=bind_select(make_ui())
        ui.search_selected_ids={A,C}
        ui._use_search_link=Mock()
        ui._enqueue_selected_search_results()
        ui._use_search_link.assert_called_once_with(url(A)+'  '+url(C),download=True)
        self.assertEqual(ui.search_selected_ids,set())

    def test_empty_selection_does_not_call_download(self):
        ui=bind_select(make_ui())
        ui._use_search_link=Mock()
        ui._enqueue_selected_search_results()
        ui._use_search_link.assert_not_called()

    def test_multi_select_queues_two_real_jobs_in_same_manager(self):
        # Run genuine app._enqueue_selected_search_results -> _use_search_link
        # -> start_downloads with mocked IO and no background network threads.
        class NoNetworkThread:
            def __init__(self, **kwargs): pass
            def start(self): pass
        class Input:
            def __init__(self, var): self.var=var
            def get(self): return self.var.get()
            def delete(self,*args): self.var.set('')
        with tempfile.TemporaryDirectory() as tmp:
            ui=bind_select(make_ui())
            ui.search_selected_ids={A,C}
            ui.url_text=FakeVar('')
            ui.url_input=Input(ui.url_text)
            ui._switch_page=Mock()
            ui._url_edited=Mock()
            ui._parse_links=lambda data: list(dict.fromkeys(re.findall(r'https?://[^\s,;<>"\']+',data)))
            ui.output_dir=SimpleNamespace(get=lambda:tmp)
            ui.mode=SimpleNamespace(get=lambda:'Video (MP4)')
            ui.quality=SimpleNamespace(get=lambda:'1080p')
            ui.audio_format=SimpleNamespace(get=lambda:'MP3')
            ui.playlist=SimpleNamespace(get=lambda:False)
            ui.manager=SimpleNamespace(add=Mock())
            ui._log_event=Mock()
            ui._metadata_worker=Mock()
            ui._refresh_progress=Mock()
            ui.after_idle=Mock()
            ui.focus_set=Mock()
            start = app_method('start_downloads', namespace={
                'messagebox':Mock(),'yt_dlp':object(),'Path':Path,
                'urlparse':urlparse,'DownloadJob':DownloadJob,
                'threading':SimpleNamespace(Thread=NoNetworkThread)})
            ui.start_downloads = MethodType(start,ui)
            ui._use_search_link=MethodType(app_method('_use_search_link'),ui)
            ui._enqueue_selected_search_results()
            added=[x.args[0] for x in ui.manager.add.call_args_list]
            self.assertEqual([x.url for x in added],[url(A),url(C)])
            self.assertEqual([x.mode for x in added],['Video (MP4)']*2)
            self.assertEqual([x.quality for x in added],['1080p']*2)
            self.assertEqual(ui.search_selected_ids,set())

    def test_new_search_clears_selection_but_pagination_does_not(self):
        threads=[]
        class NoNetworkThread:
            def __init__(self, **kwargs): threads.append(kwargs)
            def start(self): pass
        execute=app_method('_search_execute',namespace={'threading':SimpleNamespace(Thread=NoNetworkThread),'MUTED':'muted'})
        ui=bind_select(make_ui([video(A)]))
        ui.search_selected_ids.add(A)
        ui.search_text=SimpleNamespace(get=lambda:'Suchen')
        ui.youtube_api_key='not-an-actual-key'
        ui.search_status=Mock()
        ui.search_input=Mock()
        ui.search_more=Mock()
        ui.search_query_text='Suchen'
        ui.search_counter=0
        ui.search_generation=1
        ui.search_list=SimpleNamespace(winfo_children=lambda:[])
        ui.search_result_labels={}
        ui.search_favorite_buttons={}
        ui.search_result_cards=[]
        ui.search_result_titles=[]
        ui._search_layout_columns=0
        ui._search_last_wrap=0
        ui.search_next_page='next'
        ui.search_page_size=SimpleNamespace(get=lambda:'12')
        ui._search_worker=Mock()
        execute(ui,page_token='next')
        self.assertEqual(ui.search_selected_ids,{A})
        execute(ui,page_token='')
        self.assertEqual(ui.search_selected_ids,set())

    def test_unchanged_assets(self):
        import zipfile
        archive=Path(__file__).resolve().parents[2] / 'NeonTube_Downloader_V1_32_0_Intelligente_Download_Reparatur.zip'
        if not archive.exists():
            self.skipTest('source archive is not distributed')
        with zipfile.ZipFile(archive) as source:
            for p in (Path(__file__).parent/'assets').iterdir():
                self.assertEqual(p.read_bytes(),source.read('NeonTube_Downloader/assets/'+p.name),p.name)


if __name__=='__main__':
    unittest.main()
