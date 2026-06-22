# Whiteboard Video Workflow

从 SRT 字幕文件到完整白板动画视频的端到端自动化 skill。详细工作流请阅读 [`SKILL.md`](./SKILL.md)。

## 安装 Skill

将整个 `whiteboard-video-workflow` 文件夹复制到用户级 skills 目录：

```powershell
Copy-Item -LiteralPath .\whiteboard-video-workflow -Destination "$env:USERPROFILE\.agents\skills\whiteboard-video-workflow" -Recurse -Force
```

安装后目录应类似：

```text
%USERPROFILE%\.agents\skills\whiteboard-video-workflow\SKILL.md
%USERPROFILE%\.agents\skills\whiteboard-video-workflow\scripts\setup_env.py
%USERPROFILE%\.agents\skills\whiteboard-video-workflow\assets\drawing-hand.png
```

首次使用前运行环境准备脚本：

```powershell
py "$env:USERPROFILE\.agents\skills\whiteboard-video-workflow\scripts\setup_env.py"
```

脚本会在 skill 目录下创建 `.venv` 并安装视频处理依赖。

## 快速上手

### 1. 准备环境

- Python 3.9 或更高版本
- 一份 SRT 字幕文件
- 一个 ZHiAi API Key（在 [ZHiAi](https://zhiai.art/) 申请）

### 2. 安装依赖

运行环境准备脚本：

```bash
py scripts/setup_env.py
```

脚本会自动创建 `.venv` 虚拟环境并安装依赖。

### 3. 配置 API Key

推荐通过环境变量设置 API Key，避免泄露到配置文件。将下面命令中的占位符替换为本机私密值后，在当前终端运行：

```bash
# Windows PowerShell
Set-Item Env:ZHIAI_API_KEY <ZHIAI_API_KEY>

# Linux/macOS
env ZHIAI_API_KEY=<ZHIAI_API_KEY> your-command
```

`config.yaml` 中的 `image_generation.api_key` 默认保持为空。仅在本地私有环境确有需要时才写入配置文件，且不要提交真实密钥。

### 4. 触发工作流

在 Cursor / Claude Code 中向 agent 提供 SRT 路径，例如：

> 用 `D:/videos/talk.srt` 生成一段白板视频

agent 会按 `SKILL.md` 的 10 个步骤自动执行。也可以指定输出目录：

> 用 `D:/videos/talk.srt` 生成白板视频，输出到 `D:/videos/output`

## 目录结构

```text
whiteboard-video-workflow/
├── SKILL.md                      # 工作流主文档（agent 必读）
├── README.md                     # 本文件
├── config.yaml                   # 可调整参数（不要写入真实密钥后提交）
├── .gitignore
├── requirements.txt
├── assets/
│   └── drawing-hand.png          # 手部素材
├── references/
│   ├── storyboard-parser.md      # 步骤 3 subagent 读取
│   ├── image-generator.md        # 步骤 5 subagent 读取
│   └── whiteboard-animation.md   # 白板动画技术参考
└── scripts/
    ├── setup_env.py              # 环境准备
    ├── workflow_helper.py        # init-dirs / gen-prompts / merge-videos
    ├── generate-storyboard.py    # SRT + groups -> storyboard.json
    ├── generate-image.py         # 调用 ZHiAi 生图
    ├── batch_generate.py         # 批量生成白板动画片段
    └── generate_whiteboard.py    # 单张图片转白板动画
```

## 常见问题

**Q：脚本找不到 `py` 命令？**
A：请从 python.org 安装 Python，并勾选 “Add Python to PATH”。Windows 推荐使用 `py` 启动器。

**Q：图片生成提示没有 API Key？**
A：优先设置 `ZHIAI_API_KEY` 环境变量，再重新运行工作流。

**Q：图片生成全部超时？**
A：检查 `config.yaml` 中 `image_generation.api_base` 是否能访问，必要时调大 `poll_max_wait` 和 `poll_interval`。

**Q：想换一种图片风格？**
A：编辑 `config.yaml` 中的 `whiteboard_style.prompt_template` 即可，无需改代码。

**Q：生成的视频没有手绘动画效果？**
A：确认已运行 `py scripts/setup_env.py`，并且 `assets/drawing-hand.png` 存在。


