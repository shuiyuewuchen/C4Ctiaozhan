# Doubao_C4C 作业自动求解与排版流水线

> 国产模型（豆包）端到端完成 Berkeley Math 1A 作业：读取作业 → 自动求解 → 排版 PDF。
> 本目录是最终交付包，可直接评审。

## 目录结构

```
C4C挑战交付资料/
├── README.md                          # 本文件
├── Doubao_C4C_方案设计.md             # 总体方案、五段流水线设计
├── Doubao_C4C_验证报告.md             # 真实 Berkeley 试卷成绩 + 与 Claude 基线对比
├── Doubao_C4C_拿来说明.md             # 对评委的演示口径
├── Doubao_C4C_教学说明.md             # 学生/老师使用说明
├── Doubao_C4C_反思复盘.md             # 硬伤修复复盘 + 已知局限
├── Doubao_C4C_AI日志.md               # 完整 AI 交互日志
├── Doubao_C4C_作业原件.md             # 自造综合作业（10 题，非极限学科）
├── Doubao_C4C_output.pdf              # 自造作业最终 PDF（10/10）
├── Doubao_C4C_output.tex              # 对应 LaTeX 源
│
├── berkeley_baseline/                # Berkeley 真卷测试（与 Claude 基线同题）
│   ├── test1_tangent_epsilon_delta.md # Worksheet 3 原题（切线+ε-δ，8 题）
│   ├── test2_limits.md                # Worksheet 4 原题（极限，10 题）
│   ├── test1_output/                  # Worksheet 3 运行产物（8/8）
│   │   ├── 1_ingested.json
│   │   ├── 2_parsed.json
│   │   ├── 3_solutions.json
│   │   ├── homework.tex
│   │   └── homework.pdf
│   └── test2_output/                  # Worksheet 4 运行产物（7/10）
│       └── （同上结构）
│
├── test_homework/
│   ├── homework_real.md              # 自造综合作业源文件
│   └── output/                        # 运行产物（10/10）
│
└── homework_solver/                   # 可运行技能包
    ├── SKILL.md
    └── scripts/
        ├── ingest.py                  # Markdown/PDF/DOCX 读取
        ├── parse_problems.py          # 题目切分 + 数学表达式识别
        ├── solve.py                  # SymPy 求解 + 概念题模板
        ├── render_latex.py           # LaTeX 排版（ctexart 中文）
        └── pipeline.py               # 五段流水线主入口
```

## 一键运行

```bash
cd homework_solver
python3 scripts/pipeline.py <输入.md> <输出目录> --compile \
    --course "Math 1A" --student "Doubao" --title "作业标题"
```

依赖：Python 3.10+、sympy、tectonic（编译 PDF）。

## 核心成绩速览

| 测试 | 本版 | Claude 基线 |
|------|------|------------|
| Berkeley Worksheet 3 | 8/8 | 8/8 |
| Berkeley Worksheet 4 | 7/10 | 9/10 |
| **核心域合计（JSON 计数）** | **15/18 = 83.3%** | **17/18 = 94.4%** |
| 核心域合计（剔除假阳性后） | **13/18 = 72.2%** | 17/18 |
| 自造综合作业（10 题） | 10/10 | starter 域外 2/5 |

> **口径说明**：15/18 是 `3_solutions.json` 里 `solved=True` 的计数；其中 Q4/P1 是 SymPy 把抽象函数 f(x) 当乘法算错的假阳性，剔除后真实可信成绩 13/18。
> 详细逐题对照、假阳性披露、根因分析见 `Doubao_C4C_验证报告.md`。
>
> **关于 output 目录**：`test_homework/output/` 和 `berkeley_baseline/*/output/` 是运行 pipeline 生成的产物（含 JSON/tex/pdf），不建议入库；评审时可直接用仓库里已编译好的 PDF，或按上文"一键运行"重新生成。
