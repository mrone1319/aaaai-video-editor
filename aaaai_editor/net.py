"""最小 HTTP 工具（只用标准库）：JSON 请求、下载、重试。"""
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from typing import Optional

UA = "aaaai-editor"


class HttpError(RuntimeError):
    pass


def request(method: str, url: str, headers: Optional[dict] = None, body=None, timeout: int = 60,
            retries: int = 2):
    data = None
    h = {"User-Agent": UA, "Accept": "application/json"}
    h.update(headers or {})
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        h["Content-Type"] = "application/json"
    last = None
    for i in range(retries + 1):
        try:
            r = urllib.request.urlopen(urllib.request.Request(url, data=data, headers=h, method=method),
                                       timeout=timeout)
            raw = r.read()
            return json.loads(raw.decode("utf-8")) if raw else {}
        except urllib.error.HTTPError as e:
            msg = e.read().decode("utf-8", "replace")[:400]
            # 付费的提交（POST）只在「明确没受理」时重试，避免重复扣费
            again = (429, 503) if method == "POST" else (429, 500, 502, 503, 504)
            if e.code in again and i < retries:
                time.sleep(2 * (i + 1))
                last = e
                continue
            raise HttpError("HTTP %d：%s" % (e.code, msg))
        except (urllib.error.URLError, TimeoutError) as e:
            last = e
            if i < retries and (method != "POST" or isinstance(getattr(e, "reason", None), ConnectionRefusedError)):
                time.sleep(2 * (i + 1))
                continue
    raise HttpError("网络错误：%s" % last)


def download(url: str, path: str, timeout: int = 300) -> str:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as r, open(path + ".part", "wb") as f:
        while True:
            b = r.read(1 << 16)
            if not b:
                break
            f.write(b)
    os.replace(path + ".part", path)
    return path
