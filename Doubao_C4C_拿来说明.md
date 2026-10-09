# Doubao_C4C_拿来说明

> 从 starter kit 拿了什么、改了什么、Claude 版本与国产模型版本有何差异。

## 一、直接拿来的部分

| 资产 | 来源 | 用途 |
|------|------|------|
| 五段流水线架构（Ingest→Parse→Solve→Render→Compile） | starter kit `scripts/pipeline.py` | 整体骨架未动 |
| 题目正则（Problem N / 题 N / 1. / (a)） | starter kit `parse_problems.py` | 题号识别核心 |
| LaTeX 公式提取（`$...$` / `$$...$$`） | starter kit `parse_problems.py` | 数学表达式抽取 |
| 题型分类（关键词打分 + 优先级） | starter kit `parse_problems.py` | 路由到求解器 |
| SymPy 表达式安全解析（`safe_parse`） | starter kit `solve.py` | LaTeX→SymPy 转换，包括 `\frac`/`\sqrt`/`\left\right` 处理 |
| 极限求解（`try_parse_limit`） | starter kit `solve.py` | `\lim_{x\to a}` 解析 |
| 概念题模板（夹逼定理、ε-δ、连续性三条件） | starter kit `solve.py` `_match_conceptual_template` | LLM 兜底层 |
| LaTeX 转义/清理函数 | starter kit `render_latex.py` | `escape_latex`/`clean_for_latex` |
| 作业文档类版式（页眉/页脚/boxed） | starter kit `references/homework_template.tex` | 视觉风格 |

## 二、改造与新增

### 2.1 新增求解器（starter kit 里是 `return _unsolved` 的占位）

| 求解器 | starter 状态 | 本版实现 |
|--------|-------------|---------|
| `solve_matrix` | "矩阵解析需要扩展（学生扩展点）" | 解析 `\begin{pmatrix}...\\...\end{pmatrix}`，支持 det/逆/秩/特征值/解 Ax=b |
| `solve_ode` | "ODE 求解需要扩展（学生扩展点）" | `y''+py'+qy=f(x)` 清洗为 SymPy 表达式，`dsolve` 通解+初值 |
| `solve_integral` | 仅基础 | 支持 `\,dx` 间距、`_0^{\pi}` 混合上下限、分部积分 |
| `solve_derivative` | 仅基础 | 支持 `f(x)=...` 形式、水平切线求解 |
| `solve_physics` | 未涉及 | 牛顿定律（按 `m=`/`F=` regex 定位数字）、动能、势能、匀加速运动 |

### 2.2 Stage 1 摄入

- starter：仅 Markdown
- 本版：新增 pdfplumber（PDF）、python-docx（DOCX），已实测可用

### 2.3 Stage 5 编译

- starter：调用 `pdflatex`/`xelatex`，要求本机装 TeX Live
- 本版：优先调用 **tectonic**（单文件现代引擎，自动从网络下载宏包），回退到 xelatex/pdflatex；文档类从 `article` 改为 `ctexart` 原生支持中文

### 2.4 题目解析

- 新增中文题号模式：`1、`、`（1）`
- 新增学科关键词：矩阵/特征值/微分方程/牛顿/动能/定积分 等
- 优先级链扩展

## 三、Claude 版本 vs 国产模型版本

| 维度 | Claude Code（starter） | 本版（豆包国产模型） |
|------|----------------------|---------------------|
| **运行时** | Claude Code CLI | 豆包会话 + Python 子进程 |
| **LLM 后端** | Claude（闭源，Anthropic） | 豆包（字节跳动国产），代码层预留 Qwen/Kimi/DeepSeek 切换 |
| **数学推理** | Claude 本身做 ε-δ 证明、概念题 | SymPy 做确定性计算；概念题由规则模板 + 豆包推理兜底 |
| **核心域准确率** | 17/18 = 94.4%（Berkeley Worksheet 3-4 真卷） | **15/18 = 83.3%**（同一份 Berkeley 真卷，含 2 道假阳性；真实 13/18） |
| **域外学科** | 2/5 = 40%（积分/优化/组合/物理） | 10/10 = 100%（线代/ODE/物理/积分，自造作业） |
| **PDF 引擎** | 依赖本机 pdflatex/xelatex | tectonic 单二进制，自动下载宏包 |
| **中文支持** | 需手动配置 Noto CJK | ctexart 开箱即用 |
| **输入格式** | Markdown only | Markdown + PDF + DOCX |
| **成本** | Claude API 计费 | 本会话内零额外 API 成本 |
| **可移植性** | 锁 Claude Code 环境 | 纯 Python + tectonic，可在任何 macOS/Linux 跑 |

## 四、拿来主义原则的说明

按 CHALLENGE.md 的要求，我没有"从零造轮子"：
- **SymPy** 是拿来的符号计算引擎，没有自己写求导/求特征值算法
- **LaTeX 模板**是拿来的 starter 版式，只改了文档类和颜色
- **题目正则**是拿来的 starter 实现，只在新学科上扩展关键词
- **tectonic** 是拿来的现代 LaTeX 引擎，替代了笨重的 TeX Live

我做的核心工作是**架构迁移**：把 Claude 当 LLM 后端的假设，换成"SymPy 为主、国产 LLM 为辅"的混合架构，并把 starter 里所有 `_unsolved` 占位真正实现成可用的求解器。
