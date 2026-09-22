"""把文档导出成 PDF：《使用指南》（HTML → PDF）与 Mac／Windows 安装指南（Markdown → PDF）。
用法：python3 scripts/export-docs.py   （需要 Playwright 的 Chromium；会连网载入字体与 marked）
"""
import json
import os
import sys
import tempfile

from playwright.sync_api import sync_playwright

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOCS = os.path.join(ROOT, "docs")
MARGIN = {"top": "16mm", "bottom": "16mm", "left": "14mm", "right": "14mm"}
TPL = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "md-template.html"), encoding="utf-8").read()


def main() -> int:
    with sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_page()
        pg.goto("file://" + os.path.join(DOCS, "使用指南.html"))
        pg.wait_for_timeout(2500)
        pg.emulate_media(media="print")
        pg.pdf(path=os.path.join(DOCS, "使用指南.pdf"), format="A4", print_background=True, margin=MARGIN)
        print("✅ 使用指南.pdf")
        for name in ("安装指南-Mac", "安装指南-Windows"):
            md = open(os.path.join(DOCS, name + ".md"), encoding="utf-8").read()
            with tempfile.NamedTemporaryFile("w", suffix=".html", delete=False, encoding="utf-8") as f:
                f.write(TPL.replace("__MD__", json.dumps(md)))
            pg = b.new_page()
            pg.goto("file://" + f.name)
            pg.wait_for_timeout(2500)
            pg.pdf(path=os.path.join(DOCS, name + ".pdf"), format="A4", print_background=True, margin=MARGIN,
                   display_header_footer=True, header_template="<span></span>",
                   footer_template='<div style="font-size:8px;width:100%;text-align:center;color:#888">aaaai-editor · '
                                   + name + ' · <span class="pageNumber"></span>/<span class="totalPages"></span></div>')
            os.unlink(f.name)
            print("✅ %s.pdf" % name)
        b.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
