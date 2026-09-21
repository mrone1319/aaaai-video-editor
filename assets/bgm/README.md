# 常备配乐库（套件自带，7 首）

全部由 `tools/gen-bgm.py` 原创合成，**零版权风险**。每首约 6 分钟，够盖过大多数单集；片子更长会自动循环。

storyboard 里直接写曲名：`"music": {"file": "bgm:focus-quiet", "db": -18, "duck": true}`。
`db` 建议从 **-18** 起（实测基准；配乐会先正规化到跟人声同一基准再压），出 A/B 样片听过再微调。

| 曲名 | BPM | 感觉 | 适合场景 |
|---|---|---|---|
| `chill-tropical` | 84 | 热带 chill，有节奏感 | 户外／数字游民／coworking |
| `focus-quiet` | 76 | 安静专注，几乎无鼓 | 干货教学、密集资讯 |
| `lounge-vacation` | 70 | 慵懒度假，带 vibraphone | 泳池边／悠闲／放松安抚 |
| `upbeat-energetic` | 96 | 明快振奋，鼓点最密 | 发布公告／成果展示／冲刺感 |
| `minimal-intimate` | 66 | 极简安静，无底鼓 | 严肃话题／深度反思／独白 |
| `warm-story` | 80 | 温暖叙事，中等节奏 | 幕后故事／个人分享／中性场景 |
| `late-night-chill` | 68 | 深夜氛围，慢且忧郁 | 夜拍素材／沉思型 |

成片里可以使用这些配乐（授权范围见 `LICENSE.md`）。

想要新调性：`~/.aaaai-editor/bin/aaaai-editor-python ~/.aaaai-editor/app/tools/gen-bgm.py --bpm 90 --bars 130 --kick 0.25 --shaker-density 6 --vibe --out ~/.aaaai-editor/bgm/新名字.wav`
（先建好 `~/.aaaai-editor/bgm/`；参数说明在脚本开头）。放在 `~/.aaaai-editor/bgm/` 的 m4a／mp3／wav 都能用 `bgm:新名字` 引用，
`aaaai-editor bgm` 也会列出来，更新程序不会删掉。
