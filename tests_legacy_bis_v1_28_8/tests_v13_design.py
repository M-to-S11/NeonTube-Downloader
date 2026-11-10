"""Regression checks for the updated header/layout without a GUI session."""
import ast
import unittest
from pathlib import Path

APP = Path(__file__).with_name('app.py')

class DesignTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = APP.read_text(encoding='utf-8')
        cls.tree = ast.parse(cls.source)
        cls.classes = {node.name: node for node in cls.tree.body if isinstance(node, ast.ClassDef)}

    def test_hero_is_responsive_and_does_not_override_ctk_draw(self):
        self.assertIn('NeonHero', self.classes)
        methods = {node.name for node in self.classes['NeonHero'].body
                   if isinstance(node, ast.FunctionDef)}
        self.assertIn('_paint_banner', methods)
        self.assertNotIn('_draw', methods)
        self.assertIn('<Configure>', self.source)

    def test_empty_cards_are_purposeful_and_not_faked(self):
        self.assertIn('Deine Warteschlange ist leer', self.source)
        self.assertIn('Noch kein Verlauf', self.source)
        self.assertIn('if not jobs:', self.source)
        self.assertIn('if not self.history:', self.source)

    def test_functionality_retained(self):
        app_methods = {node.name for node in self.classes['NeonTubeApp'].body
                       if isinstance(node, ast.FunctionDef)}
        for method in ('start_downloads', 'pause_selected', 'cancel_selected',
                       'clear_queue', 'remove_selected', 'open_settings',
                       '_render_history_summary', '_apply_profile',
                       '_refresh_progress'):
            with self.subTest(method=method):
                self.assertIn(method, app_methods)

if __name__ == '__main__':
    unittest.main()
