"""
menubar.py
----------
进程 B：菜单栏常驻进程

职责：
  - macOS 状态栏图标（rumps）
  - 全局快捷键监听（双击 ⌘C → 触发划词翻译）
  - 管理 GUI 子进程（进程 C：gui_window.py）

由 main.py（进程 A）以脱离终端的方式启动，长期常驻后台。

【快捷键设计：双击 ⌘C】
  用户选中文本后，正常按一次 ⌘C（内容已复制到剪贴板），
  在 450ms 内再次按 ⌘C，程序检测到双击，直接读取剪贴板并触发翻译。
  优势：
    ① 第一次 ⌘C 已将内容写入剪贴板，无需再模拟复制
    ② 不与任何应用的自定义快捷键冲突（⌘C 是通用复制）
    ③ 无需申请额外权限（只需辅助功能，与单次监听相同）
"""

import os
import subprocess
import sys
import time
import threading
from multiprocessing import Process, Queue, set_start_method

import rumps
from pynput import keyboard as pynput_keyboard

BASE_DIR    = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(BASE_DIR, "config.json")
INSTANCE_FLAG = "/private/tmp/com.glucose.aitranslator.show_flag"

sys.path.insert(0, BASE_DIR)
from translator  import load_config, save_config
from gui_window  import start_gui_process


# ─────────────────────────────────────────────
# 菜单栏 App（进程 B 主线程）
# ─────────────────────────────────────────────

