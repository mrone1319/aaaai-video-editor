"""aaaai-editor — MR ONE 的 AI 剪辑工具链（ffmpeg + whisper.cpp，纯标准库）。

Copyright (c) 2026 MR ONE (@mrone.ai). All rights reserved. 见 LICENSE.md。
"""
__version__ = "1.13.1"

from . import keys as _keys  # noqa: E402,F401  载入就把环境变量里的密钥移进内存（外部程序继承不到）
