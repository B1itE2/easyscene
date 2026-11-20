---
name: cinescene
description: Turn one sentence into a realistic, cinematic 3D scene rendered in Blender (foggy forest cabin, coastal lighthouse, autumn lakeside dock, greenhouse, rainforest waterfall). Use when the user asks for a realistic 3D scene, landscape render, cinematic still or short camera move from a text description. The agent only fills in a JSON scene spec; all modelling, lighting and rendering is done by tested code.
---

# cinescene

You never write Blender code. You translate the user's sentence into a **scene spec** (JSON),
run one command, check the result, and adjust the spec if needed.

All commands are run from the cinescene folder. `BLENDER` means the Blender 5.2 executable:
- macOS: `/Applications/Blender.app/Contents/MacOS/Blender`
- Windows: `"C:\Program Files\Blender Foundation\Blender 5.2\blender.exe"`
- Linux: `blender`

---

## Step 1 — Pick the style

Choose exactly one. If nothing fits, tell the user which styles exist; do not invent one.

| `style` | What it is | Default time / weather | Camera move |
|---|---|---|---|
| `foggy_forest_cabin` | log cabin in a misty spruce forest, warm windows, chimney smoke | `morning` / `fog` | `cloud_descent` |
| `coastal_lighthouse` | lighthouse on a sea cliff at sunset, waves, light beam | `dusk` / `haze` | `orbit` |
| `lakeside_dock` | wooden dock on a calm autumn lake, red leaves, reflections | `morning` / `light_fog` | `water_skim` |
| `greenhouse` | Victorian glasshouse full of potted plants, soft daylight | `morning` / `haze` | none (still) |
| `rainforest_waterfall` | jungle waterfall, light shafts through mist, mossy rocks | `morning` / `haze` | none (still) |

Allowed values for each style are in `recipes/<style>.json` → `"supports"`.

## Step 2 — Write the spec

Create `examples/<name>.json`. Copy this and change only what the user asked for:

```json
{
  "version": 1,
  "name": "my_scene",
  "prompt": "the user's sentence, verbatim",
  "style": "foggy_forest_cabin",
  "time_of_day": "auto",
  "weather": "auto",
  "camera": {"aspect": "16:9", "lens_mm": 35, "framing": "medium", "view": "three_quarter_left"},
  "motion": {"preset": "none", "duration_s": 10, "fps": 24},
  "details": [],
  "seed": 1,
  "quality": "preview"
}
```

Translation rules:
- `"auto"` = use the style's default. Only set a value if the user said it.
- "vertical / for TikTok / 竖屏" → `"aspect": "9:16"`; "cinematic / 宽银幕" → `"2.39:1"`.
- "close-up / 近景" → `"framing": "close"`; "wide / 远景" → `"wide"`.
- "camera move / opening shot / 运镜 / 开场" → `"motion": {"preset": "auto"}`; a duration like "10 seconds" → `duration_s`.
- Objects the user mentions → `details`, e.g. `{"item": "rocking_chair", "place": "porch"}`.
  Items: `rocking_chair bench barrel crate bucket axe lantern oil_lamp basket boots watering_can flowers vase table_set`.
  Places per style: `recipes/<style>.json` → `"supports"."places"`.
- Want a different-looking result for the same sentence? Change only `seed`.

## Step 3 — Validate the spec

```
python3 -m cinescene.spec examples/my_scene.json
```
`OK` → continue. Otherwise each error line names the field and the allowed values; fix and re-run.

## Step 4 — Render

Still image:
```
BLENDER -b --factory-startup -P tools/build.py -- --spec examples/my_scene.json --still-only
```
With a camera move (only if `motion.preset` is not `none`):
```
BLENDER -b --factory-startup -P tools/build.py -- --spec examples/my_scene.json
```
Quick look at a move first (every 24th frame, ~1 min): add `--step 24`.

Output in `out/<name>/`: `still.png`, `scene.blend`, `manifest.json` (every parameter + seed),
`checks.json`, `ASSET_LICENSES.md`, and for moves `frames/`, `<quality>.mp4`, `sheet.png`.

If the log says `exceeds the ... GB safety line`: use `--quality draft`, or tell the user the
scene needs a stronger machine. Do not pass `--force` on a laptop.

## Step 5 — Read the automatic checks

The last lines of the log say `checks: ALL PASSED` or `checks: FAILED <ids>`.
Each failed check prints a hint (`-> ...`) saying which **spec field** to change.
Apply it, go back to Step 4. At most 2 rounds.

Also read `detail NOT placed:` lines and tell the user plainly which requested objects are
missing and why.

## Step 6 — Review the image

If you can see images:
```
python3 tools/review.py prepare out/my_scene
```
Open the listed images, score each rubric item 0–10 honestly, write `out/my_scene/review.json`
as shown, then:
```
python3 tools/review.py score out/my_scene
```
`PASS` → done. `FAIL` → apply the printed spec fixes, re-render, review again (max 2 rounds).

If you cannot see images: give the user the path to `still.png` and ask them to look.

## Step 7 — Report to the user

Tell them: the image/video path, the seed (so they can reproduce or vary it), anything not
placed, and the license note: all assets are CC0 (listed in `ASSET_LICENSES.md`).

---

### Rules
- Never edit files in `cinescene/` to fix a picture. Change the spec.
- Never run two Blender renders at the same time.
- Same spec + same seed = same scene. Mention the seed when you report.
