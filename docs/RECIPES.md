# 配方

写意图，不写一堆卡片。`~/.aaaai-editor/bin/aaaai-editor recipes` 列出全部，`~/.aaaai-editor/bin/aaaai-editor expand storyboard.json`
打印展开结果（想微调就把展开结果贴回 `overlays`）。

```jsonc
"beats": [0.62, 10.2],          // 可选：关键落点会吸附到 ±0.12s 内的拍点
"recipes": [
  {"use":"hook","t":[0.3,4.5],"text":"AI 剪辑的三个步骤","kicker":"EP.01","stamp":"NEW","icon":"rocket"},
  {"use":"speaker","t":[4.8,8],"name":"Alex Chen","role":"内容创作者"},
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
| `chapter` | 画面整体压暗 + 大号章节数字（陈述色）+ 标题 | 人仍看得见，字幕留在上层；otg 用星空章节页 |
| `steps` | 带标题／图标的列表；每条可写 `at`（成片秒数）对准口播说到它的时刻，没写就按字数错峰；`layout: "rows"` 改出编号行卡 | 其余节奏由内容驱动 |
| `quote_pull` | 引言淡入 + 全程缓推 | 柔和型 |
| `speaker` | 下三分之一，从左滑入 | |
| `outro` | 整屏品牌 + 片尾音画同步淡出（可加 logo） | 尾板＝品牌独立 + 保持 + 音画同步淡出 |
| `compare` | 上下两组：前一组淡色＋叉，后一组价值色＋勾、晚一拍出现（可写 `reveal` 秒数） | |
| `takeover` | 卡片接管：画面进圆角框、人物头冲出框上缘、顶部标题；背景是模糊压暗的同段画面 | 需要人像去背（Xcode 工具） |
| `callout` | 带图标的药丸（默认放大 1.35 倍，可写 `scale`），可 `behind: true` 排到人物后面 | |

配方生成的卡片接在手写 `overlays` 后面；`style`、`under_captions` 可写在配方上透传。
`outro` 应放在片尾：它会把整支片子的最后几秒一起淡出；卡片时长会自动往后多延 1 秒（保持到片尾，不会先于整体淡出消失），并排在字幕下层，最后一句字幕仍可见。
