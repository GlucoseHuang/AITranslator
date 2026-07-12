"""
history.py
----------
翻译历史记录管理模块。

使用 SQLite 本地存储最近 1000 条翻译记录，支持：
- 添加新记录
- 查询最近 N 条
- 清空历史
- 搜索关键词
"""

import sqlite3
import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional

# 历史数据库路径
DATA_DIR = Path.home() / ".aitranslator"
HISTORY_DB = DATA_DIR / "history.db"
MAX_HISTORY = 1000  # 最大保留记录数

# 确保数据目录存在
DATA_DIR.mkdir(exist_ok=True)


def _get_connection() -> sqlite3.Connection:
    """获取数据库连接，自动创建表结构"""
    conn = sqlite3.connect(str(HISTORY_DB))
    conn.row_factory = sqlite3.Row
    
    # 创建历史记录表
    conn.execute("""
        CREATE TABLE IF NOT EXISTS translations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_text TEXT NOT NULL,
            translated_text TEXT NOT NULL,
            mode TEXT NOT NULL,
            model TEXT,
            text_hash TEXT UNIQUE,  -- 用于去重
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # 创建索引
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_created_at ON translations(created_at DESC)
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_text_hash ON translations(text_hash)
    """)
    
    conn.commit()
    return conn


def _compute_hash(text: str, mode: str) -> str:
    """计算文本+模式的哈希值，用于去重"""
    content = f"{text}:{mode}"
    return hashlib.md5(content.encode("utf-8")).hexdigest()


def add_translation(
    source_text: str,
    translated_text: str,
    mode: str,
    model: Optional[str] = None
) -> bool:
    """
    添加一条翻译记录到历史。
    
    :return: 是否成功添加（如果完全重复则跳过）
    """
    if not source_text or not translated_text:
        return False
    
    text_hash = _compute_hash(source_text.strip(), mode)
    
    conn = _get_connection()
    try:
        # 检查是否已存在完全相同的记录
        cursor = conn.execute(
            "SELECT id FROM translations WHERE text_hash = ?",
            (text_hash,)
        )
        if cursor.fetchone():
            # 已存在，更新时间为最新
            conn.execute(
                """
                UPDATE translations 
                SET created_at = CURRENT_TIMESTAMP 
                WHERE text_hash = ?
                """,
                (text_hash,)
            )
            conn.commit()
            return False
        
        # 插入新记录
        conn.execute(
            """
            INSERT INTO translations (source_text, translated_text, mode, model, text_hash)
            VALUES (?, ?, ?, ?, ?)
            """,
            (source_text.strip(), translated_text.strip(), mode, model, text_hash)
        )
        
        # 清理旧记录，只保留最近的 MAX_HISTORY 条
        conn.execute(
            f"""
            DELETE FROM translations 
            WHERE id NOT IN (
                SELECT id FROM translations 
                ORDER BY created_at DESC 
                LIMIT {MAX_HISTORY}
            )
            """
        )
        
        conn.commit()
        return True
        
    except sqlite3.Error as e:
        print(f"[History] 保存历史记录失败: {e}")
        return False
    finally:
        conn.close()


def get_recent_translations(limit: int = 50) -> List[Dict]:
    """
    获取最近的翻译记录。
    
    :param limit: 返回记录数量上限
    :return: 记录列表，每条包含 source_text, translated_text, mode, created_at
    """
    conn = _get_connection()
    try:
        cursor = conn.execute(
            """
            SELECT source_text, translated_text, mode, model, created_at
            FROM translations
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (limit,)
        )
        
        results = []
        for row in cursor.fetchall():
            results.append({
                "source_text": row["source_text"],
                "translated_text": row["translated_text"],
                "mode": row["mode"],
                "model": row["model"],
                "created_at": row["created_at"]
            })
        return results
        
    except sqlite3.Error as e:
        print(f"[History] 查询历史记录失败: {e}")
        return []
    finally:
        conn.close()


def search_history(keyword: str, limit: int = 20) -> List[Dict]:
    """
    搜索历史记录（模糊匹配原文或译文）。
    
    :param keyword: 搜索关键词
    :param limit: 返回记录数量上限
    """
    conn = _get_connection()
    try:
        cursor = conn.execute(
            """
            SELECT source_text, translated_text, mode, model, created_at
            FROM translations
            WHERE source_text LIKE ? OR translated_text LIKE ?
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (f"%{keyword}%", f"%{keyword}%", limit)
        )
        
        results = []
        for row in cursor.fetchall():
            results.append({
                "source_text": row["source_text"],
                "translated_text": row["translated_text"],
                "mode": row["mode"],
                "model": row["model"],
                "created_at": row["created_at"]
            })
        return results
        
    except sqlite3.Error as e:
        print(f"[History] 搜索历史记录失败: {e}")
        return []
    finally:
        conn.close()


def clear_history() -> bool:
    """清空所有历史记录"""
    conn = _get_connection()
    try:
        conn.execute("DELETE FROM translations")
        conn.execute("DELETE FROM sqlite_sequence WHERE name = 'translations'")
        conn.commit()
        return True
    except sqlite3.Error as e:
        print(f"[History] 清空历史记录失败: {e}")
        return False
    finally:
        conn.close()


def get_history_count() -> int:
    """获取历史记录总数"""
    conn = _get_connection()
    try:
        cursor = conn.execute("SELECT COUNT(*) FROM translations")
        return cursor.fetchone()[0]
    except sqlite3.Error:
        return 0
    finally:
        conn.close()
