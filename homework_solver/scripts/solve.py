#!/usr/bin/env python3
"""
Stage 3: 自动求解器（国产模型增强版）
=====================================
引擎分工:
  - SymPy 引擎: 极限/导数/积分/方程/矩阵/ODE/化简（确定性计算）
  - LLM 推理增强层 (国产模型 Kimi/Moonshot): 概念题/证明题/物理文字题
    真实调用 Kimi API（见 llm_client.py），失败时降级到本地规则模板

新增求解器 (相比 starter kit):
  - solve_matrix: 行列式/逆/特征值/秩/解线性方程组
  - solve_ode:    一阶/二阶常系数 ODE、初值问题
  - solve_integral: 定积分/不定积分（增强版）
  - solve_physics: 运动学/牛顿定律/能量守恒
"""

from __future__ import annotations

import json
import os
import re
import sys
import traceback
from pathlib import Path

import sympy as sp
from sympy import (
    symbols, Symbol, Function, Abs, Piecewise, oo, pi, E, S,
    diff, integrate, limit, series, solve, dsolve, linsolve,
    Matrix, eye, zeros, det, Rational, Rational as R,
    sin, cos, tan, exp, log, ln, sqrt,
    simplify, expand, factor, latex, Eq,
)
from sympy.parsing.sympy_parser import (
    parse_expr, standard_transformations,
    implicit_multiplication_application, convert_xor,
)

# 标准变量
x, y, z, t, n, k = symbols("x y z t n k")
a, b, c = symbols("a b c")
f_sym = Function("f")
y_func = Function("y")

TRANSFORMS = standard_transformations + (
    implicit_multiplication_application, convert_xor,
)

# ── LLM 推理增强层（国产模型 Kimi 真实接入） ──
try:
    import llm_client as _llm
    LLM_AVAILABLE = _llm.is_available()
    LLM_MODEL = _llm.get_model()
except Exception:
    _llm = None
    LLM_AVAILABLE = False
    LLM_MODEL = "unavailable"

# 环境变量开关：LLM_OFF=1 可强制关闭模型调用（用于纯 SymPy 对照实验）
if os.environ.get("LLM_OFF") == "1":
    LLM_AVAILABLE = False


# ═══════════════════════════════════════════════════════
# 表达式安全解析
# ═══════════════════════════════════════════════════════

def _find_matching_brace(s: str, pos: int) -> int:
    if pos >= len(s) or s[pos] != "{":
        return -1
    depth = 1
    i = pos + 1
    while i < len(s) and depth > 0:
        if s[i] == "{":
            depth += 1
        elif s[i] == "}":
            depth -= 1
        i += 1
    return i - 1 if depth == 0 else -1


def safe_parse(expr_str: str):
    """把 LaTeX/数学字符串解析为 SymPy 对象。"""
    s = expr_str.strip()
    s = re.sub(r"\\begin\{.*?\}", "", s)
    s = re.sub(r"\\end\{.*?\}", "", s)

    # \frac{a}{b}
    while "\\frac{" in s:
        idx = s.index("\\frac{")
        ns = idx + 6
        ne = _find_matching_brace(s, ns - 1)
        if ne < 0:
            break
        if ne + 1 >= len(s) or s[ne + 1] != "{":
            break
        ds = ne + 2
        de = _find_matching_brace(s, ne + 1)
        if de < 0:
            break
        num = s[ns:ne]
        den = s[ds:de]
        s = s[:idx] + f"(({num})/({den}))" + s[de + 1:]

    s = re.sub(r"\\sqrt\[(\d+)\]\{([^}]+)\}", r"((\2)**(1/(\1)))", s)
    s = re.sub(r"\\sqrt\{([^}]+)\}", r"sqrt(\1)", s)
    s = re.sub(r"\\left[(\[{|]?", "(", s)
    s = re.sub(r"\\right[)\]}|]?", ")", s)
    s = s.replace("\\cdot", "*").replace("\\times", "*").replace("\\div", "/")
    s = s.replace("\\pi", "pi").replace("\\infty", "oo")

    for fn in ["sin", "cos", "tan", "ln", "log", "exp",
               "arcsin", "arccos", "arctan", "sinh", "cosh"]:
        s = s.replace(f"\\{fn}", fn)

    s = re.sub(r"\\[,;!]", " ", s)
    s = re.sub(r"\\(?:quad|qquad)", " ", s)
    s = re.sub(r"\\mathrm\{([^}]+)\}", r"\1", s)
    s = re.sub(r"\|([^|]+)\|", r"Abs(\1)", s)
    s = re.sub(r"\\[a-zA-Z]+", "", s)
    s = re.sub(r"\^\{([^}]+)\}", r"**(\1)", s)
    s = re.sub(r"\^(\w)", r"**\1", s)
    s = re.sub(r"_\{[^}]+\}", "", s)
    s = re.sub(r"_\w", "", s)
    s = s.replace("{", "(").replace("}", ")")
    s = re.sub(r"\s+", " ", s).strip()

    if not s:
        raise ValueError("空表达式")

    return parse_expr(s, local_dict={
        "x": x, "y": y, "z": z, "t": t, "n": n, "k": k,
        "a": a, "b": b, "c": c,
        "pi": pi, "e": E, "oo": oo, "inf": oo,
        "sin": sin, "cos": cos, "tan": tan,
        "exp": exp, "log": log, "ln": ln, "sqrt": sqrt,
        "Abs": Abs,
    }, transformations=TRANSFORMS)


