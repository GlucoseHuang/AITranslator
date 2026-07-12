# 🌐 AITranslator - macOS 智能翻译助手

一款专为 macOS 设计的状态栏常驻翻译工具，基于 OpenAI 兼容 API，支持学术化、生活化翻译及文本格式化三种模式。采用三进程架构设计，启动后终端立即释放，通过双击 ⌘C 即可实现全局划词翻译。

---

## ✨ 核心特性

- **状态栏常驻** - 启动后以菜单栏图标形式运行，不占用终端或 Dock 位置
- **双击 ⌘C 划词翻译** - 选中文本后快速双击 ⌘C，翻译窗口自动弹出
- **自动语言检测** - 智能识别中文/英文，自动选择翻译方向（中↔英）
- **三种处理模式** - 学术化翻译、生活化翻译、文本格式化
- **流式输出** - 处理结果实时逐字显示，无需等待完整响应
- **翻译历史** - SQLite 本地存储最近 1000 条记录，支持查看、复用
- **中英互换** - 一键将译文作为新原文进行反向翻译
- **字数统计** - 实时显示原文与译文字符数
- **深色模式** - 自动跟随系统外观主题

---

## 🎯 三种处理模式

### 📚 学术化翻译
**适用场景**：论文、技术文档、学术文章  
**特点**：
- 专业术语准确翻译
- 符合学术写作规范
- 正式严谨的表达风格
- 支持中英互译

### 💬 生活化翻译
**适用场景**：日常对话、社交媒体、邮件  
**特点**：
- 口语自然的翻译风格
- 保留原文情感色彩
- 地道流畅的表达
- 支持中英互译

### ✨ 文本格式化
**适用场景**：PDF 复制文本、网页文本、Word 文档  
**功能**：
- 去除多余换行（排版导致的断行）
- 去除嵌入的页码
- 去除引用编号（[1]、(Smith, 2020)等）
- 规范化空格（多空格→单空格）
- 保留原始段落结构
- 不改变原意，不翻译语言

**格式化示例**：
```
输入（PDF 复制）：
"这是一个很长的句
子，因为排版被断开
了。[1] 还有一些引
用编号。           23

下一段开始。"

输出（格式化后）：
"这是一个很长的句子，因为排版被断开了。还有一些引用编号。

下一段开始。"
```

---

## 🏗️ 架构设计

### 三进程架构

本项目采用 macOS 原生友好的三进程架构，确保终端即时释放与后台稳定运行：

```
┌─────────────────────────────────────────────────────────────────┐
│                         进程 A (启动器)                          │
│   main.py                                                       │
│   ├─ 检查/生成 config.json                                      │
│   ├─ 以 start_new_session 启动进程 B                            │
│   └─ 立即退出（终端恢复）                                        │
└───────────────────────┬─────────────────────────────────────────┘
                        │
                        ↓
┌─────────────────────────────────────────────────────────────────┐
│                    进程 B (菜单栏常驻进程)                        │
│   menubar.py                                                    │
│   ├─ rumps 状态栏图标（显示菜单）                                │
│   ├─ pynput 全局快捷键监听（双击 ⌘C）                            │
│   ├─ multiprocessing.Queue 进程间通信                           │
│   └─ 管理进程 C 的生命周期                                       │
└───────────────────────┬─────────────────────────────────────────┘
                        │
                        ↓ (按需启动)
┌─────────────────────────────────────────────────────────────────┐
│                     进程 C (GUI 窗口进程)                         │
│   gui_window.py                                                 │
│   ├─ CustomTkinter 翻译主界面                                    │
│   ├─ 流式翻译显示                                                │
│   ├─ 历史记录查看                                                │
│   └─ 接收 IPC 指令并执行                                         │
└─────────────────────────────────────────────────────────────────┘
```

### 为什么是三进程？

| 问题 | 传统方案 | 三进程方案 |
|------|---------|-----------|
| 终端被占用 | 需要 `&` 或 `nohup` | 进程 A 立即退出，终端完全释放 |
| 关闭终端导致程序退出 | 后台进程随终端关闭 | `start_new_session=True` 脱离终端控制组 |
| GUI 窗口占用资源 | 常驻内存 | 进程 C 按需启动，关闭窗口即释放 |
| 快捷键与 GUI 冲突 | Tkinter 主循环阻塞监听 | 进程 B 专职监听，进程 C 专职 UI |

### 进程间通信协议

进程 B 通过 `multiprocessing.Queue` 向进程 C 发送 JSON 指令：

