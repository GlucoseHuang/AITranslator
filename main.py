"""
main.py
-------
进程 A：启动器 / Launcher

职责：
  1. 检查配置文件是否存在，若不存在则生成默认配置
  2. 将 menubar.py（进程 B）以后台、脱离终端的方式启动
  3. 自身立即退出 ——— 终端不会被占用，也无需保持 Terminal 窗口

运行方式：
  python main.py
"""

import json
import os
import subprocess
import sys

# ── 路径 ──
BASE_DIR    = os.path.dirname(os.path.abspath(__file__))
INSTANCE_FLAG = "/private/tmp/com.glucose.aitranslator.show_flag"
CONFIG_PATH = os.path.join(BASE_DIR, "config.json")
MENUBAR_PY  = os.path.join(BASE_DIR, "menubar.py")

DEFAULT_CONFIG = {
    "api_key":      "YOUR_API_KEY_HERE",
    "base_url":     "https://api.longcat.chat/openai",
    "model_name":   "LongCat-Flash-Chat",
    "default_mode": "academic",
}


def ensure_config() -> bool:
    """
    确保 config.json 存在且 API Key 已填写。
    返回 True 表示可以继续启动；False 表示需要用户先配置。
    """
    if not os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(DEFAULT_CONFIG, f, indent=4, ensure_ascii=False)
        print(
            f"\n[Init] 已在以下路径生成默认配置文件：\n"
            f"       {CONFIG_PATH}\n\n"
            "       请用文本编辑器打开，填入您的 api_key，然后重新运行 main.py。\n"
        )
        return False

    with open(CONFIG_PATH, encoding="utf-8") as f:
        cfg = json.load(f)

    if cfg.get("api_key", "") in ("", "YOUR_API_KEY_HERE"):
        print(
            f"\n[警告] config.json 中的 api_key 尚未配置！\n"
            f"       路径：{CONFIG_PATH}\n"
            "       翻译功能将无法使用，请填入有效的 API Key。\n"
            "       （程序仍会启动，但翻译请求会失败）\n"
        )

    return True


def main():
    # 1. 确保配置文件就绪
    if not ensure_config():
        sys.exit(0)

    # 2. 检查是否已有实例在运行 — 通过 PID 文件判断
    pid_file = "/private/tmp/com.glucose.aitranslator.pid"
    if os.path.exists(pid_file):
        try:
            with open(pid_file) as f:
                old_pid = int(f.read().strip())
            os.kill(old_pid, 0)  # 信号 0 仅检查进程是否存在
            # 进程存在 → 写入标志文件通知弹窗，然后退出
            with open(INSTANCE_FLAG, "w") as f:
                f.write("show")
            print("✅  已有实例在运行，已通知弹窗")
            sys.exit(0)
        except (ValueError, OSError):
            pass  # 进程不存在或 PID 文件无效，正常启动

    # 3. 以「脱离终端」的方式启动 menubar.py（进程 B）
    #    start_new_session=True：创建新会话，脱离当前终端控制组
    #    stdout/stderr 写入日志文件，方便调试
    log_path = os.path.join(BASE_DIR, "translator.log")
    log_file = open(log_path, "a", buffering=1)  # 行缓冲，tail -f 可实时查看

    proc = subprocess.Popen(
        [sys.executable, MENUBAR_PY],
        start_new_session=True,   # ← 核心：脱离终端
        close_fds=True,
        stdin=subprocess.DEVNULL,  # 避免 main.py 退出后 fd 0 变无效
        stdout=log_file,
        stderr=log_file,
        cwd=BASE_DIR,
    )

    print(
        f"✅  智能翻译助手已在后台启动（PID {proc.pid}）\n"
        f"    状态栏右上角将出现「译」图标。\n"
        f"    运行日志：{log_path}\n"
        f"    如需停止：点击「译」图标 → 退出，或 kill {proc.pid}\n"
    )
    # sys.exit(0)  # 进程 A 退出，终端立刻恢复


if __name__ == "__main__":
    main()