# ═══════════════════════════════════════════════════════
# 矩阵解析
# ═══════════════════════════════════════════════════════

def parse_latex_matrix(latex_str: str) -> Matrix | None:
    """从 LaTeX \\begin{pmatrix}...\\end{pmatrix} 解析出 SymPy 矩阵。"""
    m = re.search(r"\\begin\{(?:p|b|B|v|V|array)matrix\}(.*?)\\end\{(?:p|b|B|v|V|array)matrix\}",
                  latex_str, re.DOTALL)
    if not m:
        return None
    body = m.group(1)
    # 按行分割
    rows = re.split(r"\\\\", body)
    mat = []
    for row in rows:
        row = row.strip().rstrip("\\")
        if not row:
            continue
        cells = [c.strip() for c in row.split("&")]
        parsed = []
        for c in cells:
            try:
                parsed.append(safe_parse(c))
            except Exception:
                # 单元格可能是符号
                parsed.append(S(c) if re.match(r"^[a-zA-Z]$", c) else S(0))
        if parsed:
            mat.append(parsed)
    if not mat:
        return None
    try:
        return Matrix(mat)
    except Exception:
        return None


# ═══════════════════════════════════════════════════════
# 极限 (保留 starter kit 能力)
# ═══════════════════════════════════════════════════════

def try_parse_limit(latex_str: str):
    m = re.search(r"\\lim_\{([a-z])\s*\\to\s*([^}]*)\}\s*(.+)", latex_str)
    if not m:
        m = re.search(r"\\lim_\{([a-z])\\to\s*([^}]*)\}\s*(.+)", latex_str)
    if not m:
        return None
    var_s, pt_s, expr_s = m.group(1), m.group(2).strip(), m.group(3).strip()
    direction = None
    if pt_s.endswith("^+") or pt_s.endswith("^{+}"):
        direction = "+"; pt_s = re.sub(r"\^\{?\+\}?$", "", pt_s).strip()
    elif pt_s.endswith("^-") or pt_s.endswith("^{-}"):
        direction = "-"; pt_s = re.sub(r"\^\{?-\}?$", "", pt_s).strip()
    var = Symbol(var_s)
    try:
        pt = safe_parse(pt_s)
    except Exception:
        if "infty" in pt_s:
            pt = oo
        else:
            return None
    try:
        expr = safe_parse(expr_s)
    except Exception:
        return None
    return (var, pt, direction, expr)


def _has_abstract_function(expr_str: str) -> bool:
    """判断表达式里是否含未给定具体形式的抽象函数调用（f(x)、g'(x)、f_1(x) 等）。

    注意：必须在 SymPy 解析**之前**对 latex 原文调用本函数。
    SymPy 会把 `f(x)` 当成 f*x 解析成 `f*x`，解析后再检测必然漏判。
    """
    if not expr_str:
        return False
    # 去掉 \left \right \, 等排版噪声，避免漏判与误判
    s = re.sub(r"\\(left|right|big|Big|,|;|!| )", "", expr_str)
    # f(x) / g(x) / h(x) / f_1(x) / g'(x) / \phi(x) 等函数调用形态
    if re.search(r"(?<![A-Za-z\\])([fgh])['_]?\s*\(", s):
        return True
    if re.search(r"\\(phi|varphi|psi)\s*['_]?\s*\(", s):
        return True
    # 形如 \lim ... f 单独出现的抽象函数名（无具体表达式）
    return bool(re.search(r"(?<![A-Za-z\\])(f|g|h)(?![A-Za-z0-9])", s))


def solve_limit(problem: dict) -> dict:
    math_exprs = problem.get("math_expressions", [])
    # 抽象函数 f(x)/g(x) 未给具体表达式时不能硬算，否则 SymPy 会把 f(x) 当成
    # f*x 做乘法，产出 a**2*f**2 这类假阳性。整题先扫一遍：只要含抽象函数，
    # 就整题转交 LLM/概念模板，而不是跳过单个表达式后继续硬算。
    # 必须在 SymPy 解析前用 latex 原文检测。
    for e in math_exprs:
        if _has_abstract_function(e.get("latex", "")):
            return solve_conceptual(problem)

    steps = []
    answers = []
    for e in math_exprs:
        parsed = try_parse_limit(e["latex"])
        if not parsed:
            continue
        var, pt, direction, expr = parsed
        try:
            if direction == "+":
                val = limit(expr, var, pt, "+")
            elif direction == "-":
                val = limit(expr, var, pt, "-")
            else:
                val = limit(expr, var, pt)
            steps.append(f"$\\lim_{{{var} \\to {latex(pt)}}} {latex(expr)} = {latex(val)}$")
            answers.append(val)
        except Exception as ex:
            steps.append(f"（无法直接计算：{escape_text(str(ex)[:80])}）")
    if answers:
        return _ok(problem, steps, answers[-1], solver="sympy_limit")
    # 无可直接计算的表达式：交给概念模板
    return solve_conceptual(problem)


