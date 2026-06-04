import unittest
from unittest.mock import patch, MagicMock
from PIL import Image
import io
import sys
import os

# 確保可以匯入專案模組
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import image_utils

class TestImageUtils(unittest.TestCase):
    def setUp(self):
        self.img = Image.new('RGBA', (100, 100), color=(255, 0, 0, 128)) # 半透明紅色

    def test_prepare_image_mode_jpeg(self):
        # JPEG 不支援透明度，應該被轉為 RGB
        processed = image_utils.prepare_image_mode(self.img, "JPEG")
        self.assertEqual(processed.mode, "RGB")

    def test_prepare_image_mode_png(self):
        # PNG 支援透明度，應該保持原樣 (或至少不是強制轉 RGB)
        processed = image_utils.prepare_image_mode(self.img, "PNG")
        self.assertEqual(processed.mode, "RGBA")

    def test_quality_to_png_compress_level(self):
        self.assertEqual(image_utils.quality_to_png_compress_level(100), 0)
        self.assertEqual(image_utils.quality_to_png_compress_level(1), 9)
        self.assertEqual(image_utils.quality_to_png_compress_level(50), 5)

    def test_compress_image_to_buffer(self):
        buffer, size = image_utils.compress_image_to_buffer(self.img, "JPEG", 85)
        self.assertIsInstance(buffer, io.BytesIO)
        self.assertGreater(size, 0)
        
        # 驗證 buffer 內容是否為有效的圖片
        test_img = Image.open(buffer)
        self.assertEqual(test_img.format, "JPEG")

    def test_resize_image_contain(self):
        # 原始 100x100，限制在 50x50
        resized, w, h = image_utils.resize_image_contain(self.img, 50, 50)
        self.assertEqual(w, 50)
        self.assertEqual(h, 50)
        self.assertEqual(resized.size, (50, 50))

        # 原始 100x100，限制在 200x200 (不應放大)
        resized, w, h = image_utils.resize_image_contain(self.img, 200, 200)
        self.assertEqual(w, 100)
        self.assertEqual(h, 100)

    @patch('requests.get')
    def test_load_image_from_url(self, mock_get):
        # 模擬網路請求回傳圖片資料
        img_byte_arr = io.BytesIO()
        self.img.save(img_byte_arr, format='PNG')
        
        mock_response = MagicMock()
        mock_response.content = img_byte_arr.getvalue()
        mock_response.status_code = 200
        mock_get.return_value = mock_response
        
        loaded_img = image_utils.load_image_from_url("http://example.com/test.png")
        self.assertEqual(loaded_img.size, (100, 100))

    @patch('requests.get')
    def test_load_image_from_html_og_image(self, mock_get):
        img_byte_arr = io.BytesIO()
        self.img.save(img_byte_arr, format='PNG')

        html_response = MagicMock()
        html_response.status_code = 200
        html_response.headers = {'Content-Type': 'text/html; charset=utf-8'}
        html_response.url = 'https://share.google/demo'
        html_response.text = '<html><head><meta property="og:image" content="https://cdn.example.com/p.png"></head></html>'

        image_response = MagicMock()
        image_response.status_code = 200
        image_response.headers = {'Content-Type': 'image/png'}
        image_response.content = img_byte_arr.getvalue()

        mock_get.side_effect = [html_response, image_response]

        loaded_img = image_utils.load_image_from_url('https://share.google/demo')
        self.assertEqual(loaded_img.size, (100, 100))
        self.assertEqual(mock_get.call_count, 2)

    @patch('requests.get')
    def test_load_image_from_html_img_src_relative(self, mock_get):
        img_byte_arr = io.BytesIO()
        self.img.save(img_byte_arr, format='PNG')

        html_response = MagicMock()
        html_response.status_code = 200
        html_response.headers = {'Content-Type': 'text/html'}
        html_response.url = 'https://example.com/share/page'
        html_response.text = '<html><body><img src="/assets/image.png"></body></html>'

        image_response = MagicMock()
        image_response.status_code = 200
        image_response.headers = {'Content-Type': 'image/png'}
        image_response.content = img_byte_arr.getvalue()

        mock_get.side_effect = [html_response, image_response]

        loaded_img = image_utils.load_image_from_url('https://example.com/share/page')
        self.assertEqual(loaded_img.size, (100, 100))
        called_url = mock_get.call_args_list[1][0][0]
        self.assertEqual(called_url, 'https://example.com/assets/image.png')

if __name__ == '__main__':
    unittest.main()
