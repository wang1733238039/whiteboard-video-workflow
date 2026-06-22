#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Whiteboard Video Workflow - 图片生成脚本（ZHiAi）
"""

import argparse
import asyncio
import json
import os
import random
import sys
import time
from pathlib import Path
from urllib.request import urlopen, Request
from urllib.error import HTTPError

# ---------------------------------------------------------------------------
# 配置加载
# ---------------------------------------------------------------------------
SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_DIR = SCRIPT_DIR.parent
CONFIG_FILE = SKILL_DIR / "config.yaml"


def load_config():
    defaults = {
        "api_base": "https://zhiai.art/api/v1/images/generations",
        "model": "Nano Banana 2",
        "aspect_ratio": "16:9",
        "max_retries": 3,
        "retry_base_delay": 3.0,
        "poll_interval": 5.0,
        "poll_max_wait": 300,
        "batch_concurrency": 10,
        # EasyAI / zhiai.art 接口：使用 OpenAI 兼容的 prompt 字段
        # 不需要 image 字段（文生图模式）
        "reference_image_url": "",
        "whiteboard_style": {
            "prompt_template": (
                "Minimal hand-drawn illustration, pure illustration without any text, "
                "off-white paper background(#F6F1E3), dark gray sketch lines, "
                "orange as the only accent color(#CD6441), lots of negative space, "
                "Notion-like doodle aesthetic, faceless round-headed human figure, "
                "clean editorial composition, conceptual rather than literal, "
                "simple background. Absolutely no text, no words, no letters, "
                "no typography, no realism, no 3D, no painterly texture, "
                "no high saturation, no complex scene, no photographic detail. "
                "The overall mood is restrained, lucid, and emotionally calm. "
                "Keep the whole series visually consistent."
            )
        },
    }
    if CONFIG_FILE.exists():
        try:
            import yaml
            data = yaml.safe_load(CONFIG_FILE.read_text(encoding="utf-8"))
            if data:
                img = data.get("image_generation", {})
                for key in list(defaults.keys()):
                    if key != "whiteboard_style" and key in img:
                        defaults[key] = img[key]
                ws = data.get("whiteboard_style", {})
                if ws.get("prompt_template"):
                    defaults["whiteboard_style"]["prompt_template"] = ws["prompt_template"]
        except Exception:
            pass
    return defaults


_cfg = None


def get_cfg():
    global _cfg
    if _cfg is None:
        _cfg = load_config()
    return _cfg


# ---------------------------------------------------------------------------
# 错误分类
# ---------------------------------------------------------------------------
class RetryableError(Exception):
    def __init__(self, message, *, is_rate_limit=False):
        super().__init__(message)
        self.is_rate_limit = is_rate_limit


class FatalError(Exception):
    pass


def classify_error(e):
    msg = str(e).lower()
    if isinstance(e, FatalError):
        return False, False
    if "http 429" in msg or "rate" in msg or "too many" in msg:
        return True, True
    if "http 5" in msg:
        return True, False
    return True, False


# ---------------------------------------------------------------------------
# HTTP 请求
# ---------------------------------------------------------------------------
def request_sync(method, url, body):
    cfg = get_cfg()
    api_key = cfg.get("api_key") or os.environ.get("ZHIAI_API_KEY")
    if not api_key:
        raise FatalError(
            "API key not found. Set api_key in config.yaml or ZHIAI_API_KEY environment variable."
        )

    model = cfg.get("model", "").strip()
    if not model:
        raise FatalError(
            "Model not set. Please fill in image_generation.model in config.yaml."
        )

    payload = json.dumps(body).encode("utf-8")
    req = Request(url, data=payload, method=method)
    req.add_header("Content-Type", "application/json")
    req.add_header("Authorization", f"Bearer {api_key}")

    try:
        with urlopen(req, timeout=60) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except HTTPError as e:
        body_text = e.read().decode("utf-8", errors="replace")
        if e.code in (400, 401, 403):
            raise FatalError(f"HTTP {e.code}: {body_text}")
        if e.code == 429:
            raise RetryableError(f"HTTP 429 (rate limited): {body_text}", is_rate_limit=True)
        if e.code == 424:
            raise FatalError(
                f"上游服务错误 (HTTP 424): {body_text}\n"
                f"提示：当前使用 EasyAI / ZHiAi 兼容接口（OpenAI 风格，字段为 prompt）。"
                f"如果仍然报 424，请用 GET /v1/models/list?type=image_generate 确认 model 名是否有效。"
            )
        raise RetryableError(f"HTTP {e.code}: {body_text}")
    except json.JSONDecodeError as e:
        raise RetryableError(f"Failed to parse response: {e}")
    except Exception as e:
        raise RetryableError(str(e))


# ---------------------------------------------------------------------------
# 重试逻辑
# ---------------------------------------------------------------------------
def calc_backoff(attempt, base=None, is_rate_limit=False):
    cfg = get_cfg()
    base = base or cfg["retry_base_delay"]
    multiplier = 2.0 if is_rate_limit else 1.0
    delay = base * (2 ** (attempt - 1)) * multiplier
    return delay * random.uniform(0.5, 1.5)


async def with_retry(fn, max_retries=None, context=""):
    cfg = get_cfg()
    max_retries = max_retries or cfg["max_retries"]
    for attempt in range(1, max_retries + 1):
        try:
            return await fn()
        except FatalError:
            raise
        except RetryableError as e:
            if attempt == max_retries:
                raise
            delay = calc_backoff(attempt, is_rate_limit=e.is_rate_limit)
            print(f"{context}Attempt {attempt}/{max_retries} failed: {e}. Retrying in {delay:.1f}s...")
            await asyncio.sleep(delay)
        except Exception as e:
            retryable, is_rate_limit = classify_error(e)
            if not retryable or attempt == max_retries:
                raise
            delay = calc_backoff(attempt, is_rate_limit=is_rate_limit)
            print(f"{context}Attempt {attempt}/{max_retries} failed: {e}. Retrying in {delay:.1f}s...")
            await asyncio.sleep(delay)


# ---------------------------------------------------------------------------
# 从响应中提取图片 URL（支持多种格式）
# ---------------------------------------------------------------------------
def _extract_image_url(result):
    """从 ZHiAi / EasyAI 响应中提取图片 URL，支持多种响应格式。

    已知的格式：
    1. OpenAI 风格（gpt-image-2）: {"data": [{"url": "..."}]}
    2. 直接 URL: {"url": "..."}
    3. 任务队列: {"task_id": "..."}
    4. EasyAI 任务队列成功: {"task_id": "...", "status": "success", "output": ["..."], "data": [{"type":"image","url":"..."}]}
    """
    if not isinstance(result, dict):
        return None

    # OpenAI 风格 data[].url（gpt-image-2 用这个格式）
    data = result.get("data")
    if isinstance(data, list) and len(data) > 0:
        first = data[0]
        if isinstance(first, str) and first.startswith("http"):
            return first
        if isinstance(first, dict):
            for k in ["url", "image_url", "image"]:
                v = first.get(k)
                if isinstance(v, str) and v.startswith("http"):
                    return v

    # 同步直接返回：{"url": "..."} 或 {"data": {"url": "..."}}
    for key in ["url", "image_url", "output_url"]:
        val = result.get(key)
        if isinstance(val, str) and val.startswith("http"):
            return val

    # {"data": {"url": "..."}} 嵌套结构
    if isinstance(data, dict):
        for key in ["url", "image_url", "image", "output_url"]:
            val = data.get(key)
            if isinstance(val, str) and val.startswith("http"):
                return val

    # EasyAI 任务结果：{"output": ["url1", "url2", ...]}
    output = result.get("output")
    if isinstance(output, list) and len(output) > 0:
        first = output[0]
        if isinstance(first, str) and first.startswith("http"):
            return first

    # 兜底：images/outputs/results 数组
    for container_key in ["images", "outputs", "results"]:
        container = result.get(container_key)
        if isinstance(container, list) and len(container) > 0:
            first = container[0]
            if isinstance(first, str) and first.startswith("http"):
                return first
            if isinstance(first, dict):
                for k in ["url", "image_url", "image"]:
                    v = first.get(k)
                    if isinstance(v, str) and v.startswith("http"):
                        return v

    return None


# ---------------------------------------------------------------------------
# 同步提交 + 轮询
# ---------------------------------------------------------------------------
def _generate_sync(prompt, aspect_ratio):
    cfg = get_cfg()
    url = cfg["api_base"]
    ref_image = cfg.get("reference_image_url", "").strip()

    # ZHiAi (EasyAI 兼容) 文生图 API 必填字段：model + prompt
    # 可选字段：aspect_ratio / size / n
    # image 字段仅在 reference_image_url 非空（图生图场景）时才传
    body = {
        "model": cfg["model"],
        "prompt": prompt,
    }
    if aspect_ratio:
        body["aspect_ratio"] = aspect_ratio
    if ref_image:
        body["image"] = ref_image

    result = request_sync("POST", url, body)
    return result


async def generate_single(prompt, aspect_ratio, output_dir, index, total):
    cfg = get_cfg()
    tag = f"[{index + 1}/{total}] " if total > 1 else ""

    async def _do():
        print(f"{tag}Submitting image generation...")
        result = await asyncio.to_thread(_generate_sync, prompt, aspect_ratio)

        # 先尝试直接从响应提取 URL（同步模式）
        image_url = _extract_image_url(result)
        if image_url:
            print(f"{tag}Image URL ready: {image_url}")
            return image_url

        # 如果没有 URL，尝试轮询（异步模式）
        task_id = (
            result.get("task_id")
            or result.get("taskId")
            or result.get("id")
            or result.get("job_id")
            or result.get("jobId")
        )
        if not task_id:
            raise RetryableError(
                f"Response has no image URL and no task ID. Response: {json.dumps(result)[:300]}"
            )

        print(f"{tag}Task submitted (ID: {task_id}), polling...")
        image_url = await _poll_async(task_id, tag)
        return image_url

    image_url = await with_retry(_do, max_retries=cfg["max_retries"], context=tag)

    ext = "png"
    timestamp = int(time.time() * 1000)
    suffix = f"_{str(index + 1).zfill(len(str(total)))}" if total > 1 else ""
    filename = f"banana2_{timestamp}{suffix}.{ext}"
    filepath = str(Path(output_dir) / filename)

    async def _download():
        print(f"{tag}Downloading to {filepath}...")
        await asyncio.to_thread(_download_file, image_url, filepath)
        print(f"{tag}Saved: {filepath}")
        return filepath

    return await with_retry(_download, max_retries=cfg["max_retries"], context=tag)


async def _poll_async(task_id, tag=""):
    """轮询异步任务直到图片就绪（如果 API 支持）。"""
    cfg = get_cfg()
    poll_url = cfg["api_base"].rsplit("/", 1)[0] + "/query"

    start_time = time.time()
    poll_errors = 0

    while True:
        elapsed = time.time() - start_time
        if elapsed > cfg.get("poll_max_wait", 300):
            raise RetryableError(f"{tag}Polling timeout after {elapsed:.0f}s")

        await asyncio.sleep(cfg["poll_interval"])

        try:
            body = json.dumps({"task_id": task_id}).encode()
            req = Request(poll_url, data=body, method="POST")
            req.add_header("Content-Type", "application/json")
            api_key = cfg.get("api_key") or os.environ.get("ZHIAI_API_KEY")
            req.add_header("Authorization", f"Bearer {api_key}")

            with urlopen(req, timeout=30) as resp:
                res = json.loads(resp.read().decode("utf-8"))

            status = res.get("status", "").upper()
            print(f"{tag}Poll status: {status}")

            if status == "SUCCESS" or status == "COMPLETED" or status == "DONE":
                url = _extract_image_url(res)
                if url:
                    return url
                raise RetryableError(f"{tag}Poll returned SUCCESS but no image URL: {json.dumps(res)[:200]}")

            if status == "FAILED" or status == "ERROR":
                raise FatalError(f"{tag}Task failed: {json.dumps(res)[:300]}")

            poll_errors = 0

        except FatalError:
            raise
        except Exception as e:
            poll_errors += 1
            if poll_errors > cfg.get("poll_max_retries", 5):
                raise
            print(f"{tag}Poll error (retry {poll_errors}): {e}")


# ---------------------------------------------------------------------------
# 下载文件
# ---------------------------------------------------------------------------
def _download_file(url, dest_path):
    import shutil
    with urlopen(url) as resp:
        if resp.status >= 300 and resp.status < 400:
            location = resp.headers.get("Location")
            if location:
                _download_file(location, dest_path)
                return
        if resp.status != 200:
            raise RuntimeError(f"Download failed with status {resp.status}")
        with open(dest_path, "wb") as f:
            shutil.copyfileobj(resp, f)


# ---------------------------------------------------------------------------
# 批量并发
# ---------------------------------------------------------------------------
async def run_batch(tasks, concurrency=None):
    cfg = get_cfg()
    concurrency = concurrency or cfg["batch_concurrency"]
    semaphore = asyncio.Semaphore(concurrency)
    results = [None] * len(tasks)

    async def worker(i, task):
        async with semaphore:
            try:
                results[i] = await generate_single(
                    task["prompt"], task["aspectRatio"],
                    task["outputDir"], task["index"], task["total"],
                )
            except Exception as e:
                results[i] = {"error": str(e), "task": task}

    await asyncio.gather(*(worker(i, t) for i, t in enumerate(tasks)))

    failed_indices = [i for i, r in enumerate(results) if isinstance(r, dict) and r.get("error")]
    if failed_indices:
        print(f"\nRetrying {len(failed_indices)} failed tasks...")
        await asyncio.sleep(cfg["retry_base_delay"])

        async def retry_worker(i):
            async with semaphore:
                task = results[i]["task"]
                try:
                    results[i] = await generate_single(
                        task["prompt"], task["aspectRatio"],
                        task["outputDir"], task["index"], task["total"],
                    )
                except Exception as e:
                    results[i] = {"error": str(e)}

        await asyncio.gather(*(retry_worker(i) for i in failed_indices))

    return results


# ---------------------------------------------------------------------------
# 主入口
# ---------------------------------------------------------------------------
async def main():
    cfg = get_cfg()

    parser = argparse.ArgumentParser(description="ZHiAi 图片生成器")
    parser.add_argument("prompt", nargs="?", default="", help="图片生成提示词（单张）或 JSON 字符串数组（批量）。也可省略，改为使用 --prompts-file")
    parser.add_argument("aspect_ratio", nargs="?", default=None, help="图片宽高比（如 16:9）")
    parser.add_argument("output_dir", nargs="?", default=None, help="输出目录")
    parser.add_argument("--prompts-file", metavar="FILE", help="从 JSON 文件读取提示词数组（推荐用于批量生成，避免命令行引号转义问题）")
    args = parser.parse_args()

    # 加载 prompts
    prompts = None
    if args.prompts_file:
        try:
            with open(args.prompts_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, list) and all(isinstance(p, str) for p in data):
                prompts = data
            else:
                print(f"Error: --prompts-file 内容必须是字符串数组")
                sys.exit(1)
        except Exception as e:
            print(f"Error: 读取 --prompts-file 失败: {e}")
            sys.exit(1)
    elif args.prompt.strip():
        try:
            parsed = json.loads(args.prompt)
            if isinstance(parsed, list) and len(parsed) > 0 and isinstance(parsed[0], str):
                prompts = parsed
        except (json.JSONDecodeError, ValueError):
            pass
        if not prompts:
            prompts = [args.prompt]
    else:
        print("Error: 必须提供 prompt 参数或 --prompts-file")
        sys.exit(1)

    # 确定 aspect_ratio 和 output_dir
    aspect_ratio = args.aspect_ratio if args.aspect_ratio else cfg.get("aspect_ratio", "16:9")
    output_dir = args.output_dir if args.output_dir else os.getcwd()

    Path(output_dir).mkdir(parents=True, exist_ok=True)

    total = len(prompts)
    is_batch = total > 1

    if is_batch:
        print(f"Batch mode: generating {total} images (concurrency: {cfg['batch_concurrency']})...")

    whiteboard_prompt_template = cfg.get("whiteboard_style", {}).get("prompt_template", "")

    tasks = [
        {
            "prompt": whiteboard_prompt_template + prompt,
            "aspectRatio": aspect_ratio,
            "outputDir": output_dir,
            "index": i,
            "total": total,
        }
        for i, prompt in enumerate(prompts)
    ]

    results = await run_batch(tasks)

    succeeded = [r for r in results if isinstance(r, str)]
    failed = [r for r in results if isinstance(r, dict) and r.get("error")]
    if is_batch:
        print(f"\nBatch complete: {len(succeeded)} succeeded, {len(failed)} failed.")
    if failed:
        for f in failed:
            print(f"  Error: {f['error']}")

    print(f"\n__RESULTS__{json.dumps(results)}")


if __name__ == "__main__":
    asyncio.run(main())