# ═══════════════════════════════════════════════════════
# 积分 (增强)
# ═══════════════════════════════════════════════════════

def try_parse_integral(latex_str: str):
    # 支持 \int_a^b, \int_{a}^{b}, \int_a^{b}, \int_{a}^{b}\,dx 等各种写法
    m = re.search(
        r"\\int(?:_\{?([^\s{}^]+)\}?\^\{?([^\s{}]+)\}?)?\s*(.+?)(?:\\[,;!]|\s)*d([a-z])\s*$",
        latex_str,
    )
    if not m:
        return None
    lower_s, upper_s, integrand_s, var_s = m.group(1), m.group(2), m.group(3), m.group(4)
    var = Symbol(var_s)
    try:
        integrand = safe_parse(integrand_s)
    except Exception:
        return None
    bounds = None
    if lower_s is not None and upper_s is not None:
        try:
            bounds = (safe_parse(lower_s), safe_parse(upper_s))
        except Exception:
            pass
    return (integrand, var, bounds)


def solve_integral(problem: dict) -> dict:
    math_exprs = problem.get("math_expressions", [])
    for e in math_exprs:
        parsed = try_parse_integral(e["latex"])
        if parsed:
            integrand, var, bounds = parsed
            try:
                if bounds:
                    val = integrate(integrand, (var, bounds[0], bounds[1]))
                    steps = [
                        f"$\\int_{{{latex(bounds[0])}}}^{{{latex(bounds[1])}}} {latex(integrand)}\\,d{var}$",
                        f"$= {latex(val)}$",
                    ]
                    return _ok(problem, steps, val, solver="sympy_integral")
                else:
                    val = integrate(integrand, var)
                    steps = [
                        f"$\\int {latex(integrand)}\\,d{var}$",
                        f"$= {latex(val)} + C$",
                    ]
                    return _ok(problem, steps, f"{latex(val)} + C", solver="sympy_integral")
            except Exception as ex:
                return _fail(problem, f"积分计算失败: {ex}")
    # 退回到 "求...积分" 文本模式
    text = problem["text"].lower()
    if "积分" in text or "integral" in text:
        for e in math_exprs:
            try:
                expr = safe_parse(e["latex"])
                val = integrate(expr, x)
                return _ok(problem, [f"$\\int {latex(expr)}\\,dx = {latex(val)} + C$"],
                           f"{val} + C", solver="sympy_integral")
            except Exception:
                continue
    return _fail(problem, "无法解析积分表达式")


# ═══════════════════════════════════════════════════════
# 导数
# ═══════════════════════════════════════════════════════

def solve_derivative(problem: dict) -> dict:
    math_exprs = problem.get("math_expressions", [])
    for e in math_exprs:
        latex_s = e["latex"]
        # 处理 f(x) = expr 或 y = expr: 取右边
        target = latex_s
        m = re.match(r"[fy]\s*\(\s*x\s*\)\s*=\s*(.+)", latex_s)
        if m:
            target = m.group(1)
        else:
            m = re.match(r"y\s*=\s*(.+)", latex_s)
            if m:
                target = m.group(1)
        try:
            expr = safe_parse(target)
            val = diff(expr, x)
            steps = [f"$f(x) = {latex(expr)}$",
                     f"$f'(x) = {latex(val)}$"]
            # 水平切线: f'(x)=0
            if "水平" in problem["text"] or "horizontal" in problem["text"].lower():
                crit = solve(val, x)
                steps.append(f"令 $f'(x)=0$: $x = {latex(crit)}$")
            return _ok(problem, steps, val, solver="sympy_derivative")
        except Exception:
            continue
    # 没有可求导的表达式：可能是概念题
    return solve_conceptual(problem)


# ═══════════════════════════════════════════════════════
# 方程
# ═══════════════════════════════════════════════════════

def solve_equation(problem: dict) -> dict:
    math_exprs = problem.get("math_expressions", [])
    for e in math_exprs:
        s = e["latex"]
        if "=" in s:
            try:
                lhs, rhs = s.split("=", 1)
                eq = Eq(safe_parse(lhs), safe_parse(rhs))
                ans = solve(eq, x)
                return _ok(problem,
                           [f"${latex(eq)}$", f"解得 $x = {latex(ans)}$"],
                           ans, solver="sympy_equation")
            except Exception:
                continue
    return _fail(problem, "无法解析方程")


# ═══════════════════════════════════════════════════════
# 矩阵求解器 (核心扩展)
# ═══════════════════════════════════════════════════════

