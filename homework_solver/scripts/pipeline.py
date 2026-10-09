#!/usr/bin/env python3
"""
一键流水线: 作业文件 → 解析 → 求解 → LaTeX → PDF
=================================================
用法:
    python pipeline.py <input> <output_dir> [--compile] [--course ".."] [--student ".."] [--title ".."]

示例:
    python pipeline.py homework.md out/ --compile --course "线性代数" --student "张三"
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))

from ingest import ingest                       # noqa: E402
from parse_problems import parse_problems       # noqa: E402
from solve import solve_all                     # noqa: E402
from render_latex import render_document, compile_pdf  # noqa: E402


def run_pipeline(input_path: str, output_dir: str,
                course: str = "Mathematics", student: str = "Student",
                title: str = "Homework Solutions", do_compile: bool = False) -> dict:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    print("=" * 60)
    print("🚀 国产模型作业自动求解流水线")
    print(f"   输入: {input_path}")
    print(f"   输出: {output_dir}")
    print("=" * 60)

    # Stage 1
    print("\n📄 Stage 1: 文档摄入")
    ingested = ingest(input_path)
    (output_dir / "1_ingested.json").write_text(
        json.dumps(ingested, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"   ✅ 格式 {ingested['format']}, {len(ingested['sections'])} 段")

    # Stage 2
    print("\n🔍 Stage 2: 题目解析")
    problems = parse_problems(ingested)
    (output_dir / "2_parsed.json").write_text(
        json.dumps(problems, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"   ✅ 识别 {len(problems)} 题")
    for p in problems:
        print(f"      {p['id']}: [{p['type']}] {p['text'][:50]}")

    # Stage 3
    print("\n🧮 Stage 3: 自动求解")
    solutions = solve_all(problems)
    (output_dir / "3_solutions.json").write_text(
        json.dumps(solutions, ensure_ascii=False, indent=2), encoding="utf-8")
    solved = sum(1 for s in solutions if s["solved"])
    print(f"   ✅ 求解 {solved}/{len(solutions)}")
    for s in solutions:
        flag = "✅" if s["solved"] else "❌"
        info = (s.get("answer_latex") or s.get("reason", ""))[:55]
        print(f"      {flag} {s['problem_id']}: {info}")

    # Stage 4
    print("\n📝 Stage 4: LaTeX 生成")
    tex = render_document(solutions, course=course, student=student, title=title)
    tex_path = output_dir / "homework.tex"
    tex_path.write_text(tex, encoding="utf-8")
    print(f"   ✅ {tex_path}")

    # Stage 5
    if do_compile:
        print("\n📑 Stage 5: PDF 编译")
        ok = compile_pdf(str(tex_path), str(output_dir))
        if ok:
            print(f"   ✅ PDF: {output_dir / 'homework.pdf'}")
        else:
            print("   ❌ PDF 编译失败（tex 仍可手动到 Overleaf 编译）")

    elapsed = time.time() - t0
    print("\n" + "=" * 60)
    print(f"📊 完成: {solved}/{len(problems)} solved, 耗时 {elapsed:.1f}s")
    print("=" * 60)
    return {"total": len(problems), "solved": solved, "elapsed": elapsed}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("input")
    ap.add_argument("output_dir")
    ap.add_argument("--compile", action="store_true")
    ap.add_argument("--course", default="Mathematics")
    ap.add_argument("--student", default="Student")
    ap.add_argument("--title", default="Homework Solutions")
    args = ap.parse_args()
    run_pipeline(args.input, args.output_dir,
                 course=args.course, student=args.student,
                 title=args.title, do_compile=args.compile)


if __name__ == "__main__":
    main()
