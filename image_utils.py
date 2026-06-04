from PIL import Image, ImageDraw, ImageFont, ImageEnhance
import io
import requests
import sys
import ctypes
import os
import re
import html
from functools import lru_cache
from urllib.parse import urljoin
from typing import Tuple, Optional, Union


def _resolve_watermark_position(position: str, width: int, height: int, mark_width: int, mark_height: int, margin: int) -> Tuple[int, int]:
    if position == "top-left":
        return margin, margin
    if position == "top-right":
        return width - mark_width - margin, margin
    if position == "bottom-left":
        return margin, height - mark_height - margin
    if position == "bottom-right":
        return width - mark_width - margin, height - mark_height - margin
    return (width - mark_width) // 2, (height - mark_height) // 2


@lru_cache(maxsize=32)
def _load_truetype_font(font_path: str, font_size: int):
    return ImageFont.truetype(font_path, font_size)


def _get_font_for_watermark(font_size: int):
    font_path = "arial.ttf"
    if sys.platform == "win32":
        font_path = "C:\\Windows\\Fonts\\arial.ttf"
    try:
        return _load_truetype_font(font_path, font_size)
    except IOError:
        return ImageFont.load_default()


@lru_cache(maxsize=16)
def _load_watermark_image_cached(image_path: str, modified_time: float) -> Image.Image:
    with Image.open(image_path) as wm_img:
        return wm_img.convert("RGBA").copy()

def load_image_from_path(path: str) -> Image.Image:
    """從檔案路徑載入圖片"""
    # 移除可能的引號 (Windows Copy Path)
    path = path.strip('"')
    return Image.open(path)


_REQUEST_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36",
    "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
}