def solve_matrix(problem: dict) -> dict:
    """
    支持题目形式:
      - 求矩阵 A 的行列式 / 逆 / 秩 / 特征值
      - 解线性方程组 Ax = b
    """
    text = problem["text"]
    text_lower = text.lower()
    math_exprs = problem.get("math_expressions", [])

    # 抓矩阵
    A = None
    for e in math_exprs:
        A = parse_latex_matrix(e["latex"])
        if A is not None:
            break

    if A is None:
        return _fail(problem, "未在题目中识别到 LaTeX 矩阵")

    steps = [f"给定矩阵 $A = {latex(A)}$"]

    try:
        # 行列式
        if "行列式" in text or "determinant" in text_lower or "det" in text_lower:
            d = A.det()
            steps.append(f"$\\det(A) = {latex(d)}$")
            return _ok(problem, steps, d, solver="sympy_matrix_det")

        # 逆矩阵 (文本 "逆"/"inverse" 或 LaTeX ^{-1})
        is_inv = ("逆" in text or "inverse" in text_lower
                  or re.search(r"\^\{-?1\}", text) or "^{-1}" in text)
        if is_inv:
            try:
                inv = A.inv()
                steps.append(f"$A^{{-1}} = {latex(inv)}$")
                # 验证: A * A^{-1} = I
                check = A * inv
                steps.append(f"验证: $A A^{{-1}} = {latex(check)}$")
                return _ok(problem, steps, inv, solver="sympy_matrix_inv")
            except Exception:
                return _fail(problem, "矩阵不可逆（det = 0）")

        # 秩
        if "秩" in text or "rank" in text_lower:
            r = A.rank()
            steps.append(f"$\\operatorname{{rank}}(A) = {latex(r)}$")
            return _ok(problem, steps, r, solver="sympy_matrix_rank")

        # 特征值 / 特征向量
        if "特征值" in text or "eigenvalue" in text_lower or "特征向量" in text:
            eigenvalues = A.eigenvals()
            eigenvectors = A.eigenvects()
            ev_str = ", ".join(f"{latex(k)} (重数 {v})" for k, v in eigenvalues.items())
            steps.append(f"特征值: ${ev_str}$")
            vec_lines = []
            for val, mult, vecs in eigenvectors:
                for v in vecs:
                    vec_lines.append(f"$\\lambda = {latex(val)}$, 特征向量 $= {latex(v.T)}$")
            steps.extend(vec_lines)
            return _ok(problem, steps, eigenvalues, solver="sympy_matrix_eig")

        # 解线性方程组 Ax = b
        if ("方程组" in text or "system" in text_lower or "求解" in text
                or "solve" in text_lower):
            # 尝试找向量 b
            b = None
            for e in math_exprs:
                b = parse_latex_matrix(e["latex"])
                if b is not None and b is not A:
                    # 列向量 or 行向量
                    if b.shape[0] == A.shape[0] and b.shape[1] == 1:
                        break
                    if b.shape[1] == A.shape[0] and b.shape[0] == 1:
                        b = b.T
                        break
            if b is not None:
                try:
                    sol = A.solve(b)
                    steps.append(f"$A x = {latex(b.T)}^{{T}}$")
                    steps.append(f"解得 $x = {latex(sol.T)}^{{T}}$")
                    return _ok(problem, steps, sol, solver="sympy_linsolve")
                except Exception as ex:
                    return _fail(problem, f"解方程组失败: {ex}")

        # 默认: 给出完整信息
        d = A.det()
        r = A.rank()
        steps.append(f"$\\det(A) = {latex(d)}$, $\\operatorname{{rank}}(A) = {latex(r)}$")
        if d != 0:
            inv = A.inv()
            steps.append(f"$A^{{-1}} = {latex(inv)}$")
        return _ok(problem, steps, f"det={d}, rank={r}", solver="sympy_matrix_info")

    except Exception as ex:
        return _fail(problem, f"矩阵求解异常: {ex}\n{traceback.format_exc()[:200]}")


# ═══════════════════════════════════════════════════════
# ODE 求解器 (核心扩展)
# ═══════════════════════════════════════════════════════

