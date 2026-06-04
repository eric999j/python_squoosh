import os
import zipfile
import threading
from typing import List, Callable, Optional, Set
import image_utils
from models import ImageItem

class AppLogic:
    @staticmethod
    def _get_unique_filename(filename: str, used_names: Set[str]) -> str:
        """避免 ZIP 內同名檔案互相覆蓋。"""
        if filename not in used_names:
            used_names.add(filename)
            return filename

        stem, ext = os.path.splitext(filename)
        suffix = 1
        while True:
            candidate = f"{stem}_{suffix}{ext}"
            if candidate not in used_names:
                used_names.add(candidate)
                return candidate
            suffix += 1

    @staticmethod
    def batch_download(items: List[ImageItem], zip_path: str, 
                       on_complete: Callable[[str, List[str]], None],
                       on_progress: Optional[Callable[[int, int, str], None]] = None):
        """
        批次下載處理
        
        Args:
            items: 圖片項目列表
            zip_path: 輸出 ZIP 檔路徑
            on_complete: 完成回調 (zip_path, errors)
            on_progress: 進度回調 (current, total, current_name) - 可選
        """
        def worker():
            errors = []
            total = len(items)
            used_names: Set[str] = set()

            with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
                for idx, item in enumerate(items):
                    # 回報進度
                    if on_progress:
                        on_progress(idx, total, item.name)
                    
                    fmt = item.format
                    qual = item.effective_quality()
                    name_without_ext = os.path.splitext(item.name)[0]
                    ext = '.' + fmt.lower()
                    out_name = AppLogic._get_unique_filename(f"{name_without_ext}{ext}", used_names)
                    try:
                        # Apply watermark if enabled
                        img_to_save = item.original_pil
                        if item.watermark.enabled:
                            img_to_save = image_utils.apply_watermark(item.original_pil.copy(), item.watermark)

                        output_buffer, _ = image_utils.compress_image_to_buffer(img_to_save, fmt, qual)
                        zf.writestr(out_name, output_buffer.getvalue())
                    except Exception as e:
                        errors.append(f"{item.name}: {e}")

            # 回報最終壓縮階段
            if on_progress:
                on_progress(total, total, "正在壓縮 ZIP...")

            on_complete(zip_path, errors)

        threading.Thread(target=worker, daemon=True).start()

    @staticmethod
    def parse_drop_files(data: str) -> List[str]:
        """解析 TkinterDnD 的拖放資料"""
        raw = data
        paths = []
        cur = ''
        inbrace = False
        for ch in raw:
            if ch == '{':
                inbrace = True
                cur = ''
                continue
            if ch == '}':
                inbrace = False
                paths.append(cur)
                cur = ''
                continue
            if inbrace:
                cur += ch
            else:
                if ch.isspace():
                    if cur:
                        paths.append(cur)
                        cur = ''
                else:
                    cur += ch
        if cur:
            paths.append(cur)
        return [p.strip('"') for p in paths if p.strip('"')]
