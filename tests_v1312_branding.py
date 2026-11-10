"""Offline brand identity regression checks for version 1.31.2."""
import unittest
from pathlib import Path
from PIL import Image

ROOT = Path(__file__).resolve().parent
A = ROOT / 'assets'

class BrandingTests(unittest.TestCase):
    def test_logo_asset_and_name(self):
        src = (ROOT / 'app.py').read_text('utf8')
        self.assertIn('neontube_logo.png', src)
        self.assertNotIn('youtube_logo.png', src)
        self.assertIn('APP_NAME = "NeonTube Downloader"', src)
        self.assertFalse((A / 'youtube_logo.png').exists())
    def test_hero_is_a_clean_native_asset_not_overlaid_old_logo(self):
        with Image.open(A / 'hero_art.png') as img:
            self.assertGreaterEqual(img.width, 1200)
            self.assertGreaterEqual(img.height, 250)
            # Unlike old YouTube icon image, no red rectangular icon base.
            rgb = img.convert('RGB')
            count = 0
            for r,g,b in rgb.resize((180,35)).getdata():
                if r > 215 and g < 60 and b < 130:
                    count += 1
            self.assertEqual(count, 0, 'Hero contains a red icon-like patch')
    def test_windows_icon_is_user_logo(self):
        with Image.open(A / 'app.ico') as icon, Image.open(A / 'neontube_logo.png') as png:
            self.assertEqual(icon.size, (256,256))
            self.assertEqual(png.size, (256,256))
            self.assertEqual(icon.convert('RGBA').tobytes(), png.convert('RGBA').tobytes())
    def test_asset_regeneration_preserves_our_logo_and_hero(self):
        script=(ROOT / 'make_assets.py').read_text('utf8')
        self.assertNotIn("hero.save(out/'hero_art.png')", script)
        self.assertNotIn("logo.save(out/'youtube_logo.png')", script)

if __name__ == '__main__': unittest.main()