def solve_ode(problem: dict) -> dict:
    """
    支持:
      - y'' + p y' + q y = 0  (齐次二阶)
      - y'' + p y' + q y = f(x)  (非齐次)
      - 一阶 y' + p y = q
      - 初值条件 y(0)=a, y'(0)=b
    """
    text = problem["text"]
    text_lower = text.lower()
    math_exprs = problem.get("math_expressions", [])

    # 拼接所有数学表达式文本，找 ODE 方程
    ode_latex = ""
    for e in math_exprs:
        if "y''" in e["latex"] or "y'" in e["latex"] or "frac{d" in e["latex"]:
            ode_latex = e["latex"]
            break
    if not ode_latex:
        # 退化: 用整段文本
        ode_latex = " ".join(e["latex"] for e in math_exprs)

    # 简化: 把 y'' -> y_func(x).diff(x,2), y' -> y_func(x).diff(x), y -> y_func(x)
    # 但我们直接用 sympy 的 dsolve，需要构造 Eq
    try:
        # 清洗 LaTeX
        s = ode_latex
        # 先处理 e^{...} -> exp(...)
        s = re.sub(r"e\^\{([^}]+)\}", r"exp(\1)", s)
        s = s.replace("\\frac{d^2 y}{dx^2}", " DDBANG ")
        s = s.replace("\\frac{dy}{dx}", " DBANG ")
        # 注意: 先替换 y'' (ddy) 再替换 y' (dy)，避免 ddy 里的 dy 被误替换
        s = re.sub(r"y''\s*=", "DDBANG =", s)
        s = s.replace("y''", "DDBANG")
        s = re.sub(r"y'\s*=", "DBANG =", s)
        s = s.replace("y'", "DBANG")
        s = s.replace("\\cdot", "*")
        # 把数字*y 转成数字*y_func(x)
        s = re.sub(r"(\d+(?:\.\d+)?)\s*y\b", r"\1*YYBANG", s)
        s = re.sub(r"(\d+)\s*DBANG\b", r"\1*DBANG", s)
        s = re.sub(r"(\d+)\s*DDBANG\b", r"\1*DDBANG", s)
        s = s.replace(" y ", " YYBANG ").replace("+y ", "+YYBANG ").replace("-y ", "-YYBANG ")
        s = s.replace("YYBANG", "y_func(x)")
        s = s.replace("DDBANG", "y_func(x).diff(x, 2)")
        s = s.replace("DBANG", "y_func(x).diff(x)")
        # 去掉 \sin \cos 等
        for fn in ["sin", "cos", "tan", "exp", "log"]:
            s = s.replace(f"\\{fn}", fn)
        s = re.sub(r"\\[a-zA-Z]+", "", s)
        # 残余的 ^ 形式
        s = re.sub(r"\^\{([^}]+)\}", r"**(\1)", s)
        s = re.sub(r"\^(\w)", r"**\1", s)

        if "=" in s:
            lhs, rhs = s.split("=", 1)
            eq = Eq(sp.sympify(lhs.strip(), locals={
                "y_func": y_func, "x": x,
                "sin": sin, "cos": cos, "tan": tan, "exp": exp, "log": log,
                "pi": pi,
            }), sp.sympify(rhs.strip(), locals={
                "y_func": y_func, "x": x,
                "sin": sin, "cos": cos, "tan": tan, "exp": exp, "log": log,
                "pi": pi,
            }))
        else:
            return _fail(problem, "ODE 方程缺少等号")

        # 初值条件
        ics = {}
        m = re.search(r"y\s*\(\s*0\s*\)\s*=\s*(-?[\d.]+)", text)
        if m:
            ics[y_func(0)] = float(m.group(1))
        m = re.search(r"y'\s*\(\s*0\s*\)\s*=\s*(-?[\d.]+)", text)
        if m:
            ics[y_func(x).diff(x).subs(x, 0)] = float(m.group(1))

        try:
            sol = dsolve(eq, y_func(x), ics=ics if ics else None)
        except Exception:
            sol = dsolve(eq, y_func(x))

        steps = [f"原方程: ${latex(eq)}$"]
        if ics:
            steps.append(f"初值条件: {', '.join(f'${latex(k)}={v}$' for k, v in ics.items())}")
        steps.append(f"通解/特解: ${latex(sol)}$")
        return _ok(problem, steps, sol, solver="sympy_ode")

    except Exception as ex:
        return _fail(problem, f"ODE 求解失败: {ex}\n{s[:200] if 's' in dir() else ''}")


# ═══════════════════════════════════════════════════════
# 大学物理求解器 (核心扩展)
# ═══════════════════════════════════════════════════════

def _extract_numbers(text: str) -> list[float]:
    return [float(x) for x in re.findall(r"-?\d+(?:\.\d+)?", text)]


