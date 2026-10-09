#!/usr/bin/env python3
"""
Stage 2: 题目解析（国产模型增强版）
==================================
识别题号、子题、数学公式，分类题目类型。
相比 starter kit 新增:
  - 中文题号 "1、"、"（1）"、"第一题"
  - 新学科关键词: 矩阵/特征值/微分方程/牛顿/动能/定积分 等
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Optional


# ─────────────────────────────────────────────
# 题号 / 子题模式
# ─────────────────────────────────────────────

PROBLEM_PATTERNS = [
    re.compile(r"^(?:Problem|Prob\.?)\s+(\d+)\s*[:.：]?\s*(.*)", re.IGNORECASE),
    re.compile(r"^(?:问题|题目?|第)\s*(\d+)\s*(?:题|[:.：])?\s*(.*)"),
    re.compile(r"^(\d+)\s*[.)、．]\s+(.+)"),
    re.compile(r"^Q(\d+)\s*[:.：]?\s*(.*)", re.IGNORECASE),
    re.compile(r"^Exercise\s+(\d+)\s*[:.：]?\s*(.*)", re.IGNORECASE),
    re.compile(r"^（\s*(\d+)\s*）\s*(.*)"),
]

SUB_PROBLEM_PATTERNS = [
    re.compile(r"^\(([a-z])\)\s*(.*)"),
    re.compile(r"^([a-z])\)\s*(.*)"),
    re.compile(r"^([a-z])\.\s+(.*)"),
    re.compile(r"^（\s*([a-z])\s*）\s*(.*)"),
]

SECTION_PATTERNS = [
    re.compile(r"^#{1,3}\s*Additional\s+Problems?\s*$", re.IGNORECASE),
    re.compile(r"^#{1,3}\s*Problems?\s*$", re.IGNORECASE),
    re.compile(r"^#{1,3}\s*Questions?\s*$", re.IGNORECASE),
    re.compile(r"^#{1,3}\s*Part\s+([A-Z])", re.IGNORECASE),
]


def detect_section(line: str) -> Optional[str]:
    s = line.strip()
    if re.match(r"^#{1,3}\s*Additional\s+Problems?\s*$", s, re.IGNORECASE):
        return "AP"
    if re.match(r"^#{1,3}\s*Problems?\s*$", s, re.IGNORECASE):
        return "P"
    if re.match(r"^#{1,3}\s*Questions?\s*$", s, re.IGNORECASE):
        return "Q"
    m = re.match(r"^#{1,3}\s*Part\s+([A-Z])", s, re.IGNORECASE)
    if m:
        return f"Part{m.group(1).upper()}"
    return None


def detect_problem_start(line: str) -> Optional[tuple]:
    s = line.strip()
    for pat in PROBLEM_PATTERNS:
        m = pat.match(s)
        if m:
            return (m.group(1), m.group(2))
    return None


def detect_sub_problem(line: str) -> Optional[tuple]:
    s = line.strip()
    for pat in SUB_PROBLEM_PATTERNS:
        m = pat.match(s)
        if m:
            return (m.group(1), m.group(2))
    return None


# ─────────────────────────────────────────────
# 数学公式提取
# ─────────────────────────────────────────────

def extract_math_expressions(text: str) -> list:
    expressions = []
    for m in re.finditer(r"\$\$(.+?)\$\$", text, re.DOTALL):
        expressions.append({"type": "display", "latex": m.group(1).strip()})
    for m in re.finditer(r"\\\[(.+?)\\\]", text, re.DOTALL):
        expressions.append({"type": "display", "latex": m.group(1).strip()})
    for m in re.finditer(r"(?<!\$)\$(?!\$)(.+?)(?<!\$)\$(?!\$)", text):
        expressions.append({"type": "inline", "latex": m.group(1).strip()})
    # 矩阵环境即使不在 $ 里也抓出来
    for m in re.finditer(r"\\begin\{(?:p|b|B|v|V|array)matrix\}.*?\\end\{(?:p|b|B|v|V|array)matrix\}",
                         text, re.DOTALL):
        expressions.append({"type": "matrix", "latex": m.group(0)})
    return expressions


# ─────────────────────────────────────────────
# 题型分类（增强）
# ─────────────────────────────────────────────

TYPE_KEYWORDS = {
    "epsilon_delta": ["within", "epsilon", "delta", "ε", "δ", "varepsilon", "邻域"],
    "tangent": ["tangent", "切线", "horizontal tangent", "水平切线"],
    "matrix": ["矩阵", "matrix", "行列式", "determinant", "特征值", "eigenvalue",
               "逆矩阵", "inverse", "秩", "rank", "线性方程组", "linear system",
               "特征向量", "eigenvector", "对角化", "diagonaliz"],
    "ode": ["微分方程", "differential equation", "ode", "dy/dx", "y''", "y'''",
            "二阶常微分", "初值问题", "initial value", "d^2y", "frac{d^2"],
    "physics": ["牛顿", "newton", "f=ma", "速度", "velocity", "加速度", "acceleration",
                "动能", "kinetic energy", "势能", "potential energy", "做功", "work",
                "碰撞", "collision", "抛体", "projectile", "重力", "gravity", "force",
                "力", "质量", "mass"],
    "integral": ["定积分", "不定积分", "积分", "integrate", "integral", "∫",
                 "improper integral", "换元", "integration by"],
    "limit": ["limit", "lim", "极限", "squeeze", "夹逼"],
    "derivative": ["求导", "导数", "derivative", "differentiate", "d/dx", "微分"],
    "equation": ["解方程", "solve", "求解", "方程", "equation", "system of equations"],
    "proof": ["证明", "prove", "show that", "verify", "证", "demonstrate"],
    "graph": ["画图", "plot", "graph", "sketch", "draw", "图像", "绘制"],
    "conceptual": ["explain", "describe", "what does", "what do we mean",
                   "is it true", "解释", "说明", "为什么"],
    "calculation": ["计算", "求", "compute", "calculate", "evaluate", "find",
                    "化简", "simplify"],
}

# 优先级（越靠前越具体）
PRIORITY = ["epsilon_delta", "tangent", "matrix", "ode", "physics",
            "integral", "derivative", "limit", "equation",
            "proof", "graph", "conceptual", "calculation"]


def classify_problem(text: str, sub_texts: list = None) -> str:
    combined = text + " " + " ".join(sub_texts or [])
    text_lower = combined.lower()
    scores = {}
    for ptype, kws in TYPE_KEYWORDS.items():
        score = sum(1 for kw in kws if kw.lower() in text_lower)
        if score > 0:
            scores[ptype] = score
    if not scores:
        return "calculation"
    max_score = max(scores.values())
    candidates = [t for t, s in scores.items() if s >= max_score - 1]
    for p in PRIORITY:
        if p in candidates:
            return p
    return max(scores, key=scores.get)


# ─────────────────────────────────────────────
# 主解析
# ─────────────────────────────────────────────

def make_problem(pid: str, text: str, math_exprs: list, ptype: str, subs: list = None) -> dict:
    return {
        "id": pid,
        "text": text.strip(),
        "math_expressions": math_exprs,
        "type": ptype,
        "sub_problems": subs or [],
    }


def parse_problems(ingested: dict) -> list:
    raw_text = ingested.get("raw_text", "")
    lines = raw_text.split("\n")

    problems: list[dict] = []
    section = ""
    cur_id: Optional[str] = None
    cur_lines: list[str] = []
    cur_subs: list[dict] = []
    cur_sub_id: Optional[str] = None
    cur_sub_lines: list[str] = []

    def flush_sub():
        nonlocal cur_sub_id, cur_sub_lines
        if cur_sub_id and cur_sub_lines:
            t = "\n".join(cur_sub_lines).strip()
            cur_subs.append({
                "id": cur_sub_id,
                "text": t,
                "math_expressions": extract_math_expressions(t),
            })
        cur_sub_id = None
        cur_sub_lines = []

    def flush_problem():
        nonlocal cur_id, cur_lines, cur_subs
        flush_sub()
        if cur_id and cur_lines:
            full = "\n".join(cur_lines).strip()
            pid = f"{section}{cur_id}" if section else cur_id
            problems.append(make_problem(
                pid=pid,
                text=full,
                math_exprs=extract_math_expressions(full),
                ptype=classify_problem(full, [s["text"] for s in cur_subs]),
                subs=cur_subs,
            ))
        cur_id = None
        cur_lines = []
        cur_subs = []

    for line in lines:
        sec = detect_section(line)
        if sec is not None:
            flush_problem()
            section = sec
            continue

        heading = re.match(r"^#{1,4}\s+(.*)", line)
        if heading:
            prob = detect_problem_start(heading.group(1))
            if prob:
                flush_problem()
                cur_id = prob[0]
                if prob[1]:
                    cur_lines.append(prob[1])
            continue

        prob = detect_problem_start(line)
        if prob:
            flush_problem()
            cur_id = prob[0]
            if prob[1]:
                cur_lines.append(prob[1])
            continue

        sub = detect_sub_problem(line)
        if sub and cur_id:
            flush_sub()
            cur_sub_id = sub[0]
            cur_sub_lines.append([sub[1]] if sub[1] else [])
            # sub[1] may be empty; next lines will follow
            cur_sub_lines = [sub[1]] if sub[1] else []
            continue

        if cur_sub_id is not None:
            cur_sub_lines.append(line)
        elif cur_id is not None:
            cur_lines.append(line)

    flush_problem()
    return problems


# ─────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────

def main():
    if len(sys.argv) < 3:
        print("用法: python parse_problems.py <输入.json> <输出.json>")
        sys.exit(1)
    inp, outp = sys.argv[1], sys.argv[2]
    with open(inp, "r", encoding="utf-8") as f:
        data = json.load(f)
    print(f"[Stage 2] 题目解析: {inp}")
    problems = parse_problems(data)
    Path(outp).parent.mkdir(parents=True, exist_ok=True)
    with open(outp, "w", encoding="utf-8") as f:
        json.dump(problems, f, ensure_ascii=False, indent=2)
    print(f"  识别题目: {len(problems)} 道")
    for p in problems:
        subs = f" ({len(p['sub_problems'])} 子题)" if p["sub_problems"] else ""
        print(f"    {p['id']}: [{p['type']}]{subs} {p['text'][:60]}...")


if __name__ == "__main__":
    main()
