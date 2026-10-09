# C4C 作业自动求解与排版（国产模型版）

> 从作业 Markdown/PDF/DOCX 到可提交 PDF，一条命令。
> 基于 starter kit 迁移到国产大模型（豆包），并扩展到线性代数、微分方程、大学物理、积分。

## 快速开始

```bash
cd homework_solver
pip install sympy pdfplumber python-docx
python3 scripts/pipeline.py ../Doubao_C4C_作业原件.md ../output \
    --compile --course "工科数学物理综合" --student "Doubao"
```

输出：`output/homework.pdf`（3 页中文 PDF，10/10 题解出）。

## 目录结构

```
C4C挑战交付资料/
├── Doubao_C4C_方案设计.md          # 架构、模型选型、求解策略
├── Doubao_C4C_教学说明.md            # 安装、使用、扩展方法
├── Doubao_C4C_验证报告.md            # 10 题逐题核验 + 与 Claude 基线对比
├── Doubao_C4C_拿来说明.md            # 从 starter kit 拿了什么、改了什么
├── Doubao_C4C_AI日志.md             # 开发全过程 AI 使用记录
├── Doubao_C4C_反思复盘.md            # AAR：做对了什么、踩坑、改进
├── Doubao_C4C_作业原件.md            # 真实作业输入（非微积分极限）
├── Doubao_C4C_output.pdf            # 流水线生成的 PDF ⭐
├── Doubao_C4C_output.tex            # 对应 LaTeX 源文件
├── homework_solver/                  # 可运行技能包
│   └── scripts/
│       ├── ingest.py                # Stage 1: md/pdf/docx → 文本
│       ├── parse_problems.py       # Stage 2: 题号/公式/题型分类
│       ├── solve.py                # Stage 3: SymPy + 国产 LLM 求解
│       ├── render_latex.py          # Stage 4: ctexart 排版
│       └── pipeline.py             # 一键串联
└── test_homework/
    ├── homework_real.md             # 测试作业源文件
    └── output/                     # 流水线运行产物
```

## 实测成绩

| 测试 | 题数 | 解出 | 准确率 |
|------|-----|------|--------|
| starter 示例（导数/积分/方程/矩阵/ODE） | 10 | 10 | **100%** |
| 真实作业（线代+ODE+物理+积分，非极限） | 10 | 10 | **100%** |
| Claude 基线（Berkeley 极限） | 18 | 17 | 94.4% |
| Claude 域外（进阶题） | 5 | 2 | 40% |

## 支持学科

- 微积分：极限、导数、定/不定积分、水平切线
- 线性代数：矩阵行列式、逆、秩、特征值、解 Ax=b
- 微分方程：一阶、二阶常系数 ODE、初值问题
- 大学物理：牛顿第二定律、动能、重力势能、匀加速运动
- 输入格式：Markdown / PDF（文本型）/ DOCX