def solve_physics(problem: dict) -> dict:
    """
    力学基础题:
      - F = m a
      - 运动学: v = v0 + a t, s = v0 t + 1/2 a t^2
      - 动能 K = 1/2 m v^2, 势能 U = m g h
      - 能量守恒
    """
    text = problem["text"]
    text_lower = text.lower()
    nums = _extract_numbers(text)
    steps: list[str] = []
    answer = None

    try:
        # 牛顿第二定律: 已知 m, a 求 F; 或已知 m, F 求 a
        if ("力" in text or "force" in text_lower or "f=ma" in text_lower
                or "牛顿" in text or "newton" in text_lower or "加速度" in text):
            # 按 "m = 数字" 和 "F = 数字" 定位
            m_match = re.search(r"m\s*=\s*(-?[\d.]+)", text)
            f_match = re.search(r"F\s*=\s*(-?[\d.]+)", text)
            a_in_text = "加速度" in text or "acceler" in text_lower
            if m_match and f_match and a_in_text:
                m_val = float(m_match.group(1))
                f_val = float(f_match.group(1))
                a_val = f_val / m_val
                steps = [f"由牛顿第二定律 $F = m a$",
                         f"$a = F/m = {f_val}/{m_val} = {a_val:.4g}\\,\\mathrm{{m/s^2}}$"]
                answer = f"{a_val:.4g} m/s^2"
            elif m_match and f_match:
                m_val = float(m_match.group(1))
                f_val = float(f_match.group(1))
                steps = [f"已知 $m = {m_val}\\,\\mathrm{{kg}}$, $F = {f_val}\\,\\mathrm{{N}}$",
                         f"$a = F/m = {f_val/m_val:.4g}\\,\\mathrm{{m/s^2}}$"]
                answer = f"{f_val/m_val:.4g} m/s^2"
            elif len(nums) >= 2:
                m, a = nums[0], nums[1]
                F = m * a
                steps = [f"由 $F = m a$",
                         f"$F = {m} \\times {a} = {F:.4g}\\,\\mathrm{{N}}$"]
                answer = f"{F:.4g} N"

        # 运动学: 匀加速
        if not answer and ("速度" in text or "velocity" in text_lower
                           or "位移" in text or "acceler" in text_lower):
            if len(nums) >= 3:
                v0, a_t, t_val = nums[0], nums[1], nums[2]
                v = v0 + a_t * t_val
                s = v0 * t_val + 0.5 * a_t * t_val ** 2
                steps = [
                    f"匀加速运动: $v = v_0 + a t = {v0} + {a_t}\\times {t_val} = {v:.4g}\\,\\mathrm{{m/s}}$",
                    f"位移: $s = v_0 t + \\frac{{1}}{{2}} a t^2 = {s:.4g}\\,\\mathrm{{m}}$",
                ]
                answer = f"v={v:.4g} m/s, s={s:.4g} m"

        # 动能 / 势能
        if not answer and ("动能" in text or "kinetic" in text_lower):
            if len(nums) >= 2:
                m, v = nums[0], nums[1]
                K = 0.5 * m * v ** 2
                steps = [f"$K = \\frac{{1}}{{2}} m v^2 = \\frac{{1}}{{2}}\\times {m}\\times {v}^2 = {K:.4g}\\,\\mathrm{{J}}$"]
                answer = f"{K:.4g} J"

        if not answer and ("势能" in text or "potential" in text_lower or "重力" in text):
            if len(nums) >= 2:
                m, h = nums[0], nums[1]
                g = 9.8
                U = m * g * h
                steps = [f"重力势能 $U = m g h = {m}\\times {g}\\times {h} = {U:.4g}\\,\\mathrm{{J}}$"]
                answer = f"{U:.4g} J"

        if answer is None:
            return _fail(problem, "物理题: 无法识别具体公式，请补充已知量")

        return _ok(problem, steps, answer, solver="physics_formula")

    except Exception as ex:
        return _fail(problem, f"物理求解失败: {ex}")


# ═══════════════════════════════════════════════════════
# 通用计算 (化简 / 展开 / 求极限 fallback)
# ═══════════════════════════════════════════════════════

def solve_calculation(problem: dict) -> dict:
    math_exprs = problem.get("math_expressions", [])
    text = problem["text"].lower()

    # 先看是不是积分/极限伪装成 calculation
    for e in math_exprs:
        parsed_int = try_parse_integral(e["latex"])
        if parsed_int:
            integrand, var, bounds = parsed_int
            try:
                if bounds:
                    val = integrate(integrand, (var, bounds[0], bounds[1]))
                    return _ok(problem,
                               [f"$\\int_{{{latex(bounds[0])}}}^{{{latex(bounds[1])}}} {latex(integrand)}\\,d{var} = {latex(val)}$"],
                               val, solver="sympy_integral")
                else:
                    val = integrate(integrand, var)
                    return _ok(problem,
                               [f"$\\int {latex(integrand)}\\,d{var} = {latex(val)} + C$"],
                               f"{val} + C", solver="sympy_integral")
            except Exception:
                pass
        parsed_lim = try_parse_limit(e["latex"])
        if parsed_lim:
            var, pt, direction, ex2 = parsed_lim
            try:
                val = limit(ex2, var, pt) if not direction else limit(ex2, var, pt, direction)
                return _ok(problem, [f"$= {latex(val)}$"], val)
            except Exception:
                pass

    for e in math_exprs:
        try:
            expr = safe_parse(e["latex"])
            if "化简" in text or "simplify" in text:
                val = simplify(expr)
                return _ok(problem, [f"${latex(expr)} = {latex(val)}$"], val)
            if "展开" in text or "expand" in text:
                val = expand(expr)
                return _ok(problem, [f"${latex(expr)} = {latex(val)}$"], val)
            val = simplify(expr)
            return _ok(problem, [f"${latex(expr)} = {latex(val)}$"], val)
        except Exception:
            continue
    return _fail(problem, "无法解析数学表达式")


# ═══════════════════════════════════════════════════════
# LLM 推理增强层 (国产模型)
# ═══════════════════════════════════════════════════════

# 这里保留了 starter kit 的概念题模板作为"国产模型本地推理"基线。
# 真实部署时可以把这些模板替换为对 Qwen / Kimi / DeepSeek API 的调用。
# 见 llm_solver.py 的接口预留。

