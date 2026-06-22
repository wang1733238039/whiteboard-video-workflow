# ZHiAi 图片生成器

## 前置条件

必须确保 `config.yaml` 中 `image_generation` 下的必填字段已填写：

- `api_base`（API 服务地址，默认 `https://zhiai.art/api/v1/images/generations`）
- `model`（模型名称，如 `Nano Banana 2`）
- `api_key`（API 密钥，**优先从环境变量 `ZHIAI_API_KEY` 读取**，如未设置则读 `config.yaml`）

如果未填写，脚本会报错退出，提示具体缺失字段。

## 配置文件

所有可调整参数集中在 `config.yaml`（skill 根目录下）。subagent **在执行前必须先读取该文件**，后续所有参数引用 config.yaml 中的值。

### subagent 执行步骤

1. **读取配置文件**：读取 `<skill-dir>/config.yaml`，提取 `image_generation` 节点下的所有参数
2. **执行生成脚本**：`py <skill-dir>/scripts/generate-image.py`，脚本内部已实现从 `config.yaml` 读取参数，无需在命令行手动指定

### 参数引用对照表

subagent 在读取 `config.yaml` 后，应按以下对应关系使用参数：

| config.yaml 中的键 | 用途 | 用法说明 |
|------|------|----------|
| `image_generation.api_base` | API 服务地址 | 直接作为 POST 请求目标 URL |
| `image_generation.model` | 模型标识符 | 传给 API 的 `model` 字段 |
| `image_generation.aspect_ratio` | 默认宽高比 | 命令行第二个参数；如用户未指定则使用此值 |
| `image_generation.max_retries` | 下载重试次数 | 影响脚本内部的重试逻辑 |
| `image_generation.retry_base_delay` | 重试基础间隔（秒） | 影响指数退避的计算基准 |
| `image_generation.poll_interval` | 轮询间隔（秒） | 提交后等待图片就绪的间隔 |
| `image_generation.poll_max_wait` | 最大等待时间（秒） | 单次生成任务的最长等待时间 |
| `image_generation.batch_concurrency` | 批量并发数 | 同时最多运行多少个生成任务 |
| `whiteboard_style.prompt_template` | 白板风格提示词前缀 | **拼接在每个 prompt 的最前面**，决定图片的整体艺术风格 |

### 修改白板风格

如需修改白板图片的艺术风格（如背景色、线条色、强调色、画面构图风格等），编辑 `config.yaml` 中 `whiteboard_style.prompt_template` 的内容即可。

示例——将背景色改为浅蓝色、强调色改为绿色：

```yaml
whiteboard_style:
  prompt_template: |
    Minimal hand-drawn illustration, pure illustration without any text,
    off-white paper background(#E8F4F8), dark gray sketch lines,
    green as the only accent color(#4CAF50), lots of negative space,
    Notion-like doodle aesthetic, faceless round-headed human figure,
    clean editorial composition, conceptual rather than literal,
    simple background. Absolutely no text, no words, no letters,
    no typography, no realism, no 3D, no painterly texture,
    no high saturation, no complex scene, no photographic detail.
    The overall mood is restrained, lucid, and emotionally calm.
    Keep the whole series visually consistent.
```

### 切换图片生成服务

只需修改 `config.yaml` 中 `image_generation` 下的两项（`api_key` 优先通过环境变量 `ZHIAI_API_KEY` 设置）：

```
api_base  → 新的 API 服务地址（完整 URL）
model     → 新的模型标识符
```

## 用法

运行内置脚本：

```bash
py <skill-dir>/scripts/generate-image.py "<提示词>" "<宽高比>" "<输出目录>"
```

**注意**：`<skill-dir>` 是 `whiteboard-video-workflow` skill 的绝对路径，由主 agent 在 subagent 指令中提供。

**参数：**
1. `prompt`（可选，与 `--prompts-file` 二选一）— 图片生成提示词。支持两种模式：
   - **单张模式**：传入普通字符串，如 `"一只猫坐在窗台上"`。
   - **批量模式**：传入 JSON 编码的字符串数组，如 `'["提示词1","提示词2","提示词3"]'`。
2. `--prompts-file FILE`（可选，与 `prompt` 参数二选一）— 从 JSON 文件读取提示词数组（推荐用于批量生成，避免命令行引号转义问题）。文件内容须为字符串数组。
3. `aspect-ratio`（可选）— 图片宽高比。**默认值为 `config.yaml` 中的 `image_generation.aspect_ratio`**（默认 `"16:9"`）。
4. `output-dir`（可选，默认值：当前工作目录）— 生成图片的保存目录。

**并发数**由 `config.yaml` 中的 `batch_concurrency` 控制（默认 10）。

**示例：**

单张生成：
```bash
py <skill-dir>/scripts/generate-image.py "一只猫坐在窗台上，夕阳西下" "16:9" "./output"
```

批量生成（通过命令行 JSON 参数）：
```bash
py <skill-dir>/scripts/generate-image.py '["一只猫坐在窗台上","一只狗在草地上奔跑","日落时分的海边"]' "16:9" "./output"
```

批量生成（通过 `--prompts-file`，**推荐**，跨 shell 更稳定）：
```bash
# 先将提示词写入 JSON 文件
py -c "import json; json.dump(['提示词1', '提示词2', '提示词3'], open('prompts.json', 'w', encoding='utf-8'), ensure_ascii=False)"
# 然后传入文件路径
py <skill-dir>/scripts/generate-image.py --prompts-file prompts.json "16:9" "./output"
```

## 工作流程

1. **读取 config.yaml**（必须第一步）：提取 `image_generation` 下所有参数值备用
2. 验证必填字段（`api_base`、`model`）非空，`api_key` 支持环境变量 `ZHIAI_API_KEY`
3. 验证提示词来源（`prompt` 参数或 `--prompts-file`）
4. 检测 `prompt` 是否为 JSON 数组格式，自动区分单张/批量模式
5. 脚本内部自动处理（参数来自 config.yaml）：
   - 提交生成请求，失败时按 `max_retries` 重试
   - 从响应中提取图片 URL（支持多种响应格式）
   - 下载结果图片，文件名基于时间戳命名（批量模式下文件名会附加序号后缀）
   - **批量模式**：按 `batch_concurrency` 个并发 worker 同时执行生成任务
6. 向用户报告保存的文件路径

## 批量模式说明

- 当 `prompt` 参数是 JSON 字符串数组时自动进入批量模式
- **并发数由 `config.yaml` 中的 `batch_concurrency` 控制**（默认 10）
- 每张图片独立处理，单张失败不影响其他图片
- 输出文件名格式：`banana2_<timestamp>_<序号>.<ext>`（如 `banana2_1714700000000_01.png`）
- 执行结束后会输出汇总信息：成功数和失败数
- 脚本输出的最后一行以 `__RESULTS__` 前缀加上 JSON 数组，包含每张图片的保存路径或错误信息

## 资源文件

- `config.yaml` — 统一配置文件，包含所有可调整参数（**必须读取**）
- `scripts/generate-image.py` — 独立的 Python 脚本，处理完整的生成-下载流程，支持单张和批量并发模式
