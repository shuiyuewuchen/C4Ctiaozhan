# Doubao_C4C_教学说明

> 怎么安装、怎么用、支持哪些课程。

## 一、环境要求

- macOS / Linux（Windows 未测试，理论上 Python 部分跨平台）
- Python ≥ 3.10（开发用 3.14）
- 80 MB 磁盘（tectonic 首次运行自动下载宏包）

## 二、安装

```bash
# 1. 解压交付目录后进入 homework_solver/
cd homework_solver

# 2. 装 Python 依赖
pip install sympy pdfplumber python-docx matplotlib numpy

# 3. 装 tectonic（PDF 编译器，单文件）
#    macOS arm64:
curl -L -o ~/bin/tectonic.tar.gz \
  "https://github.com/tectonic-typesetting/tectonic/releases/download/tectonic%400.15.0/tectonic-0.15.0-aarch64-apple-darwin.tar.gz"
mkdir -p ~/bin && tar -xzf ~/bin/tectonic.tar.gz -C ~/bin
chmod +x ~/bin/tectonic

# 也可以用系统 LaTeX：
#   macOS: brew install --cask mactex-no-gui
#   Ubuntu: sudo apt install texlive-xetex
```

## 三、运行

### 3.1 一键跑通（推荐）

```bash
python3 scripts/pipeline.py <作业文件> <输出目录> \
    --compile \
    --course "课程名" \
    --student "你的名字" \
    --title "作业标题"
```

示例：

```bash
python3 scripts/pipeline.py ../Doubao_C4C_作业原件.md ./output \
    --compile \
    --course "工科数学物理综合" \
    --student "张三" \
    --title "期中作业解答"
```

输出目录里会得到：

```
output/
├── 1_ingested.json      # 摄入的原始文本
├── 2_parsed.json       # 解析后的题目结构
├── 3_solutions.json    # 求解结果（含步骤）
├── homework.tex         # LaTeX 源文件
└── homework.pdf        # 可直接提交的 PDF ⭐
```

### 3.2 分步运行（调试用）

```bash
# Stage 1: 摄入
python3 scripts/ingest.py 作业.md output/1_ingested.json

# Stage 2: 解析
python3 scripts/parse_problems.py output/1_ingested.json output/2_parsed.json

# Stage 3: 求解
python3 scripts/solve.py output/2_parsed.json output/3_solutions.json

# Stage 4: 生成 LaTeX
python3 scripts/render_latex.py output/3_solutions.json output/homework.tex

# Stage 5: 编译 PDF
python3 scripts/render_latex.py output/3_solutions.json output/homework.tex --compile
```

## 四、输入支持

| 格式 | 状态 | 说明 |
|------|------|------|
| `.md` / `.txt` | ✅ | 推荐。题目用 `1.`、`Problem 1`、`题 1`、`（1）` 开头 |
| `.pdf`（文本型） | ✅ | 用 pdfplumber 提取 |
| `.docx` | ✅ | 用 python-docx，含表格 |
| `.pdf`（扫描件） | ❌ | 需 Tesseract OCR 或 Vision API（未实现） |
| `.png/.jpg` | ❌ | 需 OCR（未实现） |

## 五、题目写法建议

为了让求解器正确识别，推荐这种格式：

```markdown
## Problems

1. 求函数 $f(x) = x^2 + 3x$ 的导数。

2. 计算定积分 $\int_0^1 x^2 \, dx$。

3. 已知矩阵 $A = \begin{pmatrix} 1 & 2 \\ 3 & 4 \end{pmatrix}$，求 $\det(A)$。

4. 求解微分方程 $y' + 2y = e^{-x}$，初始条件 $y(0) = 1$。

5. 质量 $m = 2\,\mathrm{kg}$ 的物体受 $F = 10\,\mathrm{N}$ 的力，求加速度。
```

关键约定：
- 题号独占一行开头（`1.` / `Problem 1:` / `题 1`）
- 数学公式用 `$...$` 包裹
- 矩阵用 `\begin{pmatrix} a & b \\ c & d \end{pmatrix}`
- 物理题明确写出 `m = 数字`、`F = 数字`

## 六、支持的课程/学科

| 学科 | 支持度 | 题型 |
|------|-------|------|
| 微积分（极限/导数/积分） | ✅✅✅ | 极限、导数、水平切线、定/不定积分 |
| 线性代数 | ✅✅✅ | 矩阵行列式、逆、秩、特征值/特征向量、解 Ax=b |
| 微分方程 | ✅✅ | 一阶 ODE、二阶常系数齐次/非齐次、初值问题 |
| 大学物理（力学） | ✅✅ | 牛顿第二定律、匀加速运动、动能、重力势能 |
| 代数方程 | ✅✅ | 一元多项式方程 |
| 概念题/证明题 | ⚠️ | 规则模板兜底（夹逼定理、ε-δ、连续性等） |
| 电磁学/热学/光学 | ❌ | 需扩展物理公式模板 |
| 概率统计 | ❌ | 需新增求解器 |
| 信号与系统 | ❌ | 需新增傅里叶/z 变换求解 |

## 七、扩展方法

### 加一个新学科求解器

1. 在 `scripts/solve.py` 里写一个 `solve_mytopic(problem: dict) -> dict` 函数，返回 `_ok()` 或 `_fail()`。
2. 在 `SOLVERS` 字典注册：`"mytopic": solve_mytopic`。
3. 在 `scripts/parse_problems.py` 的 `TYPE_KEYWORDS` 里加关键词，让分类器把题目路由到你的求解器。

### 接入真实国产 LLM API（Qwen/Kimi/DeepSeek）

`scripts/solve.py` 末尾的 `solve_conceptual()` 是预留接口。把规则模板替换成：

```python
import openai  # DashScope / Moonshot / DeepSeek 都兼容 OpenAI SDK

client = openai.OpenAI(
    api_key=os.environ["DASHSCOPE_API_KEY"],
    base_url="https://dashscope.aliyuncs.com/api/v1",
)

resp = client.chat.completions.create(
    model="qwen-plus",
    messages=[
        {"role": "system", "content": "你是数学助教，输出解题步骤和最终答案。"},
        {"role": "user", "content": problem["text"]},
    ],
)
```

## 八、常见问题

**Q: PDF 编译慢？**
A: 第一次 tectonic 会下载宏包（~150s），之后缓存命中约 8s。

**Q: 某道题显示"未自动求解"？**
A: 查看 `3_solutions.json` 里的 `reason` 字段。常见原因：LaTeX 写法不规范、题型未覆盖、表达式过于复杂。可以手写答案后直接编辑 `homework.tex`。

**Q: 能跑 Windows 吗？**
A: Python 部分跨平台；tectonic 有 Windows 二进制；中文需装 ctex 宏包（tectonic 自动处理）。
