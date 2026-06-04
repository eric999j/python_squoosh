from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any, Tuple
from PIL import Image
import os
import image_utils

import copy

@dataclass
class WatermarkSettings:
    enabled: bool = True
    # type field is removed as we support both text and image simultaneously or implicitly
    
    # Text settings
    text: str = ""  # Default empty, so it doesn't show unless user types something
    font_size: int = 36
    text_color: str = "#FFFFFF"
    text_opacity: int = 128  # 0-255
    
    # Image settings
    image_path: Optional[str] = None
    image_scale: float = 0.2  # Scale relative to main image width
    image_opacity: int = 200 # 0-255
    
    # Common settings
    position: str = "bottom-right"  # "top-left", "top-right", "bottom-left", "bottom-right", "center"
    margin: int = 20

@dataclass
class ImageItem:
    name: str
    original_pil: Image.Image
    path: Optional[str] = None
    compressed_pil: Optional[Image.Image] = None
    format: str = "JPEG"
    quality: int = 85
    convert_only: bool = False
    preview_before: Optional[Image.Image] = None
    preview_after: Optional[Image.Image] = None
    slider_x: Optional[int] = None
    original_size: int = 0
    compressed_size: int = 0
    img_width: int = 0
    img_height: int = 0
    history: List[Image.Image] = field(default_factory=list)
    watermark: WatermarkSettings = field(default_factory=WatermarkSettings)
    watermark_history: List[WatermarkSettings] = field(default_factory=list)
    action_log: List[str] = field(default_factory=list)
    process_cache: Dict[Tuple[Any, ...], Tuple[Image.Image, int]] = field(default_factory=dict)
    last_process_key: Optional[Tuple[Any, ...]] = None
    canvas_cache_key: Optional[Tuple[Any, ...]] = None
    canvas_cache_before: Optional[Image.Image] = None
    canvas_cache_after: Optional[Image.Image] = None
    preview_source_id: Optional[int] = None

    @classmethod
    def from_path(cls, path: str, default_format: str = "JPEG", default_quality: int = 85):
        img = image_utils.load_image_from_path(path)
        name = os.path.basename(path)
        return cls(
            name=name,
            path=path,
            original_pil=img,
            format=default_format,
            quality=default_quality,
            original_size=image_utils.get_image_size(img)
        )

    @classmethod
    def from_pil(cls, img: Image.Image, name: str = "unnamed", default_format: str = "JPEG", default_quality: int = 85):
        return cls(
            name=name,
            original_pil=img,
            format=default_format,
            quality=default_quality,
            original_size=image_utils.get_image_size(img)
        )

    def _check_history_limit(self):
        """Ensure history does not exceed 30 steps"""
        MAX_HISTORY = 30
        while len(self.action_log) > MAX_HISTORY:
            removed_type = self.action_log.pop(0)
            if removed_type == 'image':
                if self.history:
                    self.history.pop(0)
            elif removed_type == 'watermark':
                if self.watermark_history:
                    self.watermark_history.pop(0)

    def add_history(self):
        self.history.append(self.original_pil.copy())
        self.action_log.append('image')
        self._check_history_limit()

    def add_watermark_history(self):
        self.watermark_history.append(copy.deepcopy(self.watermark))
        self.action_log.append('watermark')
        self._check_history_limit()

    def undo(self) -> bool:
        if self.history:
            self.original_pil = self.history.pop()
            return True
        return False

    def undo_watermark(self) -> bool:
        if self.watermark_history:
            self.watermark = self.watermark_history.pop()
            return True
        return False

    def undo_latest(self) -> bool:
        if not self.action_log:
            return False
        
        last_action = self.action_log.pop()
        if last_action == 'image':
            return self.undo()
        elif last_action == 'watermark':
            return self.undo_watermark()
        return False

    def effective_quality(self) -> int:
        return 100 if self.convert_only else self.quality

    def watermark_signature(self) -> Tuple[Any, ...]:
        wm = self.watermark
        return (
            wm.enabled,
            wm.text,
            wm.font_size,
            wm.text_color,
            wm.text_opacity,
            wm.image_path,
            wm.image_scale,
            wm.image_opacity,
            wm.position,
            wm.margin,
        )

    def build_process_key(self) -> Tuple[Any, ...]:
        return (
            id(self.original_pil),
            self.format,
            self.effective_quality(),
            self.watermark_signature(),
        )

    def get_cached_process(self, key: Tuple[Any, ...]) -> Optional[Tuple[Image.Image, int]]:
        return self.process_cache.get(key)

    def set_cached_process(self, key: Tuple[Any, ...], image: Image.Image, size: int):
        self.process_cache[key] = (image.copy(), size)
        if len(self.process_cache) > 8:
            oldest = next(iter(self.process_cache))
            if oldest != key:
                self.process_cache.pop(oldest, None)

    def clear_canvas_cache(self):
        self.canvas_cache_key = None
        self.canvas_cache_before = None
        self.canvas_cache_after = None
