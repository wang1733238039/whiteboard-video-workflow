---
name: whiteboard-video-workflow
description: 从 SRT 字幕文件自动生成完整白板动画视频的端到端工作流。依次完成分镜解析、图片生成、视频生成三个阶段。当用户提供 SRT 文件并要求生成白板动画视频，或说"从字幕生成白板视频"、"白板视频工作流"时触发。
---

# Whiteboard Video Workflow

从 SRT 字幕文件到完整白板动画视频片段的自动化工作流。

## 输入参数

| 参数 | 必填 | 说明 |
|------|------|------|
| `srtPath` | 是 | SRT 字幕文件的绝对路径 |
| `outputDir` | 否 | 输出根目录，默认为 SRT 文件所在目录 |

## 工作流步骤

整个流程分为 10 步，必须严格按顺序执行。步骤 3、5、7 使用 subagent，其余步骤由主 agent 直接执行。

### 步骤 0: 环境准备

首次运行前，先执行环境准备脚本，创建 Python 虚拟环境并安装所有依赖：

```bash
py <skill-dir>/scripts/setup_env.py
```

- 脚本会自动创建 `.venv` 虚拟环境（如已存在则跳过）
- 自动安装 opencv-python、numpy、av 三个视频处理依赖
- **输出最后一行 `PYTHON_PATH=<路径>`**，记录该路径用于步骤 7 和步骤 8
- 如果环境已就绪（所有依赖已安装），直接输出路径，不重复安装

> **Windows 用户注意**：请使用 `py` 命令而非 `python3`，`py` 是 Windows 自带的 Python 启动器。

#### 故障排查

| 问题 | 原因 | 修复方法 |
|------|------|----------|
| `py` 命令不存在 | 未安装 Python Launcher | 从 python.org 安装 Python，勾选 "Add Python to PATH" |
| opencv/numpy/av 安装失败 | 网络或权限问题 | 以管理员身份运行 PowerShell，重试 |
| `.venv` 创建失败 | 路径权限问题 | 确认 skill 目录有写入权限 |

### 步骤 1: 确定输出目录

- 如果用户未指定 `outputDir`，则使用 `srtPath` 所在目录作为输出根目录
- 将 `outputDir` 转换为绝对路径

### 步骤 2: 创建输出目录结构

运行本 skill 的 `workflow_helper.py`：

```bash
py <skill-dir>/scripts/workflow_helper.py init-dirs "<outputDir>"
```

输出 JSON 含 `storyboardDir`、`imageDir`、`videoDir` 三个绝对路径，保存备用。

### 步骤 3: 解析 SRT 生成分镜脚本（subagent）

启动一个 **subagent**，指令为：

> 使用 Read 工具读取文件 `<将本 skill 目录替换为实际绝对路径>/references/storyboard-parser.md`，按照其中的工作流步骤执行。
>
> 输入参数：
> - srtPath = `<将srtPath替换为实际绝对路径>`
> - projectRoot = `<将storyboardDir替换为实际绝对路径>`
> - skill-dir = `<将本 skill 目录替换为实际绝对路径>`（用于定位脚本）
>
> 完成后返回 storyboard.json 的绝对路径和场景数量。
>
> **注意：主 agent 必须将实际路径值填入指令中，不要传递变量名，subagent 无法访问主 agent 的上下文。**

**必须等待 subagent 完成并获取 storyboard.json 路径后才继续。**

### 步骤 4: 解析 storyboard 生成图片提示词

运行本 skill 的 `workflow_helper.py`：

```bash
py <skill-dir>/scripts/workflow_helper.py gen-prompts "<storyboardJsonPath>"
```

输出一个 JSON 字符串数组，每个元素是一个带白板风格前缀的图片生成提示词，数组索引与 storyboard 中的 scenes 顺序一一对应。

同时从 storyboard.json 中提取每个 scene 的 `duration` 值（毫秒），按顺序记录为数组备用。

### 步骤 5: 批量生成白板图片（subagent）

启动一个 **subagent**，指令为：

