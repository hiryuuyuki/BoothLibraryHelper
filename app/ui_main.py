import os
import re
import sys
import subprocess
import webbrowser
import threading
from math import ceil
from pathlib import Path
from datetime import datetime
import tkinter as tk
from tkinter import filedialog, messagebox
from tkinter import ttk

from app.storage import scan_dl_folder
from app.logger import get_logger
from app.settings import set_last_dl_folder, get_last_dl_folder, get_ui_state, set_ui_state
from app.utils import (
    apply_purchase_import_json,
    build_purchase_json_from_urls_and_html,
    build_purchase_json_from_html_files,
    build_public_item_url,
)

logger = get_logger(__name__)

# Viewerは実装は残すが、ボタンはデフォルト非表示
SHOW_VIEWER_BUTTON = False

# Thumbnail tuning (middle-by-default)
THUMB_SCALE = 0.88   # was 0.92 (a bit too large)
THUMB_MIN = 256
THUMB_MAX = 608
THUMB_STEP = 32

# Auto scan delay after UI shows (ms)
AUTO_SCAN_DELAY_MS = 300

# Filter apply throttle (ms)
FILTER_APPLY_DELAY_MS = 180

# UI state save throttle (ms)
UI_STATE_SAVE_DELAY_MS = 800


class MainUI:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("BoothLibraryHelper")

        self.main_frame = tk.Frame(root, padx=12, pady=12)
        self.main_frame.pack(fill=tk.BOTH, expand=True)

        self._metadata = None
        self._current_root_folder = None

        # scan state
        self._scan_in_progress = False

        # ----------------------------
        # Card view state (virtualized)
        # ----------------------------
        self._items_all = []
        self._items = []  # visible items after filter/sort
        self._cards = []  # pool list[dict]
        self._selected_path = None

        # selection index map (rebuilt on filter apply)
        self._items_index_map = {}

        # UI state persistence
        self._ui_save_after_id = None
        try:
            self._ui_state = get_ui_state()
        except Exception:
            self._ui_state = {}
        if not isinstance(self._ui_state, dict):
            self._ui_state = {}

        # Close handler (save UI state)
        try:
            self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        except Exception:
            pass

        # (abs_thumb_path, size) -> PhotoImage
        self._img_cache = {}
        self._thumb_queue = []          # list[tuple[path,size]]
        self._thumb_waiting = set()     # set[tuple[path,size]]
        self._thumb_after_id = None

        self._layout_after_id = None

        # refresh throttling (wheel spam safe)
        self._refresh_after_id = None
        self._refresh_force_pending = False

        # filter throttling
        self._filter_after_id = None
        self._base_summary_text = ""
        self._sort_desc = False

        # Layout constants
        self._card_min_width = 300
        self._card_pad = 10

        # dynamic per relayout
        self._thumb_px = 288
        self._card_height = 520
        self._cols = 1
        self._card_w = self._card_min_width

        # scroll refresh throttling (row-based)
        self._last_first_row = -1
        self._last_cols = -1
        self._last_thumb_px = -1

        # ----------------------------
        # Top controls
        # ----------------------------
        self.status_label = tk.Label(self.main_frame, text="未選択", anchor="w")
        self.status_label.pack(fill=tk.X)

        self.summary_label = tk.Label(self.main_frame, text="", anchor="w")
        self.summary_label.pack(fill=tk.X, pady=(2, 6))

        self.select_button = tk.Button(
            self.main_frame,
            text="DLフォルダを選択してスキャン",
            command=self.select_and_scan_folder,
            height=2,
        )
        self.select_button.pack(fill=tk.X)

        # --- Last folder quick-scan (new) ---
        self._last_folder = None
        try:
            self._last_folder = get_last_dl_folder()
        except Exception:
            self._last_folder = None

        self.last_folder_label = tk.Label(self.main_frame, text="", anchor="w")
        self.last_scan_button = tk.Button(
            self.main_frame,
            text="前回DLフォルダでスキャン",
            command=self.scan_last_folder,
            height=1,
        )

        if self._last_folder:
            disp_last = self._last_folder.replace("\\", "/")
            self.last_folder_label.config(text=f"前回DLフォルダ: {disp_last}")
            self.last_folder_label.pack(fill=tk.X, pady=(6, 0))
            self.last_scan_button.pack(fill=tk.X, pady=(4, 0))
        else:
            # keep spacing consistent
            tk.Frame(self.main_frame, height=2).pack(fill=tk.X, pady=(6, 0))

        # 起動直後にもう一度反映（設定の修正直後でもUIが空白にならないように）
        self.root.after(0, self._refresh_last_folder_ui)

        self.gen_text_button = tk.Button(
            self.main_frame,
            text="購入一覧(URL入力) → JSON自動生成",
            command=self.generate_purchase_json_from_text,
            height=1,
        )
        self.gen_text_button.pack(fill=tk.X, pady=(6, 0))

        self.gen_html_button = tk.Button(
            self.main_frame,
            text="購入一覧(HTMLファイル選択) → JSON自動生成",
            command=self.generate_purchase_json_from_html,
            height=1,
        )
        self.gen_html_button.pack(fill=tk.X, pady=(4, 0))

        self.import_button = tk.Button(
            self.main_frame,
            text="purchase_import.json を読み込んで metadata.json に反映",
            command=self.import_purchase_json,
            height=1,
        )
        self.import_button.pack(fill=tk.X, pady=(4, 8))

        # Viewer button (keep code, default hide)
        self.viewer_button = tk.Button(
            self.main_frame,
            text="Viewer (PySide6) を開く",
            command=self.open_viewer,
            height=1,
        )
        if SHOW_VIEWER_BUTTON:
            self.viewer_button.pack(fill=tk.X, pady=(0, 10))
        else:
            tk.Frame(self.main_frame, height=2).pack(fill=tk.X, pady=(0, 10))

        # ----------------------------
        # Filter / Search / Sort bar (minimal UI)
        # ----------------------------
        bar = tk.Frame(self.main_frame)
        bar.pack(fill=tk.X, pady=(0, 8))

        tk.Label(bar, text="検索", anchor="w").pack(side=tk.LEFT)

        self.search_var = tk.StringVar(value="")
        self.search_entry = ttk.Entry(bar, textvariable=self.search_var, width=28)
        self.search_entry.pack(side=tk.LEFT, padx=(6, 6))

        self.clear_search_btn = tk.Button(bar, text="×", width=2, command=self._clear_search)
        self.clear_search_btn.pack(side=tk.LEFT, padx=(0, 10))

        self.filter_var = tk.StringVar(value="すべて")
        self.filter_combo = ttk.Combobox(
            bar,
            textvariable=self.filter_var,
            state="readonly",
            width=9,
            values=("すべて", "ZIPあり", "文書あり", "ソースあり", "画像あり", "サムネ無し", "購入情報無し"),
        )
        self.filter_combo.pack(side=tk.LEFT)

        tk.Label(bar, text="並び", anchor="w").pack(side=tk.LEFT, padx=(12, 0))

        self.sort_var = tk.StringVar(value="タイトル")
        self.sort_combo = ttk.Combobox(
            bar,
            textvariable=self.sort_var,
            state="readonly",
            width=10,
            values=("タイトル", "ID", "購入日", "ZIP数", "文書数", "画像数"),
        )
        self.sort_combo.pack(side=tk.LEFT)

        self.sort_dir_btn = tk.Button(bar, text="▲", width=2, command=self._toggle_sort_dir)
        self.sort_dir_btn.pack(side=tk.LEFT, padx=(6, 0))

        # Restore UI state (search/filter/sort) if present
        try:
            st = self._ui_state if isinstance(self._ui_state, dict) else {}
            q0 = st.get("search")
            if isinstance(q0, str):
                self.search_var.set(q0)
            m0 = st.get("filter")
            if isinstance(m0, str) and m0 in ("すべて", "ZIPあり", "文書あり", "ソースあり", "画像あり", "サムネ無し", "購入情報無し"):
                self.filter_var.set(m0)
            s0 = st.get("sort")
            if isinstance(s0, str) and s0 in ("タイトル", "ID", "購入日", "ZIP数", "文書数", "画像数"):
                self.sort_var.set(s0)
            d0 = st.get("sort_desc")
            self._sort_desc = bool(d0)
            self.sort_dir_btn.config(text="▼" if self._sort_desc else "▲")
        except Exception:
            pass

        # Events (throttled apply)
        self.search_entry.bind("<KeyRelease>", self._on_search_key)
        self.filter_combo.bind("<<ComboboxSelected>>", lambda e: self._apply_filters(reset_scroll=True))
        self.sort_combo.bind("<<ComboboxSelected>>", lambda e: self._apply_filters(reset_scroll=True))

        # Shortcuts
        self.root.bind_all("<Control-f>", self._on_ctrl_f, add="+")
        self.root.bind_all("<Escape>", self._on_escape, add="+")
        # Keyboard navigation (cards)
        self.root.bind_all("<Left>", lambda e: self._nav_move(e, dx=-1, dy=0), add="+")
        self.root.bind_all("<Right>", lambda e: self._nav_move(e, dx=1, dy=0), add="+")
        self.root.bind_all("<Up>", lambda e: self._nav_move(e, dx=0, dy=-1), add="+")
        self.root.bind_all("<Down>", lambda e: self._nav_move(e, dx=0, dy=1), add="+")
        self.root.bind_all("<Home>", self._nav_home, add="+")
        self.root.bind_all("<End>", self._nav_end, add="+")
        self.root.bind_all("<Return>", self._on_enter_open_folder, add="+")
        self.root.bind_all("<Control-Return>", self._on_ctrl_enter_open_url, add="+")

        # Context menu (right-click)
        self._ctx_menu = tk.Menu(self.root, tearoff=0)
        self._ctx_menu.add_command(label="フォルダを開く", command=self._ctx_open_folder)
        self._ctx_menu.add_command(label="商品ページを開く", command=self._ctx_open_url)
        self._ctx_menu.add_separator()
        self._ctx_menu.add_command(label="パスをコピー", command=self._ctx_copy_path)
        self._ctx_menu.add_command(label="URLをコピー", command=self._ctx_copy_url)
        self._ctx_menu.add_command(label="タイトルをコピー", command=self._ctx_copy_title)

        # ----------------------------
        # Cards area (Canvas + Scroll)
        # ----------------------------
        self.cards_frame = tk.Frame(self.main_frame)
        self.cards_frame.pack(fill=tk.BOTH, expand=True)

        self.canvas = tk.Canvas(self.cards_frame, highlightthickness=0, borderwidth=0)
        self.v_scroll = ttk.Scrollbar(self.cards_frame, orient=tk.VERTICAL, command=self._on_scrollbar)
        self.canvas.configure(yscrollcommand=self.v_scroll.set)

        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.v_scroll.pack(side=tk.RIGHT, fill=tk.Y)

        # Mouse wheel
        self.root.bind_all("<MouseWheel>", self._on_mousewheel_all, add="+")  # Windows

        # Resize relayout (throttle)
        self.canvas.bind("<Configure>", self._on_canvas_configure)
        self.root.bind("<Configure>", self._on_resize)

        # auto scan last folder if exists
        self.root.after(AUTO_SCAN_DELAY_MS, self._auto_scan_start)

    # ----------------------------
    # UI state persistence
    # ----------------------------
    def _collect_ui_state(self) -> dict:
        try:
            q = str(self.search_var.get() or "")
        except Exception:
            q = ""
        try:
            mode = str(self.filter_var.get() or "すべて")
        except Exception:
            mode = "すべて"
        try:
            sort_key = str(self.sort_var.get() or "タイトル")
        except Exception:
            sort_key = "タイトル"

        return {
            "search": q,
            "filter": mode,
            "sort": sort_key,
            "sort_desc": bool(self._sort_desc),
        }

    def _schedule_save_ui_state(self, delay_ms: int = UI_STATE_SAVE_DELAY_MS):
        try:
            if self._ui_save_after_id:
                self.root.after_cancel(self._ui_save_after_id)
        except Exception:
            pass
        try:
            self._ui_save_after_id = self.root.after(int(delay_ms), self._save_ui_state_now)
        except Exception:
            self._ui_save_after_id = None

    def _save_ui_state_now(self):
        self._ui_save_after_id = None
        try:
            st = self._collect_ui_state()
            set_ui_state(st)
        except Exception:
            pass

    def _on_close(self):
        # save ui state first, then close
        try:
            self._save_ui_state_now()
        except Exception:
            pass
        try:
            self.root.destroy()
        except Exception:
            pass

    # ----------------------------
    # Keyboard navigation
    # ----------------------------
    def _is_text_input_focused(self, widget) -> bool:
        try:
            if widget is self.search_entry:
                return True
            cls = widget.winfo_class()
            return cls in ("Entry", "TEntry", "Text")
        except Exception:
            return False

    def _nav_home(self, event=None):
        if self._is_text_input_focused(getattr(event, "widget", None)):
            return
        if not self._items:
            return
        self._select_by_index(0)

    def _nav_end(self, event=None):
        if self._is_text_input_focused(getattr(event, "widget", None)):
            return
        if not self._items:
            return
        self._select_by_index(len(self._items) - 1)

    def _nav_move(self, event, dx: int, dy: int):
        if self._is_text_input_focused(getattr(event, "widget", None)):
            return
        if not self._items:
            return

        cols = max(1, int(self._cols or 1))
        if dy != 0:
            step = dy * cols
        else:
            step = dx

        cur = 0
        if self._selected_path:
            cur = int(self._items_index_map.get(self._selected_path, 0) or 0)

        self._select_by_index(cur + step)

    def _select_by_index(self, idx: int):
        if not self._items:
            return
        try:
            idx = int(idx)
        except Exception:
            idx = 0
        idx = max(0, min(len(self._items) - 1, idx))

        it = self._items[idx]
        if not isinstance(it, dict):
            return
        p = self._norm_path(str(it.get("path") or ""))
        if not p:
            return

        self._select_card(p)
        self._ensure_index_visible(idx)
        self._schedule_refresh_visible(force=True)

    def _ensure_index_visible(self, idx: int):
        # scroll so that the row containing idx is visible
        try:
            cols = max(1, int(self._cols or 1))
            pad = int(self._card_pad)
            row = int(idx // cols)
            row_span = int(self._card_height + pad)
            target_y = pad + row * row_span

            sr = str(self.canvas.cget("scrollregion") or "").strip()
            if not sr:
                return
            parts = sr.split()
            if len(parts) != 4:
                return
            y2 = float(parts[3])
            total_h = max(1.0, y2)
            target_y = max(0.0, min(total_h - 1.0, float(target_y)))
            self.canvas.yview_moveto(target_y / total_h)
        except Exception:
            pass

    def _on_enter_open_folder(self, event=None):
        if self._is_text_input_focused(getattr(event, "widget", None)):
            return
        if not self._selected_path:
            return
        self._open_folder(self._selected_path)

    def _on_ctrl_enter_open_url(self, event=None):
        if self._is_text_input_focused(getattr(event, "widget", None)):
            return
        it = self._get_selected_item()
        if not it:
            return
        url = self._get_product_url(it)
        if url:
            self._open_url(url)

    def _get_selected_item(self) -> dict | None:
        if not self._selected_path:
            return None
        idx = self._items_index_map.get(self._selected_path)
        if idx is None:
            return None
        try:
            it = self._items[int(idx)]
        except Exception:
            return None
        return it if isinstance(it, dict) else None

    # ----------------------------
    # Context menu
    # ----------------------------
    def _on_card_right_click(self, event, card: dict):
        try:
            p = card.get("path") or ""
            if p:
                self._select_card(p)
        except Exception:
            pass

        try:
            self._ctx_menu.tk_popup(event.x_root, event.y_root)
        except Exception:
            pass
        finally:
            try:
                self._ctx_menu.grab_release()
            except Exception:
                pass

    def _copy_to_clipboard(self, s: str):
        try:
            self.root.clipboard_clear()
            self.root.clipboard_append(str(s))
            self.root.update_idletasks()
        except Exception:
            pass

    def _ctx_open_folder(self):
        if self._selected_path:
            self._open_folder(self._selected_path)

    def _ctx_open_url(self):
        it = self._get_selected_item()
        if not it:
            return
        url = self._get_product_url(it)
        if url:
            self._open_url(url)

    def _ctx_copy_path(self):
        if self._selected_path:
            self._copy_to_clipboard(self._selected_path)

    def _ctx_copy_url(self):
        it = self._get_selected_item()
        if not it:
            return
        url = self._get_product_url(it)
        if url:
            self._copy_to_clipboard(url)

    def _ctx_copy_title(self):
        it = self._get_selected_item()
        if not it:
            return
        self._copy_to_clipboard(self._get_display_title(it))

    # --------------
    # Helpers
    # --------------
    def _auto_scan_start(self):
        if self._last_folder:
            self.scan_folder(self._last_folder)

    def _is_digits_id(self, s: str) -> bool:
        return bool(re.fullmatch(r"\d{5,}", s or ""))

    def _guess_product_id(self, it: dict) -> str:
        pid = str(it.get("product_id") or "").strip()
        if self._is_digits_id(pid):
            return pid

        url = str(it.get("product_url") or "").strip()
        m = re.search(r"/items/(\d{5,})", url)
        if m:
            return m.group(1)

        for key in ("purchase_title", "title"):
            txt = str(it.get(key) or "")
            m = re.search(r"\[(\d{5,})\]", txt)
            if m:
                return m.group(1)
            m = re.search(r"/items/(\d{5,})", txt)
            if m:
                return m.group(1)

        p = str(it.get("path") or "").strip()
        base = os.path.basename(p) if p else ""
        m = re.search(r"\[(\d{5,})\]", base)
        if m:
            return m.group(1)

        m = re.search(r"(\d{5,})", base)
        if m:
            return m.group(1)

        return ""

    def _get_display_title(self, it: dict) -> str:
        title = str(it.get("purchase_title") or it.get("title") or "").strip()
        if title:
            return title
        pid = self._guess_product_id(it)
        if pid:
            return f"(untitled) {pid}"
        return "(untitled)"

    def _get_product_url(self, it: dict) -> str:
        url = str(it.get("product_url") or "").strip()
        if url.startswith("http://") or url.startswith("https://"):
            return url
        pid = self._guess_product_id(it)
        if pid:
            return build_public_item_url(pid)
        return ""

    def _norm_path(self, p: str) -> str:
        try:
            return os.path.normpath(p)
        except Exception:
            return str(p or "")

    def _quantize_px(self, px: int, step: int = THUMB_STEP, mn: int = THUMB_MIN, mx: int = THUMB_MAX) -> int:
        px = int(max(mn, min(mx, px)))
        q = int(round(px / step) * step)
        return int(max(mn, min(mx, q)))

    def _set_controls_enabled(self, enabled: bool):
        state = tk.NORMAL if enabled else tk.DISABLED
        for w in (
            self.select_button,
            self.last_scan_button,
            self.gen_text_button,
            self.gen_html_button,
            self.import_button,
        ):
            try:
                w.configure(state=state)
            except Exception:
                pass

    # ----------------------------
    # Filter/Search handlers
    # ----------------------------
    def _on_ctrl_f(self, event=None):
        try:
            self.search_entry.focus_set()
            self.search_entry.selection_range(0, tk.END)
        except Exception:
            pass

    def _on_escape(self, event=None):
        try:
            if str(self.search_var.get() or ""):
                self._clear_search()
        except Exception:
            pass

    def _on_search_key(self, event=None):
        self._schedule_apply_filters(delay_ms=FILTER_APPLY_DELAY_MS)
        self._schedule_save_ui_state()

    def _clear_search(self):
        try:
            self.search_var.set("")
        except Exception:
            pass
        self._schedule_apply_filters(delay_ms=0)
        self._schedule_save_ui_state()

    def _toggle_sort_dir(self):
        self._sort_desc = not bool(self._sort_desc)
        self.sort_dir_btn.config(text="▼" if self._sort_desc else "▲")
        self._apply_filters(reset_scroll=True)
        self._schedule_save_ui_state()

    def _schedule_apply_filters(self, delay_ms: int = FILTER_APPLY_DELAY_MS):
        if self._filter_after_id:
            try:
                self.root.after_cancel(self._filter_after_id)
            except Exception:
                pass
        self._filter_after_id = self.root.after(int(max(0, delay_ms)), lambda: self._apply_filters(reset_scroll=True))

    def _compose_summary_text(self) -> str:
        total = len(self._items_all)
        visible = len(self._items)
        base = str(self._base_summary_text or "").strip()
        if base:
            return f"{base} / 表示: {visible} / 全{total}"
        return f"表示: {visible} / 全{total}"

    def _refresh_last_folder_ui(self):
        """前回DLフォルダ表示を再評価して更新（Tclのバックスラッシュ解釈を避けるため表示は/に寄せる）"""
        try:
            folder = get_last_dl_folder()
        except Exception:
            folder = None

        if isinstance(folder, str) and folder.strip():
            self._last_folder = folder.strip()
            disp = self._last_folder.replace("\\", "/")
            self.last_folder_label.config(text=f"前回DLフォルダ: {disp}")
            if not self.last_folder_label.winfo_ismapped():
                self.last_folder_label.pack(fill=tk.X, pady=(6, 0))
            if not self.last_scan_button.winfo_ismapped():
                self.last_scan_button.pack(fill=tk.X, pady=(4, 0))
        else:
            try:
                self.last_folder_label.pack_forget()
            except Exception:
                pass
            try:
                self.last_scan_button.pack_forget()
            except Exception:
                pass

    # ----------------------------
    # UI actions
    # ----------------------------
    def select_and_scan_folder(self):
        folder = filedialog.askdirectory(title="DLフォルダを選択")
        if folder:
            self.scan_folder(folder)

    def scan_last_folder(self):
        folder = None
        try:
            folder = get_last_dl_folder()
        except Exception:
            folder = None
        if folder:
            self.scan_folder(folder)
        else:
            messagebox.showwarning("情報", "前回DLフォルダが見つかりませんでした。")

    def scan_folder(self, folder: str):
        if self._scan_in_progress:
            return
        if not folder:
            return
        folder = os.path.normpath(folder)

        self._scan_in_progress = True
        self.status_label.config(text=f"スキャン中: {folder}")
        self._set_controls_enabled(False)

        def worker():
            try:
                self._current_root_folder = folder
                set_last_dl_folder(folder)
                items = scan_dl_folder(folder)
                self._metadata = {"items": items}
                self._items_all = items
                self._base_summary_text = f"スキャン完了: {folder}"
                self._apply_filters(reset_scroll=True)
            except Exception as e:
                logger.exception("scan failed: %s", e)
                msg = str(e)
                self.root.after(0, lambda m=msg: messagebox.showerror("エラー", m))
            finally:
                self._scan_in_progress = False
                self.root.after(0, lambda: self._set_controls_enabled(True))
                self.root.after(0, self._refresh_last_folder_ui)

        threading.Thread(target=worker, daemon=True).start()

    def generate_purchase_json_from_text(self):
        # unchanged (existing implementation)
        text = messagebox.askquestion("入力", "購入一覧URL/HTMLをクリップボード経由で生成しますか？\n(OK: クリップボード / キャンセル: ファイル指定)")
        if text == "yes":
            try:
                clip = self.root.clipboard_get()
            except Exception:
                clip = ""
            if not clip.strip():
                messagebox.showwarning("入力", "クリップボードが空です。")
                return
            out_path = filedialog.asksaveasfilename(
                title="purchase_import.json 保存先",
                defaultextension=".json",
                initialfile="purchase_import.json",
                filetypes=[("JSON", "*.json")],
            )
            if not out_path:
                return
            try:
                build_purchase_json_from_urls_and_html(clip, out_path)
                messagebox.showinfo("完了", f"生成しました:\n{out_path}")
            except Exception as e:
                messagebox.showerror("エラー", str(e))
        else:
            messagebox.showinfo("情報", "この機能は既存実装のままです。")

    def generate_purchase_json_from_html(self):
        html_files = filedialog.askopenfilenames(title="購入一覧HTMLを選択", filetypes=[("HTML", "*.html;*.htm"), ("All", "*.*")])
        if not html_files:
            return
        out_path = filedialog.asksaveasfilename(
            title="purchase_import.json 保存先",
            defaultextension=".json",
            initialfile="purchase_import.json",
            filetypes=[("JSON", "*.json")],
        )
        if not out_path:
            return
        try:
            build_purchase_json_from_html_files(list(html_files), out_path)
            messagebox.showinfo("完了", f"生成しました:\n{out_path}")
        except Exception as e:
            messagebox.showerror("エラー", str(e))

    def import_purchase_json(self):
        if not self._current_root_folder:
            messagebox.showwarning("情報", "先にDLフォルダをスキャンしてください。")
            return
        json_path = filedialog.askopenfilename(title="purchase_import.json を選択", filetypes=[("JSON", "*.json"), ("All", "*.*")])
        if not json_path:
            return
        try:
            updated, matched, total = apply_purchase_import_json(self._current_root_folder, json_path)
            messagebox.showinfo("完了", f"反映完了: 更新 {updated} 件 / マッチ {matched} 件 / 総 {total} 件")
            items = scan_dl_folder(self._current_root_folder)
            self._metadata = {"items": items}
            self._items_all = items
            self._base_summary_text = f"スキャン完了: {self._current_root_folder}"
            self._apply_filters(reset_scroll=True)
        except Exception as e:
            messagebox.showerror("エラー", str(e))

    def open_viewer(self):
        # viewer.py is not present; keep behavior
        viewer_path = Path(__file__).resolve().parent.parent / "viewer.py"
        if not viewer_path.exists():
            messagebox.showwarning("Viewer", f"viewer.py が見つかりません:\n{viewer_path}")
            return

        try:
            subprocess.Popen([sys.executable, str(viewer_path)], cwd=str(viewer_path.parent))
        except Exception as e:
            messagebox.showerror("エラー", str(e))

    # ----------------------------
    # Filtering / Sorting
    # ----------------------------
    def _apply_filters(self, reset_scroll: bool = False):
        if self._filter_after_id:
            self._filter_after_id = None

        items = self._items_all if isinstance(self._items_all, list) else []
        q = ""
        try:
            q = str(self.search_var.get() or "").strip().lower()
        except Exception:
            q = ""

        mode = ""
        try:
            mode = str(self.filter_var.get() or "すべて")
        except Exception:
            mode = "すべて"

        sort_key = ""
        try:
            sort_key = str(self.sort_var.get() or "タイトル")
        except Exception:
            sort_key = "タイトル"

        def _has_zip(it: dict) -> bool:
            return int(it.get("zip_count") or 0) > 0

        def _has_docs(it: dict) -> bool:
            return int(it.get("doc_count") or 0) > 0

        def _has_source(it: dict) -> bool:
            return int(it.get("source_count") or 0) > 0

        def _has_img(it: dict) -> bool:
            return int(it.get("image_count") or 0) > 0

        def _has_thumb(it: dict) -> bool:
            t = it.get("thumbnail")
            return isinstance(t, str) and bool(t.strip())

        def _has_purchase_info(it: dict) -> bool:
            return bool(str(it.get("purchase_title") or "").strip())

        filtered = []
        for it in items:
            if not isinstance(it, dict):
                continue

            title = self._get_display_title(it).lower()
            pid = self._guess_product_id(it)
            path = str(it.get("path") or "")
            if q:
                if (q not in title) and (q not in str(pid)) and (q not in path.lower()):
                    continue

            if mode == "ZIPあり" and not _has_zip(it):
                continue
            if mode == "文書あり" and not _has_docs(it):
                continue
            if mode == "ソースあり" and not _has_source(it):
                continue
            if mode == "画像あり" and not _has_img(it):
                continue
            if mode == "サムネ無し" and _has_thumb(it):
                continue
            if mode == "購入情報無し" and _has_purchase_info(it):
                continue

            filtered.append(it)

        # sort
        def _key_title(it: dict):
            return self._get_display_title(it).lower()

        def _key_id(it: dict):
            pid = self._guess_product_id(it)
            try:
                return int(pid)
            except Exception:
                return 0

        def _key_date(it: dict):
            s = str(it.get("purchased_at") or "")
            return s or ""

        def _key_zip(it: dict):
            return int(it.get("zip_count") or 0)

        def _key_docs(it: dict):
            return int(it.get("doc_count") or 0)

        def _key_img(it: dict):
            return int(it.get("image_count") or 0)

        try:
            if sort_key == "タイトル":
                filtered.sort(key=_key_title, reverse=bool(self._sort_desc))
            elif sort_key == "ID":
                filtered.sort(key=_key_id, reverse=bool(self._sort_desc))
            elif sort_key == "購入日":
                filtered.sort(key=_key_date, reverse=bool(self._sort_desc))
            elif sort_key == "ZIP数":
                filtered.sort(key=_key_zip, reverse=bool(self._sort_desc))
            elif sort_key == "文書数":
                filtered.sort(key=_key_docs, reverse=bool(self._sort_desc))
            elif sort_key == "画像数":
                filtered.sort(key=_key_img, reverse=bool(self._sort_desc))
        except Exception:
            pass

        self._items = filtered

        # rebuild index map for keyboard navigation
        try:
            self._items_index_map = {}
            for i, it in enumerate(self._items):
                if not isinstance(it, dict):
                    continue
                p = self._norm_path(str(it.get("path") or ""))
                if p:
                    self._items_index_map[p] = i
        except Exception:
            self._items_index_map = {}

        # persist UI state (throttled)
        self._schedule_save_ui_state()

        # selection might become invisible
        if self._selected_path:
            exists = any(self._norm_path(it.get("path", "")) == self._selected_path for it in self._items)
            if not exists:
                self._selected_path = None

        # refresh summary
        try:
            self.summary_label.config(text=self._compose_summary_text())
        except Exception:
            pass

        if reset_scroll:
            try:
                self.canvas.yview_moveto(0.0)
            except Exception:
                pass

        self._relayout_cards()

    # ----------------------------
    # Virtualized cards rendering
    # ----------------------------
    def _on_scrollbar(self, *args):
        try:
            self.canvas.yview(*args)
        except Exception:
            return
        self._schedule_refresh_visible(force=False)

    def _on_mousewheel_all(self, event):
        try:
            delta = int(-1 * (event.delta / 120))
        except Exception:
            delta = 0
        if delta == 0:
            return
        try:
            self.canvas.yview_scroll(delta, "units")
        except Exception:
            return
        self._schedule_refresh_visible(force=False)

    def _on_canvas_configure(self, event):
        self._schedule_relayout()

    def _on_resize(self, event):
        self._schedule_relayout()

    def _schedule_relayout(self):
        if self._layout_after_id:
            try:
                self.root.after_cancel(self._layout_after_id)
            except Exception:
                pass
        self._layout_after_id = self.root.after(120, self._relayout_cards)

    def _schedule_refresh_visible(self, force: bool):
        if force:
            self._refresh_force_pending = True
        if self._refresh_after_id:
            return
        self._refresh_after_id = self.root.after(45, self._do_refresh_visible)

    def _do_refresh_visible(self):
        self._refresh_after_id = None
        force = bool(self._refresh_force_pending)
        self._refresh_force_pending = False
        self._refresh_visible_cards(force=force)
        self._update_visible_thumbnails_only()

    def _select_card(self, path: str):
        self._selected_path = path
        for c in self._cards:
            if c.get("path") == path:
                c["frame"].configure(highlightbackground="#4a90e2", highlightcolor="#4a90e2")
            else:
                c["frame"].configure(highlightbackground="#dddddd", highlightcolor="#dddddd")

    def _calc_columns(self, width: int) -> int:
        if width <= 0:
            return 1
        cols = max(1, int(width // self._card_min_width))
        return min(4, cols)

    def _relayout_cards(self):
        if not self._items:
            self.canvas.configure(scrollregion=(0, 0, 0, 0))
            return

        width = self.canvas.winfo_width()
        height = self.canvas.winfo_height()
        if width <= 10:
            width = self.root.winfo_width()
        if height <= 10:
            height = self.root.winfo_height()

        cols = self._calc_columns(width)
        pad = self._card_pad

        usable = max(1, width - pad * (cols + 1))
        card_w = max(self._card_min_width, int(usable / cols))

        raw_thumb = int(card_w * THUMB_SCALE)
        thumb_px = self._quantize_px(raw_thumb, step=THUMB_STEP, mn=THUMB_MIN, mx=THUMB_MAX)

        card_h = int(max(420, thumb_px + 210))

        old_thumb = self._thumb_px

        self._cols = cols
        self._card_w = card_w
        self._thumb_px = thumb_px
        self._card_height = card_h

        if old_thumb != thumb_px:
            self._thumb_queue = []
            self._thumb_waiting = set()

        row_span = card_h + pad
        visible_rows = max(1, int(height // max(1, row_span)) + 2)
        desired_pool = min(len(self._items), cols * visible_rows)
        self._ensure_pool_size(desired_pool)

        for c in self._cards:
            try:
                c["frame"].configure(width=card_w, height=card_h)
                c["frame"].pack_propagate(False)
            except Exception:
                pass

        total_rows = int(ceil(len(self._items) / cols))
        total_h = pad + total_rows * (card_h + pad)
        self.canvas.configure(scrollregion=(0, 0, width, total_h))

        self._refresh_visible_cards(force=True)
        self._update_visible_thumbnails_only()

    def _ensure_pool_size(self, desired: int):
        while len(self._cards) < max(desired, 10):
            self._cards.append(self._create_pool_card())

        while len(self._cards) > max(desired, 10):
            c = self._cards.pop()
            try:
                self.canvas.delete(c["window_id"])
            except Exception:
                pass
            try:
                c["frame"].destroy()
            except Exception:
                pass

    def _create_pool_card(self):
        frame = tk.Frame(
            self.canvas,
            bd=1,
            relief="solid",
            padx=10,
            pady=8,
            highlightthickness=2,
            highlightbackground="#dddddd",
            highlightcolor="#dddddd",
        )
        frame.pack_propagate(False)

        title_label = tk.Label(frame, text="", anchor="w", justify="left", font=("Segoe UI", 10, "bold"))
        title_label.pack(fill=tk.X)

        id_label = tk.Label(frame, text="", anchor="w", justify="left")
        id_label.pack(fill=tk.X, pady=(4, 0))

        thumb_box = tk.Frame(frame)
        thumb_box.pack(fill=tk.X, pady=(8, 0))

        thumb_label = tk.Label(thumb_box, text="(thumbnail)", width=1)
        thumb_label.pack()

        counts_label = tk.Label(frame, text="", anchor="w")
        counts_label.pack(fill=tk.X, pady=(8, 0))

        btn_row = tk.Frame(frame)
        btn_row.pack(fill=tk.X, pady=(8, 0))

        open_btn = tk.Button(btn_row, text="フォルダ", height=1, width=10, state=tk.DISABLED)
        open_btn.pack(side=tk.LEFT)

        link_btn = tk.Button(btn_row, text="商品ページ", height=1, width=10, state=tk.DISABLED)
        link_btn.pack(side=tk.LEFT, padx=(8, 0))

        path_label = tk.Label(frame, text="", anchor="w", justify="left")
        path_label.pack(fill=tk.X, pady=(8, 0))

        card = {
            "frame": frame,
            "window_id": None,
            "data": None,
            "idx": None,
            "path": "",
            "url": "",
            "title_label": title_label,
            "id_label": id_label,
            "thumb_label": thumb_label,
            "thumb_box": thumb_box,
            "counts_label": counts_label,
            "open_btn": open_btn,
            "link_btn": link_btn,
            "path_label": path_label,
        }

        def _bind_click(widget):
            widget.bind("<Button-1>", lambda e, c=card: self._on_card_clicked(c))
            widget.bind("<Double-Button-1>", lambda e, c=card: self._open_folder(c.get("path") or ""))
            widget.bind("<Button-3>", lambda e, c=card: self._on_card_right_click(e, c))

        # NOTE: do NOT bind btn_row / buttons
        _bind_click(frame)
        for w in (title_label, id_label, thumb_box, thumb_label, counts_label, path_label):
            _bind_click(w)

        win_id = self.canvas.create_window(0, 0, window=frame, anchor="nw")
        card["window_id"] = win_id
        return card

    def _on_card_clicked(self, card: dict):
        p = card.get("path") or ""
        if p:
            self._select_card(p)

    def _assign_card(self, card: dict, idx: int, it: dict, card_w: int, thumb_px: int, force: bool):
        if (not force) and card.get("idx") == idx:
            return

        card["idx"] = idx
        card["data"] = it

        path = str(it.get("path") or "")
        path = self._norm_path(path)
        card["path"] = path

        title = self._get_display_title(it)
        url = self._get_product_url(it)
        card["url"] = url

        pid = self._guess_product_id(it)
        if pid:
            id_text = f"ID: {pid}"
        else:
            id_text = ""

        zip_count = int(it.get("zip_count") or 0)
        doc_count = int(it.get("doc_count") or 0)
        src_count = int(it.get("source_count") or 0)
        img_count = int(it.get("image_count") or 0)

        purchased_at = str(it.get("purchased_at") or "").strip()
        if purchased_at:
            try:
                dt = datetime.fromisoformat(purchased_at.replace("Z", "+00:00"))
                purchased_text = dt.strftime("%Y-%m-%d")
            except Exception:
                purchased_text = purchased_at
        else:
            purchased_text = ""

        counts_text = f"ZIP: {zip_count} / 文書: {doc_count} / ソース: {src_count} / 画像: {img_count}"
        if purchased_text:
            counts_text += f" / 購入日: {purchased_text}"

        try:
            card["title_label"].configure(text=title)
            card["id_label"].configure(text=id_text)
            card["counts_label"].configure(text=counts_text)
            card["path_label"].configure(text=path.replace("\\", "/"))
        except Exception:
            pass

        try:
            if path and os.path.exists(path):
                card["open_btn"].configure(state=tk.NORMAL, command=lambda p=path: self._open_folder(p))
            else:
                card["open_btn"].configure(state=tk.DISABLED, command=lambda: None)
        except Exception:
            pass

        try:
            if url:
                card["link_btn"].configure(state=tk.NORMAL, command=lambda u=url: self._open_url(u))
            else:
                card["link_btn"].configure(state=tk.DISABLED, command=lambda: None)
        except Exception:
            pass

        # thumbnail
        thumb_rel = it.get("thumbnail")
        if isinstance(thumb_rel, str) and thumb_rel.strip():
            thumb_path = os.path.join(path, thumb_rel.strip())
            key = (thumb_path, int(thumb_px))
            img = self._img_cache.get(key)
            if img:
                try:
                    card["thumb_label"].configure(image=img, text="")
                except Exception:
                    pass
            else:
                try:
                    card["thumb_label"].configure(image="", text="(thumbnail)")
                except Exception:
                    pass
                self._queue_thumb(thumb_path, int(thumb_px))
        else:
            try:
                card["thumb_label"].configure(text="(no thumb)", image="")
            except Exception:
                pass

        if self._selected_path and path == self._selected_path:
            card["frame"].configure(highlightbackground="#4a90e2", highlightcolor="#4a90e2")
        else:
            card["frame"].configure(highlightbackground="#dddddd", highlightcolor="#dddddd")

    def _open_folder(self, path: str):
        try:
            if os.path.exists(path):
                os.startfile(path)
        except Exception:
            logger.exception("フォルダを開けませんでした: %s", path)

    def _open_url(self, url: str):
        try:
            if url:
                webbrowser.open(url)
        except Exception:
            logger.exception("URLを開けませんでした: %s", url)

    def _refresh_visible_cards(self, force: bool = False):
        if not self._items or not self._cards:
            return

        pad = self._card_pad
        cols = max(1, self._cols)
        card_w = self._card_w
        card_h = self._card_height
        thumb_px = self._thumb_px

        try:
            y0 = self.canvas.canvasy(0)
        except Exception:
            y0 = 0

        first_row = max(0, int((y0 - pad) // max(1, (card_h + pad))))
        if not force:
            if first_row == self._last_first_row and cols == self._last_cols and thumb_px == self._last_thumb_px:
                return

        self._last_first_row = first_row
        self._last_cols = cols
        self._last_thumb_px = thumb_px

        visible_count = len(self._cards)
        start_idx = first_row * cols
        end_idx = min(len(self._items), start_idx + visible_count)

        # place pool cards
        pool_i = 0
        for idx in range(start_idx, end_idx):
            it = self._items[idx]
            if not isinstance(it, dict):
                continue

            r = idx // cols
            c = idx % cols
            x = pad + c * (card_w + pad)
            y = pad + r * (card_h + pad)

            card = self._cards[pool_i]
            pool_i += 1

            self._assign_card(card, idx, it, card_w, thumb_px, force=force)

            try:
                self.canvas.coords(card["window_id"], x, y)
                self.canvas.itemconfigure(card["window_id"], state="normal")
            except Exception:
                pass

        # hide remaining
        for j in range(pool_i, len(self._cards)):
            card = self._cards[j]
            try:
                self.canvas.itemconfigure(card["window_id"], state="hidden")
            except Exception:
                pass

    def _queue_thumb(self, abs_path: str, size: int):
        key = (abs_path, int(size))
        if key in self._thumb_waiting:
            return
        self._thumb_waiting.add(key)
        self._thumb_queue.append(key)

        if not self._thumb_after_id:
            self._thumb_after_id = self.root.after(12, self._process_thumb_queue)

    def _process_thumb_queue(self):
        self._thumb_after_id = None
        if not self._thumb_queue:
            return

        # pop a few per tick
        batch = []
        while self._thumb_queue and len(batch) < 6:
            batch.append(self._thumb_queue.pop(0))

        for abs_path, size in batch:
            self._thumb_waiting.discard((abs_path, size))
            img = self._get_tk_image(abs_path, max_size=int(size))
            if img:
                self._img_cache[(abs_path, int(size))] = img

        self._update_visible_thumbnails_only()

        if self._thumb_queue:
            self._thumb_after_id = self.root.after(16, self._process_thumb_queue)

    def _update_visible_thumbnails_only(self):
        if not self._cards:
            return
        thumb_px = int(self._thumb_px)

        for c in self._cards:
            if not c.get("data"):
                continue
            it = c.get("data")
            if not isinstance(it, dict):
                continue
            path = c.get("path") or ""
            if not path:
                continue

            thumb_rel = it.get("thumbnail")
            if not isinstance(thumb_rel, str) or not thumb_rel.strip():
                continue

            thumb_path = os.path.join(path, thumb_rel.strip())
            key = (thumb_path, thumb_px)
            img = self._img_cache.get(key)
            if img:
                try:
                    c["thumb_label"].configure(image=img, text="")
                except Exception:
                    pass
            else:
                self._queue_thumb(thumb_path, thumb_px)

    def _get_tk_image(self, abs_path: str, max_size: int = 288):
        if not abs_path or not os.path.exists(abs_path):
            return None

        ext = os.path.splitext(abs_path)[1].lower()
        try:
            from PIL import Image, ImageTk, ImageOps  # type: ignore

            img = Image.open(abs_path)
            img = ImageOps.exif_transpose(img)

            size = int(max_size) if int(max_size) > 0 else 288

            if img.mode not in ("RGB", "RGBA"):
                img = img.convert("RGBA")

            try:
                thumb = ImageOps.fit(img, (size, size), method=Image.Resampling.BILINEAR, centering=(0.5, 0.5))
            except Exception:
                img.thumbnail((size, size))
                thumb = img

            return ImageTk.PhotoImage(thumb)

        except Exception:
            try:
                if ext in (".png", ".gif"):
                    return tk.PhotoImage(file=abs_path)
            except Exception:
                pass

        return None


def main():
    root = tk.Tk()
    MainUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
