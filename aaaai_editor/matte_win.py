"""Windows 的人像分割助手（MediaPipe）：和 macOS 的 Swift 助手同一套输入输出，其余程序不用改。

用法：python -m aaaai_editor.matte_win <宽> <高> [fast|balanced|accurate]
从 stdin 读 BGRA 原始帧，往 stdout 写 8 位灰度遮罩（0＝背景、255＝人）。

模型：安装器会下载 Google 官方的 selfie_segmenter.tflite 到 ~/.aaaai-editor/models/；
没有模型时改用 MediaPipe 旧版内建的人像分割（有装的话）。需要 pip 套件 mediapipe、numpy。
"""
from __future__ import annotations

import os
import sys

MODEL = os.path.join(os.path.expanduser(os.environ.get("AAAAI_EDITOR_HOME") or "~/.aaaai-editor"),
                     "models", "selfie_segmenter.tflite")


def _segmenter():
    import mediapipe as mp
    if os.path.isfile(MODEL):
        from mediapipe.tasks.python import BaseOptions
        from mediapipe.tasks.python import vision
        seg = vision.ImageSegmenter.create_from_options(vision.ImageSegmenterOptions(
            base_options=BaseOptions(model_asset_path=MODEL), output_confidence_masks=True))

        def run(rgb):
            r = seg.segment(mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb))
            return r.confidence_masks[0].numpy_view()
        return run
    sol = mp.solutions.selfie_segmentation.SelfieSegmentation(model_selection=1)   # 旧版 API（有的版本才有）

    def run_old(rgb):
        return sol.process(rgb).segmentation_mask
    return run_old


def main(argv) -> int:
    if len(argv) < 3:
        sys.stderr.write("用法: matte_win <宽> <高> [fast|balanced|accurate]\n")
        return 2
    W, H = int(argv[1]), int(argv[2])
    try:
        import numpy as np
        run = _segmenter()
    except Exception as e:   # 没装 mediapipe／numpy，或模型读不了
        sys.stderr.write("人像分割需要 mediapipe 与 numpy（重跑 install.ps1，或 pip install mediapipe numpy）：%s\n" % e)
        return 3
    n = W * H * 4
    inp, out = sys.stdin.buffer, sys.stdout.buffer
    while True:
        buf = inp.read(n)
        if not buf or len(buf) < n:
            break
        bgra = np.frombuffer(buf, dtype=np.uint8).reshape(H, W, 4)
        rgb = np.ascontiguousarray(bgra[:, :, 2::-1])
        try:
            m = run(rgb)
            m = np.asarray(m, dtype=np.float32)
            if m.shape[:2] != (H, W):   # 模型输出尺寸不同时：最近邻缩放回原尺寸
                ys = (np.arange(H) * m.shape[0] // H).clip(0, m.shape[0] - 1)
                xs = (np.arange(W) * m.shape[1] // W).clip(0, m.shape[1] - 1)
                m = m[ys][:, xs]
            g = (np.clip(m, 0.0, 1.0) * 255.0 + 0.5).astype(np.uint8)
        except Exception:
            g = np.zeros((H, W), dtype=np.uint8)
        out.write(g.tobytes())
        out.flush()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
