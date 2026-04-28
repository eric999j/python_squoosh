import unittest
from unittest.mock import patch, MagicMock
from PIL import Image
import os
import sys

# 確保可以匯入專案模組
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import image_utils

class TestImageUtilsExtended(unittest.TestCase):
    def setUp(self):
        self.img = Image.new('RGB', (100, 100), color='white')

    @patch('image_utils.prepare_image_mode')
    @patch('PIL.Image.Image.save')
    def test_save_image_to_file_jpeg(self, mock_save, mock_prepare):
        # Setup mock behavior
        mock_prepare.return_value = self.img
        
        # Execute
        image_utils.save_image_to_file(self.img, "test.jpg", "JPEG", 85)
        
        # Verify
        mock_prepare.assert_called_once()
        mock_save.assert_called_once()
        args, kwargs = mock_save.call_args
        self.assertEqual(kwargs['format'], 'JPEG')
        self.assertEqual(kwargs['quality'], 85)
        self.assertTrue(kwargs['optimize'])

    @patch('image_utils.quality_to_png_compress_level')
    @patch('PIL.Image.Image.save')
    def test_save_image_to_file_png(self, mock_save, mock_q_map):
        mock_q_map.return_value = 5
        image_utils.save_image_to_file(self.img, "test.png", "PNG", 50)
        
        mock_save.assert_called_once()
        args, kwargs = mock_save.call_args
        self.assertEqual(kwargs['format'], 'PNG')
        self.assertEqual(kwargs['compress_level'], 5)

if __name__ == '__main__':
    unittest.main()
