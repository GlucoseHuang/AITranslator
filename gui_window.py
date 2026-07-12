"""
gui_window.py
-------------
CustomTkinter 翻译窗口，运行在独立子进程中。
通过 multiprocessing.Queue 接收来自主进程（菜单栏/快捷键）的指令：

  {"action": "show"}                        → 显示/激活窗口
  {"action": "show_with_text", "text": ...} → 填入文本并自动翻译
  {"action": "update_mode", "mode": ...}    → 切换翻译模式
  None                                      → 退出信号
"""

import os
import sys
import queue as stdlib_queue
import subprocess
import threading

import customtkinter as ctk

# translator.py 与本文件在同一目录
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
from translator import translate_stream, load_config, save_config, MODE_LABELS, detect_language
from history import add_translation, get_recent_translations, clear_history, get_history_count

# ── 全局外观设置（跟随系统深色 / 浅色模式）──
ctk.set_appearance_mode("System")
ctk.set_default_color_theme("green")


class HistoryWindow:
    """
    历史记录查看窗口
    """

    def __init__(self, parent_root, on_select_callback=None):
        self.parent_root = parent_root
        self.on_select_callback = on_select_callback
        self.window = None
        self.records = []

    def show(self):
        """显示历史记录窗口"""
        if self.window is not None and self.window.winfo_exists():
            self.window.lift()
            self.window.focus_force()
            self._refresh_list()
            return

        self.window = ctk.CTkToplevel(self.parent_root)
        self.window.title("翻译历史")
        self.window.geometry("700x500")
        self.window.minsize(600, 400)

        # 居中显示
        self.window.update_idletasks()
        sw = self.window.winfo_screenwidth()
        sh = self.window.winfo_screenheight()
        x = (sw - 700) // 2
        y = (sh - 500) // 2
        self.window.geometry(f"700x500+{x}+{y}")

        # 顶部工具栏
        toolbar = ctk.CTkFrame(self.window, height=50)
        toolbar.pack(fill="x", padx=10, pady=(10, 0))
        toolbar.pack_propagate(False)

        # 记录数量
        self.count_label = ctk.CTkLabel(toolbar, text="", font=ctk.CTkFont(size=12))
        self.count_label.pack(side="left", padx=10)

        # 刷新按钮
        ctk.CTkButton(
            toolbar,
            text="🔄 刷新",
            command=self._refresh_list,
            width=80,
            font=ctk.CTkFont(size=12)
        ).pack(side="right", padx=5)

        # 清空按钮
        ctk.CTkButton(
            toolbar,
            text="🗑 清空",
            command=self._clear_all,
            width=80,
            fg_color=("#d9534f", "#c9302c"),
            hover_color=("#c9302c", "#ac2925"),
            font=ctk.CTkFont(size=12)
        ).pack(side="right", padx=5)

        # 历史列表区域
        self.list_frame = ctk.CTkScrollableFrame(self.window)
        self.list_frame.pack(fill="both", expand=True, padx=10, pady=10)

        # 加载数据
        self._refresh_list()

    def _refresh_list(self):
        """刷新历史记录列表"""
        # 清除旧内容
        for widget in self.list_frame.winfo_children():
            widget.destroy()

        # 获取记录
        self.records = get_recent_translations(limit=100)
        count = get_history_count()
        self.count_label.configure(text=f"共 {count} 条记录（显示最近 {len(self.records)} 条）")

        if not self.records:
            ctk.CTkLabel(
                self.list_frame,
                text="暂无翻译历史",
                font=ctk.CTkFont(size=14),
                text_color=("gray50", "gray60")
            ).pack(pady=50)
            return

        # 显示记录
        for idx, record in enumerate(self.records):
            self._create_record_item(idx, record)

    def _create_record_item(self, idx: int, record: dict):
        """创建单条记录卡片"""
        card = ctk.CTkFrame(self.list_frame)
        card.pack(fill="x", padx=5, pady=5)

        # 头部：时间和模式
        header = ctk.CTkFrame(card, fg_color="transparent")
        header.pack(fill="x", padx=10, pady=(8, 4))

        time_str = record.get("created_at", "未知时间")
        mode_str = "📚 学术化" if record.get("mode") == "academic" else "💬 生活化"

        ctk.CTkLabel(
            header,
            text=time_str,
            font=ctk.CTkFont(size=11),
            text_color=("gray50", "gray60")
        ).pack(side="left")

        ctk.CTkLabel(
            header,
            text=mode_str,
            font=ctk.CTkFont(size=11),
            text_color=("gray50", "gray60")
        ).pack(side="right")

        # 原文预览
        source = record.get("source_text", "")[:100] + "..." if len(record.get("source_text", "")) > 100 else record.get("source_text", "")
        ctk.CTkLabel(
            card,
            text=f"原文: {source}",
            font=ctk.CTkFont(size=12),
            wraplength=600,
            justify="left"
        ).pack(anchor="w", padx=10, pady=(4, 2))

        # 译文预览
        target = record.get("translated_text", "")[:100] + "..." if len(record.get("translated_text", "")) > 100 else record.get("translated_text", "")
        ctk.CTkLabel(
            card,
            text=f"译文: {target}",
            font=ctk.CTkFont(size=12),
            wraplength=600,
            justify="left",
            text_color=("gray40", "gray70")
        ).pack(anchor="w", padx=10, pady=(2, 8))

        # 操作按钮区
        btn_frame = ctk.CTkFrame(card, fg_color="transparent")
        btn_frame.pack(fill="x", padx=10, pady=(0, 8))

        ctk.CTkButton(
            btn_frame,
            text="使用原文",
            command=lambda r=record: self._use_source(r),
            width=90,
            height=28,
            font=ctk.CTkFont(size=11)
        ).pack(side="left", padx=(0, 5))

        ctk.CTkButton(
            btn_frame,
            text="使用译文",
            command=lambda r=record: self._use_target(r),
            width=90,
            height=28,
            font=ctk.CTkFont(size=11)
        ).pack(side="left", padx=5)

    def _use_source(self, record: dict):
        """使用选中的原文"""
        if self.on_select_callback:
            self.on_select_callback(record.get("source_text", ""))
        self.window.destroy()

    def _use_target(self, record: dict):
        """使用选中的译文"""
        if self.on_select_callback:
            self.on_select_callback(record.get("translated_text", ""))
        self.window.destroy()

    def _clear_all(self):
        """清空所有历史记录"""
        dialog = ctk.CTkToplevel(self.window)
        dialog.title("确认")
        dialog.geometry("300x150")
        dialog.transient(self.window)
        dialog.grab_set()

        ctk.CTkLabel(
            dialog,
            text="确定要清空所有历史记录吗？",
            font=ctk.CTkFont(size=13)
        ).pack(pady=20)

        btn_frame = ctk.CTkFrame(dialog, fg_color="transparent")
        btn_frame.pack(pady=10)

        def confirm():
            clear_history()
            self._refresh_list()
            dialog.destroy()

        ctk.CTkButton(
            btn_frame,
            text="取消",
            command=dialog.destroy,
            width=80
        ).pack(side="left", padx=5)

        ctk.CTkButton(
            btn_frame,
            text="确定",
            command=confirm,
            width=80,
            fg_color=("#d9534f", "#c9302c")
        ).pack(side="left", padx=5)


