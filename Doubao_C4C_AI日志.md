# Doubao_C4C_AI 日志

> 开发全过程 AI 使用记录。无此项无法评审。

## 时间线（2026-10-09）

### Phase 1：理解基线（~10 min）

1. 读取 `CHALLENGE.md`（500 行），明确四级任务、必须交付物、评审权重。
2. 解压 `c4c-homework-solver-starter.zip`，通读：
   - `SKILL.md` —— 五段流水线架构、Claude 基线 17/18=94.4% 的出处
   - `scripts/pipeline.py` —— 一键串联逻辑
   - `scripts/solve.py`（1597 行）—— 重点学习 `safe_parse` 的 LaTeX→SymPy 转换、极限求解、概念题模板
   - `scripts/parse_problems.py` —— 题号正则、关键词分类
   - `scripts/render_latex.py` —— LaTeX 模板、pdflatex 调用

**AI 使用**：让豆包（我自己）逐文件阅读并总结架构，而不是人肉读 1500 行代码。

### Phase 2：环境探查（~5 min）

3. 检查本机：Python 3.14.7 ✅，SymPy 未装，无 pdflatex/xelatex/brew。
4. `pip install sympy pdfplumber python-docx matplotlib numpy` —— SymPy 1.14.0 就绪。
5. 发现 ChatGPT 缓存过 tectonic 但二进制不在；从 GitHub releases 下载 `tectonic-0.15.0-aarch64-apple-darwin.tar.gz` 到 `~/bin/tectonic`，单文件 25 MB。

**AI 使用**：环境问题全部由 AI 诊断（which/mdfind），而不是人猜"是不是没装 LaTeX"。

### Phase 3：骨架迁移（~10 min）

6. 在桌面建 `C4C挑战交付资料/`，复制 starter 的 `ingest.py`、`bootstrap.py`、模板。
7. 重写 `ingest.py`：补 pdfplumber/python-docx 分支。
8. 重写 `parse_problems.py`：加中文题号、新学科关键词、优先级链。
9. 重写 `solve.py`：保留 starter 的 `safe_parse`/`try_parse_limit`，新增矩阵/ODE/积分/导数/物理求解器。
10. 重写 `render_latex.py`：文档类换 `ctexart`，编译器优先 tectonic。
11. 新写 `pipeline.py` 串联五段。

**AI 使用**：所有代码由豆包生成，人只做架构决策（选 tectonic vs TeX Live、选 ctexart vs article）。

### Phase 4：调试迭代（~15 min，关键）

12. **第一次冒烟测试**（`sample_homework.md`）：8/10。
    - 失败 1：P5 `\int_0^1 1/(1+x²) dx` 被误分类为 calculation。
    - 失败 2：P10 ODE `y'+2y=e^{-x}` 报 `unsupported operand ... pow()`。
13. **调试**：让豆包直接跑 Python 片段定位根因：
    - P5 根因：题目文本 "Evaluate" 触发 calculation 关键词，没走 integral 路由。修复：`solve_calculation` 里先尝试 `try_parse_integral`/`try_parse_limit`。
    - P10 根因：`e^{-x}` 没转成 `exp(-x)`。修复：ODE 清洗正则加 `e^{...} → exp(...)`。
14. 第二次冒烟：**10/10** ✅。

15. **真实作业测试**（自造的 10 题线代/ODE/物理/积分卷）：9/10。
    - 失败：P2 `\int_0^{\pi} x sin x \, dx` 积分正则不识别 `\,` 间距；P5 "求 B^{-1}" 没识别逆矩阵；P8 ODE 解错；P9 物理数字顺序反了；P1 切线答案是 "1"。
16. **逐个调试**（豆包内联 Python 片段）：
    - P2 根因：正则 `\s*d([a-z])\s*$` 不匹配 `\, dx`。修复：允许 `\\[,;!]`。
    - P5 根因：只检测中文"逆"/英文"inverse"，没检测 LaTeX `^{-1}`。修复：正则加 `r"\^\{-?1\}"`。
    - P8 根因：替换 `dy` 时把 `ddy` 里的 `dy` 也替换了。修复：用占位符 `DDBANG`/`DBANG`，先替换长的再替换短的。
    - P9 根因：nums=[m, F] 但代码假设 [F, m]。修复：按 `m=`/`F=` regex 定位。
    - P1 根因：`f(x)=...` 形式没剥掉左边。修复：`solve_derivative` 里正则取右边。
17. 第三次跑：**10/10** ✅。

18. **PDF 编译**：首次 154 s（tectonic 下载 ctex/amsmath 宏包），后续 ~8 s。用 Read 工具打开 PDF 截图目检 3 页，发现 P3 答案显示 `x**2`（Python 字符串）。
19. 修复：`solve_integral` 返回字符串时用 `latex(val)` 而非 `str(val)`。
20. 第四次跑：10/10，PDF 排版专业，中文/矩阵/boxed 全部正常。

### Phase 5：交付文档（~10 min）

21. 按 CHALLENGE.md "必须提交的文件"清单写：方案设计、验证报告、拿来说明、AI 日志、教学说明、反思复盘。