def _extract_image_url_from_html(page_url: str, html_text: str) -> Optional[str]:
    patterns = [
        r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)["\']',
        r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:image["\']',
        r'<meta[^>]+name=["\']twitter:image(?::src)?["\'][^>]+content=["\']([^"\']+)["\']',
        r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+name=["\']twitter:image(?::src)?["\']',
        r'<link[^>]+rel=["\']image_src["\'][^>]+href=["\']([^"\']+)["\']',
        r'<img[^>]+src=["\']([^"\']+)["\']',
    ]

    for pattern in patterns:
        m = re.search(pattern, html_text, flags=re.IGNORECASE)
        if not m:
            continue
        candidate = html.unescape(m.group(1)).strip()
        if not candidate:
            continue
        candidate = urljoin(page_url, candidate)
        lower = candidate.lower()
        if lower.startswith("data:") or lower.startswith("javascript:"):
            continue
        return candidate
    return None


def _download_image_bytes(url: str) -> bytes:
    response = requests.get(url, timeout=10, headers=_REQUEST_HEADERS, allow_redirects=True)
    response.raise_for_status()

    content_type = (response.headers.get("Content-Type") or "").lower()
    if content_type.startswith("image/"):
        return response.content

    if "html" in content_type:
        html_text = response.text
        image_url = _extract_image_url_from_html(response.url, html_text)
        if image_url:
            image_response = requests.get(
                image_url,
                timeout=10,
                headers={**_REQUEST_HEADERS, "Referer": response.url},
                allow_redirects=True,
            )
            image_response.raise_for_status()
            image_content_type = (image_response.headers.get("Content-Type") or "").lower()
            if image_content_type.startswith("image/"):
                return image_response.content

    raise RuntimeError("網址內容不是可解析的圖片，請提供直接圖片連結或可公開預覽的分享頁。")

def load_image_from_url(url: str) -> Image.Image:
    """從網址下載並載入圖片"""
    image_bytes = _download_image_bytes(url)
    image_data = io.BytesIO(image_bytes)
    img = Image.open(image_data)
    img.load()
    return img

def get_image_size(img: Image.Image) -> int:
    """估算圖片原始大小 (嘗試以原格式儲存)"""
    img_byte_arr = io.BytesIO()
    try:
        fmt = img.format if img.format else 'PNG'
        img.save(img_byte_arr, format=fmt)
        return img_byte_arr.tell()
    except Exception:
        return 0

def prepare_image_mode(img: Image.Image, target_format: str) -> Image.Image:
    """根據目標格式處理圖片模式 (如透明度處理)"""
    process_img = img.copy()
    if target_format == "JPEG":
        # JPEG 不支援透明，需轉為 RGB 白色背景
        if process_img.mode in ('RGBA', 'LA'):
            background = Image.new('RGB', process_img.size, (255, 255, 255))
            background.paste(process_img, mask=process_img.split()[-1])
            process_img = background
        elif process_img.mode != 'RGB':
            process_img = process_img.convert('RGB')
    return process_img

def quality_to_png_compress_level(quality: int) -> int:
    """把 1-100 的 quality 映射到 Pillow 的 compress_level (0-9)."""
    q = max(1, min(100, int(quality)))
    level = int(round((100 - q) * 9 / 99))
    return max(0, min(9, level))

def _save_image_internal(img: Image.Image, destination: Union[str, io.BytesIO], target_format: str, quality: int):
    """內部統一的儲存邏輯"""
    process_img = prepare_image_mode(img, target_format)
    try:
        if target_format == "JPEG":
            process_img.save(destination, format="JPEG", quality=quality, optimize=True)
        elif target_format == "PNG":
            compress_level = quality_to_png_compress_level(quality)
            process_img.save(destination, format="PNG", optimize=True, compress_level=compress_level)
        elif target_format == "WEBP":
            try:
                process_img.save(destination, format="WEBP", quality=quality, method=6)
            except TypeError:
                process_img.save(destination, format="WEBP", quality=quality)
        else:
            process_img.save(destination, format=target_format)
    except Exception as e:
        raise RuntimeError(f"無法以 {target_format} 格式儲存圖片: {e}") from e

def compress_image_to_buffer(img: Image.Image, target_format: str, quality: int) -> Tuple[io.BytesIO, int]:
    """壓縮圖片並回傳 Buffer 與大小"""
    buffer = io.BytesIO()
    _save_image_internal(img, buffer, target_format, quality)
    size = buffer.tell()
    buffer.seek(0)
    return buffer, size

def save_image_to_file(img: Image.Image, path: str, target_format: str, quality: int):
    """將圖片儲存至檔案"""
    _save_image_internal(img, path, target_format, quality)

def resize_image_contain(img: Image.Image, max_width: int, max_height: int) -> Tuple[Image.Image, int, int]:
    """等比例縮放圖片以適應顯示區域"""
    w, h = img.size
    ratio = min(max_width / w, max_height / h)
    if ratio < 1:
        new_w, new_h = int(w * ratio), int(h * ratio)
        return img.resize((new_w, new_h), Image.Resampling.LANCZOS), new_w, new_h
    return img.copy(), w, h

def copy_to_clipboard(img: Image.Image):
    """將圖片複製到剪貼簿 (目前僅支援 Windows)"""
    if sys.platform != 'win32':
        # 非 Windows 平台暫不支援或需其他實作
        return False

    try:
        # 轉換為 RGB 並儲存為 BMP 格式
        # BMP 檔頭前 14 bytes 是 BITMAPFILEHEADER，之後是 DIB 資料
        output = io.BytesIO()
        img.convert("RGB").save(output, "BMP")
        data = output.getvalue()[14:]
        output.close()

        CF_DIB = 8
        GMEM_MOVEABLE = 0x0002
        GMEM_ZEROINIT = 0x0040
        
        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32
        
        # 定義參數與回傳型別，避免 64-bit 系統下指標被截斷
        user32.OpenClipboard.argtypes = [ctypes.c_void_p]
        user32.OpenClipboard.restype = ctypes.c_bool
        
        user32.EmptyClipboard.argtypes = []
        user32.EmptyClipboard.restype = ctypes.c_bool
        
        user32.SetClipboardData.argtypes = [ctypes.c_uint, ctypes.c_void_p]
        user32.SetClipboardData.restype = ctypes.c_void_p
        
        user32.CloseClipboard.argtypes = []
        user32.CloseClipboard.restype = ctypes.c_bool
        
        kernel32.GlobalAlloc.argtypes = [ctypes.c_uint, ctypes.c_size_t]
        kernel32.GlobalAlloc.restype = ctypes.c_void_p
        
        kernel32.GlobalLock.argtypes = [ctypes.c_void_p]
        kernel32.GlobalLock.restype = ctypes.c_void_p
        
        kernel32.GlobalUnlock.argtypes = [ctypes.c_void_p]
        kernel32.GlobalUnlock.restype = ctypes.c_bool

        # 嘗試開啟剪貼簿 (重試機制)
        opened = False
        for _ in range(5):
            if user32.OpenClipboard(None):
                opened = True
                break
            import time
            time.sleep(0.1)
            
        if not opened:
            print("Failed to open clipboard")
            return False
            
        try:
            user32.EmptyClipboard()
            
            # 分配全域記憶體
            h_mem = kernel32.GlobalAlloc(GMEM_MOVEABLE | GMEM_ZEROINIT, len(data))
            if not h_mem:
                print("GlobalAlloc failed")
                return False
                
            # 鎖定記憶體並寫入資料
            p_mem = kernel32.GlobalLock(h_mem)
            if not p_mem:
                print("GlobalLock failed")
                return False
                
            ctypes.memmove(p_mem, data, len(data))
            kernel32.GlobalUnlock(h_mem)
            
            # 設定剪貼簿資料
            if not user32.SetClipboardData(CF_DIB, h_mem):
                print("SetClipboardData failed")
                return False
                
            return True
        finally:
            user32.CloseClipboard()
    except Exception as e:
        print(f"Clipboard error: {e}")
        return False

def hex_to_rgb(hex_color: str) -> Tuple[int, int, int]:
    """將 Hex 顏色字串轉換為 RGB Tuple"""
    hex_color = hex_color.lstrip('#')
    if len(hex_color) == 3:
        hex_color = ''.join([c*2 for c in hex_color])
    return tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))

