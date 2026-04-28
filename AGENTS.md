# Agent Instructions — Python Squoosh

## Project Overview

桌面圖片壓縮轉檔工具，使用 Tkinter GUI，支援 JPEG/PNG/WEBP 壓縮、格式轉換、裁切、浮水印、批次處理。詳見 [README.md](README.md)。

## Quick Commands

```bash
# 安裝依賴
pip install -r requirements.txt

# 啟動應用
python main.py

# 執行測試
python -m unittest discover tests
```

## Architecture

MVC-like 分層架構：

| 模組 | 職責 |
|------|------|
| `main.py` | 入口點，初始化 TkinterDnD root |
| `gui.py` | UI 層：所有 Tkinter 元件、事件處理、Canvas 繪製 |
| `app_logic.py` | 業務邏輯：批次下載、ZIP 匯出、拖放檔案解析 |
| `models.py` | 資料模型：`ImageItem`、`WatermarkSettings` (dataclass) |
| `image_utils.py` | 圖片處理：壓縮、載入、浮水印、濾鏡、特效 |
| `constants.py` | 全域常數：主題色彩、視窗大小、格式清單 |

### Key Data Flow

1. 使用者透過 GUI 載入圖片 → 建立 `ImageItem` (from_path / from_pil)
2. 調整參數 → `gui.py` debounce 200ms 後呼叫 `image_utils.compress_image_to_buffer()`
3. 匯出 → `image_utils.save_image()` + 選擇性套用浮水印

## Code Conventions

- **Type hints**: 所有函式簽名都使用型別提示
- **Naming**: PascalCase (類別)、snake_case (函式/變數)、UPPER_CASE (常數)
- **Dataclasses**: 資料模型使用 `@dataclass`，搭配 `field(default_factory=...)` 處理可變預設值
- **Factory methods**: `ImageItem.from_path()`, `ImageItem.from_pil()` 用於建構
- **Duck typing**: `image_utils.apply_watermark()` 的 `settings` 參數使用 duck typing 避免循環匯入

## Important Patterns

### Parallel Undo History
`ImageItem` 維護**雙軌歷史**：`history` (圖片編輯) + `watermark_history` (浮水印)，透過 `action_log` 協調順序。上限 30 步。修改 undo/redo 時必須同時考慮兩條軌道。

### Debounced Processing
`gui.py` 中 `schedule_process_image()` 使用 `root.after()` + `after_cancel()` 實現 200ms debounce，避免滑桿拖動時頻繁壓縮。

### Threading
`app_logic.py` 的批次操作使用 `threading.Thread(daemon=True)`。測試中以 `ImmediateThread` mock 替代，使非同步邏輯可同步測試。

## Testing

- 框架：`unittest` (標準庫)
- 測試目錄：`tests/`
- 慣例：大量使用 `unittest.mock.patch` mock 網路與檔案 I/O
- 測試圖片：測試中以 `Image.new("RGB", (100, 100), "red")` 在記憶體產生，不依賴外部檔案
- 新增功能時，在 `tests/` 下建立對應測試檔案，遵循 `test_<module>.py` 命名

## Dependencies

核心依賴見 [requirements.txt](requirements.txt)：Pillow、requests、tkinterdnd2。
GUI 使用標準庫 `tkinter`，測試使用標準庫 `unittest`。

## Pitfalls

- `gui.py` 是最大的檔案，包含完整的 UI 邏輯；修改 GUI 時注意 Canvas 的多種模式 (crop/resize/zoom) 之間的狀態切換
- PNG 的「品質」參數實際上映射為壓縮等級 (反向)：高品質 = 低壓縮，見 `quality_to_png_compress_level()`
- 浮水印在「僅轉檔」模式下仍會套用
- Windows 剪貼簿操作使用 `ctypes`，跨平台時需注意
