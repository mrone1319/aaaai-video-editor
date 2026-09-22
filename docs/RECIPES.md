# 配方

写意图，不写一堆卡片。`~/.aaaai-editor/bin/aaaai-editor recipes` 列出全部，`~/.aaaai-editor/bin/aaaai-editor expand storyboard.json`
打印展开结果（想微调就把展开结果贴回 `overlays`）。

```jsonc
"beats": [0.62, 10.2],          // 可选：关键落点会吸附到 ±0.12s 内的拍点
"recipes": [
  {"use":"hook","t":[0.3,4.5],"text":"AI 剪辑的三个步骤","kicker":"EP.01","stamp":"NEW","icon":"rocket"},
  {"use":"speaker","t":[4.8,8],"name":"Alex Chen","role":"内容创作者"},
  {"use":"avatar","t":[4.8,8],"file":"assets/me.jpg","name":"Alex Chen","role":"内容创作者"},
  {"use":"stat_hit","t":[9,13],"value":24800,"from":1200,"suffix":"+","label":"月活钱包","icon":"wallet"},
  {"use":"chapter","t":[14,17],"index":2,"title":"先定构思，再选效果"},
  {"use":"steps","t":[18,24],"title":"三步完成","items":[{"text":"转录成文字","icon":"mic"}]},
  {"use":"compare","t":[25,31],"left":{"title":"传统剪辑","items":["手动对轴"]},"right":{"title":"aaaai-editor","items":["自动转录"]}},
  {"use":"callout","t":[32,35],"text":"省下 80% 时间","icon":"clock"},
  {"use":"quote_pull","t":[36,41],"text":"先定构思，再选效果","by":"剪辑笔记"},
  {"use":"outro","t":[42.5,48.9],"text":"下期见","sub":"关注我，下期见"}
]
```

| 配方 | 展开成 | 依据 |
|---|---|---|
| `hook` | 印章 + 弹出大标题 + 标题落地瞬切推近 | 冲击型开场 |
| `stat_hit` | 计数数据卡（价值绿）+ 数字落定瞬切推近 | 绿＝能量／价值色 |
| `chapter` | 画面整体压暗 + 大号章节数字（风格强调色）+ 标题 | 人仍看得见，字幕留在上层；otg 用星空章节页 |
| `steps` | 带标题／图标的列表；每条可写 `at`（成片秒数）对准口播说到它的时刻，没写就按字数错峰；`layout: "rows"` 改出编号行卡 | 其余节奏由内容驱动 |
| `quote_pull` | 引言淡入 + 全程缓推 | 柔和型 |
| `speaker` | 下三分之一，从左滑入 | |
| `avatar` | 左下角圆形头像（强调色外圈）＋姓名与职务；照片放 `assets/`，可写 `focus`（`[x, y]` 取景中心，0–1）、`photo_size` | 头像比纯文字更好认人 |
| `outro` | 画面半透明压暗 + 居中标题与按钮式标签 + 片尾音画同步淡出（可加 logo，`dim: 1` 为全黑） | 尾板＝品牌独立 + 保持 + 音画同步淡出 |
| `compare` | 上下两组：前一组淡色＋叉，后一组价值色＋勾、晚一拍出现（可写 `reveal` 秒数） | |
| `takeover` | 卡片接管：画面进圆角框、人物头冲出框上缘；上方是标题或面板区。`bg`：不写＝模糊压暗的同段画面、`"paper"`＝纸面（卡片自动白底深字）；`hold: true` 停到片尾；`sfx` 进场音效 | 需要人像去背（Xcode 工具） |
| `callout` | 带图标的药丸（默认放大 1.35 倍，可写 `scale`），可 `behind: true` 排到人物后面 | |

**开头预告（不是配方，是剪辑命令）**：`aaaai-editor hook storyboard.json --text "<那句话的几个字>"` 在字幕里找到那句，
按人声起止修准，剪一份放到片头（`--mode move` 改成搬过去、不重复）；已排好的卡片、推近时间自动顺延。

配方生成的卡片接在手写 `overlays` 后面；`style`、`under_captions` 可写在配方上透传。
`outro` 应放在片尾：它会把整支片子的最后几秒一起淡出；卡片时长会自动往后多延 1 秒（保持到片尾，不会先于整体淡出消失），并排在字幕下层，最后一句字幕仍可见。

## 卡片收合三连发（秀证据型内容）

爆点开卡片秀证据 → 中段讲流程 → 结尾停在行动号召。改时间与文字即可（截图放 `assets/`）：

```jsonc
"recipes": [
  {"use": "takeover", "t": [20.0, 26.0], "bg": "paper", "sfx": "whoosh"},   // 爆点：证据截图
  {"use": "takeover", "t": [36.0, 44.5], "bg": "paper"},                    // 两张截图并排 → 工作流
  {"use": "takeover", "t": [55.5, 62.0], "bg": "paper", "hold": true}       // 行动号召，停到片尾
],
"overlays": [
  {"type": "proof", "t": [20.3, 26.0], "file": "assets/proof1.png", "kicker": "9/20 星期六 · 后台数据",
   "pill": "9/20 · 本周", "stamp": "+$1,593", "stamp_at": 22.2, "stamp_sfx": "coin"},
  {"type": "proof", "t": [36.3, 40.2], "file": "assets/proof2.png", "x": 0.285, "pill": "9/22 · $892"},
  {"type": "proof", "t": [37.2, 40.2], "file": "assets/proof3.png", "x": 0.715, "pill": "9/23 · $896", "sfx": "pop"},
  {"type": "flow", "t": [40.4, 44.5], "kicker": "这支视频的工作流", "sfx": "pop", "steps": [
    {"icon": "camera", "top": "随手拍", "big": "3 分钟", "at": 40.6},
    {"icon": "rocket", "top": "AI", "big": "自动剪辑", "at": 41.6},
    {"icon": "money", "top": "现金流", "big": "每周进账", "at": 42.6}]},
  {"type": "cta", "t": [55.8, 62.0], "hold": true, "kicker": "想少绕一点路？", "question": "怎么**用 AI** 入门",
   "question_at": 56.0, "keyword": "留言「入门」", "cta_at": 58.2, "badge": "我把分享会链接发给你", "sfx": "ding"}
]
```

- 接管期间的卡片自动放进上方面板区（6%～32%），改成底板版；纸面背景时白卡深字，字幕落在纸面上会自动改深字。
- `proof`：`width`（比例）、`x`（中心）、`top`、`max_h` 可调；截图太高会自动缩到面板区放得下。
- `flow`：最后一张是强调色「结果」卡（`"result": false` 关掉）；图标用 `aaaai-editor icons` 里的名称。
- `cta`：`question` 可用 `**关键词**` 变强调色；`keyword` 是大药丸，`badge` 是下面一行小字。
