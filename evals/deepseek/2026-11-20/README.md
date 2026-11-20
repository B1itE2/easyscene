# DeepSeek 实测记录 · 2026-11-20

- 模型：DeepSeek V4.1 `deepseek-flash`（思考模式默认开启），通过 DeepSeek API 调用
- DeepSeek 拿到的内容：SKILL.md 第 1–2 步（选风格、写说明书）+ 各风格 `recipes/*.json` 的 `supports` 可选值
- DeepSeek 只负责写场景说明书（`spec_by_deepseek.json`）。渲染命令由操作者按 SKILL.md 原样执行（DeepSeek 无法直接操作本机 Blender）
- 说明书：**一次通过校验，0 次重试，未做任何人工修改**
- 渲染时额外加了 `--quality final_fast`（1080p 展示画质），说明书里写的是 `preview`；只影响清晰度，不影响内容

| 场景 | 用户的话 | DeepSeek 的关键选择 | 自动检查 |
|---|---|---|---|
| ds_lighthouse | 傍晚海边悬崖上的灯塔，竖屏，给抖音用 | coastal_lighthouse · dusk · 9:16 · 不加运镜 | 全部通过 |
| ds_dock | 秋天湖边的木码头，码头尽头放个水桶和一盏灯笼，宽银幕 | lakeside_dock · 2.39:1 · bucket + lantern @ dock_end | 全部通过 |
| ds_cabin | 起大雾的清晨，森林里的小木屋，门廊上有把摇椅，近景 | foggy_forest_cabin · morning · dense_fog · close · rocking_chair @ porch | 全部通过 |

## 如实说明
- `still_first_run.jpg` 是第一次渲染的结果。当时暴露出 skill 的问题（竖屏/宽银幕/近景构图、近景树干挡镜头、秋叶像星星贴纸、大雾偏冷像恐怖片、检查提示写反），
  这些问题在**代码**里修好后，用**同一份未改动的说明书**重新渲染，得到 `still.jpg`。
- 因为测试期间改过代码，这不是一次"冻结代码"的严格测试；说明书本身全部出自 DeepSeek。
- 种子均为 DeepSeek 默认填写的 1，未挑选种子。
