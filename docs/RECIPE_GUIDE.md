# 配方卡写法 / How to write a recipe card

一种风格 = 三个文件：
1. `recipes/<id>.json`：所有参数（代码只读这个）
2. `recipes/<id>.md`：给人和 AI 看的说明（为什么这样定）
3. `easyscene/styles/<id>.py`：搭建场景的代码（复用代码库里的地形、水面、雾、植被、相机）

只想**改一种已有风格的感觉**（颜色、雾、季节、尺寸）？复制它的 JSON，改个 `id`，再在 `easyscene/styles/__init__.py` 里把新 id 指向原来的模块即可，不用写代码。

---

## JSON 格式

| 键 | 必填 | 说明 |
|---|---|---|
| `id`, `title` | ✔ | 标识与显示名 |
| `supports` | ✔ | 允许的 `time_of_day` / `weather` / `motion` / `subject` / `places` |
| `defaults` | | `"auto"` 时用的默认值 |
| `lighting_by_time` | ✔ | 时间 → 灯光预设（`cold_fog_morning` `golden_dusk` `rainy_night` `interior_warm` `soft_daylight`） |
| `lighting_overrides` | | 按时间覆盖太阳方向/高度/强度/色温、环境光、曝光 |
| `fog` | ✔ | 雾颜色、各向异性、高度衰减、打散、按天气的密度 |
| `camera` | ✔ | 视角方位、眼高、主体占比、光圈 |
| `assets` | ✔ | Poly Haven 的 HDRI / 贴图 / 模型 id（全部 CC0；缺了自动退回程序化） |
| `post` | ✔ | 后期：对比、饱和、冷暖、暗角、颗粒 |
| `checks` | ✔ | 自动检查阈值：平均亮度、过曝、死黑、主体占比 |
| `rubric` | ✔ | AI 评审项和权重 |
| `review` | | 及格分、轮数、每项不及格时改哪个说明书字段 |
| 其他 | | 风格自己的参数（如 `forest`、`ocean`、`dock`） |

### 可变范围（让每个种子都不一样）
任何数值都可以写成范围，由种子在范围内抽取：

```json
"tower_height": {"between": [14.0, 21.0]},
"bands": {"int_between": [2, 6]},
"palette": {"choice": [{"band": [0.42, 0.05, 0.03]}, {"band": [0.03, 0.03, 0.04]}]}
```
原则：**范围内任何组合都要好看**。拿不准就把范围收窄，用 `tools/seed_sheet.py` 出 5 个种子看一眼。

---

## 空白模板

```json
{
  "id": "my_style",
  "title": "中文名 / English name",
  "card": "recipes/my_style.md",
  "supports": {"time_of_day": ["morning"], "weather": ["haze"], "motion": ["none"],
               "subject": ["my_subject"], "places": []},
  "defaults": {"time_of_day": "morning", "weather": "haze", "subject": {"type": "my_subject"},
               "motion": {"preset": "none"}},
  "lighting_by_time": {"morning": "soft_daylight"},
  "lighting_overrides": {},
  "fog": {"color": [0.9, 0.92, 0.95], "anisotropy": 0.5, "height_falloff_m": 15.0,
          "breakup_scale_m": 30.0, "breakup_amount": 0.4,
          "density_by_weather": {"haze": {"between": [0.004, 0.008]}},
          "cloud_layer": {"center_m": 0.0, "thickness_m": 1.0, "density": 0.0}},
  "camera": {"view_azimuth_deg": {"front": 0, "three_quarter_left": -30, "three_quarter_right": 30},
             "eye_height_m": 1.6, "subject_fill": {"wide": 0.2, "medium": 0.35, "close": 0.55},
             "fstop": 4.0},
  "assets": {"hdri": "", "textures": {}, "models": {}},
  "post": {"contrast": 1.04, "saturation": 1.0, "gamma": 1.0,
           "shadows_rgb": [0, 0, 0], "highlights_rgb": [0, 0, 0], "vignette_angle": 0.45, "grain": 4},
  "checks": {"mean_luma": [0.18, 0.65], "clipped_highlights_max": 0.02,
             "crushed_shadows_max": 0.05, "subject_area": [0.02, 0.5]},
  "review": {"pass_score": 7.0, "max_rounds": 2, "fixes": {}},
  "rubric": [{"id": "mood", "weight": 3, "desc": "整体氛围"}]
}
```

`.md` 配方卡建议的小节：一句话气质 → 光 → 色 → 材质 → 构图规则 → 可变范围 → 常见错误（现象 / 原因 / 防护）→ 评分标准。

---

## 完整示例：雾气森林小木屋

看 `recipes/foggy_forest_cabin.json` + `recipes/foggy_forest_cabin.md`。几个值得学的决定：

- **光**：环境光弱（0.55）、太阳强（14）且逆光 → 被太阳照亮的雾明显亮于被天空照亮的雾，才有光柱。
- **冷暖**：太阳 7200K 偏冷，暖色只留给窗户（2400K），对比才强。
- **雾的层次**：地面密度 0.022/m + 14m 高度衰减 + 噪声打散 → 近清楚、中微雾、远隐去。
- **构图规则写进代码**：相机到主体的视线上压平地形、不种树、不放大石；太阳方向自动开"光窗"。
- **常见错误清单**：每踩一个坑就记一行"现象 / 原因 / 防护"，下一个做风格的人（或 AI）就不会再踩。