> 使用 Read 工具读取文件 `<将本 skill 目录替换为实际绝对路径>/references/image-generator.md`，按照其中的工作流步骤执行。
>
> **第一步必须执行：读取 `<skill-dir>/config.yaml`，提取 `image_generation` 节点下的所有参数（API 地址、分辨率、并发数等）。后续所有参数引用 config.yaml 中的值。**
>
> 使用批量模式，将以下 JSON 字符串数组作为 prompt 参数传入：
> `<将步骤4输出的提示词JSON数组的实际内容粘贴于此>`
>
> 参数：
> - skill-dir = `<将本 skill 目录替换为实际绝对路径>`（用于定位脚本和 config.yaml）
> - 输出目录 = `<将imageDir替换为实际绝对路径>`
> - 宽高比 = 来自 `config.yaml` 的 `image_generation.aspect_ratio`（默认为 `"16:9"`，如需覆盖可指定其他值）
>
> **注意：主 agent 必须将实际提示词内容和路径值填入指令中，不要传递变量名，subagent 无法访问主 agent 的上下文。**
>
> **重要：** 返回所有生成图片的路径列表，顺序必须与提示词数组顺序一致。

**必须等待 subagent 完成并获取所有图片路径后才继续。**

### 步骤 6: 校验图片顺序

确认步骤 5 返回的图片路径数组长度与 storyboard 的 scenes 数量一致，顺序正确（第 i 张图片对应第 i 个 scene）。

### 步骤 7: 批量生成白板动画视频片段（subagent）

启动一个 **subagent**，指令为：

> **第一步：确保环境就绪**
>
> 调用 `<skill-dir>/scripts/setup_env.py --check`，如果失败则先运行 `setup_env.py`（不带参数）准备环境。
>
> 获取虚拟环境的 Python 路径（最后一行 `PYTHON_PATH=`）。
>
> **第二步：运行批量生成脚本**
>
> 使用批量模式，将以下图片路径和时长传入 `batch_generate.py`：
>
> ```
> <PYTHON_PATH> <skill-dir>/scripts/batch_generate.py \
>   --images <imagePaths[0]> <imagePaths[1]> ... \
>   --durations <durations[0]> <durations[1]> ... \
>   --output-dir <videoDir绝对路径>
> ```
>
> 参数说明：
> - `--images`：按分镜顺序排列的图片路径列表（空格分隔）
> - `--durations`：与图片一一对应的时长列表（**单位：毫秒**，直接使用 storyboard 中的 duration 值，无需转换）
> - `--output-dir`：`<videoDir绝对路径>`
>
> **注意：主 agent 必须将实际路径值填入指令中，不要传递变量名，subagent 无法访问主 agent 的上下文。**
>
> **重要：** 完成后，收集 `<videoDir>` 目录下所有生成的视频文件路径，按文件名时间戳排序，将完整的视频路径列表返回给主 agent。顺序必须与输入图片顺序一致。

**必须等待 subagent 完成并获取所有视频路径后才继续。**

### 步骤 8: 合并视频片段

运行本 skill 的 `workflow_helper.py`，将所有视频片段按顺序合并为一个完整视频。**必须使用步骤 0 获取的 `PYTHON_PATH`**（PyAV 依赖在虚拟环境中）：

```bash
<PYTHON_PATH> <skill-dir>/scripts/workflow_helper.py merge-videos "<outputDir>" <videoPath1> <videoPath2> ...
```

- 第一个参数为输出目录（合并后的视频保存在此目录）
- 后续参数为按分镜顺序排列的视频片段路径

输出 JSON 含 `mergedVideo`（合并后的视频绝对路径）、`totalSegments`、`sizeMB`。

### 步骤 9: 输出结果

输出最终结果，包含合并后的完整视频路径和所有片段信息：

输出格式示例：

```json
{
  "mergedVideo": "/path/to/output/白板视频_20260329_120000.mp4",
  "videoSegments": [
    "/path/to/video/vid_20260329_120000_h264.mp4",
    "/path/to/video/vid_20260329_120010_h264.mp4"
  ],
  "totalSegments": 2,
  "sizeMB": 15.3,
  "outputDir": "/path/to/output"
}
```

## 关键约束

