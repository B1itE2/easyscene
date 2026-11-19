# 台式机正式渲染说明（Windows + NVIDIA RTX）

> 适用：RTX 2060（6GB 显存）或更好的 NVIDIA 显卡。Mac 上只做低质量预览，正式渲染都在这里跑。

## 1. 准备（只做一次）
1. 安装 **Blender 5.2.3**（与 Mac 上同一版本，保证结果一致）：<https://www.blender.org/download/>
   默认装到 `C:\Program Files\Blender Foundation\Blender 5.2\`。
2. 安装 **ffmpeg**（用来合成 MP4；不装也能渲染，只是不出视频）：
   ```
   winget install Gyan.FFmpeg
   ```
   装完**重新打开**命令行窗口，输入 `ffmpeg -version` 能看到版本号就行。
3. 显卡驱动更新到最新（OptiX 需要较新的驱动）。

## 2. 拿到渲染包
Mac 上运行 `tools/make_desktop_pack.sh`，会在桌面生成 `cinescene_desktop_pack.zip`（约 97MB，内含代码和 1k+2k 两套 CC0 素材缓存）。
拷到台式机，解压到一个**路径里没有中文和空格**的位置，例如 `D:\cinescene`。

## 3. 开始渲染（最简单）
双击 `tools\desktop\render_windows.bat`，按提示选：

| 选项 | 内容 | 分辨率 / 采样 | 预计耗时（RTX 2060，粗估） |
|---|---|---|---|
| 0 | **测速**：快速正式画质只渲 11 帧（每秒取 1 帧） | 1920×1080 / 64 | 10–20 分钟 |
| 1 | 正式静帧（云雾下降的最后一帧） | 1920×1080 / 256 | 2–6 分钟 |
| 2 | 预览动画 | 960×540 / 32，241 帧 | 20–40 分钟 |
| 3 | **快速正式动画（推荐）**：64 采样 + 降噪，雾精度减半 | 1920×1080 / 64，241 帧 | 1–2 小时 |
| 4 | 完整正式动画：画面最干净 | 1920×1080 / 256，241 帧 | 4–10 小时（过夜） |

> 耗时是按 Mac 实测换算的粗估。台式机第一次跑完后，`out\...\manifest.json` 里会记下真实耗时，下次估算就准了。
> **先跑 0（测速）**，把日志里 `s/frame` 那一行发我，就能算出 3 和 4 的准确时间。

如果 Blender 没装在默认位置，先在命令行里指定再运行：
```
set BLENDER=D:\Blender\blender.exe
tools\desktop\render_windows.bat
```

## 4. 手动命令（想自己控制时）
在 cinescene 文件夹里打开命令行：
```
set CINESCENE_CACHE=%CD%\asset_cache
set CINESCENE_MEM_LIMIT_GB=12
"C:\Program Files\Blender Foundation\Blender 5.2\blender.exe" -b --factory-startup -P tools\build.py -- --spec examples\foggy_cabin_cloud_descent.json --quality final
```
常用参数：
- `--still-only`：只渲最后一帧
- `--step 4`：每 4 帧渲 1 帧，快速看动作
- `--seed 12`：换一个种子（换一个场景）
- `--out out\xxx`：指定输出文件夹

## 5. 输出在哪
`out\<名字>\` 下：
- `scene.blend`：Blender 工程，可以直接打开
- `still.png`：调色后的单帧（`still_raw.png` 是未调色原图）
- `frames\`：帧序列
- `final.mp4` / `preview.mp4`：合成的视频
- `sheet.png`：6 格缩略对比图
- `manifest.json`：所有参数、种子、版本、耗时（可复现的依据）
- `ASSET_LICENSES.md`：素材许可清单

## 6. 常见问题
| 现象 | 处理 |
|---|---|
| 日志里写 `on CPU` | 没识别到显卡：更新驱动；Blender 偏好设置 → 系统 → Cycles 渲染设备选 OptiX |
| `estimated ... exceeds the ... GB safety line` | 估算超了安全线：加 `--force` 强制渲染，或把 `CINESCENE_MEM_LIMIT_GB` 调大 |
| 显存不足（CUDA out of memory） | 关掉其他占显存的程序；仍不行就告诉我，我把正式画质的贴图降到 1k |
| 没有 MP4，只有帧序列 | ffmpeg 没装好；装好后把 `frames` 文件夹发我，或我给你一条合成命令 |
| 和 Mac 上的画面有极细微的噪点差异 | 正常：不同显卡计算有微小误差，布局和参数完全一样 |