def apply_watermark(img: Image.Image, settings) -> Image.Image:
    """
    對圖片應用浮水印
    settings: WatermarkSettings 物件 (避免循環引用，這裡使用 duck typing)
    """
    if not settings.enabled:
        return img

    # 建立一個與原圖大小相同的透明圖層
    watermark_layer = Image.new('RGBA', img.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(watermark_layer)
    
    w, h = img.size
    margin = settings.margin
    
    if settings.text:
        text = settings.text
        font_size = settings.font_size
        font = _get_font_for_watermark(font_size)
            
        # 計算文字大小
        bbox = draw.textbbox((0, 0), text, font=font)
        text_w = bbox[2] - bbox[0]
        text_h = bbox[3] - bbox[1]
        
        # 計算位置
        x, y = _resolve_watermark_position(settings.position, w, h, text_w, text_h, margin)
            
        # 繪製文字
        color = hex_to_rgb(settings.text_color)
        draw.text((x, y), text, font=font, fill=color + (settings.text_opacity,))
        
    if settings.image_path:
        try:
            modified_time = os.path.getmtime(settings.image_path)
            wm_img = _load_watermark_image_cached(settings.image_path, modified_time).copy()
            
            # 調整浮水印圖片大小
            target_w = int(w * settings.image_scale)
            ratio = target_w / wm_img.width
            target_h = int(wm_img.height * ratio)
            wm_img = wm_img.resize((target_w, target_h), Image.Resampling.LANCZOS)
            
            # 調整透明度
            if settings.image_opacity < 255:
                alpha = wm_img.split()[3]
                alpha = ImageEnhance.Brightness(alpha).enhance(settings.image_opacity / 255.0)
                wm_img.putalpha(alpha)
            
            # 計算位置
            wm_w, wm_h = wm_img.size
            x, y = _resolve_watermark_position(settings.position, w, h, wm_w, wm_h, margin)
                
            watermark_layer.paste(wm_img, (int(x), int(y)), wm_img)
            
        except Exception as e:
            print(f"Failed to load watermark image: {e}")
            # Don't return img here, just skip image watermark if it fails, 
            # so text watermark (if any) is preserved.
            pass

    # 合併圖層
    if img.mode != 'RGBA':
        img = img.convert('RGBA')
        
    # 保留透明度：如果原圖是 RGB，可以轉回 RGB，但若原圖有透明需求（如 PNG），則應保留 RGBA
    # 這裡回傳 RGBA，讓後續儲存流程（prepare_image_mode）決定是否要轉為 RGB（例如存為 JPEG 時）
    return Image.alpha_composite(img, watermark_layer)


def rotate_image(img: Image.Image, angle: int) -> Image.Image:
    """
    旋轉圖片
    
    Args:
        img: 原始圖片
        angle: 旋轉角度 (90, 180, 270)
    
    Returns:
        旋轉後的圖片
    """
    if angle == 90:
        return img.transpose(Image.Transpose.ROTATE_90)
    elif angle == 180:
        return img.transpose(Image.Transpose.ROTATE_180)
    elif angle == 270:
        return img.transpose(Image.Transpose.ROTATE_270)
    return img.copy()


def flip_image(img: Image.Image, direction: str) -> Image.Image:
    """
    翻轉圖片
    
    Args:
        img: 原始圖片
        direction: 翻轉方向 ('horizontal' 或 'vertical')
    
    Returns:
        翻轉後的圖片
    """
    if direction == 'horizontal':
        return img.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
    elif direction == 'vertical':
        return img.transpose(Image.Transpose.FLIP_TOP_BOTTOM)
    return img.copy()


def apply_filter(img: Image.Image, filter_type: str) -> Image.Image:
    """
    套用濾鏡效果
    
    Args:
        img: 原始圖片
        filter_type: 濾鏡類型
            - 'grayscale': 灰階
            - 'sepia': 復古懷舊
            - 'negative': 負片
            - 'blur': 模糊
            - 'sharpen': 銳化
            - 'edge': 邊緣檢測
            - 'emboss': 浮雕
            - 'warm': 暖色調
            - 'cool': 冷色調
    
    Returns:
        處理後的圖片
    """
    from PIL import ImageFilter, ImageOps
    
    result = img.copy()
    
    # 確保圖片是 RGB 模式 (部分濾鏡需要)
    if result.mode not in ('RGB', 'RGBA'):
        result = result.convert('RGB')
    
    if filter_type == 'grayscale':
        # 灰階
        result = ImageOps.grayscale(result).convert('RGB')
        
    elif filter_type == 'sepia':
        # 復古懷舊 - 使用矩陣運算優化
        # Matrix mostly for RGB, alpha layer needs care if present
        if result.mode == 'RGBA':
            alpha = result.split()[3]
            result = result.convert('RGB')
            # R, G, B matrix
            matrix = ( 0.393, 0.769, 0.189, 0,
                       0.349, 0.686, 0.168, 0,
                       0.272, 0.534, 0.131, 0 )
            result = result.convert("RGB", matrix)
            result.putalpha(alpha)
        else:
            matrix = ( 0.393, 0.769, 0.189, 0,
                       0.349, 0.686, 0.168, 0,
                       0.272, 0.534, 0.131, 0 )
            result = result.convert("RGB", matrix)
                
    elif filter_type == 'negative':
        # 負片 - 使用 ImageOps
        if result.mode == 'RGBA':
            r, g, b, a = result.split()
            rgb_image = Image.merge('RGB', (r, g, b))
            inverted_image = ImageOps.invert(rgb_image)
            r2, g2, b2 = inverted_image.split()
            result = Image.merge('RGBA', (r2, g2, b2, a))
        else:
            result = ImageOps.invert(result)
                
    elif filter_type == 'blur':
        # 模糊
        result = result.filter(ImageFilter.GaussianBlur(radius=3))
        
    elif filter_type == 'sharpen':
        # 銳化
        result = result.filter(ImageFilter.SHARPEN)
        
    elif filter_type == 'edge':
        # 邊緣檢測
        result = result.filter(ImageFilter.FIND_EDGES)
        
    elif filter_type == 'emboss':
        # 浮雕
        result = result.filter(ImageFilter.EMBOSS)
        
    elif filter_type == 'warm':
        # 暖色調 - 使用通道乘法優化
        enhancer = ImageEnhance.Color(result)
        result = enhancer.enhance(1.2)
        
        # 處理 RGB 通道
        if result.mode == 'RGBA':
            r, g, b, a = result.split()
            r = r.point(lambda i: i * 1.1)
            g = g.point(lambda i: i * 1.05)
            result = Image.merge('RGBA', (r, g, b, a))
        else:
            r, g, b = result.split()
            r = r.point(lambda i: i * 1.1)
            g = g.point(lambda i: i * 1.05)
            result = Image.merge('RGB', (r, g, b))
                
    elif filter_type == 'cool':
        # 冷色調 - 使用通道乘法優化
        enhancer = ImageEnhance.Color(result)
        result = enhancer.enhance(1.1)
        
        if result.mode == 'RGBA':
            r, g, b, a = result.split()
            r = r.point(lambda i: i * 0.9)
            b = b.point(lambda i: i * 1.1)
            result = Image.merge('RGBA', (r, g, b, a))
        else:
            r, g, b = result.split()
            r = r.point(lambda i: i * 0.9)
            b = b.point(lambda i: i * 1.1)
            result = Image.merge('RGB', (r, g, b))
    
    return result


def enhance_image(img: Image.Image, sharpness: float = 1.5, contrast: float = 1.1, color: float = 1.1, brightness: float = 1.0) -> Image.Image:
    """
    提升圖片畫質
    
    Args:
        img: 原始圖片
        sharpness: 銳利度增強倍數 (1.0 = 原始, >1.0 = 更銳利)
        contrast: 對比度增強倍數 (1.0 = 原始, >1.0 = 更高對比)
        color: 色彩飽和度增強倍數 (1.0 = 原始, >1.0 = 更鮮豔)
        brightness: 亮度調整倍數 (1.0 = 原始)
    
    Returns:
        處理後的圖片
    """
    result = img.copy()
    
    # 確保圖片是 RGB 模式
    if result.mode not in ('RGB', 'RGBA'):
        result = result.convert('RGB')
    
    # 應用銳利度增強
    if sharpness != 1.0:
        enhancer = ImageEnhance.Sharpness(result)
        result = enhancer.enhance(sharpness)
    
    # 應用對比度增強
    if contrast != 1.0:
        enhancer = ImageEnhance.Contrast(result)
        result = enhancer.enhance(contrast)
    
    # 應用色彩飽和度增強
    if color != 1.0:
        enhancer = ImageEnhance.Color(result)
        result = enhancer.enhance(color)
    
    # 應用亮度調整
    if brightness != 1.0:
        enhancer = ImageEnhance.Brightness(result)
        result = enhancer.enhance(brightness)
    
    return result


