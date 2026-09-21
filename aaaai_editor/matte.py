"""人像遮罩：用 Apple Vision 的人物分割，生成与成片时间轴对齐的灰度遮罩视频。

管线是三段直通，不落中间帧文件：
    ffmpeg 解码并套用剪辑图 → (bgra 原始帧) → personmatte → (gray 原始帧) → ffmpeg 编码遮罩
助手程序是本项目自己写的 Swift，调用系统 Vision 框架，首次使用时就地编译并缓存。
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
from typing import List, Optional, Tuple

from . import env

CACHE = os.path.expanduser("~/.cache/aaaai-editor")

SWIFT_SRC = r'''
// personmatte — 从 stdin 读 BGRA 原始帧，用 Vision 人物分割，往 stdout 写 8 位灰度遮罩。
// 用法: personmatte <宽> <高> [fast|balanced|accurate]
import Foundation
import Vision
import CoreVideo

let a = CommandLine.arguments
guard a.count >= 3, let W = Int(a[1]), let H = Int(a[2]), W > 0, H > 0 else {
    FileHandle.standardError.write("用法: personmatte <宽> <高> [fast|balanced|accurate]\n".data(using: .utf8)!)
    exit(2)
}
let level: VNGeneratePersonSegmentationRequest.QualityLevel
switch a.count > 3 ? a[3] : "balanced" {
case "fast": level = .fast
case "accurate": level = .accurate
default: level = .balanced
}

let req = VNGeneratePersonSegmentationRequest()
req.qualityLevel = level
req.outputPixelFormat = kCVPixelFormatType_OneComponent8

var pbOpt: CVPixelBuffer?
CVPixelBufferCreate(nil, W, H, kCVPixelFormatType_32BGRA,
                    [kCVPixelBufferIOSurfacePropertiesKey: [:]] as CFDictionary, &pbOpt)
guard let pb = pbOpt else { exit(3) }

let frameBytes = W * H * 4
let inFH = FileHandle.standardInput
let outFH = FileHandle.standardOutput
var out = [UInt8](repeating: 0, count: W * H)

while true {
    var data = Data()
    while data.count < frameBytes {
        guard let chunk = try? inFH.read(upToCount: frameBytes - data.count), !chunk.isEmpty
        else { break }
        data.append(chunk)
    }
    if data.count < frameBytes { break }

    CVPixelBufferLockBaseAddress(pb, [])
    let dst = CVPixelBufferGetBaseAddress(pb)!
    let drb = CVPixelBufferGetBytesPerRow(pb)
    data.withUnsafeBytes { (src: UnsafeRawBufferPointer) in
        let sb = src.baseAddress!
        for y in 0..<H { memcpy(dst.advanced(by: y * drb), sb.advanced(by: y * W * 4), W * 4) }
    }
    CVPixelBufferUnlockBaseAddress(pb, [])

    var ok = false
    let handler = VNImageRequestHandler(cvPixelBuffer: pb, options: [:])
    if (try? handler.perform([req])) != nil,
       let obs = req.results?.first,
       let mask = obs.pixelBuffer as CVPixelBuffer? {
        CVPixelBufferLockBaseAddress(mask, .readOnly)
        let mw = CVPixelBufferGetWidth(mask), mh = CVPixelBufferGetHeight(mask)
        let mrb = CVPixelBufferGetBytesPerRow(mask)
        if let mb = CVPixelBufferGetBaseAddress(mask)?.assumingMemoryBound(to: UInt8.self),
           mw > 0, mh > 0 {
            // 双线性放大到输出尺寸（遮罩本身分辨率低于画面）
            for y in 0..<H {
                let fy = max(0.0, (Double(y) + 0.5) * Double(mh) / Double(H) - 0.5)
                let y0 = min(mh - 1, Int(fy)), y1 = min(mh - 1, y0 + 1)
                let wy = fy - Double(y0)
                let r0 = mb + y0 * mrb, r1 = mb + y1 * mrb
                let drow = y * W
                for x in 0..<W {
                    let fx = max(0.0, (Double(x) + 0.5) * Double(mw) / Double(W) - 0.5)
                    let x0 = min(mw - 1, Int(fx)), x1 = min(mw - 1, x0 + 1)
                    let wx = fx - Double(x0)
                    let top = Double(r0[x0]) * (1 - wx) + Double(r0[x1]) * wx
                    let bot = Double(r1[x0]) * (1 - wx) + Double(r1[x1]) * wx
                    out[drow + x] = UInt8(max(0, min(255, Int((top * (1 - wy) + bot * wy).rounded()))))
                }
            }
            ok = true
        }
        CVPixelBufferUnlockBaseAddress(mask, .readOnly)
    }
    if !ok { for i in 0..<(W * H) { out[i] = 0 } }
    outFH.write(Data(out))
}
'''


def helper() -> str:
    """返回分割助手路径；首次使用时编译（源码哈希变了会重编）。"""
    os.makedirs(CACHE, exist_ok=True)
    tag = hashlib.sha1(SWIFT_SRC.encode()).hexdigest()[:12]
    exe = os.path.join(CACHE, "personmatte_%s" % tag)
    if os.path.isfile(exe) and os.access(exe, os.X_OK):
        return exe
    # /usr/bin/swiftc 在每台 Mac 上都存在（只是占位）：没装 CLT 时一跑就弹安装窗口，所以先问 xcode-select
    if subprocess.run(["xcode-select", "-p"], capture_output=True).returncode != 0 or not shutil.which("swiftc"):
        raise env.ToolError("人像去背需要 Xcode Command Line Tools。在终端执行 xcode-select --install，装完再试"
                            "（不用人像穿插／卡片接管的话可以忽略）")
    src = os.path.join(CACHE, "personmatte_%s.swift" % tag)
    with open(src, "w", encoding="utf-8") as f:
        f.write(SWIFT_SRC)
    p = subprocess.run(["swiftc", "-O", "-framework", "Vision", "-framework", "CoreVideo",
                        "-o", exe, src], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if p.returncode != 0:
        raise env.ToolError("编译人像分割助手失败：\n" + (p.stderr or "")[-1200:])
    return exe


def available() -> bool:
    try:
        helper()
        return True
    except env.ToolError:
        return False


def build(source: str, base_graph: str, window: Tuple[float, float], work: str,
          W: int, H: int, fps: float, quality: str = "balanced",
          scale: float = 0.5, key: str = "") -> Tuple[str, int, int]:
    """为成片时间轴上的 [a,b] 生成遮罩视频。返回 (路径, 遮罩宽, 遮罩高)。"""
    a, b = window
    mw = max(16, int(round(W * scale)) & ~1)
    mh = max(16, int(round(H * scale)) & ~1)
    d = os.path.join(work, "mattes")
    os.makedirs(d, exist_ok=True)
    st = os.stat(source)   # 同名换了素材也要重算
    sig = hashlib.sha1(json.dumps([os.path.abspath(source), st.st_size, st.st_mtime_ns, base_graph, a, b,
                                   mw, mh, fps, quality], sort_keys=True).encode()).hexdigest()[:16]
    out = os.path.join(d, "matte_%s.mkv" % sig)
    if os.path.isfile(out):
        return out, mw, mh

    ff = env.ffmpeg()
    dec = subprocess.Popen(
        [ff, "-v", "error", "-i", source, "-filter_complex",
         "%s;[base]trim=%.3f:%.3f,setpts=PTS-STARTPTS,scale=%d:%d[o]" % (base_graph, a, b, mw, mh),
         "-map", "[o]", "-f", "rawvideo", "-pix_fmt", "bgra", "-"],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, cwd=work)
    seg = subprocess.Popen([helper(), str(mw), str(mh), quality],
                           stdin=dec.stdout, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    dec.stdout.close()
    enc = subprocess.Popen(
        [ff, "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "gray", "-s", "%dx%d" % (mw, mh),
         "-r", str(fps), "-i", "-", "-c:v", "ffv1", "-pix_fmt", "gray", out],
        stdin=seg.stdout, stderr=subprocess.PIPE)
    seg.stdout.close()
    enc.communicate()
    seg.wait()
    dec.wait()
    if enc.returncode != 0 or not os.path.isfile(out) or os.path.getsize(out) < 200:
        msg = (seg.stderr.read().decode(errors="replace") if seg.stderr else "")
        raise env.ToolError("生成人像遮罩失败（%s）：%s" % (key or "matte", msg[-800:]))
    return out, mw, mh


def coverage(path: str) -> float:
    """遮罩平均覆盖率（0–1）。接近 0 表示这段没认出人，用来提醒而不是报错。"""
    p = subprocess.run([env.ffmpeg(), "-v", "error", "-i", path, "-vf", "scale=64:64",
                        "-f", "rawvideo", "-pix_fmt", "gray", "-"],
                       stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    b = p.stdout
    return (sum(b) / len(b) / 255.0) if b else 0.0
