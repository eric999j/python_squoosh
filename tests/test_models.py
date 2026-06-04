import unittest
from PIL import Image
import sys
import os

# 確保可以匯入專案模組
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from models import ImageItem

class TestImageItem(unittest.TestCase):
    def setUp(self):
        # 建立一個簡單的 10x10 紅色圖片用於測試
        self.img = Image.new('RGB', (10, 10), color='red')
        self.item = ImageItem.from_pil(self.img, name="test_image")

    def test_initialization(self):
        self.assertEqual(self.item.name, "test_image")
        self.assertEqual(self.item.original_pil.size, (10, 10))
        self.assertEqual(self.item.format, "JPEG")
        self.assertEqual(self.item.quality, 85)

    def test_add_history_and_undo(self):
        # 初始狀態沒有歷史
        self.assertEqual(len(self.item.history), 0)
        
        # 模擬修改圖片前儲存歷史
        self.item.add_history()
        self.assertEqual(len(self.item.history), 1)
        
        # 修改圖片
        new_img = Image.new('RGB', (5, 5), color='blue')
        self.item.original_pil = new_img
        
        # 執行 Undo
        success = self.item.undo()
        self.assertTrue(success)
        self.assertEqual(self.item.original_pil.size, (10, 10))
        self.assertEqual(len(self.item.history), 0)

    def test_undo_empty_history(self):
        success = self.item.undo()
        self.assertFalse(success)

    def test_watermark_history_and_undo(self):
        # Initial state
        self.assertEqual(len(self.item.watermark_history), 0)
        self.assertEqual(self.item.watermark.text, "")
        
        # Save state
        self.item.add_watermark_history()
        self.assertEqual(len(self.item.watermark_history), 1)
        
        # Modify watermark
        self.item.watermark.text = "New Watermark"
        
        # Undo
        success = self.item.undo_watermark()
        self.assertTrue(success)
        self.assertEqual(self.item.watermark.text, "")
        self.assertEqual(len(self.item.watermark_history), 0)

    def test_undo_mixed_history(self):
        # 1. Add watermark
        self.item.add_watermark_history()
        self.item.watermark.text = "WM1"
        
        # 2. Crop (Image change)
        self.item.add_history()
        self.item.original_pil = Image.new('RGB', (5, 5), color='blue')
        
        # Undo 2 (Crop)
        success = self.item.undo_latest()
        self.assertTrue(success)
        self.assertEqual(self.item.original_pil.size, (10, 10)) # Back to original size
        self.assertEqual(self.item.watermark.text, "WM1") # Watermark still there
        
        # Undo 1 (Watermark)
        success = self.item.undo_latest()
        self.assertTrue(success)
        self.assertEqual(self.item.watermark.text, "") # Back to empty
        
        # Undo empty
        success = self.item.undo_latest()
        self.assertFalse(success)

    def test_undo_watermark_empty_history(self):
        self.assertEqual(len(self.item.watermark_history), 0)

    def test_undo_watermark_empty_history(self):
        success = self.item.undo_watermark()
        self.assertFalse(success)

    def test_effective_quality(self):
        self.item.quality = 72
        self.item.convert_only = False
        self.assertEqual(self.item.effective_quality(), 72)

        self.item.convert_only = True
        self.assertEqual(self.item.effective_quality(), 100)

    def test_build_process_key_changes_with_settings(self):
        key1 = self.item.build_process_key()
        self.item.quality = 60
        key2 = self.item.build_process_key()
        self.assertNotEqual(key1, key2)

        self.item.watermark.text = "wm"
        key3 = self.item.build_process_key()
        self.assertNotEqual(key2, key3)

    def test_process_cache_roundtrip(self):
        key = self.item.build_process_key()
        img = Image.new('RGB', (6, 6), color='green')
        self.item.set_cached_process(key, img, 1234)

        cached = self.item.get_cached_process(key)
        self.assertIsNotNone(cached)
        cached_img, cached_size = cached
        self.assertEqual(cached_size, 1234)
        self.assertEqual(cached_img.size, (6, 6))

if __name__ == '__main__':
    unittest.main()