- 步骤 0 必须在首次运行时执行（setup_env.py 会在环境就绪后直接输出路径，不会重复安装）
- 步骤 3、5、7 必须使用 subagent 执行，主 agent 等待结果
- 步骤 0 获取的 `PYTHON_PATH` 必须传递给步骤 7 和步骤 8 使用（PyAV 依赖在虚拟环境中）
- 图片和视频的顺序必须与 storyboard 的 scenes 顺序严格对应
- duration 贯穿全链路使用毫秒，从 storyboard 到 batch_generate.py 再到 generate_whiteboard.py 统一为毫秒，避免浮点转换丢失精度
- 步骤 8 使用 PyAV（Python 库）合并视频片段，通过 H.264 重新编码输出统一格式的最终视频

## Resources

### references/

- `storyboard-parser.md` - SRT 分镜解析工作流指令，由步骤 3 的 subagent 读取执行
- `image-generator.md` - ZHiAi 图片生成工作流指令，由步骤 5 的 subagent 读取执行
- `whiteboard-animation.md` - 白板动画生成技术参考文档（供 subagent 理解内部原理）

### scripts/

- `setup_env.py` - Python 虚拟环境准备脚本，安装视频处理依赖，输出 PYTHON_PATH
- `workflow_helper.py` - 提供 `init-dirs`、`gen-prompts`、`merge-videos` 三个子命令
- `generate-storyboard.py` - 解析 SRT + groups.json 生成 storyboard.json
- `generate-image.py` - ZHiAi 文生图，支持单张和批量并发模式，**配置从 `config.yaml` 读取**
- `batch_generate.py` - 批量调用 generate_whiteboard.py，生成多个白板动画视频片段
- `generate_whiteboard.py` - 单张图片转白板手绘动画（核心算法，cv2 + numpy + av）

### 配置文件

**`config.yaml`**（skill 根目录下）— 所有可调整参数的统一入口。

常用配置项：

| 分类 | 配置项 | 作用 |
|------|--------|------|
| **图片生成** | `image_generation.api_base` | API 服务地址 |
| **图片生成** | `image_generation.model` | 模型标识符（必填） |
| **图片生成** | `image_generation.aspect_ratio` | 默认宽高比 |
| **图片生成** | `image_generation.max_retries` | 重试次数 |
| **图片生成** | `image_generation.poll_interval` | 轮询间隔（秒） |
| **图片生成** | `image_generation.poll_max_wait` | 单次生成最大等待时间（秒） |
| **图片生成** | `image_generation.batch_concurrency` | 批量并发数 |
| **图片生成** | `image_generation.api_key` | API 密钥（必填，优先使用环境变量 `ZHIAI_API_KEY`） |
| **图片生成** | `whiteboard_style.prompt_template` | 白板风格提示词前缀，决定图片艺术风格 |
| **分镜解析** | `storyboard.target_scene_duration` | 目标场景时长范围（秒） |
| **动画参数** | `animation.phases.sketch_weight` / `color_weight` | 手绘/上色时长比例 |
| **动画参数** | `animation.phases.hold_duration` | 停留阶段基准时长 |
| **动画参数** | `animation.drawing.split_len` | 网格切分边长 |
| **动画参数** | `animation.drawing.color_brush_radius` | 上色笔刷半径 |
| **动画参数** | `animation.colors.background_hex` | 背景画布颜色 |

**API Key 优先级**：`ZHIAI_API_KEY` 环境变量 > `config.yaml` 中的 `image_generation.api_key`。

**切换图片生成服务**：只需修改 `config.yaml` 中 `image_generation` 下的 `api_base`、`model`、`api_key` 三项，脚本会自动使用新配置。

**白板风格提示词模板**：`config.yaml` 中的 `whiteboard_style.prompt_template`，拼接在每个生图 prompt 的最前面。

**视频动画参数**（位于 `scripts/generate_whiteboard.py` 文件顶部的常量定义）：如需调整帧率、网格大小、上色笔刷半径等，请直接编辑该脚本文件顶部的常量。

**手部素材替换**：直接替换 `assets/drawing-hand.png` 文件即可，建议保持原图比例和相对位置。