```python
# 显示窗口
{"action": "show"}

# 显示窗口并填入文本、自动翻译
{"action": "show_with_text", "text": "Hello World"}

# 更新翻译模式
{"action": "update_mode", "mode": "academic"}

# 退出信号
None
```

---

## 📁 项目结构

```
AITranslator/
├── main.py              # 进程 A：启动器，检查配置并拉起后台进程
├── menubar.py           # 进程 B：状态栏图标 + 全局快捷键监听
├── gui_window.py        # 进程 C：CustomTkinter 翻译窗口
├── translator.py        # 翻译核心逻辑（OpenAI API 封装）
├── history.py           # 翻译历史记录管理（SQLite）
├── config.json          # 配置文件（API Key、模型等）
├── config.json.example  # 配置示例
├── requirements.txt     # Python 依赖
├── app_icon.png         # Dock 图标（可选）
├── menubar_icon.png     # 状态栏图标（自定义图标）
├── translator.log       # 运行日志（自动生成）
└── README.md
```

### 模块职责详解

#### main.py - 启动器
- 检查 `config.json` 是否存在，不存在则生成默认配置
- 检查 API Key 是否已填写（未填写仅打印警告，允许启动后翻译会失败）
- 以 `start_new_session=True` 启动 `menubar.py`（脱离终端控制）
- 重定向 stdout/stderr 到 `translator.log`
- 打印启动信息后由 main() 自然返回，进程 A 退出
- **单实例检测**：通过 PID 文件 `/private/tmp/com.glucose.aitranslator.pid` 防止重复启动；若已有实例在运行则写入标志文件通知旧实例弹窗

#### menubar.py - 菜单栏常驻进程
- **rumps 状态栏图标**：提供「显示主界面」「默认模式」「修改设置」「开机自启」「退出」菜单
- **双击 ⌘C 检测**：450ms 内两次 ⌘C 触发翻译
- **进程 C 管理**：检测进程存活、按需重启、优雅退出
- **配置持久化**：保存默认模式设置到 `config.json`
- **开机自启**：通过 `launchctl enable/disable gui/$UID/com.glucose.aitranslator` 切换 `~/Library/LaunchAgents/com.glucose.aitranslator.plist` 的启用状态
- **单实例协作**：后台线程轮询标志文件 `/private/tmp/com.glucose.aitranslator.show_flag`，被新实例触发时自动弹窗
- **快速打开配置**：菜单「修改设置」调用 `open config.json` 用系统默认编辑器编辑

#### gui_window.py - 翻译窗口
- **CustomTkinter UI**：现代美观的图形界面
- **三种模式选择**：学术化、生活化、格式化
- **流式处理**：逐字显示处理结果
- **历史记录窗口**：查看最近翻译，一键复用
- **中英互换**：将译文作为新原文反向翻译
- **语言检测显示**：自动识别并显示翻译方向
- **IPC 监听**：后台线程轮询进程间通信队列

#### translator.py - 翻译核心
- **OpenAI API 封装**：支持任意 OpenAI 兼容接口
- **三模式五套提示词**：英译中（学术/生活）、中译英（学术/生活）、格式化各一套
- **自动语言检测**：基于中文字符占比判断源语言
- **流式输出**：`translate_stream()` 生成器函数
- **非流式输出**：`translate()` 标准函数
- **配置读写**：`load_config()` / `save_config()`

#### history.py - 历史记录管理
- **SQLite 本地存储**：数据库位于 `~/.aitranslator/history.db`
- **自动去重**：相同原文+模式只更新时间，不重复存储
- **容量限制**：自动清理，只保留最近 1000 条
- **搜索功能**：`search_history()` 模糊匹配原文或译文（函数已实现，UI 中暂未暴露）
- **统计功能**：查询历史记录总数

---

## 🚀 快速开始

### 系统要求

- macOS（已测试 macOS 12+）
- Python 3.9+
- 辅助功能权限（用于全局快捷键监听）

### 安装步骤

#### 1. 克隆项目

```bash
git clone https://github.com/GlucoseHuang/AITranslator.git
cd AITranslator
```

#### 2. 安装 Python 依赖

```bash
pip install -r requirements.txt
```

依赖说明：
- **rumps** - macOS 状态栏图标框架
- **customtkinter** - 现代化 Tkinter UI 框架
- **pynput** - 全局键盘监听（需辅助功能权限）
- **openai** - OpenAI 官方 Python 客户端

#### 3. 配置 API Key

首次运行 `main.py` 会自动生成 `config.json`，或手动创建：

