"""API 密钥：全部可选。存在 macOS 钥匙串（服务名 aaaai-editor），也可用同名环境变量覆盖。

密钥只由用户本人在自己的终端输入（`aaaai-editor keys set NAME`，钥匙串会以隐藏方式提示输入），
不经过聊天、不写进命令行参数、不写进仓库或项目文件。
"""
from __future__ import annotations

import os
import subprocess
from typing import Dict, Optional

SERVICE = "aaaai-editor"

KEYS: Dict[str, dict] = {
    "PEXELS_API_KEY": {
        "for": "免费素材库（B-roll 第 0 层，$0）",
        "cost": "免费（每小时 200 次请求）；使用素材须标注 Pexels 与摄影师",
        "url": "https://www.pexels.com/api/new/",
    },
    "FAL_KEY": {
        "for": "AI 生成 B-roll：Flux 首帧＋Wan 2.2 动态（第 1 层）、可灵（第 2 层）",
        "cost": "按次付费：首帧约 $0.003、Wan 2.2 约 $0.15/条、可灵 2.5 约 $0.35/5 秒",
        "url": "https://fal.ai/dashboard/keys",
    },
    "HF_CREDENTIALS": {
        "for": "Higgsfield（第 3 层兜底，只在你指定时使用；格式 KEY_ID:KEY_SECRET）",
        "cost": "扣 Higgsfield 账户额度；失败或被内容审核拒绝会退还",
        "url": "https://cloud.higgsfield.ai/",
    },
}


# 用环境变量给的密钥：载入时就从环境里移走、只留在本进程的内存。
# 之后启动的 ffmpeg、whisper 等外部程序都继承不到，密钥不会跟着外流。
_ENV: Dict[str, str] = {k: os.environ.pop(k) for k in list(KEYS) if os.environ.get(k)}


def get(name: str) -> Optional[str]:
    v = _ENV.get(name) or os.environ.get(name)
    if v:
        return v.strip()
    for svc in (SERVICE,):
        try:
            p = subprocess.run(["security", "find-generic-password", "-s", svc, "-a", name, "-w"],
                               capture_output=True, text=True, timeout=10)
            if p.returncode == 0 and p.stdout.strip():
                return p.stdout.strip()
        except (OSError, subprocess.SubprocessError):
            pass
    return None


def has(name: str) -> bool:
    return bool(get(name))


def set_interactive(name: str) -> bool:
    """交给钥匙串隐藏提示输入（-w 放最后且不带值：密码不会出现在参数与历史记录里）。"""
    if name not in KEYS:
        raise KeyError("没有这个密钥名：%s（可用：%s）" % (name, " ".join(KEYS)))
    print("「%s」用于：%s\n费用：%s\n申请：%s" % (name, KEYS[name]["for"], KEYS[name]["cost"], KEYS[name]["url"]))
    print("接下来钥匙串会请你输入两次（不会显示在屏幕上）：")
    p = subprocess.run(["security", "add-generic-password", "-U", "-s", SERVICE, "-a", name, "-w"])
    return p.returncode == 0


def remove(name: str) -> bool:
    ok = False
    for svc in (SERVICE,):
        p = subprocess.run(["security", "delete-generic-password", "-s", svc, "-a", name],
                           capture_output=True, text=True)
        ok = ok or p.returncode == 0
    return ok


def status() -> Dict[str, bool]:
    return {k: has(k) for k in KEYS}
