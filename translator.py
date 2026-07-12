"""
translator.py
-------------
封装大模型 API 翻译逻辑，以及配置文件的读写操作。
"""

import json
import os
from openai import OpenAI

# ─────────────────────────────────────────────
# 翻译模式的系统提示词
# ─────────────────────────────────────────────

# 英译中提示词
EN_TO_CN_PROMPTS = {
    "academic": (
        "你是一位专业的学术翻译专家。请将用户提供的英文文本翻译成中文：\n"
        "- 翻译前先在内部整理原文：去除多余的换行、空格、连字符断行等排版噪声，将其还原为完整连贯的语义单元，再进行翻译\n"
        "- 译文须符合中文的原生表达习惯：使用地道的中文学术语体，避免英文句式的直译腔（如'其中'、'在…方面'、'基于…的'等生硬结构），多用中文惯用的短句、主动句和四字词组\n"
        "- 准确传递原文的专业内涵与逻辑层次，使用规范术语\n"
        "- 直接输出翻译结果，不加任何说明、前缀或注释"
    ),
    "daily": (
        "你是一位友好自然的翻译助手。请将用户提供的英文文本翻译成中文：\n"
        "- 翻译前先在内部整理原文：去除多余的换行、空格、连字符断行等排版噪声，将其还原为完整连贯的语义单元，再进行翻译\n"
        "- 译文须符合中文的原生表达习惯：使用中国人日常说话的方式来表达，不要逐字对应英文结构，遇到英文惯用表达要转化成中文里对应的自然说法\n"
        "- 保留原文的情感色彩和语气\n"
        "- 直接输出翻译结果，不加任何说明、前缀或注释"
    ),
}

# 中译英提示词
CN_TO_EN_PROMPTS = {
    "academic": (
        "你是一位专业的学术翻译专家。请将用户提供的中文文本翻译成英文：\n"
        "- 翻译前先在内部整理原文：去除多余的换行、空格等排版噪声，将其还原为完整连贯的语义单元，再进行翻译\n"
        "- 译文须符合英文的原生表达习惯：遵循英文学术写作规范，使用地道的学术英语表达，避免中式英语（Chinglish），注意学术写作的正式性、准确性和逻辑性\n"
        "- 准确传递原文的专业内涵与逻辑层次，使用国际通用的学术术语\n"
        "- 注意学术写作的语法规范：正确使用被动语态、名词化结构、复杂从句等学术英语特征\n"
        "- 直接输出翻译结果，不加任何说明、前缀或注释"
    ),
    "daily": (
        "你是一位友好自然的翻译助手。请将用户提供的中文文本翻译成英文：\n"
        "- 翻译前先在内部整理原文：去除多余的换行、空格等排版噪声，将其还原为完整连贯的语义单元，再进行翻译\n"
        "- 译文须符合英文的原生表达习惯：使用地道、自然的英语口语和书面表达，避免中式英语，让母语者感觉亲切自然\n"
        "- 保留原文的情感色彩、语气和风格（正式/随意/幽默等）\n"
        "- 注意英语的地道表达：正确使用习语、俚语、固定搭配，避免逐字翻译\n"
        "- 直接输出翻译结果，不加任何说明、前缀或注释"
    ),
}

# 文本格式化提示词
FORMAT_PROMPT = (
    "你是一位专业的文本格式化助手。请将用户提供的文本进行格式化处理：\n"
    "- 去除多余的换行：将因排版（如 PDF 复制、网页排版）导致的不必要换行合并，恢复为完整连贯的句子和段落\n"
    "- 去除页码：识别并删除文本中嵌入的页码（如独立成行的数字、页眉页脚中的页码等）\n"
    "- 去除引用编号：删除学术引用标记（如 [1]、[Smith et al., 2020]、(Johnson, 2019) 等），保持文本流畅\n"
    "- 规范化空格：将多个连续空格缩减为一个，去除行首行尾多余空格\n"
    "- 合理分段：保留原本的段落分隔（空行），确保段落结构清晰\n"
    "- 保持原意：不改变文本内容的含义，只做格式上的优化\n"
    "- 语言保持：原文是中文就输出中文，是英文就输出英文，不进行翻译\n"
    "- 直接输出格式化后的文本，不加任何说明、前缀或注释"
)

MODE_LABELS = {
    "academic": "学术化 (Academic)",
    "daily": "生活化 (Daily)",
    "format": "格式化 (Format)",
}


# ─────────────────────────────────────────────
# 语言检测
# ─────────────────────────────────────────────

def detect_language(text: str) -> str:
    """
    简单检测文本的主要语言。
    
    :param text: 待检测文本
    :return: "zh" 表示中文为主，"en" 表示英文为主
    """
    if not text:
        return "en"
    
    # 统计中文字符和英文字符
    chinese_chars = sum(1 for c in text if '\u4e00' <= c <= '\u9fff')
    english_chars = sum(1 for c in text if c.isascii() and c.isalpha())
    
    # 如果中文字符明显多于英文字符，判定为中文
    if chinese_chars > english_chars * 0.5:
        return "zh"
    return "en"