```json
{
    "api_key": "sk-xxxxxxxxxxxxxxxxxxxxxxxx",
    "base_url": "https://api.longcat.chat/openai",
    "model_name": "LongCat-Flash-Chat",
    "default_mode": "academic"
}
```

配置项说明：

| 字段 | 说明 | 示例 |
|------|------|------|
| `api_key` | OpenAI 兼容 API 密钥 | `sk-xxx...` |
| `base_url` | API 基础地址 | `https://api.openai.com/v1` |
| `model_name` | 使用的模型名称 | `gpt-3.5-turbo` |
| `default_mode` | 默认处理模式 | `academic`、`daily` 或 `format` |

#### 4. 授予辅助功能权限

**重要**：双击 ⌘C 功能需要辅助功能权限。

1. 打开 **系统设置** → **隐私与安全性** → **辅助功能**
2. 点击左下角锁图标解锁
3. 点击 **+** 添加你的终端应用：
   - Terminal.app
   - iTerm.app
   - 或其他使用的终端程序
4. 勾选添加的应用，确保权限已启用

#### 5. 启动程序

```bash
python main.py
```

输出示例：

```
✅  智能翻译助手已在后台启动（PID 12345）
    状态栏右上角将出现「译」图标。
    运行日志：/Users/you/AITranslator/translator.log
    如需停止：点击状态栏图标 → 退出，或 kill 12345
```

终端会立即回到命令提示符，程序在后台运行。

---

## 📖 使用指南

### 方式一：菜单栏操作

1. 点击状态栏的 **「译」图标**
2. 选择 **显示主界面**
3. 在左侧输入框输入/粘贴文本
4. 选择处理模式（📚 学术化 / 💬 生活化 / ✨ 格式化）
5. 点击 **处理** 按钮或按 `⌘ + ↵`
6. 右侧实时显示结果

### 方式二：双击 ⌘C 划词处理

1. 在任意应用中选中需要处理的文本
2. 按 `⌘C`（正常复制，文本进入剪贴板）
3. 在 **450 毫秒内**再按一次 `⌘C`
4. 处理窗口自动弹出，原文已填入并开始处理

**优势**：
- 第一次 `⌘C` 已完成复制，无需模拟按键
- 不与任何应用的自定义快捷键冲突
- `⌘C` 是通用操作，无需记忆新快捷键

### 窗口功能

#### 工具栏按钮

| 按钮 | 快捷键 | 功能 |
|------|--------|------|
| **翻译/格式化 ⌘↵** | `⌘ + ↵` | 开始处理（文本随模式变化） |
| **历史** | - | 打开历史记录窗口 |
| **⇄ 中英互换** | - | 将译文作为新原文反向翻译（仅翻译模式） |
| **清空** | - | 清空原文和译文框 |

#### 处理模式选择

在窗口顶部的单选按钮中选择：
- **📚 学术化** - 专业学术翻译
- **💬 生活化** - 自然日常翻译  
- **✨ 格式化** - 文本格式整理

#### 历史记录

- 点击 **历史** 按钮打开历史窗口
- 显示最近 100 条处理记录
- 每条记录显示：时间、模式、原文预览、结果预览
- 点击 **使用原文** 或 **使用结果** 可快速复用
- 支持清空所有历史记录

### 状态栏菜单

点击状态栏的 **「译」图标**，显示菜单：

- **显示主界面** - 打开处理窗口
- **默认模式** - 设置启动时的默认处理模式
  - ✓ 学术化
  - 生活化
  - 格式化
- **修改设置** - 用系统默认编辑器打开 `config.json`
- **开机自启** - 切换登录时是否自动启动（基于 `launchctl enable/disable`）
- **退出** - 完全退出程序

---

## ⚙️ 高级配置

### 调整双击间隔

如果觉得双击间隔太短或太长，可在 `menubar.py` 中修改：

```python
DOUBLE_INTERVAL = 0.45  # 单位：秒，默认 450ms
```

建议范围：0.3 ~ 0.8 秒

### 查看运行日志

```bash
# 实时查看日志
tail -f translator.log

# 查看最近 50 行
tail -50 translator.log
```

日志包含：
- 程序启动信息
- 快捷键触发事件
- 处理请求与结果
- 错误与异常信息

### 历史记录存储

- 数据库位置：`~/.aitranslator/history.db`
- 最大记录数：1000 条
- 自动去重：相同原文+模式只更新时间
- 手动清理：历史窗口 → 清空

### 自定义 API 接口

支持任意 OpenAI 兼容 API：

```json
{
    "api_key": "your-key",
    "base_url": "https://api.openai.com/v1",
    "model_name": "gpt-4"
}
```

