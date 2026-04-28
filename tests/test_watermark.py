import unittest
from unittest.mock import patch, MagicMock
from PIL import Image, ImageDraw
import sys
import os

# Ensure project modules can be imported
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import image_utils
from models import WatermarkSettings

class TestWatermark(unittest.TestCase):
    def setUp(self):
        self.img = Image.new('RGB', (200, 200), color='white')
        self.settings = WatermarkSettings()

    def test_watermark_disabled(self):
        self.settings.enabled = False
        self.settings.text = "Test"
        result = image_utils.apply_watermark(self.img, self.settings)
        # Should be identical to original if disabled
        self.assertEqual(list(result.getdata()), list(self.img.getdata()))

    def test_text_watermark(self):
        self.settings.enabled = True
        self.settings.text = "Test"
        self.settings.text_color = "#000000" # Black
        self.settings.text_opacity = 255
        
        # We don't mock truetype here because load_default() might use it internally
        # and we don't want to break load_default().
        # On Windows, Arial should exist. If not, it falls back to load_default()
        # which should work unless truetype is broken globally.
        
        result = image_utils.apply_watermark(self.img, self.settings)
        
        # Check if image is modified (not white anymore)
        # Since we drew black text on white image
        pixels = list(result.getdata())
        self.assertNotEqual(pixels, list(self.img.getdata()))
        
        # Check if some pixels are not white (255, 255, 255)
        has_non_white = any(p != (255, 255, 255) for p in pixels)
        self.assertTrue(has_non_white)

    def test_image_watermark(self):
        self.settings.enabled = True
        self.settings.text = "" # Disable text
        
        # Create a dummy watermark image
        wm_path = "test_wm.png"
        wm_img = Image.new('RGBA', (50, 50), color='blue')
        wm_img.save(wm_path)
        
        try:
            self.settings.image_path = wm_path
            self.settings.image_opacity = 255
            
            result = image_utils.apply_watermark(self.img, self.settings)
            
            # Check if image is modified
            pixels = list(result.getdata())
            self.assertNotEqual(pixels, list(self.img.getdata()))
            
            # Check for blue pixels (approximate due to resizing/blending)
            # But since opacity is 255 and it's on white, we should see blue-ish pixels
            # Blue is (0, 0, 255)
            has_blueish = any(p[2] > 200 and p[0] < 50 for p in pixels)
            self.assertTrue(has_blueish)
            
        finally:
            if os.path.exists(wm_path):
                os.remove(wm_path)

    def test_both_watermarks(self):
        self.settings.enabled = True
        self.settings.text = "Test"
        
        # Create a dummy watermark image
        wm_path = "test_wm_both.png"
        wm_img = Image.new('RGBA', (50, 50), color='green')
        wm_img.save(wm_path)
        
        try:
            self.settings.image_path = wm_path
            
            # Should run without error
            result = image_utils.apply_watermark(self.img, self.settings)
            
            pixels = list(result.getdata())
            self.assertNotEqual(pixels, list(self.img.getdata()))
            
        finally:
            if os.path.exists(wm_path):
                os.remove(wm_path)

if __name__ == '__main__':
    unittest.main()
