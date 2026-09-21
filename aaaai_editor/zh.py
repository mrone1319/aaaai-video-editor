"""繁→简。whisper 不带提示词时常输出繁体（「轉錄」），比对前要统一成简体。
OpenCC 是可选依赖：有就用，没有就原样返回（只影响比对的命中率，不影响出片）。"""
from __future__ import annotations

from functools import lru_cache


@lru_cache(maxsize=1)
def _conv():
    try:
        import opencc
        return opencc.OpenCC("t2s").convert
    except Exception:
        return None


def t2s(s: str) -> str:
    c = _conv()
    return c(s) if (c and s) else s


def available() -> bool:
    return _conv() is not None