def get_system_prompt(mode: str, source_lang: str = "auto") -> str:
    """
    根据模式和源语言获取对应的系统提示词。
    
    :param mode: 翻译模式，"academic"、"daily" 或 "format"
    :param source_lang: 源语言，"zh" 或 "en" 或 "auto"（自动检测）
    :return: 系统提示词
    """
    # 格式化模式使用独立的提示词
    if mode == "format":
        return FORMAT_PROMPT
    
    if source_lang == "auto":
        # 默认使用英译中
        return EN_TO_CN_PROMPTS.get(mode, EN_TO_CN_PROMPTS["academic"])
    
    if source_lang == "zh":
        return CN_TO_EN_PROMPTS.get(mode, CN_TO_EN_PROMPTS["academic"])
    else:
        return EN_TO_CN_PROMPTS.get(mode, EN_TO_CN_PROMPTS["academic"])


# ─────────────────────────────────────────────
# 配置文件读写
# ─────────────────────────────────────────────

def load_config(config_path: str = "config.json") -> dict:
    """
    读取 JSON 配置文件，返回配置字典。
    若文件不存在则抛出 FileNotFoundError。
    """
    if not os.path.exists(config_path):
        raise FileNotFoundError(
            f"配置文件 '{config_path}' 不存在，"
            "请先运行 main.py 以自动生成默认配置，然后填入 API Key。"
        )
    with open(config_path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_config(config: dict, config_path: str = "config.json") -> None:
    """
    将配置字典写回 JSON 文件（格式化输出，保持可读性）。
    """
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=4, ensure_ascii=False)


# ─────────────────────────────────────────────
# 翻译核心函数
# ─────────────────────────────────────────────

def translate(text: str, mode: str, config: dict, source_lang: str = "auto") -> str:
    """
    调用 OpenAI 兼容 API 执行翻译（非流式）。
    自动检测语言方向：中文→英文 或 英文→中文

    :param text:   待翻译的原文字符串
    :param mode:   翻译模式，"academic"、"daily" 或 "format"
    :param config: 由 load_config() 返回的配置字典
    :param source_lang: 源语言，"zh"、"en" 或 "auto"（自动检测）
    :return:       翻译结果字符串
    :raises ValueError:  输入为空或模式不支持
    :raises Exception:   API 调用失败（超时、认证错误等）
    """
    # ── 输入验证 ──
    if not text or not text.strip():
        raise ValueError("输入文本不能为空")
    
    # 支持三种模式
    valid_modes = list(MODE_LABELS.keys())
    if mode not in valid_modes:
        raise ValueError(f"不支持的模式：'{mode}'，可选值为 {valid_modes}")

    # ── 自动检测语言 ──
    if source_lang == "auto":
        source_lang = detect_language(text.strip())

    api_key = config.get("api_key", "")
    if not api_key or api_key == "YOUR_API_KEY_HERE":
        raise ValueError("API Key 未配置，请在 config.json 中填入有效的 api_key")

    # ── 构建客户端 ──
    client = OpenAI(
        api_key=api_key,
        base_url=config.get("base_url", "https://api.longcat.chat/openai"),
    )

    # ── 获取对应的系统提示词 ──
    system_prompt = get_system_prompt(mode, source_lang)

    # ── 调用 API ──
    response = client.chat.completions.create(
        model=config.get("model_name", "LongCat-Flash-Chat"),
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user",   "content": text.strip()},
        ],
        timeout=30,  # 最长等待 30 秒，超时则抛出异常
    )

    return response.choices[0].message.content


def translate_stream(text: str, mode: str, config: dict, source_lang: str = "auto"):
    """
    调用 OpenAI 兼容 API 执行翻译（流式输出）。
    自动检测语言方向：中文→英文 或 英文→中文
    
    :param text:   待翻译的原文字符串
    :param mode:   翻译模式，"academic"、"daily" 或 "format"
    :param config: 由 load_config() 返回的配置字典
    :param source_lang: 源语言，"zh"、"en" 或 "auto"（自动检测）
    :yield:        每次返回新增的文本片段
    :raises ValueError:  输入为空或模式不支持
    :raises Exception:   API 调用失败（超时、认证错误等）
    """
    # ── 输入验证 ──
    if not text or not text.strip():
        raise ValueError("输入文本不能为空")
    
    # 支持三种模式
    valid_modes = list(MODE_LABELS.keys())
    if mode not in valid_modes:
        raise ValueError(f"不支持的模式：'{mode}'，可选值为 {valid_modes}")

    # ── 自动检测语言 ──
    if source_lang == "auto":
        source_lang = detect_language(text.strip())

    api_key = config.get("api_key", "")
    if not api_key or api_key == "YOUR_API_KEY_HERE":
        raise ValueError("API Key 未配置，请在 config.json 中填入有效的 api_key")

    # ── 构建客户端 ──
    client = OpenAI(
        api_key=api_key,
        base_url=config.get("base_url", "https://api.longcat.chat/openai"),
    )

    # ── 获取对应的系统提示词 ──
    system_prompt = get_system_prompt(mode, source_lang)

    # ── 流式调用 API ──
    stream = client.chat.completions.create(
        model=config.get("model_name", "LongCat-Flash-Chat"),
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user",   "content": text.strip()},
        ],
        stream=True,
        timeout=30,
    )

    for chunk in stream:
        if chunk.choices and chunk.choices[0].delta.content:
            yield chunk.choices[0].delta.content