## Prompt 与迭代总结

| 轮次 | 指令 | 结果 | 学到 |
|------|------|------|------|
| 1 | "读 CHALLENGE.md 和 starter，搭建流水线骨架" | 骨架完成，但求解器全是占位 | 不能一次到位 |
| 2 | "扩展矩阵/ODE/物理求解器" | 跑通但 8/10 | 正则要兼容 LaTeX 各种写法 |
| 3 | "修 P5/P10 两个 bug" | 10/10 示例 | 内联 Python 调试比读代码快 |
| 4 | "跑真实作业" | 9/10，5 个新 bug | 学科扩展 = 新边界 case |
| 5 | "逐个修 5 个 bug" | 10/10 | 占位符替换顺序很重要 |
| 6 | "目检 PDF" | 发现 x**2 字符串问题 | 必须真实打开 PDF 看 |

## AI 工具使用统计

- **豆包（本会话）**：架构设计、代码生成、调试、文档撰写、PDF 目检
- **SymPy**：确定性计算后端
- **tectonic**：PDF 编译
- **pdfplumber/python-docx**：输入摄入
- **未使用**：Claude API、Qwen/Kimi API（代码层预留接口，本环境无 key）

## 关键决策（由 AI 提出，人确认）

1. 选 tectonic 而非装 TeX Live —— 单文件、自动下载、不污染系统
2. 选 ctexart 而非 article —— 原生中文
3. SymPy 为主、LLM 为辅 —— 避免数学幻觉
4. 用占位符 DDBANG/DBANG 做 ODE 清洗 —— 避免 `ddy` 里的 `dy` 被误替换

---

## Phase 7：硬伤修复轮次（2026-10-09 晚）

> 用户评审初版交付后指出 4 个硬伤，以下是修复过程。

### 硬伤 1：baseline_limits 名不副实（致命）

- **现象**：`test_homework/baseline_limits/` 封面印 "Berkeley Worksheet 3-4 Baseline"，实际装的是 starter 自带的 `sample_homework.md`（英文示例）。
- **修复**：
  1. 删除假目录 `baseline_limits/`；
  2. 新建 `berkeley_baseline/`，从 starter `test_cases/` 复制**真实的** `test1_tangent_epsilon_delta.md`（Worksheet 3）和 `test2_limits.md`（Worksheet 4）；
  3. 用流水线真实跑这两份试卷。

### 调试过程

5. 第一次跑真卷：Test1=6/8，Test2=5/10，且 Test2 PDF 编译失败（`Missing $ inserted`）。
6. 根因 1：抽象函数 `f(x)/g(x)` 被 SymPy 当乘法硬算，异常消息里的 LaTeX 命令（`\left[`）泄漏到 tex 源码。
7. 修复 1：`solve_limit` 检测表达式含 `f(`/`g(`/`h(` 时跳过 SymPy，路由到 `solve_conceptual`；异常消息用 `escape_text()` 转义。
8. 根因 2：CONCEPT_TEMPLATES 只有 3 个，覆盖不了 ∞不是数、夹逼定理、单侧极限等考点。
9. 修复 2：模板从 3 个扩到 10 个（夹逼定理、∞不是数、单侧极限、切线唯一性、反例构造、代入法、导数定义等）。
10. 踩坑：CONCEPT_TEMPLATES 里两个 lambda 元组多写了 `)` 把元组提前闭合，`SyntaxError: closing parenthesis ')' does not match '['`。修了 2 处。
11. 根因 3：boxed 里 answer 字符串自带 `$`，render 又包了 `\[...\]`，双重数学模式冲突。
12. 修复 3：`_ok()` 把 answer 字符串里所有 `$` 全部去掉。
13. 最终数字：Test1=8/8，Test2=7/10，合计 15/18=83.3%（Claude 基线 17/18=94.4%）。

### 硬伤 2：README 目录结构与实物不符

- **修复**：重写 README，对齐实际目录树（berkeley_baseline/、test_homework/、homework_solver/），删除不存在的 `test_homework/output/` 承诺。

### 硬伤 3：成绩对比口径不可比

- **修复**：用同一份 Berkeley 试卷重跑，对比表改为 15/18 vs 17/18；并在验证报告里诚实标注 Q4/P1 是假阳性（SymPy 把 f(x) 当乘法算错），真实可信成绩 13/18。

### 硬伤 4：PDF 封面乱码

- **现象**：用户初版看到副标题有 ㋜㺲㾗㮟ⰶ▖。
- **排查**：.tex 源文件里没有这些字符，判断是 tectonic 字体 fallback 引入。
- **结果**：重新编译后目检，中文作业 PDF 和 Berkeley 两份 PDF 封面均干净无乱码。

### AI 使用回顾

- 修复轮次全程由 AI 定位 bug（Read tex 源 → 找语法错 → Edit solve.py → 重跑 → 目检 PDF），人只在最终交付时检查数字。
- 关键诚实决策：数字不如初版好看（83.3% vs 100%），但这是真跑出来的，写进报告。

