#!/usr/bin/env python3
"""用法：~/.aaaai-editor/bin/aaaai-editor-python detect_cuts.py <video> [预期帧数]
场景切点检测（阈值 0.1），自带"管道确实产出数据"的校验。"""
import subprocess, sys, re


def _resolve_ffmpeg():
    """$AAAAI_EDITOR_FFMPEG -> ffmpeg-full (Apple Silicon) -> ffmpeg-full (Intel) -> PATH."""
    import os, shutil
    for c in (os.environ.get("AAAAI_EDITOR_FFMPEG"),
              "/opt/homebrew/opt/ffmpeg-full/bin/ffmpeg",
              "/usr/local/opt/ffmpeg-full/bin/ffmpeg"):
        if c and os.path.isfile(c) and os.access(c, os.X_OK):
            return c
    return shutil.which("ffmpeg") or "ffmpeg"


def _sibling_ffprobe(ff):
    import os, shutil
    p = os.path.join(os.path.dirname(ff), "ffprobe")
    if os.path.dirname(ff) and os.access(p, os.X_OK):
        return p
    return shutil.which("ffprobe") or "ffprobe"


FFMPEG = _resolve_ffmpeg()
FFPROBE = _sibling_ffprobe(FFMPEG)
FF = FFMPEG

src=sys.argv[1]; expect=int(sys.argv[2]) if len(sys.argv)>2 else None
p=subprocess.run([FF,"-v","error","-i",src,"-filter_complex",
  "select='gte(scene,0)',metadata=print:file=-","-an","-f","null","-"],
  capture_output=True,text=True)
t=None; rows=[]
for line in p.stdout.splitlines():
    m=re.search(r'pts_time:([\d.]+)',line)
    if m: t=float(m.group(1))
    m2=re.search(r'scene_score=([\d.]+)',line)
    if m2 and t is not None: rows.append((t,float(m2.group(1))))
# 管道有效性校验：必须真的收到数据
print(f"[校验] 收到 {len(rows)} 个 scene_score" + (f" / 预期约 {expect} 帧" if expect else ""))
if not rows:
    sys.exit("[!] 管道无输出 —— 这是静默失败，不是'零切点'。检查命令。")
if expect and len(rows) < expect*0.9:
    print(f"[!] 警告：收到数远少于帧数，结果可能不完整")
mx=max(r[1] for r in rows)
print(f"[校验] scene_score 最大 {mx:.4f} 均值 {sum(r[1] for r in rows)/len(rows):.4f}")
cuts=[r for r in rows if r[1]>=0.1]
print(f"\n阈值 0.1 检测点: {len(cuts)} 个")
for tt,ss in cuts[:30]: print(f"  {tt:7.3f}s  score={ss:.4f}")