class TranslatorWindow:
    """
    翻译主界面：左侧原文输入区 + 右侧译文输出区，顶部工具栏含模式切换。
    新增功能：字数统计、中英互换、流式输出、历史记录。
    """

    def __init__(self, ipc_queue, config_path: str = "config.json"):
        self.ipc_queue   = ipc_queue
        self.config_path = config_path
        self._translating = False          # 防止并发请求
        self._current_source = ""          # 当前原文
        self._current_result = ""          # 当前译文
        self._history_window = None        # 历史记录窗口

        # ── 加载配置 ──
        try:
            self.config = load_config(config_path)
        except FileNotFoundError as e:
            print(f"[GUI] 配置加载失败: {e}")
            self.config = {}

        self.current_mode = self.config.get("default_mode", "academic")

        # ── 构建 UI ──
        self._build_root()
        self._build_toolbar()
        self._build_content()
        self._build_statusbar()

        # 关闭按钮
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.root.bind("<Command-q>", lambda _: self._on_close())

        # 绑定文本变化事件（字数统计）
        self.input_box.bind("<KeyRelease>", lambda _: self._update_word_count())
        self.input_box.bind("<ButtonRelease>", lambda _: self._update_word_count())
        
        # 绑定模式切换事件（更新按钮文本和标签）
        self.mode_var.trace_add("write", self._on_mode_change)

        # ── 启动 IPC 监听线程 ──
        self._start_ipc_listener()

    # ═══════════════════════════════════════════
    # UI 构建
    # ═══════════════════════════════════════════

    def _build_root(self):
        self.root = ctk.CTk()
        self.root.withdraw()  # 立即隐藏，避免 update_idletasks 时闪现空白窗口
        self.root.title("智能翻译助手")
        self.root.geometry("960x540")
        self.root.minsize(640, 400)
        # macOS：让窗口出现在屏幕中央
        self.root.update_idletasks()
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        x  = (sw - 960) // 2
        y  = (sh - 540) // 2
        self.root.geometry(f"960x540+{x}+{y}")
        # 挂载窗口图标（macOS 用 NSApplication 设置 Dock 图标）
        try:
            from AppKit import NSApplication, NSImage
            _base = os.path.dirname(os.path.abspath(__file__))   # ← 不依赖 BASE_DIR
            icon_path = os.path.join(_base, "app_icon.png")
            ns_image = NSImage.alloc().initWithContentsOfFile_(icon_path)
            if ns_image is None:
                raise FileNotFoundError(f"NSImage 无法加载: {icon_path}")
            NSApplication.sharedApplication().setApplicationIconImage_(ns_image)
            print(f"[GUI] Dock 图标加载成功: {icon_path}", flush=True)
        except Exception as e:
            print(f"[GUI] 图标加载失败: {e}", flush=True)

    def _build_toolbar(self):
        """顶部工具栏：模式选择 + 操作按钮"""
        bar = ctk.CTkFrame(self.root, height=52, corner_radius=0)
        bar.pack(fill="x", padx=0, pady=(0, 0))
        bar.pack_propagate(False)

        # 模式标签
        ctk.CTkLabel(bar, text="翻译模式：", font=ctk.CTkFont(size=13)).pack(
            side="left", padx=(16, 4), pady=12
        )

        # 单选按钮：学术化 / 生活化 / 格式化
        self.mode_var = ctk.StringVar(value=self.current_mode)
        for mode_key, mode_label in [("academic", "📚 学术化"), ("daily", "💬 生活化"), ("format", "✨ 格式化")]:
            ctk.CTkRadioButton(
                bar,
                text=mode_label,
                variable=self.mode_var,
                value=mode_key,
                font=ctk.CTkFont(size=13),
            ).pack(side="left", padx=8, pady=12)

        # 右侧按钮区
        mode = self.mode_var.get() if hasattr(self, 'mode_var') else self.current_mode
        btn_text = "格式化  ⌘↵" if mode == "format" else "翻  译  ⌘↵"
        self.translate_btn = ctk.CTkButton(
            bar,
            text=btn_text,
            command=self.do_translate,
            width=110,
            height=34,
            font=ctk.CTkFont(size=13, weight="bold"),
            fg_color=("#059669", "#10B981"),
            hover_color=("#047857", "#059669"),
        )
        self.translate_btn.pack(side="right", padx=(6, 16), pady=9)

        # 历史按钮
        ctk.CTkButton(
            bar,
            text="📜 历史",
            command=self._show_history,
            width=80,
            height=34,
            fg_color=("#94A3B8", "#334155"),
            hover_color=("#64748B", "#1E293B"),
            font=ctk.CTkFont(size=13),
        ).pack(side="right", padx=4, pady=9)

        # 中英互换按钮
        self.swap_btn = ctk.CTkButton(
            bar,
            text="⇄ 中英互换",
            command=self._swap_and_translate,
            width=100,
            height=34,
            fg_color=("#0D9488", "#14B8A6"),
            hover_color=("#0F766E", "#0D9488"),
            font=ctk.CTkFont(size=13),
        )
        self.swap_btn.pack(side="right", padx=4, pady=9)

        ctk.CTkButton(
            bar,
            text="清  空",
            command=self.clear_all,
            width=80,
            height=34,
            fg_color=("#94A3B8", "#334155"),
            hover_color=("#64748B", "#1E293B"),
            font=ctk.CTkFont(size=13),
        ).pack(side="right", padx=4, pady=9)

    def _build_content(self):
        """主内容区：左右分栏（原文 / 译文）"""
        pane = ctk.CTkFrame(self.root, corner_radius=0, fg_color="transparent")
        pane.pack(fill="both", expand=True, padx=12, pady=(8, 0))

        # ── 左侧：原文输入 ──
        left = ctk.CTkFrame(pane)
        left.pack(side="left", fill="both", expand=True, padx=(0, 6))

        # 标题行：原文 + 字数统计
        left_header = ctk.CTkFrame(left, fg_color="transparent")
        left_header.pack(fill="x", padx=10, pady=(8, 2))
        
        self.source_lang_label = ctk.CTkLabel(
            left_header, text="原  文", font=ctk.CTkFont(size=13, weight="bold")
        )
        self.source_lang_label.pack(side="left")
        
        self.source_count_var = ctk.StringVar(value="0 字符")
        ctk.CTkLabel(
            left_header, 
            textvariable=self.source_count_var, 
            font=ctk.CTkFont(size=11),
            text_color=("gray50", "gray60")
        ).pack(side="right")

        self.input_box = ctk.CTkTextbox(left, wrap="word", font=ctk.CTkFont(size=14))
        self.input_box.pack(fill="both", expand=True, padx=8, pady=(0, 8))

        # ⌘↵ 触发翻译
        self.input_box.bind("<Command-Return>", lambda _e: self.do_translate())

        # ── 右侧：译文输出 ──
        right = ctk.CTkFrame(pane)
        right.pack(side="right", fill="both", expand=True, padx=(6, 0))

        # 标题行：译文 + 字数统计
        right_header = ctk.CTkFrame(right, fg_color="transparent")
        right_header.pack(fill="x", padx=10, pady=(8, 2))
        
        self.target_lang_label = ctk.CTkLabel(
            right_header, text="译  文", font=ctk.CTkFont(size=13, weight="bold")
        )
        self.target_lang_label.pack(side="left")
        
        self.target_count_var = ctk.StringVar(value="0 字符")
        ctk.CTkLabel(
            right_header, 
            textvariable=self.target_count_var, 
            font=ctk.CTkFont(size=11),
            text_color=("gray50", "gray60")
        ).pack(side="right")

        self.output_box = ctk.CTkTextbox(
            right, wrap="word", font=ctk.CTkFont(size=14), state="disabled"
        )
        self.output_box.pack(fill="both", expand=True, padx=8, pady=(0, 8))

    def _build_statusbar(self):
        """底部状态栏"""
        self.status_var = ctk.StringVar(value="就绪  ·  按 ⌘↵ 快速处理  ·  自动检测语言方向")
        self.status_label = ctk.CTkLabel(
            self.root,
            textvariable=self.status_var,
            font=ctk.CTkFont(size=11),
            text_color=("gray50", "gray60"),
        )
        self.status_label.pack(anchor="w", padx=16, pady=(2, 8))

    # ═══════════════════════════════════════════
    # 模式切换处理
    # ═══════════════════════════════════════════

    def _on_mode_change(self, *args):
        """模式切换时更新按钮文本和语言标签"""
        mode = self.mode_var.get()
        
        # 更新按钮文本
        if mode == "format":
            self.translate_btn.configure(text="格式化  ⌘↵")
        else:
            self.translate_btn.configure(text="翻  译  ⌘↵")
        
        # 更新语言标签
        self._update_word_count()

    # ═══════════════════════════════════════════
    # 字数统计与语言显示
    # ═══════════════════════════════════════════

    def _update_word_count(self):
        """更新原文和译文的字数统计，并检测语言显示方向"""
        source_text = self.input_box.get("1.0", "end").strip()
        target_text = self.output_box.get("1.0", "end").strip()
        
        source_chars = len(source_text)
        target_chars = len(target_text)
        
        self.source_count_var.set(f"{source_chars} 字符")
        self.target_count_var.set(f"{target_chars} 字符")

        # 更新语言标签（格式化模式不显示语言方向）
        current_mode = self.mode_var.get()
        if current_mode == "format":
            self.source_lang_label.configure(text="原  文")
            self.target_lang_label.configure(text="格式化结果")
        elif source_text:
            source_lang = detect_language(source_text)
            if source_lang == "zh":
                self.source_lang_label.configure(text="原  文 (中文)")
                self.target_lang_label.configure(text="译  文 (English)")
            else:
                self.source_lang_label.configure(text="原  文 (English)")
                self.target_lang_label.configure(text="译  文 (中文)")

    # ═══════════════════════════════════════════
    # 中英互换功能
    # ═══════════════════════════════════════════

    def _swap_and_translate(self):
        """
        中英互换：把当前译文作为新原文，并自动触发反向翻译。
        例如：英文→中文后，互换变成中文→英文
        """
        target_text = self._current_result if self._current_result else self.output_box.get("1.0", "end").strip()
        
        if not target_text:
            self._set_status("⚠️  没有可互换的译文", color="orange")
            return
        
        # 把译文放到原文框
        self.input_box.delete("1.0", "end")
        self.input_box.insert("1.0", target_text)
        
        # 清空译文框
        self.output_box.configure(state="normal")
        self.output_box.delete("1.0", "end")
        self.output_box.configure(state="disabled")
        
        self._current_source = target_text
        self._current_result = ""
        
        self._update_word_count()
        self._set_status("已互换，正在反向翻译...", color=("#3a7bd5", "#5b9de1"))
        
        # 自动触发翻译（会自动检测新原文的语言并反向翻译）
        self.do_translate()

    # ═══════════════════════════════════════════
    # 历史记录功能
    # ═══════════════════════════════════════════

    def _show_history(self):
        """显示历史记录窗口"""
        if self._history_window is None:
            self._history_window = HistoryWindow(
                self.root,
                on_select_callback=self._load_from_history
            )
        self._history_window.show()

    def _load_from_history(self, text: str):
        """从历史记录加载文本到输入框"""
        self.input_box.delete("1.0", "end")
        self.input_box.insert("1.0", text)
        self._update_word_count()
        self.show_window()

    # ═══════════════════════════════════════════
    # 窗口显示 / 隐藏
    # ═══════════════════════════════════════════

    def show_window(self):
        """将窗口显示并置于最前"""
        self.root.deiconify()
        self.root.lift()
        self.root.attributes("-topmost", True)
        self.root.after(100, lambda: self.root.attributes("-topmost", False))
        self.root.focus_force()
        # 通过 AppleScript 激活 Python 进程
        subprocess.Popen(
            ["osascript", "-e",
             f'tell application "System Events" to set frontmost of '
             f'(first process whose unix id is {os.getpid()}) to true'],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )

    def _on_close(self):
        """用户点击窗口关闭按钮时退出进程 C"""
        self.root.quit()

    def show_with_text(self, text: str):
        """显示窗口，填入文本，并自动触发翻译"""
        self.show_window()
        self.input_box.delete("1.0", "end")
        self.input_box.insert("1.0", text)
        self._update_word_count()
        if text.strip():
            self.do_translate()

    # ═══════════════════════════════════════════
    # 翻译逻辑（流式输出）
    # ═══════════════════════════════════════════

    def do_translate(self):
        """读取输入框内容，在子线程中流式调用 API，实时更新译文框"""
        if self._translating:
            return

        text = self.input_box.get("1.0", "end").strip()
        if not text:
            mode = self.mode_var.get()
            if mode == "format":
                self._set_status("⚠️  请先在左侧输入需要格式化的文本", color="orange")
            else:
                self._set_status("⚠️  请先在左侧输入需要翻译的文本", color="orange")
            return

        self._translating = True
        self._current_source = text
        self._current_result = ""
        
        # 根据模式设置按钮文本
        mode = self.mode_var.get()
        if mode == "format":
            self.translate_btn.configure(state="disabled", text="格式化中…")
        else:
            self.translate_btn.configure(state="disabled", text="翻译中…")
        
        self.swap_btn.configure(state="disabled")
        
        # 清空译文框并设为可编辑
        self.output_box.configure(state="normal")
        self.output_box.delete("1.0", "end")
        
        # 根据模式显示不同状态信息
        if mode == "format":
            self._set_status("正在格式化文本...", color=("#3a7bd5", "#5b9de1"))
        else:
            # 检测语言并显示
            source_lang = detect_language(text)
            lang_name = "中文" if source_lang == "zh" else "英文"
            target_lang_name = "英文" if source_lang == "zh" else "中文"
            self._set_status(f"正在翻译: {lang_name} → {target_lang_name}...", color=("#3a7bd5", "#5b9de1"))

        # 重新加载配置
        try:
            self.config = load_config(self.config_path)
        except Exception:
            pass

        config = self.config

        def worker():
            full_result = []
            try:
                # 流式获取翻译结果
                for chunk in translate_stream(text, mode, config, source_lang="auto"):
                    full_result.append(chunk)
                    self.root.after(0, lambda c=chunk: self._append_translation(c))
                
                # 翻译完成
                final_result = "".join(full_result)
                self._current_result = final_result
                
                # 保存到历史记录
                try:
                    add_translation(
                        source_text=text,
                        translated_text=final_result,
                        mode=mode,
                        model=config.get("model_name", "unknown")
                    )
                except Exception as e:
                    print(f"[GUI] 保存历史记录失败: {e}")
                
                self.root.after(0, lambda: self._on_stream_success())
                
            except ValueError as exc:
                msg = str(exc)
                self.root.after(0, lambda: self._on_stream_error(msg, "orange"))
            except Exception as exc:
                err = str(exc)
                if "timeout" in err.lower():
                    tip = "❌  API 请求超时，请检查网络连接"
                elif any(k in err.lower() for k in ("401", "api_key", "authentication")):
                    tip = "❌  API Key 无效，请检查 config.json 中的 api_key 字段"
                elif "connection" in err.lower():
                    tip = "❌  无法连接到 API 服务器，请检查 base_url 与网络"
                else:
                    tip = f"❌  处理失败：{err[:80]}"
                self.root.after(0, lambda t=tip: self._on_stream_error(t, "red"))

        threading.Thread(target=worker, daemon=True).start()

    def _append_translation(self, chunk: str):
        """追加流式翻译结果到输出框"""
        self.output_box.insert("end", chunk)
        self.output_box.see("end")
        self._update_word_count()

    def _on_stream_success(self):
        """流式翻译成功完成"""
        self.output_box.configure(state="disabled")
        self._translating = False
        
        mode = self.mode_var.get()
        if mode == "format":
            self.translate_btn.configure(state="normal", text="格式化  ⌘↵")
            self._set_status("✅  格式化完成", color="green")
        else:
            self.translate_btn.configure(state="normal", text="翻  译  ⌘↵")
            self._set_status("✅  翻译完成", color="green")
        
        self.swap_btn.configure(state="normal")

    def _on_stream_error(self, msg: str, color: str):
        """流式翻译出错"""
        self.output_box.configure(state="disabled")
        self._translating = False
        
        mode = self.mode_var.get()
        if mode == "format":
            self.translate_btn.configure(state="normal", text="格式化  ⌘↵")
        else:
            self.translate_btn.configure(state="normal", text="翻  译  ⌘↵")
        
        self.swap_btn.configure(state="normal")
        self._set_status(msg, color=color)

    def clear_all(self):
        """清空输入框与输出框"""
        self.input_box.delete("1.0", "end")
        self.output_box.configure(state="normal")
        self.output_box.delete("1.0", "end")
        self.output_box.configure(state="disabled")
        self._current_source = ""
        self._current_result = ""
        self.source_lang_label.configure(text="原  文")
        self.target_lang_label.configure(text="译  文")
        self._update_word_count()
        self._set_status("就绪  ·  按 ⌘↵ 快速处理  ·  自动检测语言方向")

    def _set_status(self, msg: str, color=("gray50", "gray60")):
        self.status_var.set(msg)
        self.status_label.configure(text_color=color)

    # ═══════════════════════════════════════════
    # IPC：监听主进程发来的指令
    # ═══════════════════════════════════════════

    def _start_ipc_listener(self):
        """在后台线程中轮询 multiprocessing.Queue"""
        def listener():
            while True:
                try:
                    cmd = self.ipc_queue.get(timeout=0.2)
                except stdlib_queue.Empty:
                    continue
                except (EOFError, OSError):
                    self.root.after(0, self.root.quit)
                    break

                if cmd is None:
                    self.root.after(0, self.root.quit)
                    break

                action = cmd.get("action", "")
                if action == "show":
                    self.root.after(0, self.show_window)
                elif action == "show_with_text":
                    text = cmd.get("text", "")
                    self.root.after(0, lambda t=text: self.show_with_text(t))
                elif action == "update_mode":
                    mode = cmd.get("mode", "academic")
                    self.root.after(0, lambda m=mode: self.mode_var.set(m))

        threading.Thread(target=listener, daemon=True).start()

    # ═══════════════════════════════════════════
    # 启动入口
    # ═══════════════════════════════════════════

    def run(self):
        self.root.mainloop()


# ─────────────────────────────────────────────
# 子进程入口函数
# ─────────────────────────────────────────────

def start_gui_process(ipc_queue, config_path: str = "config.json"):
    """GUI 子进程（进程 C）的入口"""
    import sys as _sys

    log_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "translator.log")
    try:
        _log = open(log_path, "a", buffering=1, encoding="utf-8")
        _sys.stdout = _log
        _sys.stderr = _log
    except Exception:
        _devnull = open(os.devnull, "w")
        _sys.stdout = _devnull
        _sys.stderr = _devnull

    window = TranslatorWindow(ipc_queue, config_path)
    window.run()

    try:
        ipc_queue.close()
        ipc_queue.join_thread()
    except Exception:
        pass