CONCEPT_TEMPLATES = [
    (lambda t: "squeeze" in t or "夹逼" in t,
     ["**夹逼定理 (Squeeze Theorem):** 若 $g(x) \\le f(x) \\le h(x)$ 在 $a$ 附近成立，"
      "且 $\\lim_{x\\to a} g(x) = \\lim_{x\\to a} h(x) = L$，则 $\\lim_{x\\to a} f(x) = L$。",
      "几何直观：$f$ 被上下两个函数\"夹住\"，两者都收敛到 $L$，$f$ 也必收敛到 $L$。"],
     "L（由夹逼定理）"),
    (lambda t: ("infinity" in t or "∞" in t or "infty" in t) and "number" in t,
     ["$\\infty$ **不是实数**。",
      "$\\lim_{x\\to a} f(x) = \\infty$ 表示 $f(x)$ 在 $x\\to a$ 时无界增长（发散），"
      "这个极限**在通常意义下不存在**。"],
     "$\\infty$ 不是数；该极限为发散"),
    (lambda t: ("one-sided" in t or "left" in t or "right" in t or
                ("a^-" in t and "a^+" in t) or ("a^{-}" in t and "a^{+}" in t) or
                "mean by" in t and "lim" in t),
     ["**左极限** $\\lim_{x\\to a^-} f(x) = L$：$x$ 从小于 $a$ 的方向趋近 $a$ 时 $f(x)\\to L$。",
      "**右极限** $\\lim_{x\\to a^+} f(x) = L$：$x$ 从大于 $a$ 的方向趋近 $a$ 时 $f(x)\\to L$。",
      "双侧极限 $\\lim_{x\\to a} f(x)$ 存在当且仅当左、右极限都存在且相等。",
      "反例：$f(x)=|x|/x$ 在 $a=0$ 处左极限 $=-1$，右极限 $=1$，不相等。"],
     "左/右极限定义；双侧存在 ⟺ 左=右"),
    (lambda t: ("连续" in t or "continu" in t) and
               ("定义" in t or "condition" in t or "三" in t or "mean" in t),
     ["$f$ 在 $a$ 连续当且仅当三条：(1) $f(a)$ 有定义；(2) $\\lim_{x\\to a}f(x)$ 存在；"
      "(3) $\\lim_{x\\to a}f(x)=f(a)$。"],
     "三条条件"),
    (lambda t: "more than one tangent" in t or "tangent at a given point" in t,
     ["对函数图像 $y=f(x)$，若 $f'(a)$ 存在，则切线唯一。",
      "一般曲线（非函数图像）在自交点处可以有多条切线。"],
     "函数图像在可导点处切线唯一"),
    (lambda t: ("doesn't have a tangent" in t or "without a tangent" in t or
                "not have a tangent" in t or "no tangent" in t or
                "doesn't have a" in t or "doesnt have" in t),
     ["存在。例如 $f(x)=|x|$ 在 $x=0$ 处有尖角，不可导，没有切线。",
      "其它例子：$x^{1/3}$ 在 $x=0$ 处有垂直切线。"],
     "存在，例如 $|x|$ 在 $x=0$"),
    (lambda t: "sum" in t and "limit" in t and ("always" in t or "is it" in t or "?" in t),
     ["**不总是**。极限的加法法则要求两个极限都存在。",
      "反例：$f(x)=1/x$，$g(x)=-1/x$。$\\lim_{x\\to 0}f$ 与 $\\lim_{x\\to 0}g$ 都不存在，"
      "但 $\\lim_{x\\to 0}[f+g]=\\lim_{x\\to 0}0=0$。"],
     "不总是；反例 $1/x + (-1/x)$"),
    (lambda t: "product" in t and "limit" in t and ("always" in t or "is it" in t or "?" in t),
     ["**不总是**。乘法法则要求两个极限都存在。",
      "反例：$f(x)=x$，$g(x)=1/x$。$\\lim_{x\\to 0}g$ 不存在，但 $\\lim_{x\\to 0}fg=\\lim_{x\\to 0}1=1$。"],
     "不总是；反例 $x \\cdot 1/x$"),
    (lambda t: "plugging in" in t or "just plug" in t or "substitut" in t or
              "what kinds of functions" in t or "kinds of functions" in t or
              ("evaluate the limit" in t and "just" in t),
     ["**连续函数**可以直接代入：多项式、有理函数（分母非零时）、三角、指数、对数函数。",
      "反例：$f(x)=(x^2-1)/(x-1)$ 在 $x=1$ 处直接代入得 $0/0$，"
      "但化简后 $\\lim_{x\\to 1}(x+1)=2$。"],
     "连续函数可直接代入；$0/0$ 型需化简"),
    (lambda t: "derivative definition" in t or ("definition" in t and "derivative" in t),
     ["$f'(a)=\\lim_{h\\to 0}\\frac{f(a+h)-f(a)}{h}$。",
      "识别：$\\lim_{x\\to a}\\frac{f(x)-f(a)}{x-a}=f'(a)$。"],
     "$f'(a)$ 定义"),
]


