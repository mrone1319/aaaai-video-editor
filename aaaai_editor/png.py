"""最小 RGBA PNG 写入器（只用标准库 zlib/struct）。"""
from __future__ import annotations

import struct
import zlib


def _chunk(tag: bytes, data: bytes) -> bytes:
    return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)


def write_rgba(path: str, w: int, h: int, buf: bytearray) -> None:
    """buf 为 w*h*4 的 RGBA（非预乘）字节序列。"""
    stride = w * 4
    raw = bytearray()
    for y in range(h):
        raw.append(0)  # filter type 0（None）：小图不值得做滤波搜索
        raw += buf[y * stride:(y + 1) * stride]
    out = b"\x89PNG\r\n\x1a\n"
    out += _chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0))
    out += _chunk(b"IDAT", zlib.compress(bytes(raw), 6))
    out += _chunk(b"IEND", b"")
    with open(path, "wb") as f:
        f.write(out)
