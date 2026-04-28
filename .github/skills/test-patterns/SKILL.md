---
name: test-patterns
description: 'Generate unit tests following project conventions: unittest framework, in-memory Pillow images, ImmediateThread for async, mock patterns for I/O. Use when writing or updating tests.'
argument-hint: 'Module or function to test, e.g. image_utils.apply_filter'
---

# Test Patterns for Python Squoosh

## When to Use
- Writing new test files for added features
- Adding test cases to existing test files
- Verifying a bug fix with a regression test

## Run Tests

```bash
python -m unittest discover tests
```

## File & Class Conventions

1. **One test file per module**: `tests/test_<module>.py`
2. **Class per logical group**: `class Test<Feature>(unittest.TestCase)`
3. **Every test file** starts with the sys.path preamble:

```python
import unittest
from PIL import Image
import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
```

## Core Patterns

### 1. In-Memory Test Images (No External Files)

Always generate test images in code. Never depend on external image files.

```python
def setUp(self):
    self.img = Image.new('RGB', (100, 100), color='red')
```

For transparency tests use RGBA:
```python
self.img = Image.new('RGBA', (100, 100), color=(255, 0, 0, 128))
```

### 2. ImmediateThread — Synchronous Testing of Threaded Code

`app_logic.py` uses `threading.Thread(daemon=True)`. Tests replace it with `ImmediateThread` to run synchronously:

```python
from unittest.mock import patch

class ImmediateThread:
    def __init__(self, target=None, daemon=None):
        self._target = target
    def start(self):
        self._target()

# Usage: define a helper that patches threading
@staticmethod
def _run_batch_download_sync(items, zip_path, on_complete, on_progress=None):
    with patch('app_logic.threading.Thread', side_effect=ImmediateThread):
        AppLogic.batch_download(items, zip_path, on_complete, on_progress)
```

### 3. Mock Network Calls

Use `@patch('requests.get')` and return image bytes:

```python
@patch('requests.get')
def test_load_image_from_url(self, mock_get):
    img_byte_arr = io.BytesIO()
    self.img.save(img_byte_arr, format='PNG')

    mock_response = MagicMock()
    mock_response.content = img_byte_arr.getvalue()
    mock_response.status_code = 200
    mock_get.return_value = mock_response

    loaded_img = image_utils.load_image_from_url("http://example.com/test.png")
    self.assertEqual(loaded_img.size, (100, 100))
```

### 4. Mock File I/O — Verify Save Parameters

Patch `PIL.Image.Image.save` and assert kwargs:

```python
@patch('PIL.Image.Image.save')
def test_save_jpeg(self, mock_save):
    image_utils.save_image_to_file(self.img, "out.jpg", "JPEG", 85)
    args, kwargs = mock_save.call_args
    self.assertEqual(kwargs['format'], 'JPEG')
    self.assertEqual(kwargs['quality'], 85)
```

### 5. Temporary Files — Always Clean Up

When a test must write to disk (e.g. watermark image), use `try/finally` or `tempfile`:

```python
import tempfile

# Option A: try/finally
wm_path = "test_wm.png"
wm_img = Image.new('RGBA', (50, 50), color='blue')
wm_img.save(wm_path)
try:
    # ... test logic ...
finally:
    if os.path.exists(wm_path):
        os.remove(wm_path)

# Option B: tempfile (preferred for batch tests)
with tempfile.TemporaryDirectory() as tmp:
    zip_path = os.path.join(tmp, "output.zip")
    # ... test logic ...
```

### 6. Callback / State Capture

For async-style APIs that report results via callbacks, capture state in a dict:

```python
callback_state = {}

def on_complete(path, errors):
    callback_state["path"] = path
    callback_state["errors"] = errors

self._run_batch_download_sync(items, zip_path, on_complete=on_complete)

self.assertEqual(callback_state["path"], zip_path)
self.assertEqual(callback_state["errors"], [])
```

### 7. ImageItem Test Fixtures

Use factory methods, then configure format/watermark as needed:

```python
item = ImageItem.from_pil(Image.new('RGB', (20, 20), color='red'), name='photo.jpg')
item.format = "PNG"
item.watermark.enabled = False
```

## Checklist Before Submitting Tests

- [ ] No external image files — all generated with `Image.new()`
- [ ] Network and file I/O mocked with `unittest.mock.patch`
- [ ] Threaded code wrapped with `ImmediateThread`
- [ ] Temporary files cleaned up (try/finally or tempfile)
- [ ] Test file follows `test_<module>.py` naming
- [ ] `python -m unittest discover tests` passes