def solve_conceptual(problem: dict) -> dict:
    """概念题/证明题求解。

    优先级：Kimi 真实推理 > 本地规则模板 > 标记未解。
    """
    # 先尝试真实调用国产模型 Kimi
    if LLM_AVAILABLE and _llm is not None:
        try:
            r = _llm.call_llm(problem["text"], max_tokens=2000)
            if r.get("ok") and r.get("content"):
                content = r["content"]
                steps = _llm.extract_steps(content)
                ans = _llm.extract_answer(content) or "见解答"
                res = _ok(problem, steps, ans, solver=f"llm_kimi:{LLM_MODEL}")
                res["llm_meta"] = {
                    "model": LLM_MODEL,
                    "elapsed_s": r.get("elapsed"),
                    "usage": r.get("usage"),
                    "response_id": r.get("response_id"),
                }
                return res
        except Exception:
            pass  # 任何异常都安全降级到模板

    # 降级：本地规则模板
    text = problem["text"].lower()
    for matcher, steps, ans in CONCEPT_TEMPLATES:
        try:
            if matcher(text):
                res = _ok(problem, steps, ans, solver="template_fallback")
                res["llm_meta"] = {"model": "local_template",
                                   "fallback": True,
                                   "reason": "Kimi API 不可用或调用失败"}
                return res
        except Exception:
            continue
    return _fail(problem, "概念题需要 LLM 推理（Kimi API 不可用且无匹配模板）")


def escape_text(s: str) -> str:
    """把异常消息等纯文本安全化，避免泄漏 LaTeX 命令。"""
    return s.replace("\\", "\\textbackslash{}").replace("{", "\\{").replace("}", "\\}")


# ═══════════════════════════════════════════════════════
# 求解路由
# ═══════════════════════════════════════════════════════

SOLVERS = {
    "limit": solve_limit,
    "integral": solve_integral,
    "derivative": solve_derivative,
    "tangent": solve_derivative,   # 切线题先求导 (starter kit 的切线能力由 LLM 扩展)
    "equation": solve_equation,
    "matrix": solve_matrix,
    "ode": solve_ode,
    "physics": solve_physics,
    "conceptual": solve_conceptual,
    "calculation": solve_calculation,
}


def solve_problem(problem: dict) -> dict:
    ptype = problem.get("type", "calculation")
    solver = SOLVERS.get(ptype, solve_calculation)
    try:
        result = solver(problem)
    except Exception:
        result = _fail(problem, f"求解异常: {traceback.format_exc()[:300]}")

    # 子题兜底
    if not result.get("solved") and problem.get("sub_problems"):
        sub_sols = []
        for sub in problem["sub_problems"]:
            sub_prob = {
                "id": f"{problem['id']}.{sub['id']}",
                "text": sub["text"],
                "math_expressions": sub.get("math_expressions", []),
                "type": ptype,
                "sub_problems": [],
            }
            sub_res = solve_problem(sub_prob)
            sub_res["problem_id"] = sub_prob["id"]
            sub_sols.append(sub_res)
        result["sub_solutions"] = sub_sols
        if any(s.get("solved") for s in sub_sols):
            result["solved"] = True
            if not result.get("answer_latex"):
                result["answer"] = "见子题"
                result["answer_latex"] = "\\text{见子题}"
    return result


def solve_all(problems: list) -> list:
    return [solve_problem(p) for p in problems]


# ═══════════════════════════════════════════════════════
# 工具
# ═══════════════════════════════════════════════════════

def _ok(problem, steps, answer, solver="sympy"):
    if isinstance(answer, str):
        # 去掉所有 $，因为 render 已经在 \[...\] 数学模式里
        answer_latex = answer.replace("$", "")
    else:
        answer_latex = latex(answer)
    return {
        "problem_id": problem["id"],
        "problem_text": problem["text"],
        "solved": True,
        "steps": steps,
        "answer": str(answer),
        "answer_latex": answer_latex,
        "solver": solver,
        "sub_solutions": problem.get("sub_solutions", []),
    }


def _fail(problem, reason, sub_solutions=None):
    return {
        "problem_id": problem["id"],
        "problem_text": problem["text"],
        "solved": False,
        "steps": [],
        "answer": None,
        "answer_latex": "",
        "reason": reason,
        "solver": "none",
        "sub_solutions": sub_solutions or problem.get("sub_problems", []),
    }


# ═══════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════

def main():
    if len(sys.argv) < 3:
        print("用法: python solve.py <输入.json> <输出.json>")
        sys.exit(1)
    with open(sys.argv[1], "r", encoding="utf-8") as f:
        problems = json.load(f)
    print(f"[Stage 3] 自动求解: {len(problems)} 道")
    solutions = solve_all(problems)
    Path(sys.argv[2]).parent.mkdir(parents=True, exist_ok=True)
    with open(sys.argv[2], "w", encoding="utf-8") as f:
        json.dump(solutions, f, ensure_ascii=False, indent=2)
    solved = sum(1 for s in solutions if s["solved"])
    print(f"  已解: {solved}/{len(solutions)}")
    for s in solutions:
        flag = "✅" if s["solved"] else "❌"
        info = (s.get("answer_latex") or s.get("reason", ""))[:60]
        print(f"    {flag} {s['problem_id']}: {info}")


if __name__ == "__main__":
    main()
