"""最小 HTTP 工具（只用标准库）：JSON 请求、下载、重试。

密钥安全：
  - 带 Authorization 的请求只发给登记过的主机（trust），API 回传的网址若换了主机就拒绝，密钥不会被带到别处；
  - 跳转（redirect）到别的主机时拿掉 Authorization（urllib 默认会原样带过去）；
  - 只走 https（本机 localhost 测试例外）；错误信息里若出现密钥一律打码。
"""
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from typing import Iterable, Optional, Set
from urllib.parse import urlsplit

UA = "aaaai-editor"
_TRUSTED: Set[str] = set()
_LOCAL = ("localhost", "127.0.0.1", "::1")


class HttpError(RuntimeError):
    pass


def _host(url: str) -> str:
    return (urlsplit(url).hostname or "").lower()


def _safe_scheme(url: str) -> bool:
    u = urlsplit(url)
    return u.scheme == "https" or (u.scheme == "http" and (u.hostname or "") in _LOCAL)


def safe_base(url: Optional[str], default: str) -> str:
    """测试用的网址覆盖（环境变量）：只接受 https，或本机的 http；其他一律退回官方网址。"""
    if not url:
        return default
    if _safe_scheme(url):
        return url.rstrip("/")
    print("⚠️ 忽略不安全的网址覆盖 %s（只接受 https）" % url)
    return default


def trust(*urls: str) -> None:
    """登记可以收到密钥的主机。"""
    for u in urls:
        if u:
            _TRUSTED.add(_host(u))


def redact(text: str, secrets: Iterable[str]) -> str:
    for s in secrets:
        if s and len(s) >= 6:
            text = text.replace(s, s[:3] + "***")
    return text


class _StripAuthOnRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not _safe_scheme(newurl) and urlsplit(newurl).scheme != "http":
            raise HttpError("拒绝跳转到不安全的网址")
        new = super().redirect_request(req, fp, code, msg, headers, newurl)
        if new is None:
            return None
        if _host(newurl) != _host(req.full_url) or not _safe_scheme(newurl):
            for k in list(new.headers):
                if k.lower() == "authorization":
                    del new.headers[k]
            for k in list(new.unredirected_hdrs):
                if k.lower() == "authorization":
                    del new.unredirected_hdrs[k]
        return new


_OPENER = urllib.request.build_opener(_StripAuthOnRedirect)


def _check_url(url: str, authed: bool) -> None:
    if not _safe_scheme(url):
        raise HttpError("只接受 https 网址：%s://%s" % (urlsplit(url).scheme, _host(url)))
    if authed and _host(url) not in _TRUSTED:
        raise HttpError("拒绝把密钥发给未登记的主机：%s" % _host(url))


def request(method: str, url: str, headers: Optional[dict] = None, body=None, timeout: int = 60,
            retries: int = 2):
    data = None
    h = {"User-Agent": UA, "Accept": "application/json"}
    h.update(headers or {})
    secrets = [v.split(" ", 1)[-1] for k, v in h.items() if k.lower() == "authorization"]
    _check_url(url, bool(secrets))
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        h["Content-Type"] = "application/json"
    last = None
    for i in range(retries + 1):
        try:
            r = _OPENER.open(urllib.request.Request(url, data=data, headers=h, method=method), timeout=timeout)
            raw = r.read()
            return json.loads(raw.decode("utf-8")) if raw else {}
        except urllib.error.HTTPError as e:
            msg = redact(e.read().decode("utf-8", "replace")[:400], secrets)
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
    raise HttpError(redact("网络错误：%s" % last, secrets))


def download(url: str, path: str, timeout: int = 300) -> str:
    """下载素材（不带密钥）。只接受 http(s)：API 回传 file:// 之类的网址会被拒绝，不会读到本机文件。"""
    if urlsplit(url).scheme not in ("https", "http"):
        raise HttpError("只接受 http(s) 下载网址")
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with _OPENER.open(req, timeout=timeout) as r, open(path + ".part", "wb") as f:
        while True:
            b = r.read(1 << 16)
            if not b:
                break
            f.write(b)
    os.replace(path + ".part", path)
    return path
