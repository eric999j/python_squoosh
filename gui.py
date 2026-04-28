import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from typing import List, Optional
from PIL import Image, ImageTk, ImageGrab
import threading
import os
import traceback
from tkinterdnd2 import DND_FILES

import image_utils
from models import ImageItem
from app_logic import AppLogic
import constants

class ImageCompressorApp:
    def __init__(self, root):
        self.root = root
        self.root.title(constants.WINDOW_TITLE)
        self.root.geometry(constants.WINDOW_SIZE)

        # --- 啟用拖放功能 ---
        self.root.drop_target_register(DND_FILES)
        self.root.dnd_bind('<<Drop>>', self.on_drop)

        # --- 綁定快捷鍵 ---
        self.root.bind('<Control-v>', self.paste_from_clipboard)
        self.root.bind('<Control-c>', self.copy_result_to_clipboard)
        self.root.bind('<Delete>', self.remove_current_item)

        # --- 資料變數 ---
        self.items: List[ImageItem] = []
        self.current_index: Optional[int] = None
        
        self.zoom_level = 1.0
        self.crop_mode = False
        self.crop_start = None
        self.crop_rect_id = None
        
        # 調整大小相關變數
        self.resize_mode = False
        self.resize_start = None
        self.resize_original_size = None
        self.resize_handle_size = 20  # 右下角拖曳控制點大小
        self.resize_target_size = None  # 追蹤拖曳時的目標尺寸 (w, h)
        
        self.process_after_id = None   # 追蹤延遲壓縮排程 ID

        # --- 樣式設定 ---
        self.style = ttk.Style()
        self.style.theme_use('clam')  # 使用較美觀的主題
        self.is_dark_mode = True     # 預設暗色模式

        # --- UI 佈局 ---
        self.create_widgets()
        self.apply_theme()

    def paste_from_clipboard(self, event=None):
        """從剪貼簿貼上圖片"""
        try:
            # 嘗試取得剪貼簿內容
            img = ImageGrab.grabclipboard()
            if isinstance(img, Image.Image):
                # 如果是圖片物件
                self.add_item(img, "Clipboard_Image")
            elif isinstance(img, list):
                # 如果是檔案路徑列表
                for path in img:
                    if os.path.isfile(path):
                        self.add_item_from_path(path)
            else:
                # 嘗試取得文字網址
                try:
                    text = self.root.clipboard_get()
                    if text.startswith('http'):
                        self.url_var.set(text)
                        self.load_from_url_thread()
                except:
                    pass
        except Exception as e:
            print(f"Paste error: {e}")

    def copy_result_to_clipboard(self, event=None):
        """複製處理後的圖片到剪貼簿"""
        if not self.items or self.current_index is None:
            return
        
        item = self.items[self.current_index]
        # 優先複製壓縮後的圖片，如果沒有則複製原圖
        img_to_copy = item.compressed_pil if item.compressed_pil else item.original_pil
        
        if img_to_copy:
            success = image_utils.copy_to_clipboard(img_to_copy)
            if success:
                self.show_toast("已複製圖片到剪貼簿")
            else:
                msg = "複製失敗"
                if os.name != 'nt':
                    msg += " (僅支援 Windows)"
                self.show_toast(msg)

    def show_toast(self, message, duration=1500):
        try:
            toast = tk.Toplevel(self.root)
            toast.overrideredirect(True)
            label = tk.Label(toast, text=message, bg="#333", fg="white", padx=10, pady=5, font=("Arial", 10))
            label.pack()
            toast.update_idletasks()
            
            root_x = self.root.winfo_x()
            root_y = self.root.winfo_y()
            root_w = self.root.winfo_width()
            root_h = self.root.winfo_height()
            
            x = root_x + (root_w - toast.winfo_width()) // 2
            y = root_y + root_h - 80
            
            toast.geometry(f"+{x}+{y}")
            toast.after(duration, toast.destroy)
        except Exception:
            pass

    def create_widgets(self):
        self._create_toolbar()
        self._create_notebook()
        self._create_preview_area()
        self._create_control_panel()

    def _create_toolbar(self):
        toolbar = ttk.Frame(self.root, padding=6)
        toolbar.pack(fill="x", padx=8, pady=6)

        self.url_var = tk.StringVar()
        # ttk.Button(toolbar, text="開啟圖檔", width=8, command=self.load_local_file).pack(side="left")
        # ttk.Label(toolbar, text=" ").pack(side="left", padx=4)
        ttk.Entry(toolbar, textvariable=self.url_var, width=40).pack(side="left", padx=4)
        ttk.Button(toolbar, text="由圖片網址載入", width=15, command=self.load_from_url_thread).pack(side="left", padx=4)
        ttk.Label(toolbar, text=" ").pack(side="left", padx=6)
        
        self.btn_watermark = ttk.Button(toolbar, text="浮水印", width=8, command=self.open_watermark_dialog)
        self.btn_watermark.pack(side="left", padx=4)

        self.btn_enhance = ttk.Button(toolbar, text="提升畫質", width=10, command=self.open_enhance_dialog)
        self.btn_enhance.pack(side="left", padx=4)

        self.btn_filter = ttk.Button(toolbar, text="濾鏡", width=8, command=self.open_filter_dialog)
        self.btn_filter.pack(side="left", padx=4)

        self.btn_rotate = ttk.Button(toolbar, text="旋轉/翻轉", width=10, command=self.open_rotate_dialog)
        self.btn_rotate.pack(side="left", padx=4)

        self.btn_crop = ttk.Button(toolbar, text="裁切", width=12, command=self.toggle_crop_mode)
        self.btn_crop.pack(side="left")

        self.btn_download = ttk.Button(toolbar, text="下載", width=8, command=self.save_image, state="disabled")
        self.btn_download.pack(side="left")
        ttk.Label(toolbar, text=" ").pack(side="left", padx=6)
        
        self.btn_batch = ttk.Button(toolbar, text="批次下載 (zip)", width=14, command=self.batch_download, state="disabled")
        self.btn_batch.pack(side="left")
        ttk.Label(toolbar, text=" ").pack(side="left", padx=6)

        self.btn_delete = ttk.Button(toolbar, text="刪除", width=8, command=self.remove_current_item, state="disabled")
        self.btn_delete.pack(side="left")
        ttk.Label(toolbar, text=" ").pack(side="left", padx=4)
        
        self.btn_undo = ttk.Button(toolbar, text="回復 (Undo)", width=15, command=self.undo_last_action, state="disabled")
        self.btn_undo.pack(side="left", padx=4)
        
        # 提醒使用者 Undo 限制
        # Tooltip realization using simple bind if needed, but text update in check_undo_state covers it.
        # Just to be safe and clear initially:
        # ttk.Label(toolbar, text="(Max 30)").pack(side="left")

    def _create_notebook(self):
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill="x", padx=8, pady=(0,6))
        self.notebook.bind('<<NotebookTabChanged>>', self.on_tab_changed)

    def _create_preview_area(self):
        self.canvas_frame = ttk.Frame(self.root)
        self.canvas_frame.pack(fill="both", expand=True, padx=10, pady=5)
        
        self.canvas = tk.Canvas(self.canvas_frame, bg=constants.CANVAS_BG, cursor="sb_h_double_arrow")
        self.canvas.pack(fill="both", expand=True)
        
        self.canvas.bind("<B1-Motion>", self.on_canvas_drag)
        self.canvas.bind("<Button-1>", self.on_canvas_click)
        self.canvas.bind("<ButtonRelease-1>", self.on_canvas_release)
        self.canvas.bind("<Motion>", self.on_canvas_motion)
        
        self.canvas.bind("<MouseWheel>", self.on_zoom)
        self.canvas.bind("<Button-4>", self.on_zoom)
        self.canvas.bind("<Button-5>", self.on_zoom)
        self.canvas.bind("<Button-3>", self.show_context_menu)

    def _create_control_panel(self):
        control_frame = ttk.Frame(self.root, padding=6)
        control_frame.pack(fill="x", padx=8, pady=6)

        ttk.Label(control_frame, text="格式:").pack(side="left", padx=(0,4))
        self.format_var = tk.StringVar(value=constants.DEFAULT_FORMAT)
        self.format_cb = ttk.Combobox(control_frame, textvariable=self.format_var, values=constants.SUPPORTED_FORMATS, state="readonly", width=8)
        self.format_cb.pack(side="left", padx=(0,10))
        self.format_cb.bind("<<ComboboxSelected>>", self.on_format_change)

        self.convert_only_var = tk.BooleanVar(value=False)
        self.convert_only_cb = ttk.Checkbutton(control_frame, text="僅轉檔", variable=self.convert_only_var, command=self.on_convert_only_change)
        self.convert_only_cb.pack(side="left", padx=(0,10))

        ttk.Label(control_frame, text="品質:").pack(side="left", padx=(0,4))
        self.quality_var = tk.IntVar(value=constants.DEFAULT_QUALITY)
        self.quality_scale = ttk.Scale(control_frame, from_=1, to=100, variable=self.quality_var, orient="horizontal", length=180)
        self.quality_scale.pack(side="left", padx=(0,6))
        self.quality_scale.configure(command=self.on_quality_change)

        self.quality_label = ttk.Label(control_frame, text=str(constants.DEFAULT_QUALITY))
        self.quality_label.pack(side="left", padx=(0,8))

        self.btn_theme = ttk.Button(control_frame, text="☀", width=4, command=self.toggle_theme)
        self.btn_theme.pack(side="right", padx=5)

        self.info_label = ttk.Label(control_frame, text="請先載入圖片...", font=("Arial", 10, "bold"))
        self.info_label.pack(side="right")

    def toggle_theme(self):
        self.is_dark_mode = not self.is_dark_mode
        self.apply_theme()

    def apply_theme(self):
        theme = constants.THEME_DARK if self.is_dark_mode else constants.THEME_LIGHT
        
        # 設定 Root 背景
        self.root.configure(bg=theme["bg"])
        
        # 設定 ttk 樣式
        self.style.configure(".", background=theme["bg"], foreground=theme["fg"])
        self.style.configure("TFrame", background=theme["bg"])
        self.style.configure("TLabel", background=theme["bg"], foreground=theme["fg"])
        self.style.configure("TButton", background=theme["button_bg"], foreground=theme["fg"])
        self.style.map("TButton",
            background=[("active", theme["active_bg"])],
            foreground=[("active", theme["fg"])]
        )
        self.style.configure("TCheckbutton", background=theme["bg"], foreground=theme["fg"])
        self.style.configure("TRadiobutton", background=theme["bg"], foreground=theme["fg"])
        self.style.configure("TCombobox", fieldbackground=theme["entry_bg"], background=theme["button_bg"], foreground=theme["fg"])
        
        # 設定 TEntry 樣式 - 確保深色模式下文字可見
        # 深色模式: 淺色背景 + 深色文字；淺色模式: 白色背景 + 深色文字
        if self.is_dark_mode:
            self.style.configure("TEntry", fieldbackground="#f0f0f0", foreground="#000000", insertcolor="#000000")
            self.style.map("TEntry",
                fieldbackground=[("focus", "#ffffff"), ("!focus", "#f0f0f0")],
                foreground=[("focus", "#000000"), ("!focus", "#000000")]
            )
        else:
            self.style.configure("TEntry", fieldbackground="#ffffff", foreground="#333333", insertcolor="#333333")
            self.style.map("TEntry",
                fieldbackground=[("focus", "#ffffff"), ("!focus", "#ffffff")],
                foreground=[("focus", "#333333"), ("!focus", "#333333")]
            )
        
        # 設定 Canvas
        self.canvas.configure(bg=theme["canvas_bg"])
        
        # 更新按鈕文字
        self.btn_theme.configure(text="☀" if self.is_dark_mode else "🌙")

    def on_tab_changed(self, event):
        try:
            sel = self.notebook.index(self.notebook.select())
        except Exception:
            sel = None
        
        self.current_index = sel
        if sel is None:
            return
            
        item = self.items[sel]
        
        # 更新 UI 狀態
        self.format_var.set(item.format)
        self.quality_var.set(item.quality)
        self.quality_label.configure(text=str(item.quality))
        self.convert_only_var.set(item.convert_only)
        
        # 根據是否僅轉檔禁用品質滑桿
        if item.convert_only:
            self.quality_scale.configure(state="disabled")
        else:
            self.quality_scale.configure(state="normal")
        
        # 更新 Undo 按鈕狀態
        self.btn_undo.configure(state="normal" if item.history else "disabled")
            
        # 如果尚未處理過，立即處理一次以建立預覽
        if not item.preview_before:
            self.process_image()
        else:
            self.update_canvas()
            self.update_info_label()

    def on_drop(self, event):
        paths = AppLogic.parse_drop_files(event.data)
        for p in paths:
            self.add_item_from_path(p)

    def load_local_file(self):
        path = filedialog.askopenfilename(filetypes=constants.IMAGE_FILE_TYPES)
        if path:
            self.add_item_from_path(path)

    def load_from_url_thread(self):
        url = self.url_var.get().strip()
        if not url:
            return
        threading.Thread(target=self.load_from_url, args=(url,), daemon=True).start()

    def load_from_url(self, url):
        try:
            img = image_utils.load_image_from_url(url)
            self.root.after(0, self.add_item, img, "url_image")
        except Exception as e:
            self.root.after(0, messagebox.showerror, "錯誤", f"無法下載圖片: {e}")

    def add_item_from_path(self, path):
        try:
            item = ImageItem.from_path(path, self.format_var.get(), self.quality_var.get())
            self._register_item(item)
        except Exception as e:
            messagebox.showerror("錯誤", f"無法載入: {path}\n{e}")

    def add_item(self, img, name="unnamed"):
        item = ImageItem.from_pil(img, name, self.format_var.get(), self.quality_var.get())
        self._register_item(item)

    def _register_item(self, item: ImageItem):
        self.items.append(item)
        tab = ttk.Frame(self.notebook)
        self.notebook.add(tab, text=item.name)
        self.notebook.select(len(self.items)-1)
        self.btn_download.configure(state="normal")
        self.btn_delete.configure(state="normal")

    def remove_current_item(self, event=None):
        if self.current_index is None:
            return
            
        # 移除資料與 Tab
        idx = self.current_index
        del self.items[idx]
        self.notebook.forget(idx)
        
        # 調整當前索引
        if self.items:
            new_idx = min(idx, len(self.items) - 1)
            self.notebook.select(new_idx)
        else:
            self.current_index = None
            self.canvas.delete("all")
            self.info_label.configure(text="請先載入圖片...")
            self.btn_download.configure(state="disabled")
            self.btn_batch.configure(state="disabled")
            self.btn_delete.configure(state="disabled")
            self.btn_undo.configure(state="disabled")
            self.quality_scale.configure(state="disabled")
        self.btn_batch.configure(state="normal")

    def process_image(self):
        if self.current_index is None:
            return

        item = self.items[self.current_index]

        if self.process_after_id:
            self.root.after_cancel(self.process_after_id)
            self.process_after_id = None

        try:
            # 應用浮水印 (如果啟用)
            img_to_compress = item.original_pil
            if item.watermark.enabled:
                img_to_compress = image_utils.apply_watermark(item.original_pil.copy(), item.watermark)

            # 如果是僅轉檔，則使用最高品質 (100)
            effective_quality = 100 if item.convert_only else item.quality
            buffer, size = image_utils.compress_image_to_buffer(img_to_compress, item.format, effective_quality)
            item.compressed_size = size
            compressed_img = Image.open(buffer)
            compressed_img.load()
            item.compressed_pil = compressed_img.copy()

            # 更新預覽縮圖
            item.preview_before, item.img_width, item.img_height = image_utils.resize_image_contain(
                item.original_pil, constants.MAX_PREVIEW_WIDTH, constants.MAX_PREVIEW_HEIGHT
            )
            
            # 確保壓縮後的預覽圖大小一致
            item.preview_after = item.compressed_pil.resize((item.img_width, item.img_height), Image.Resampling.LANCZOS)

            if item.slider_x is None:
                item.slider_x = item.img_width // 2

            self.update_canvas()
            self.update_info_label()

        except Exception as e:
            tb = traceback.format_exc()
            self.show_traceback(tb, title="壓縮失敗詳情")
            messagebox.showerror("錯誤", f"壓縮失敗: {e}")

    def schedule_process_image(self):
        if self.current_index is None:
            return
        if self.process_after_id:
            self.root.after_cancel(self.process_after_id)
        self.process_after_id = self.root.after(200, self.process_image)

    def on_quality_change(self, value):
        val = int(float(value))
        self.quality_label.configure(text=str(val))
        if self.current_index is not None:
            self.items[self.current_index].quality = val
            self.schedule_process_image()

    def on_convert_only_change(self):
        if self.current_index is not None:
            is_convert_only = self.convert_only_var.get()
            self.items[self.current_index].convert_only = is_convert_only
            
            # 同步禁用品質滑桿
            if is_convert_only:
                self.quality_scale.configure(state="disabled")
            else:
                self.quality_scale.configure(state="normal")
                
            self.schedule_process_image()

    def on_format_change(self, event=None):
        if self.current_index is not None:
            self.items[self.current_index].format = self.format_var.get()
            self.schedule_process_image()

    def toggle_crop_mode(self):
        self.crop_mode = not self.crop_mode
        self.btn_crop.configure(text=f"裁切")
        if not self.crop_mode:
            self.canvas.delete(self.crop_rect_id)
            self.crop_rect_id = None

    def on_zoom(self, event):
        if self.current_index is None: return
        if event.num == 5 or (hasattr(event, 'delta') and event.delta < 0):
            self.zoom_level = max(0.1, self.zoom_level - 0.1)
        else:
            self.zoom_level = min(5.0, self.zoom_level + 0.1)
        self.update_canvas()

    def show_context_menu(self, event):
        if self.current_index is None: return
        menu = tk.Menu(self.root, tearoff=0)
        menu.add_command(label="複製結果 (Copy Result)", command=self.copy_result_to_clipboard)
        menu.add_separator()
        menu.add_command(label="調整尺寸 (Resize)...", command=self.open_resize_dialog)
        menu.add_command(label="重置縮放 (Reset Zoom)", command=self.reset_zoom)
        menu.post(event.x_root, event.y_root)

    def reset_zoom(self):
        self.zoom_level = 1.0
        self.update_canvas()

    def open_resize_dialog(self):
        if self.current_index is None: return
        item = self.items[self.current_index]
        orig_w, orig_h = item.original_pil.size
        
        dlg = tk.Toplevel(self.root)
        dlg.title("調整尺寸")
        dlg.geometry("300x200")
        
        ttk.Label(dlg, text=f"目前尺寸: {orig_w} x {orig_h}").pack(pady=10)
        frame = ttk.Frame(dlg)
        frame.pack(pady=5)
        
        w_var = tk.IntVar(value=orig_w)
        h_var = tk.IntVar(value=orig_h)
        
        ttk.Label(frame, text="寬:").grid(row=0, column=0)
        ttk.Entry(frame, textvariable=w_var, width=10).grid(row=0, column=1)
        ttk.Label(frame, text="高:").grid(row=1, column=0)
        ttk.Entry(frame, textvariable=h_var, width=10).grid(row=1, column=1)
        
        def apply():
            new_w, new_h = w_var.get(), h_var.get()
            if new_w > 0 and new_h > 0:
                item.add_history()
                item.original_pil = item.original_pil.resize((new_w, new_h), Image.Resampling.LANCZOS)
                item.slider_x = None 
                self.process_image()
                dlg.destroy()
                
        ttk.Button(dlg, text="套用", command=apply).pack(pady=10)

    def open_watermark_dialog(self):
        if self.current_index is None: return
        item = self.items[self.current_index]
        wm = item.watermark
        
        dlg = tk.Toplevel(self.root)
        dlg.title("浮水印設定")
        dlg.geometry("400x350")
        dlg.resizable(False, False)
        
        # Settings Notebook
        nb = ttk.Notebook(dlg)
        # 修改: 改為 fill="x" 且移除 expand=True，讓 Notebook 高度隨內容調整，不佔用額外空間
        nb.pack(fill="x", padx=10, pady=5)
        
        # Text Tab
        text_frame = ttk.Frame(nb)
        nb.add(text_frame, text="文字設定")
        
        ttk.Label(text_frame, text="內容:").grid(row=0, column=0, sticky="w", pady=5, padx=5)
        text_content_var = tk.StringVar(value=wm.text)
        ttk.Entry(text_frame, textvariable=text_content_var).grid(row=0, column=1, sticky="ew", pady=5, padx=5)
        
        ttk.Label(text_frame, text="大小:").grid(row=1, column=0, sticky="w", pady=5, padx=5)
        font_size_var = tk.IntVar(value=wm.font_size)
        ttk.Scale(text_frame, from_=10, to=200, variable=font_size_var).grid(row=1, column=1, sticky="ew", pady=5, padx=5)
        
        ttk.Label(text_frame, text="顏色 (Hex):").grid(row=2, column=0, sticky="w", pady=5, padx=5)
        color_var = tk.StringVar(value=wm.text_color)
        ttk.Entry(text_frame, textvariable=color_var).grid(row=2, column=1, sticky="ew", pady=5, padx=5)
        
        ttk.Label(text_frame, text="透明度:").grid(row=3, column=0, sticky="w", pady=5, padx=5)
        text_opacity_var = tk.IntVar(value=wm.text_opacity)
        ttk.Scale(text_frame, from_=0, to=255, variable=text_opacity_var).grid(row=3, column=1, sticky="ew", pady=5, padx=5)
        
        # Image Tab
        img_frame = ttk.Frame(nb)
        nb.add(img_frame, text="圖片設定")
        
        path_var = tk.StringVar(value=wm.image_path if wm.image_path else "")
        def browse_img():
            p = filedialog.askopenfilename(filetypes=[("Images", "*.png;*.jpg;*.jpeg;*.webp")])
            if p: path_var.set(p)
            
        ttk.Button(img_frame, text="選擇圖片...", command=browse_img).pack(fill="x", pady=5, padx=5)
        ttk.Label(img_frame, textvariable=path_var, wraplength=300).pack(fill="x", pady=5, padx=5)
        
        ttk.Label(img_frame, text="縮放比例 (0.1-1.0):").pack(anchor="w", padx=5)
        scale_var = tk.DoubleVar(value=wm.image_scale)
        ttk.Scale(img_frame, from_=0.05, to=1.0, variable=scale_var).pack(fill="x", padx=5)
        
        ttk.Label(img_frame, text="透明度 (0-255):").pack(anchor="w", padx=5)
        img_opacity_var = tk.IntVar(value=wm.image_opacity)
        ttk.Scale(img_frame, from_=0, to=255, variable=img_opacity_var).pack(fill="x", padx=5)
        
        # Common Settings
        common_frame = ttk.LabelFrame(dlg, text="位置設定")
        common_frame.pack(fill="x", padx=10, pady=5)
        
        pos_var = tk.StringVar(value=wm.position)
        positions = ["top-left", "top-right", "center", "bottom-left", "bottom-right"]
        ttk.Combobox(common_frame, textvariable=pos_var, values=positions, state="readonly").pack(fill="x", pady=5, padx=5)
        
        ttk.Label(common_frame, text="邊距:").pack(anchor="w", padx=5)
        margin_var = tk.IntVar(value=wm.margin)
        ttk.Scale(common_frame, from_=0, to=100, variable=margin_var).pack(fill="x", padx=5)
        
        def apply():
            # Save current watermark state to history before applying changes
            item.add_watermark_history()
            self.btn_undo.configure(state="normal")

            wm.enabled = True
            
            wm.text = text_content_var.get()
            wm.font_size = int(font_size_var.get())
            wm.text_color = color_var.get()
            wm.text_opacity = int(text_opacity_var.get())
            
            wm.image_path = path_var.get()
            wm.image_scale = float(scale_var.get())
            wm.image_opacity = int(img_opacity_var.get())
            
            wm.position = pos_var.get()
            wm.margin = int(margin_var.get())
            
            self.process_image()
            dlg.destroy()
            
        ttk.Button(dlg, text="套用", command=apply).pack(pady=10)

    def open_rotate_dialog(self):
        """開啟旋轉/翻轉對話框"""
        if self.current_index is None:
            messagebox.showwarning("提示", "請先載入圖片")
            return
        item = self.items[self.current_index]
        
        dlg = tk.Toplevel(self.root)
        dlg.title("旋轉/翻轉")
        dlg.geometry("320x280")
        dlg.resizable(False, False)
        
        # 旋轉區塊
        rotate_frame = ttk.LabelFrame(dlg, text="旋轉")
        rotate_frame.pack(fill="x", padx=15, pady=10)
        
        btn_rotate_frame = ttk.Frame(rotate_frame)
        btn_rotate_frame.pack(pady=10)
        
        def rotate_action(angle):
            item.add_history()
            self.btn_undo.configure(state="normal")
            item.original_pil = image_utils.rotate_image(item.original_pil, angle)
            item.slider_x = None
            self.process_image()
            self.show_toast(f"已旋轉 {angle}°")
        
        ttk.Button(btn_rotate_frame, text="↺ 90°", width=8, 
                   command=lambda: rotate_action(90)).pack(side="left", padx=5)
        ttk.Button(btn_rotate_frame, text="180°", width=8,
                   command=lambda: rotate_action(180)).pack(side="left", padx=5)
        ttk.Button(btn_rotate_frame, text="↻ 270°", width=8,
                   command=lambda: rotate_action(270)).pack(side="left", padx=5)
        
        # 翻轉區塊
        flip_frame = ttk.LabelFrame(dlg, text="翻轉")
        flip_frame.pack(fill="x", padx=15, pady=10)
        
        btn_flip_frame = ttk.Frame(flip_frame)
        btn_flip_frame.pack(pady=10)
        
        def flip_action(direction):
            item.add_history()
            self.btn_undo.configure(state="normal")
            item.original_pil = image_utils.flip_image(item.original_pil, direction)
            item.slider_x = None
            self.process_image()
            direction_text = "水平" if direction == "horizontal" else "垂直"
            self.show_toast(f"已{direction_text}翻轉")
        
        ttk.Button(btn_flip_frame, text="↔ 水平翻轉", width=12,
                   command=lambda: flip_action("horizontal")).pack(side="left", padx=10)
        ttk.Button(btn_flip_frame, text="↕ 垂直翻轉", width=12,
                   command=lambda: flip_action("vertical")).pack(side="left", padx=10)
        
        # 關閉按鈕
        ttk.Button(dlg, text="關閉", command=dlg.destroy).pack(pady=15)

    def open_filter_dialog(self):
        """開啟濾鏡效果對話框"""
        if self.current_index is None:
            messagebox.showwarning("提示", "請先載入圖片")
            return
        item = self.items[self.current_index]
        
        dlg = tk.Toplevel(self.root)
        dlg.title("濾鏡效果")
        dlg.geometry("400x380")
        dlg.resizable(False, False)
        
        # 濾鏡選項
        filters = [
            ("grayscale", "灰階", "將圖片轉為黑白灰色調"),
            ("sepia", "復古懷舊", "營造復古泛黃效果"),
            ("negative", "負片", "反轉所有顏色"),
            ("blur", "模糊", "高斯模糊效果"),
            ("sharpen", "銳化", "增強圖片邊緣"),
            ("edge", "邊緣檢測", "突顯圖片輪廓"),
            ("emboss", "浮雕", "3D 浮雕效果"),
            ("warm", "暖色調", "增加橘紅色調"),
            ("cool", "冷色調", "增加藍綠色調"),
        ]
        
        filter_var = tk.StringVar(value="grayscale")
        
        # 濾鏡列表
        list_frame = ttk.LabelFrame(dlg, text="選擇濾鏡")
        list_frame.pack(fill="both", expand=True, padx=15, pady=10)
        
        for filter_id, filter_name, filter_desc in filters:
            frame = ttk.Frame(list_frame)
            frame.pack(fill="x", padx=5, pady=2)
            ttk.Radiobutton(frame, text=filter_name, value=filter_id, 
                           variable=filter_var).pack(side="left")
            ttk.Label(frame, text=f"- {filter_desc}", foreground="gray").pack(side="left", padx=10)
        
        # 按鈕區
        btn_frame = ttk.Frame(dlg)
        btn_frame.pack(fill="x", padx=15, pady=10)
        
        def apply_filter_action():
            selected = filter_var.get()
            item.add_history()
            self.btn_undo.configure(state="normal")
            item.original_pil = image_utils.apply_filter(item.original_pil, selected)
            item.slider_x = None
            self.process_image()
            
            # 找到濾鏡名稱
            filter_name = next((name for fid, name, _ in filters if fid == selected), selected)
            self.show_toast(f"已套用「{filter_name}」濾鏡")
            dlg.destroy()
        
        ttk.Button(btn_frame, text="取消", command=dlg.destroy).pack(side="right", padx=5)
        ttk.Button(btn_frame, text="套用", command=apply_filter_action).pack(side="right", padx=5)

    def open_enhance_dialog(self):
        """開啟提升畫質對話框"""
        if self.current_index is None: 
            messagebox.showwarning("提示", "請先載入圖片")
            return
        item = self.items[self.current_index]
        
        dlg = tk.Toplevel(self.root)
        dlg.title("提升畫質")
        dlg.geometry("400x320")
        dlg.resizable(False, False)
        
        # 參數變數
        sharpness_var = tk.DoubleVar(value=1.5)
        contrast_var = tk.DoubleVar(value=1.1)
        color_var = tk.DoubleVar(value=1.1)
        brightness_var = tk.DoubleVar(value=1.0)
        
        # 銳利度
        frame1 = ttk.Frame(dlg)
        frame1.pack(fill="x", padx=20, pady=8)
        ttk.Label(frame1, text="銳利度:", width=10).pack(side="left")
        sharpness_scale = ttk.Scale(frame1, from_=0.5, to=3.0, variable=sharpness_var, orient="horizontal", length=200)
        sharpness_scale.pack(side="left", padx=5)
        sharpness_label = ttk.Label(frame1, text="1.5", width=5)
        sharpness_label.pack(side="left")
        def update_sharpness_label(val):
            sharpness_label.configure(text=f"{float(val):.1f}")
        sharpness_scale.configure(command=update_sharpness_label)
        
        # 對比度
        frame2 = ttk.Frame(dlg)
        frame2.pack(fill="x", padx=20, pady=8)
        ttk.Label(frame2, text="對比度:", width=10).pack(side="left")
        contrast_scale = ttk.Scale(frame2, from_=0.5, to=2.0, variable=contrast_var, orient="horizontal", length=200)
        contrast_scale.pack(side="left", padx=5)
        contrast_label = ttk.Label(frame2, text="1.1", width=5)
        contrast_label.pack(side="left")
        def update_contrast_label(val):
            contrast_label.configure(text=f"{float(val):.1f}")
        contrast_scale.configure(command=update_contrast_label)
        
        # 色彩飽和度
        frame3 = ttk.Frame(dlg)
        frame3.pack(fill="x", padx=20, pady=8)
        ttk.Label(frame3, text="色彩飽和:", width=10).pack(side="left")
        color_scale = ttk.Scale(frame3, from_=0.5, to=2.0, variable=color_var, orient="horizontal", length=200)
        color_scale.pack(side="left", padx=5)
        color_label = ttk.Label(frame3, text="1.1", width=5)
        color_label.pack(side="left")
        def update_color_label(val):
            color_label.configure(text=f"{float(val):.1f}")
        color_scale.configure(command=update_color_label)
        
        # 亮度
        frame4 = ttk.Frame(dlg)
        frame4.pack(fill="x", padx=20, pady=8)
        ttk.Label(frame4, text="亮度:", width=10).pack(side="left")
        brightness_scale = ttk.Scale(frame4, from_=0.5, to=2.0, variable=brightness_var, orient="horizontal", length=200)
        brightness_scale.pack(side="left", padx=5)
        brightness_label = ttk.Label(frame4, text="1.0", width=5)
        brightness_label.pack(side="left")
        def update_brightness_label(val):
            brightness_label.configure(text=f"{float(val):.1f}")
        brightness_scale.configure(command=update_brightness_label)
        
        # 說明
        info_frame = ttk.LabelFrame(dlg, text="說明")
        info_frame.pack(fill="x", padx=20, pady=10)
        ttk.Label(info_frame, text="• 數值 1.0 = 原始狀態\n• 大於 1.0 = 增強效果\n• 小於 1.0 = 減弱效果", justify="left").pack(padx=10, pady=5)
        
        # 按鈕區
        btn_frame = ttk.Frame(dlg)
        btn_frame.pack(fill="x", padx=20, pady=10)
        
        def apply_enhance():
            # 儲存歷史以便 Undo
            item.add_history()
            self.btn_undo.configure(state="normal")
            
            # 套用畫質提升
            item.original_pil = image_utils.enhance_image(
                item.original_pil,
                sharpness=sharpness_var.get(),
                contrast=contrast_var.get(),
                color=color_var.get(),
                brightness=brightness_var.get()
            )
            item.slider_x = None
            self.process_image()
            dlg.destroy()
            self.show_toast("已提升畫質")
        
        def reset_values():
            sharpness_var.set(1.0)
            contrast_var.set(1.0)
            color_var.set(1.0)
            brightness_var.set(1.0)
            update_sharpness_label(1.0)
            update_contrast_label(1.0)
            update_color_label(1.0)
            update_brightness_label(1.0)
        
        ttk.Button(btn_frame, text="重置", command=reset_values).pack(side="left", padx=5)
        ttk.Button(btn_frame, text="取消", command=dlg.destroy).pack(side="right", padx=5)
        ttk.Button(btn_frame, text="套用", command=apply_enhance).pack(side="right", padx=5)

    def is_in_resize_handle(self, event):
        """檢查滑鼠是否在右下角調整大小控制點區域"""
        if self.current_index is None:
            return False
        item = self.items[self.current_index]
        if not item.preview_before:
            return False
        
        w = int(item.img_width * self.zoom_level)
        h = int(item.img_height * self.zoom_level)
        handle_size = self.resize_handle_size
        
        return (w - handle_size <= event.x <= w and 
                h - handle_size <= event.y <= h)

    def on_canvas_motion(self, event):
        """處理滑鼠移動，改變右下角區域的游標"""
        if self.crop_mode:
            return
        
        if self.is_in_resize_handle(event):
            self.canvas.configure(cursor="size_nw_se")
        else:
            self.canvas.configure(cursor="sb_h_double_arrow")

    def on_canvas_click(self, event):
        if self.crop_mode:
            self.crop_start = (event.x, event.y)
            if self.crop_rect_id:
                self.canvas.delete(self.crop_rect_id)
            self.crop_rect_id = self.canvas.create_rectangle(event.x, event.y, event.x, event.y, outline="red", width=2, dash=(4, 4))
        elif self.is_in_resize_handle(event):
            # 開始調整大小模式
            self.resize_mode = True
            self.resize_start = (event.x, event.y)
            if self.current_index is not None:
                item = self.items[self.current_index]
                self.resize_original_size = item.original_pil.size
        else:
            self.on_slider_drag(event)

    def on_canvas_drag(self, event):
        if self.crop_mode:
            if self.crop_start:
                x1, y1 = self.crop_start
                self.canvas.coords(self.crop_rect_id, x1, y1, event.x, event.y)
        elif self.resize_mode:
            self.on_resize_drag(event)
        else:
            self.on_slider_drag(event)

    def on_canvas_release(self, event):
        if self.crop_mode and self.crop_start:
            x1, y1 = self.crop_start
            x2, y2 = event.x, event.y
            left, right = sorted([x1, x2])
            top, bottom = sorted([y1, y2])
            
            if right - left > 10 and bottom - top > 10:
                if messagebox.askyesno("裁切確認", "是否裁切選取區域？"):
                    self.apply_crop(left, top, right, bottom)
            
            self.canvas.delete(self.crop_rect_id)
            self.crop_rect_id = None
            self.crop_start = None
        elif self.resize_mode:
            self.apply_resize(event)
            self.resize_mode = False
            self.resize_start = None
            self.resize_original_size = None
            self.resize_target_size = None

    def apply_crop(self, x1, y1, x2, y2):
        if self.current_index is None: return
        item = self.items[self.current_index]
        
        current_display_w = int(item.img_width * self.zoom_level)
        current_display_h = int(item.img_height * self.zoom_level)
        
        orig_w, orig_h = item.original_pil.size
        scale_x, scale_y = orig_w / current_display_w, orig_h / current_display_h
        
        real_x1, real_y1 = int(x1 * scale_x), int(y1 * scale_y)
        real_x2, real_y2 = int(x2 * scale_x), int(y2 * scale_y)

        item.add_history()
        self.btn_undo.configure(state="normal")
        item.original_pil = item.original_pil.crop((real_x1, real_y1, real_x2, real_y2))
        
        self.toggle_crop_mode()
        self.process_image()

    def on_resize_drag(self, event):
        """處理拖曳調整大小時的即時預覽"""
        if self.current_index is None or not self.resize_start:
            return
        
        item = self.items[self.current_index]
        if not self.resize_original_size:
            return
        
        # 計算拖曳距離
        dx = event.x - self.resize_start[0]
        dy = event.y - self.resize_start[1]
        
        # 使用較大的變化量來決定縮放比例（保持長寬比）
        delta = max(dx, dy)
        
        # 計算縮放因子
        orig_w, orig_h = self.resize_original_size
        display_w = int(item.img_width * self.zoom_level)
        
        scale_factor = (display_w + delta) / display_w
        scale_factor = max(0.1, min(5.0, scale_factor))  # 限制範圍
        
        # 計算目標尺寸並儲存供 Canvas 顯示
        new_w = max(10, int(orig_w * scale_factor))
        new_h = max(10, int(orig_h * scale_factor))
        self.resize_target_size = (new_w, new_h)
        
        # 即時更新 zoom level 來顯示預覽
        # （實際圖片大小在釋放時才會改變）
        self.zoom_level = scale_factor
        self.update_canvas()

    def apply_resize(self, event):
        """應用無損放大/縮小"""
        if self.current_index is None or not self.resize_start:
            return
        
        item = self.items[self.current_index]
        if not self.resize_original_size:
            return
        
        orig_w, orig_h = self.resize_original_size
        
        # 計算拖曳距離
        dx = event.x - self.resize_start[0]
        dy = event.y - self.resize_start[1]
        
        # 使用較大的變化量來決定縮放比例
        delta = max(dx, dy)
        
        # 計算目標尺寸
        display_w = int(item.img_width * 1.0)  # 使用初始 zoom level 1.0 計算
        scale_factor = (display_w + delta) / display_w
        scale_factor = max(0.1, min(5.0, scale_factor))
        
        new_w = int(orig_w * scale_factor)
        new_h = int(orig_h * scale_factor)
        
        # 確保最小尺寸
        new_w = max(10, new_w)
        new_h = max(10, new_h)
        
        # 如果尺寸變化很小，不進行調整
        if abs(new_w - orig_w) < 5 and abs(new_h - orig_h) < 5:
            self.zoom_level = 1.0
            self.update_canvas()
            return
        
        # 儲存歷史以便 Undo
        item.add_history()
        self.btn_undo.configure(state="normal")
        
        # 使用 LANCZOS 進行無損縮放
        item.original_pil = item.original_pil.resize((new_w, new_h), Image.Resampling.LANCZOS)
        item.slider_x = None
        
        # 重置 zoom level
        self.zoom_level = 1.0
        
        self.process_image()
        self.show_toast(f"已調整大小為 {new_w} x {new_h}")

    def undo_last_action(self):
        if self.current_index is None: return
        item = self.items[self.current_index]
        
        if item.undo_latest():
            self.process_image()
            self.check_undo_state(item)
            
    def check_undo_state(self, item):
        has_history = bool(item.action_log)
        if has_history:
            count = len(item.action_log)
            self.btn_undo.configure(state="normal", text=f"回復 (Undo) {count}/30")
        else:
            self.btn_undo.configure(state="disabled", text="回復 (Undo)")

    def on_slider_drag(self, event):
        if self.current_index is None: return
        item = self.items[self.current_index]
        if not item.preview_before: return
        
        current_w = int(item.img_width * self.zoom_level)
        item.slider_x = max(0, min(event.x, current_w))
        self.update_canvas()

    def update_canvas(self):
        if self.current_index is None: return
        item = self.items[self.current_index]
        if not item.preview_before: return
            
        self.canvas.delete("all")
        w, h = int(item.img_width * self.zoom_level), int(item.img_height * self.zoom_level)
        resample_method = Image.Resampling.NEAREST if self.zoom_level > 1 else Image.Resampling.LANCZOS
        
        zoomed_before = item.preview_before.resize((w, h), resample_method)
        zoomed_after = item.preview_after.resize((w, h), resample_method)
        
        self.tk_img_before = ImageTk.PhotoImage(zoomed_before)
        self.canvas.create_image(0, 0, anchor="nw", image=self.tk_img_before)
        
        slider_x = item.slider_x if item.slider_x is not None else w // 2
        if slider_x < w:
            box = (slider_x, 0, w, h)
            cropped_after = zoomed_after.crop(box)
            self.tk_img_after = ImageTk.PhotoImage(cropped_after)
            self.canvas.create_image(slider_x, 0, anchor="nw", image=self.tk_img_after)
        
        self.canvas.create_line(slider_x, 0, slider_x, h, fill="white", width=2)
        self.canvas.create_text(10, 10, text="Original", anchor="nw", fill="white", font=("Arial", 12, "bold"))
        self.canvas.create_text(w - 10, 10, text="Compressed", anchor="ne", fill="white", font=("Arial", 12, "bold"))
        self.canvas.create_text(w // 2, 10, text=f"{int(self.zoom_level * 100)}%", fill="yellow", font=("Arial", 10))
        
        # 繪製右下角調整大小控制點
        handle_size = self.resize_handle_size
        # 繪製三角形控制點
        self.canvas.create_polygon(
            w, h - handle_size,
            w, h,
            w - handle_size, h,
            fill="#4CAF50", outline="white", width=1
        )
        # 繪製斜線紋理表示可拖曳
        for i in range(3):
            offset = 5 + i * 5
            self.canvas.create_line(
                w - offset, h,
                w, h - offset,
                fill="white", width=1
            )
        
        # 如果正在拖曳調整大小，顯示目標尺寸
        if self.resize_mode and self.resize_target_size:
            target_w, target_h = self.resize_target_size
            size_text = f"{target_w} x {target_h}"
            # 在右下角控制點上方顯示尺寸
            box_w = 120  # 背景框寬度
            box_h = 24   # 背景框高度
            box_x = w - handle_size - box_w - 5
            box_y = h - handle_size - box_h - 5
            # 繪製背景框讓文字更清晰
            self.canvas.create_rectangle(
                box_x, box_y,
                box_x + box_w, box_y + box_h,
                fill="#333333", outline="#4CAF50", width=2
            )
            self.canvas.create_text(
                box_x + box_w // 2, box_y + box_h // 2,
                text=size_text, anchor="center",
                fill="#4CAF50", font=("Arial", 11, "bold")
            )
        
        self.canvas.config(scrollregion=(0, 0, w, h))

    def update_info_label(self):
        if self.current_index is None: return
        item = self.items[self.current_index]
        if item.original_size == 0: return
        
        ratio = (1 - (item.compressed_size / item.original_size)) * 100
        text = f"原始: {item.original_size/1024:.1f} KB -> 壓縮後: {item.compressed_size/1024:.1f} KB (節省 {ratio:.1f}%)"
        self.info_label.configure(text=text)

    def show_traceback(self, tb_text, title="錯誤詳細"):
        dlg = tk.Toplevel(self.root)
        dlg.title(title)
        dlg.geometry('700x400')
        frm = ttk.Frame(dlg, padding=6)
        frm.pack(fill='both', expand=True)
        text = tk.Text(frm, wrap='none')
        text.insert('1.0', tb_text)
        text.configure(state='disabled')
        text.pack(side='left', fill='both', expand=True)
        v = ttk.Scrollbar(frm, orient='vertical', command=text.yview)
        v.pack(side='right', fill='y')
        text['yscrollcommand'] = v.set
        btn_frame = ttk.Frame(dlg)
        btn_frame.pack(fill='x')
        def save_log():
            p = filedialog.asksaveasfilename(defaultextension='.log', filetypes=[('Log','*.log'),('Text','*.txt')])
            if p:
                with open(p, 'w', encoding='utf-8') as f: f.write(tb_text)
        ttk.Button(btn_frame, text='另存為...', command=save_log).pack(side='left', padx=6, pady=6)
        ttk.Button(btn_frame, text='關閉', command=dlg.destroy).pack(side='right', padx=6, pady=6)

    def save_image(self):
        if self.current_index is None: return
        item = self.items[self.current_index]
        ext_map = {"JPEG": ".jpg", "PNG": ".png", "WEBP": ".webp"}
        path = filedialog.asksaveasfilename(defaultextension=ext_map.get(item.format, ".jpg"), filetypes=[(item.format, f"*{ext_map.get(item.format)}")])
        if path:
            try:
                effective_quality = 100 if item.convert_only else item.quality
                
                # Apply watermark if enabled
                img_to_save = item.original_pil
                if item.watermark.enabled:
                    img_to_save = image_utils.apply_watermark(item.original_pil.copy(), item.watermark)
                
                image_utils.save_image_to_file(img_to_save, path, item.format, effective_quality)
                messagebox.showinfo("成功", "圖片已儲存！")
            except Exception as e:
                messagebox.showerror("錯誤", f"儲存失敗: {e}")

    def batch_download(self):
        if not self.items: return
        zip_path = filedialog.asksaveasfilename(defaultextension='.zip', filetypes=[('ZIP', '*.zip')])
        if not zip_path: return
        
        # 建立進度對話框
        progress_dlg = tk.Toplevel(self.root)
        progress_dlg.title("批次處理中...")
        progress_dlg.geometry("400x150")
        progress_dlg.resizable(False, False)
        progress_dlg.transient(self.root)
        progress_dlg.grab_set()
        
        # 進度標籤
        progress_label = ttk.Label(progress_dlg, text="準備中...", font=("Arial", 10))
        progress_label.pack(pady=(20, 10))
        
        # 進度條
        progress_var = tk.DoubleVar(value=0)
        progress_bar = ttk.Progressbar(progress_dlg, variable=progress_var, maximum=100, length=350, mode='determinate')
        progress_bar.pack(pady=10, padx=20)
        
        # 詳細資訊
        detail_label = ttk.Label(progress_dlg, text="", foreground="gray")
        detail_label.pack(pady=5)
        
        def on_progress(current, total, name):
            """進度回調，在主執行緒更新 UI"""
            def update():
                if total > 0:
                    percent = (current / total) * 100
                    progress_var.set(percent)
                    progress_label.configure(text=f"處理中... ({current}/{total})")
                    detail_label.configure(text=name)
            self.root.after(0, update)
        
        def on_complete(path, errors):
            def finish():
                progress_dlg.destroy()
                if errors:
                    messagebox.showwarning('完成（部分失敗）', f'已建立 {path}\n但有 {len(errors)} 個失敗。')
                    self.show_traceback('\n'.join(errors), '批次處理錯誤清單')
                else:
                    messagebox.showinfo('完成', f'已建立 {path}')
            self.root.after(0, finish)

        AppLogic.batch_download(list(self.items), zip_path, on_complete, on_progress)