class TranslatorMenuBar(rumps.App):
    """
    macOS 状态栏常驻图标，提供：
      - 显示主界面
      - 默认模式切换（二级菜单）
      - 退出程序
    """

    def __init__(self, ipc_queue: Queue, gui_process):
        menubar_icon_path = os.path.join(BASE_DIR, "menubar_icon.png")
        super().__init__(name="Translator", title="", icon=menubar_icon_path, quit_button=None)
        self.ipc_queue    = ipc_queue
        self._gui_process = gui_process   # 持有引用，供 _quit() 直接操作
        self._gui_lock    = threading.Lock()  # 保护 _gui_process 创建，防止并发创建多个

        # ── 开机自启状态 ──
        self.item_autostart = rumps.MenuItem(
            "开机自启", callback=self._toggle_autostart
        )
        # 初始化时检查并更新标题
        if self._check_autostart():
            self.item_autostart.title = "✓ 开机自启"

        # ── 加载配置 ──
        try:
            self.config  = load_config(CONFIG_PATH)
        except Exception as e:
            print(f"[MenuBar] 配置加载失败: {e}", flush=True)
            self.config  = {}

        current_mode = self.config.get("default_mode", "academic")

        # ── 二级菜单：默认模式 ──
        check_a = "✓ " if current_mode == "academic" else "   "
        check_d = "✓ " if current_mode == "daily"    else "   "
        check_f = "✓ " if current_mode == "format"   else "   "

        self.item_academic = rumps.MenuItem(
            f"{check_a}学术化", callback=self._set_academic
        )
        self.item_daily = rumps.MenuItem(
            f"{check_d}生活化", callback=self._set_daily
        )
        self.item_format = rumps.MenuItem(
            f"{check_f}格式化", callback=self._set_format
        )

        self.menu = [
            rumps.MenuItem("显示主界面", callback=self._open_ui),
            None,
            {"默认模式": [self.item_academic, self.item_daily, self.item_format]},
            None,
            rumps.MenuItem("修改设置", callback=self._open_config),
            None,
            self.item_autostart,
            None,
            rumps.MenuItem("退出", callback=self._quit),
        ]

        # ── 单实例：写入 PID 文件 + 启动标志文件监听 ──
        with open("/private/tmp/com.glucose.aitranslator.pid", "w") as f:
            f.write(str(os.getpid()))
        self._start_socket_server()

        # ── 启动全局快捷键监听线程 ──
        self._start_hotkey_listener()
        print("[MenuBar] 状态栏图标已启动", flush=True)

    # ── 菜单回调 ─────────────────────────────

    def _ensure_gui_alive(self):
        """
        确保进程 C 正在运行。
        若已退出则重新拉起，返回时可安全地向 self.ipc_queue 发送指令。
        使用锁保护，防止并发调用（如快捷键线程）同时创建多个进程。
        """
        with self._gui_lock:
            if self._gui_process is None or not self._gui_process.is_alive():
                self.ipc_queue = Queue()
                self._gui_process = Process(
                    target=start_gui_process,
                    args=(self.ipc_queue, CONFIG_PATH),
                    daemon=True,
                    name="TranslatorGUI",
                )
                self._gui_process.start()
                print(f"[MenuBar] 重新启动 GUI 子进程 (PID {self._gui_process.pid})", flush=True)
                # 给新进程短暂的初始化时间，避免指令在窗口就绪前到达
                time.sleep(0.3)

    def _open_ui(self, _=None):
        """
        显示翻译窗口：
        - 若进程 C 仍在运行，发送 show 指令激活窗口
        - 若进程 C 已退出（用户关闭过窗口），重新拉起一个新进程
        """
        self._ensure_gui_alive()
        self.ipc_queue.put({"action": "show"})

    def _set_academic(self, _):
        self._update_mode("academic")

    def _set_daily(self, _):
        self._update_mode("daily")

    def _set_format(self, _):
        self._update_mode("format")

    def _update_mode(self, mode: str):
        self.item_academic.title = ("✓ " if mode == "academic" else "   ") + "学术化"
        self.item_daily.title    = ("✓ " if mode == "daily"    else "   ") + "生活化"
        self.item_format.title   = ("✓ " if mode == "format"   else "   ") + "格式化"
        try:
            cfg = load_config(CONFIG_PATH)
            cfg["default_mode"] = mode
            save_config(cfg, CONFIG_PATH)
        except Exception as e:
            print(f"[MenuBar] 配置保存失败: {e}", flush=True)
        self.ipc_queue.put({"action": "update_mode", "mode": mode})

    def _check_autostart(self):
        """检查是否启用开机自启（通过 launchctl disabled 标志，重启后持久）"""
        PLIST = os.path.expanduser("~/Library/LaunchAgents/com.glucose.aitranslator.plist")
        if not os.path.exists(PLIST):
            return False
        label = "com.glucose.aitranslator"
        uid = os.getuid()
        try:
            result = subprocess.run(
                ["launchctl", "print-disabled", f"gui/{uid}"],
                capture_output=True, text=True, timeout=3,
            )
            # launchctl print-disabled 输出: "label" => enabled 或 "label" => disabled
            for line in result.stdout.splitlines():
                if f'"{label}"' in line:
                    return "enabled" in line
            return True  # 未出现在 disabled 列表中，说明是启用的（默认）
        except Exception:
            return os.path.exists(PLIST)  # 降级：plist 文件存在则假定启用

    def _toggle_autostart(self, _):
        """切换开机自启状态（使用 launchctl disable/enable，重启后保持）"""
        PLIST = os.path.expanduser("~/Library/LaunchAgents/com.glucose.aitranslator.plist")
        label = "com.glucose.aitranslator"
        uid = os.getuid()
        domain = f"gui/{uid}/{label}"
        if self._check_autostart():
            # 关闭：先停止当前实例，再标记为 disable
            subprocess.run(["launchctl", "bootout", f"gui/{uid}", PLIST],
                           capture_output=True, timeout=5)
            subprocess.run(["launchctl", "disable", domain],
                           capture_output=True, timeout=5)
            self.item_autostart.title = "开机自启"
        else:
            # 开启：取消 disable 标记（下次登录自动启动）
            subprocess.run(["launchctl", "enable", domain],
                           capture_output=True, timeout=5)
            self.item_autostart.title = "✓ 开机自启"

    def _open_config(self, _):
        """用系统默认编辑器打开 config.json"""
        subprocess.run(["open", CONFIG_PATH])

    def _quit(self, _):
        """
        退出流程：
          1. 发 None 信号让进程 C 优雅退出（root.quit → mainloop 结束）
          2. 等待 C 自行结束（最多 2 秒）
          3. 超时则强制 terminate
          4. 最后退出菜单栏进程本身
        在此处完整处理 C 的关闭，不依赖 finally 块
        （rumps.quit_application 内部走 ObjC NSApp.terminate_，
         可能绕过 Python finally，所以把清理逻辑提前到这里）
        """
        # ── 通知进程 C 优雅退出 ──
        self.ipc_queue.put(None)

        # ── 等待进程 C 结束（最多 2 秒）──
        if self._gui_process is not None and self._gui_process.is_alive():
            self._gui_process.join(timeout=2)
            if self._gui_process.is_alive():
                print("[MenuBar] 进程 C 未在 2 秒内退出，强制 terminate", flush=True)
                self._gui_process.terminate()
                self._gui_process.join(timeout=1)

        print("[MenuBar] 进程 C 已关闭，退出菜单栏", flush=True)
        rumps.quit_application()

    # ── 单实例检测：轮询标志文件 ──

    def _start_socket_server(self):
        """后台轮询标志文件，检测到新实例通知时弹窗"""
        def watcher_loop():
            while True:
                try:
                    if os.path.exists(INSTANCE_FLAG):
                        os.remove(INSTANCE_FLAG)
                        self._open_ui()
                except Exception:
                    pass
                time.sleep(0.5)

        t = threading.Thread(target=watcher_loop, daemon=True)
        t.start()

    # ── 双击 ⌘C 全局快捷键 ──────────────────

    def _start_hotkey_listener(self):
        """
        在后台线程中启动 pynput keyboard.Listener，
        检测「双击 ⌘C」（两次 ⌘C 间隔 < DOUBLE_INTERVAL 秒）。

        注意：需要在「系统设置 → 隐私与安全性 → 辅助功能」中
              为终端（或 Python）授权，否则监听静默失效。
        """
        DOUBLE_INTERVAL = 0.45   # 双击间隔阈值（秒），可按需调整

        # 用于跟踪修饰键和时间的可变容器（闭包）
        state = {
            "cmd_held":    False,
            "last_cmd_c":  0.0,
        }

        def on_press(key):
            # 记录 Cmd 键按下
            if key in (
                pynput_keyboard.Key.cmd,
                pynput_keyboard.Key.cmd_l,
                pynput_keyboard.Key.cmd_r,
            ):
                state["cmd_held"] = True
                return

            # 检测 Cmd + C
            if state["cmd_held"] and hasattr(key, "char") and key.char == "c":
                now = time.time()
                elapsed = now - state["last_cmd_c"]

                if elapsed < DOUBLE_INTERVAL:
                    # ✅ 双击 ⌘C 确认 —— 触发翻译
                    state["last_cmd_c"] = 0.0   # 重置，防止三击也触发
                    print(
                        f"[Hotkey] 检测到双击 ⌘C（间隔 {elapsed*1000:.0f}ms），触发翻译",
                        flush=True,
                    )
                    threading.Thread(
                        target=self._handle_translate_hotkey,
                        daemon=True,
                    ).start()
                else:
                    # 第一次 ⌘C：正常复制，记录时间
                    state["last_cmd_c"] = now

        def on_release(key):
            if key in (
                pynput_keyboard.Key.cmd,
                pynput_keyboard.Key.cmd_l,
                pynput_keyboard.Key.cmd_r,
            ):
                state["cmd_held"] = False

        def listener_thread():
            try:
                with pynput_keyboard.Listener(
                    on_press=on_press,
                    on_release=on_release,
                ) as listener:
                    print("[Hotkey] 双击 ⌘C 快捷键监听已激活", flush=True)
                    listener.join()
            except Exception as e:
                print(
                    f"[Hotkey] 监听失败: {e}\n"
                    "请确认已在「系统设置 → 隐私与安全性 → 辅助功能」中为终端授权。",
                    flush=True,
                )

        t = threading.Thread(target=listener_thread, daemon=True)
        t.start()

    def _handle_translate_hotkey(self):
        """
        双击 ⌘C 触发后的处理逻辑：
          - 第一次 ⌘C 已将选中文本写入剪贴板，此处直接读取
          - 短暂等待，确保系统剪贴板写入完成（部分应用有延迟）
          - 将剪贴板内容发送到 GUI 进程
        """
        # 第二次 ⌘C 按下时，剪贴板应已由第一次写入
        # 保险起见额外等待 100ms
        time.sleep(0.1)

        clipboard_text = ""
        try:
            result = subprocess.run(
                ["pbpaste"],
                capture_output=True, text=True, timeout=3,
            )
            clipboard_text = result.stdout.strip()
        except subprocess.TimeoutExpired:
            print("[Hotkey] pbpaste 超时", flush=True)
        except Exception as e:
            print(f"[Hotkey] 剪贴板读取失败: {e}", flush=True)

        if clipboard_text:
            print(f"[Hotkey] 剪贴板内容（前50字）：{clipboard_text[:50]}…", flush=True)
            self._ensure_gui_alive()
            self.ipc_queue.put({"action": "show_with_text", "text": clipboard_text})
        else:
            print("[Hotkey] 剪贴板为空，仅显示翻译窗口", flush=True)
            self._ensure_gui_alive()
            self.ipc_queue.put({"action": "show"})


# ─────────────────────────────────────────────
# 进程 B 入口
# ─────────────────────────────────────────────

def main():
    # multiprocessing spawn 模式（macOS 默认，显式声明保证兼容性）
    try:
        set_start_method("spawn")
    except RuntimeError:
        pass

    # 创建进程间通信队列
    ipc_queue: Queue = Queue()

    # 进程 C 按需启动（点击菜单或触发快捷键时由 _ensure_gui_alive 拉起）
    gui_process = None

    # 在主线程启动菜单栏 App（阻塞，直到用户点击「退出」）
    app = TranslatorMenuBar(ipc_queue, gui_process)
    try:
        app.run()
    finally:
        # rumps.quit_application() 可能绕过此处，但 daemon=True 确保 C 会被 OS 回收
        # 正常流程下 _quit() 已完成清理，此处仅作最后兜底
        if gui_process.is_alive():
            gui_process.terminate()
        print("[MenuBar] 进程 B 退出", flush=True)


if __name__ == "__main__":
    main()