已知兼容的服务：
- OpenAI API
- Azure OpenAI
- LongCat API
- Claude API（通过兼容层）
- 本地部署模型（如 Ollama）

---

## 🔧 故障排除

### Q: 双击 ⌘C 没反应？

**A:** 检查以下项目：

1. **辅助功能权限**
   - 系统设置 → 隐私与安全性 → 辅助功能
   - 确保终端已添加并勾选

2. **程序是否运行**
   - 检查状态栏是否有「译」图标
   - 或运行 `ps aux | grep menubar.py`

3. **日志检查**
   ```bash
   tail -20 translator.log
   ```
   查看是否有 `[Hotkey] 监听失败` 错误

### Q: 翻译/格式化失败或超时？

**A:** 可能原因：

1. **API Key 无效**
   ```
   ❌ API Key 无效，请检查 config.json 中的 api_key 字段
   ```
   - 检查 `config.json` 中的 `api_key` 是否正确
   - 确认没有多余的空格或换行

2. **网络连接问题**
   ```
   ❌ 无法连接到 API 服务器，请检查 base_url 与网络
   ```
   - 检查 `base_url` 是否可访问
   - 尝试在浏览器打开 `base_url` 测试连接

3. **请求超时**
   ```
   ❌ API 请求超时，请检查网络连接
   ```
   - 网络不稳定，稍后重试
   - 或在 `translator.py` 中增加 `timeout` 值（默认 30 秒）

### Q: 如何彻底停止程序？

**A:** 有以下方式：

1. **正常退出**
   - 点击状态栏「译」图标 → **退出**
   - 会优雅关闭所有进程

2. **命令行强制退出**
   ```bash
   pkill -f menubar.py
   ```

3. **查找并手动 kill**
   ```bash
   ps aux | grep -E "(menubar|gui_window)"
   kill <PID>
   ```

### Q: 历史记录丢失？

**A:** 历史记录存储在 `~/.aitranslator/history.db`：
- 检查文件是否存在
- 检查文件权限
- 查看日志是否有数据库错误

### Q: 窗口显示异常？

**A:** 尝试以下步骤：

1. **重启程序**
   ```bash
   pkill -f menubar.py
   python main.py
   ```

2. **检查 customtkinter 版本**
   ```bash
   pip show customtkinter
   pip install --upgrade customtkinter
   ```

3. **清除缓存**
   ```bash
   rm -rf ~/Library/Caches/customtkinter
   ```

---

## 🛡️ 安全与隐私

### 数据安全

- **本地存储**：历史记录仅存储在本地 SQLite 数据库
- **无云端同步**：不涉及任何云端存储或同步
- **API 传输**：处理内容通过 HTTPS 加密传输到 API 服务

### 权限说明

| 权限 | 用途 | 必需性 |
|------|------|--------|
| 辅助功能 | 监听全局快捷键（双击 ⌘C） | 快捷键功能必需 |
| 网络访问 | 调用翻译 API | 核心功能必需 |
| 文件读写 | 保存配置和历史记录 | 程序功能必需 |

### API Key 保护

- `config.json` 建议添加到 `.gitignore`
- 不要在公开仓库中提交 API Key
- 建议使用环境变量或密钥管理工具

---

## 📝 开发说明

### 代码风格

- 遵循 PEP 8 规范
- 使用类型注解（Type Hints）
- 详细的函数和模块文档字符串
- 中英文注释混合

### 依赖版本

```
rumps>=0.4.0
customtkinter>=5.2.2
pynput>=1.7.6
openai>=1.14.0
```

### 扩展建议

- **多语言支持**：扩展 `translator.py` 支持更多语言对
- **提示词定制**：在 `translator.py` 中添加更多处理模式
- **快捷键自定义**：修改 `menubar.py` 支持自定义快捷键
- **导出功能**：在 `history.py` 中添加导出为 CSV/JSON

---

## 📄 许可证

本项目仅供学习和个人使用。

---

## 🙏 致谢

- [rumps](https://github.com/jaredks/rumps) - 简洁的 macOS 状态栏框架
- [CustomTkinter](https://github.com/TomSchimansky/CustomTkinter) - 现代化的 Tkinter UI
- [pynput](https://github.com/moses-palmer/pynput) - 跨平台输入设备监听
- [OpenAI Python SDK](https://github.com/openai/openai-python) - 官方 API 客户端

---

## 📮 反馈与支持

如遇到问题或有改进建议，欢迎：
- 提交 Issue
- 发起 Pull Request

---

**享受智能翻译与文本处理体验！** 🎉
