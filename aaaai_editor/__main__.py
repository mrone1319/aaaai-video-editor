import os
import subprocess
import sys

if sys.platform == "win32" and not sys.flags.utf8_mode:
    # Windows 默认用 GBK 读写文字：中文路径、storyboard、字幕、ffmpeg 输出会乱码或报错 → 以 UTF-8 模式重新启动
    env = dict(os.environ, PYTHONUTF8="1")
    sys.exit(subprocess.call([sys.executable, "-X", "utf8", "-m", "aaaai_editor"] + sys.argv[1:], env=env))

from .cli import main  # noqa: E402

sys.exit(main())
