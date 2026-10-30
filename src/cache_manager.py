"""
Caching: InMemoryCache (RAM) aur SQLiteCache (file on disk).
"""
from langchain_core.caches import InMemoryCache
from langchain_core.globals import set_llm_cache
from langchain_community.cache import SQLiteCache

from src.config import SQLITE_DB_PATH


def set_cache(cache_type: str) -> str:
    """Ek global cache register karo. Bar bar same prompt par API call nahi hoti."""
    if cache_type == "InMemoryCache":
        set_llm_cache(InMemoryCache())
        return "In-memory cache active (RAM, cleared on restart)."
    if cache_type == "SQLiteCache":
        set_llm_cache(SQLiteCache(database_path=SQLITE_DB_PATH))
        return f"SQLite cache active (saved in {SQLITE_DB_PATH}, survives restart)."
    raise ValueError(f"Unknown cache type: {cache_type}")