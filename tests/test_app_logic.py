import unittest
import sys
import os
import tempfile
import zipfile
from unittest.mock import patch
from PIL import Image

# 確保可以匯入專案模組
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app_logic import AppLogic
from models import ImageItem

class TestAppLogic(unittest.TestCase):
    @staticmethod
    def _run_batch_download_sync(items, zip_path, on_complete, on_progress=None):
        class ImmediateThread:
            def __init__(self, target=None, daemon=None):
                self._target = target

            def start(self):
                self._target()

        with patch('app_logic.threading.Thread', side_effect=ImmediateThread):
            AppLogic.batch_download(items, zip_path, on_complete, on_progress)

    def test_parse_drop_files_single(self):
        data = "C:/path/to/image.jpg"
        result = AppLogic.parse_drop_files(data)
        self.assertEqual(result, ["C:/path/to/image.jpg"])

    def test_parse_drop_files_multiple_with_spaces(self):
        # TkinterDnD 格式：多個檔案且路徑含空白時會用 {} 包起來
        data = "{C:/path with spaces/img1.jpg} {D:/another path/img2.png}"
        result = AppLogic.parse_drop_files(data)
        self.assertEqual(result, ["C:/path with spaces/img1.jpg", "D:/another path/img2.png"])

    def test_parse_drop_files_mixed(self):
        data = "C:/simple.jpg {D:/path with spaces/img.png}"
        result = AppLogic.parse_drop_files(data)
        self.assertEqual(result, ["C:/simple.jpg", "D:/path with spaces/img.png"])

    def test_batch_download_writes_unique_names(self):
        item1 = ImageItem.from_pil(Image.new('RGB', (20, 20), color='red'), name='photo.jpg')
        item2 = ImageItem.from_pil(Image.new('RGB', (20, 20), color='blue'), name='photo.jpg')
        item1.format = "PNG"
        item2.format = "PNG"
        item1.watermark.enabled = False
        item2.watermark.enabled = False

        callback_state = {}
        progress_events = []

        with tempfile.TemporaryDirectory() as tmp:
            zip_path = os.path.join(tmp, "output.zip")

            def on_complete(path, errors):
                callback_state["path"] = path
                callback_state["errors"] = errors

            def on_progress(current, total, current_name):
                progress_events.append((current, total, current_name))

            self._run_batch_download_sync(
                [item1, item2],
                zip_path,
                on_complete=on_complete,
                on_progress=on_progress
            )

            with zipfile.ZipFile(zip_path, 'r') as zf:
                zip_names = sorted(zf.namelist())

        self.assertEqual(zip_names, ["photo.png", "photo_1.png"])
        self.assertEqual(callback_state["path"], zip_path)
        self.assertEqual(callback_state["errors"], [])
        self.assertEqual(progress_events[-1], (2, 2, "正在壓縮 ZIP..."))

    def test_batch_download_collects_item_errors(self):
        item_ok = ImageItem.from_pil(Image.new('RGB', (20, 20), color='green'), name='ok.jpg')
        item_bad = ImageItem.from_pil(Image.new('RGB', (20, 20), color='yellow'), name='bad.jpg')
        item_ok.format = "PNG"
        item_bad.format = "INVALID_FORMAT"
        item_ok.watermark.enabled = False
        item_bad.watermark.enabled = False

        callback_state = {}

        with tempfile.TemporaryDirectory() as tmp:
            zip_path = os.path.join(tmp, "output.zip")

            def on_complete(path, errors):
                callback_state["path"] = path
                callback_state["errors"] = errors

            self._run_batch_download_sync([item_ok, item_bad], zip_path, on_complete=on_complete)

            with zipfile.ZipFile(zip_path, 'r') as zf:
                zip_names = zf.namelist()

        self.assertEqual(zip_names, ["ok.png"])
        self.assertEqual(callback_state["path"], zip_path)
        self.assertEqual(len(callback_state["errors"]), 1)
        self.assertIn("bad.jpg", callback_state["errors"][0])

if __name__ == '__main__':
    unittest.main()
