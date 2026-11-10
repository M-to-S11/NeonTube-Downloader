"""V1.4 visual regression checks that do not require a desktop display."""
import ast
import hashlib
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent


class V14DesignTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = (ROOT / "app.py").read_text(encoding="utf-8")
        cls.tree = ast.parse(cls.source)
        cls.classes = {
            node.name: node for node in cls.tree.body
            if isinstance(node, ast.ClassDef)
        }

    def test_custom_panels_do_not_shadow_ctk_private_draw(self):
        for name in ("NeonGlassPanel", "GradientButton", "NeonSelectionButton",
                     "NeonGradientProgress", "NeonHero"):
            with self.subTest(widget=name):
                self.assertIn(name, self.classes)
                methods = {
                    method.name for method in self.classes[name].body
                    if isinstance(method, ast.FunctionDef)
                }
                self.assertNotIn("_draw", methods)
        # V1.7 keeps the original CTk frames but removes the hard top light stripe.
        self.assertNotIn("_paint_glass_highlight", self.source)
        self.assertIn("border_width=1", self.source)

    def test_glass_elements_and_round_thumbnails_are_implemented(self):
        self.assertIn("NeonGlassPanel(parent, height=height)", self.source)
        self.assertIn('gradient="gradient_purple.png", icon=""', self.source)
        self.assertIn("output.putalpha(clip)", self.source)
        self.assertIn("ImageDraw.Draw(clip).rounded_rectangle", self.source)
        self.assertIn("self.preview_backplate", self.source)

    def test_no_fabricated_download_data_and_engine_is_untouched(self):
        self.assertIn('if not jobs:', self.source)
        self.assertIn('if not self.history:', self.source)
        v13_engine = Path(__file__).resolve().parents[2] / "NeonTube_Downloader_V1_3" / "NeonTube_Downloader" / "downloader.py"
        if v13_engine.exists():
            self.assertEqual(
                hashlib.sha256((ROOT / "downloader.py").read_bytes()).hexdigest(),
                hashlib.sha256(v13_engine.read_bytes()).hexdigest())

    def test_visual_assets_present(self):
        for filename in ("hero_art.png", "sidebar_art.png", "gradient_hot.png",
                         "gradient_purple.png", "preview_mountain.png"):
            with self.subTest(asset=filename):
                self.assertTrue((ROOT / "assets" / filename).is_file())


if __name__ == "__main__":
    unittest.main()
