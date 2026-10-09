#!/usr/bin/env python3
"""
LLM 推理增强层 —— 国产模型（Kimi / Moonshot）真实接入
=====================================================
职责:
  - 对 SymPy 无法确定性求解的概念题/证明题/物理文字题，调用国产大模型 Kimi 求解
  - 把每一次真实调用的 请求体 / 响应体 / 耗时 / token 用量 完整记录到 AI 日志
    （评审需要可追溯的真实调用证据，而非"模板假装推理"）

设计要点:
  - 零第三方 SDK 依赖，仅用标准库 urllib 直连 REST API，便于评委复现
  - API Key 只从环境变量 MOONSHOT_API_KEY 读取，绝不硬编码、绝不入库
  - 无 Key 或调用失败时安全降级到本地规则模板（不抛异常、不伪造成功）
  - Kimi k2 系列要求 temperature=1（该系列不接受其他取值），通过固定 system prompt
    + 低温替代方案失效的约束下，用结构化的 FINAL 标记来稳定抽取答案

环境变量:
  MOONSHOT_API_KEY   必填，Kimi 开放平台密钥 (sk-...)
  MOONSHOT_BASE_URL  选填，默认 https://api.moonshot.cn/v1
  MOONSHOT_MODEL     选填，默认 kimi-k2.6
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path

DEFAULT_BASE_URL = "https://api.moonshot.cn/v1"
DEFAULT_MODEL = "kimi-k2.6"

# AI 调用日志的落盘位置（相对本文件）
_LOG_PATH = Path(__file__).resolve().parent.parent / "logs" / "llm_calls.jsonl"


def _load_dotenv():
    """从项目根目录 .env 读取配置（不覆盖已有环境变量）。

    这样评委 clone 后只要放一个 .env 就能复现，无需 export。
    """
    env_path = Path(__file__).resolve().parent.parent.parent / ".env"
    if not env_path.exists():
        return
    try:
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            k, v = k.strip(), v.strip().strip('"').strip("'")
            if k and k not in os.environ:
                os.environ[k] = v
    except Exception:
        pass


_load_dotenv()


def get_api_key() -> str | None:
    return os.environ.get("MOONSHOT_API_KEY") or os.environ.get("KIMI_API_KEY")


def get_base_url() -> str:
    return os.environ.get("MOONSHOT_BASE_URL", DEFAULT_BASE_URL).rstrip("/")


def get_model() -> str:
    return os.environ.get("MOONSHOT_MODEL", DEFAULT_MODEL)


def is_available() -> bool:
    """是否具备真实调用条件。"""
    return bool(get_api_key())


SYSTEM_PROMPT = (
    "你是一位严谨的大学数学助教，正在批改 Berkeley Math 1A 微积分作业。"
    "请用简体中文分步解答，数学公式用 LaTeX 表示（行内 $...$，行间 \\[...\\]）。"
    "要求：\n"
    "1. 先给结论，再给推理步骤；\n"
    "2. 涉及定义时给出严格表述，涉及判断时给出反例或理由；\n"
    "3. 不要复述题目，不要写与解答无关的客套话；\n"
    "4. 若题目要求画图，用文字精确描述图像的形状与关键特征。"
)

USER_TEMPLATE = (
    "请解答下面这道题，并在最后一行用 `FINAL: <答案>` 的形式给出最终答案。\n\n"
    "题目：{problem}"
)


# Kimi k2 系列只接受 temperature=1（其他取值返回 HTTP 400
# "invalid temperature: only 1 is allowed for this model"）。
# 首次被服务端拒绝后缓存该模型的合法取值，避免每道题都白撞一次 400。
_TEMPERATURE_CACHE: dict = {}


def _effective_temperature(model: str, requested: float) -> float:
    """返回该模型实际接受的 temperature。k2 系列被拒后固定为 1。"""
    return _TEMPERATURE_CACHE.get(model, requested)


def report_temperature_rejected(model: str):
    """服务端明确拒绝 temperature 后调用，后续请求直接使用 1。"""
    _TEMPERATURE_CACHE[model] = 1.0


def call_llm(problem_text: str, *, timeout: int = 120,
             max_tokens: int = 2000, temperature: float = 1.0,
             max_retries: int = 2) -> dict:
    """调用 Kimi 求解一道题。

    返回 dict:
      成功: {"ok": True, "content": str, "elapsed": float, "usage": {...},
             "request": {...}, "response": {...}, "model": str,
             "attempts": int, "response_id": str}
      失败: {"ok": False, "error": str, "elapsed": float, "request": {...},
             "attempts": int}

    重试策略：仅对网络类异常与 429/5xx 重试；4xx（temperature 非法、鉴权失败）
    不重试，但完整记录错误体以便追溯。
    """
    key = get_api_key()
    model = get_model()
    url = f"{get_base_url()}/chat/completions"

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": USER_TEMPLATE.format(problem=problem_text)},
        ],
        "temperature": _effective_temperature(model, temperature),
        "max_tokens": max_tokens,
    }

    record = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "provider": "Moonshot (Kimi)",
        "model": model,
        "endpoint": url,
        "problem": problem_text,
        "request": payload,
    }

    if not key:
        record.update({"ok": False, "error": "MOONSHOT_API_KEY 未配置",
                       "elapsed": 0.0})
        _append_log(record)
        return record

    t0 = time.time()
    attempts = 0
    last_error = ""
    while attempts <= max_retries:
        attempts += 1
        req = urllib.request.Request(
            url,
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {key}",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = resp.read().decode("utf-8")
                body = json.loads(raw)
            elapsed = time.time() - t0
            content = body["choices"][0]["message"]["content"]
            record.update({
                "ok": True,
                "elapsed": round(elapsed, 2),
                "attempts": attempts,
                "content": content,
                "content_chars": len(content),
                "finish_reason": body["choices"][0].get("finish_reason"),
                "usage": body.get("usage", {}),
                "response_id": body.get("id"),
                "response_model": body.get("model"),
                "response_created": body.get("created"),
                "response": body,
            })
            _append_log(record)
            return record
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", errors="replace")[:2000]
            last_error = f"HTTP {e.code}: {detail}"
            # k2 系列拒绝非 1 的 temperature：改用它接受的取值后立即重试一次
            if e.code == 400 and "temperature" in detail and \
                    _effective_temperature(model, temperature) != 1.0:
                report_temperature_rejected(model)
                payload["temperature"] = 1.0
                continue
            # 4xx（参数/鉴权错误）重试无意义
            if 400 <= e.code < 500 and e.code != 429:
                break
        except Exception as e:
            last_error = f"{type(e).__name__}: {e}"
        if attempts <= max_retries:
            time.sleep(1.5 * attempts)

    elapsed = time.time() - t0
    record.update({"ok": False, "elapsed": round(elapsed, 2),
                   "attempts": attempts, "error": last_error})
    _append_log(record)
    return record


def _append_log(record: dict):
    """每次真实调用追加一行 JSON，形成可追溯的 AI 调用日志。"""
    try:
        _LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception:
        pass


def extract_answer(content: str) -> str:
    """从模型输出里抽取 FINAL: 后面的答案；没有就取最后一段。"""
    if not content:
        return ""
    for line in reversed(content.splitlines()):
        s = line.strip().lstrip("*_ `#").strip()
        if s.upper().startswith("FINAL:"):
            return s.split(":", 1)[1].strip().strip("*_ `")
    lines = [l.strip() for l in content.splitlines() if l.strip()]
    return lines[-1] if lines else ""


def extract_steps(content: str) -> list:
    """把模型输出切成适合 LaTeX 渲染的步骤（按行/编号切分）。"""
    if not content:
        return []
    steps = []
    for raw in content.splitlines():
        s = raw.strip()
        if not s:
            continue
        steps.append(s)
    return steps


if __name__ == "__main__":
    # 自检：python llm_client.py "求 lim_{x->0} sin(x)/x"
    import sys
    q = sys.argv[1] if len(sys.argv) > 1 else "Is ∞ a number?"
    print(f"可用: {is_available()} | 模型: {get_model()} | 端点: {get_base_url()}")
    r = call_llm(q)
    if r.get("ok"):
        print(f"✅ 耗时 {r['elapsed']}s, tokens={r.get('usage')}")
        print(r["content"][:600])
        print("--- FINAL:", extract_answer(r["content"]))
    else:
        print("❌", r.get("error"))
