# 自定义风格

放在 `~/.aaaai-editor/themes/`（你的所有项目都生效，更新程序不会覆盖）或项目目录的 `themes/`（只对该项目生效），格式是 `*.json`：

```json
{"extends": "neon", "desc": "我的品牌：neon 底 + 品牌紫", "accent": "#9B5CFF", "on_accent": "#FFFFFF", "radius": 12}
```

文件名就是风格名（也可写 `"name"`）。没写的令牌从 `extends` 继承，默认继承 `ink`。
值写成 `"@value"` 表示引用另一个令牌。
