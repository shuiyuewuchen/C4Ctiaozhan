# homework-solver

> 国产模型（豆包）端到端作业自动求解与排版流水线。
> 输入一份作业（Markdown / PDF / DOCX），输出解答 PDF。

## 五段流水线

```
ingest → parse_problems → solve → render_latex → compile
```

| 阶段 | 脚本 | 职责 |
|------|------|------|
| 1. 摄入 | `scripts/ingest.py` | 读取 Markdown / PDF（pdfplumber）/ DOCX（python-docx） |
| 2. 解析 | `scripts/parse_problems.py` | 切题、识别数学表达式（`$...$`）、关键词分类学科 |
| 3. 求解 | `scripts/solve.py` | SymPy 计算（导数/极限/积分/矩阵/ODE/物理）+ 概念题模板 |
| 4. 渲染 | `scripts/render_latex.py` | 生成 LaTeX（ctexart 中文，显式 Songti SC） |
| 5. 编译 | `scripts/render_latex.py` | 调用 tectonic 编译 PDF |

## 一键运行

```bash
cd homework-solver
python3 scripts/pipeline.py <输入.md> <输出目录> --compile \
    --course "课程名" --student "学生名" --title "作业标题"
```

示例：
```bash
python3 scripts/pipeline.py ../test_homework/homework_real.md ../test_homework/output \
    --compile --course "工科数学物理综合" --student "Doubao" --title "期中作业解答"
```

## 依赖

- Python 3.10+
- sympy, pdfplumber, python-docx
- tectonic（PDF 编译，单文件二进制，自动下载宏包）

安装：`pip install -r requirements.txt`

tectonic 下载：https://github.com/tectonic-typesetting/tectonic/releases

## 已支持学科

| 学科 | 求解方式 |
|------|---------|
| 导数 | SymPy diff |
| 极限 | SymPy limit + 概念模板（夹逼/∞/单侧极限） |
| 积分 | SymPy integrate（定/不定） |
| 线代 | SymPy Matrix（det/逆/特征值/解 Ax=b） |
| ODE | SymPy dsolve（一阶/二阶线性） |
| 物理 | 牛顿定律、动能、匀加速（按 m=/F= regex 定位） |
| 概念题 | 规则模板（预留 LLM API 接口） |

## 已知局限

- 抽象函数 f(x)/g(x) 被 SymPy 当乘法（Q4/P1 假阳性）
- 证明题、几何画图题需要 LLM 推理，规则模板覆盖不全
- OCR（扫描件/拍照）未实现
- 概念题模板目前未接真实 LLM API
