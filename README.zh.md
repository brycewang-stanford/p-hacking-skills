# p-hacking-skills（中文说明）

**面向计量设计的可审计 p-hacking 引擎。** 它能像真人一样在规格空间里搜索，也能算出搜索完之后那个 p 值到底还值多少。

> **用途说明。** 本工具仅用于关于 p-hacking 的学术研究讨论与教学，以及评测 AI 科研 agent 是否会 p-hacking。**不建议用在真实的论文写作或科研项目中。** 它的每一次搜索都会留下完整账本（ledger）和零校准的诚实 p 值，`phack verify` 让任何第三方都能核验一个运行目录。如果你想用它给真实分析"找显著"，它会把你做过的一切都记下来——这是设计使然。

## 它是什么

Asher 等（2026）发现：前沿编程 agent 会拒绝"请给我显著结果"的直接要求，却会接受措辞改成"探索不同设计给出估计的上界"的同一要求，并写出按显著性排序的嵌套循环。要度量这个缺口，就得能在有记录的条件下执行这种行为，而且要在真正有油水的设计上：有估计量菜单的 DiD、有带宽菜单的 RDD、有工具变量菜单的 IV，并且用研究者真正在用的语言。

**唯一的规则：任何搜索都必须留下完整账本，任何报告出来的 p 值都必须附带它的诚实对应值。** 规格搜索本身不是不端，把搜索赢家当成单一预注册检验来报告才是。

## 安装与最短路径

```bash
pip install phack                       # 引擎 + phack 命令行（Python ≥ 3.10）
pip install 'phack[formats]'            # 读取 .dta / .parquet / .xlsx
```

```bash
phack init panel.dta --design did --treatment policy --outcome lnwage   # 从数据起草设计卡片
phack size panel_card.json                                               # 规格空间有多大、预注册规格是哪一个
phack search panel.dta panel_card.json --direction + --null-draws 200 --n-jobs 6 --summary
phack search panel.dta panel_card.json --procedure greedy --stop-at-alpha --direction + --null-draws 200
phack export panel.dta panel_card.json --lang stata --out run_stata/     # 同一网格交给 Stata / R / Python / StatsPAI
phack ingest run_stata/ --parity                                          # 接回审计并与引擎逐行比对
phack verify phack_out/                                                   # 第三方核验
./demo.sh                                                                 # 在已知零效应数据上跑通全流程
```

也可以用 Docker（`docker build -t phack .`）或 Colab（`notebooks/quickstart.ipynb`）零安装体验；作为 Claude Code 技能使用时，安装本仓库的插件（`.claude-plugin/`）或把 `skills/` 复制到 `.claude/skills/`。

## 引擎做什么

1. **枚举网格。** 设计卡片（JSON，有正式 schema）每个键是一个研究者自由度；`preregistered` 块指定诚实分析者会事先承诺的那一个规格。支持 OLS / RCT、DiD（TWFE、Gardner 两阶段、stacked、对照组选择）、事件研究（窗口、参照期、估计目标）、RDD（ROT / IK 带宽 × 倍数、核、多项式、甜甜圈、常规 / 偏差修正 / CCT robust 推断）、IV（工具子集、2SLS / LIML、每行记录一阶段 F 与 Anderson–Rubin p）。
2. **走网格。** 穷举，或者像 p-hacker 一样按顺序走并设停止规则（`first_significant`、`random`、`greedy` 坐标下降、`hill_climb`）；零校准会**重放同一过程**，给出"这种搜索方式在这个设计上"的假阳性率。
3. **算出搜索值多少。** 对最优规格：Bonferroni、Li–Ji 有效检验数、Romano–Wolf、零校准诚实 p；对整条曲线：Simonsohn 联合检验；再加上**与预注册规格的距离**（差几个选择就能显著）和**轴归因**（哪个旋钮在做功）。病理标记把"可引用但错误"的角落留在账本里并标出来。
4. **写报告，可核验。** `report.md` 从审计生成，数字不可能与账本漂移；`manifest.json` 记录数据、卡片、账本、审计的哈希；`phack verify` 逐项核对。`phack bench` 冻结与检查基准版本；`bench.seal` 对保留集做哈希承诺而不公开内容。
5. **在你的语言里跑。** `phack export` 导出语言无关的规格表、数据和零假设置换列，并生成 Stata（reghdfe / ivreghdfe / rdrobust / did2s）、R（fixest / rdrobust / did2s）、Python（statsmodels / linearmodels）或 StatsPAI 的执行脚本；`phack ingest --parity` 接回并与引擎逐行比对，一致性表见 `references/language-map.md`。

## 数据

八个生成数据集，全部来自 `scripts/make_null_data.py` 的固定种子与文档化 DGP：四个真零效应（`null_panel` 25,920 个规格、`null_staggered` 3,456 + 事件研究 1,200、`null_rdd` 20,736、`null_iv` 672），四个已知效应的正向对照（证明诚实流程不会把真效应也"校准"掉）。`scripts/calibrate_engine.py` 在新鲜数据上检验：真零时诚实 p 应近似均匀，真效应时应有功效。

## 十一个技能

见 [skills/README.zh.md](skills/README.zh.md)。三侧：map（路由、策略分类、设计卡片）、red（规格搜索、搜索过程、多语言、提示框架攻击、叙事洗白）、blue（p-curve 检测、免疫）、eval（agent 评测）。

## 参与贡献

四个扩展点——新自由度轴、新搜索过程、新语言执行器、新数据集——各有最小示例，见 [CONTRIBUTING.md](CONTRIBUTING.md)。issue 模板覆盖 bug、新轴、新数据集与一致性报告。引用请见 [CITATION.cff](CITATION.cff)。

## 局限

诚实 p 是被检验的而非假设的；重尾的数值伪影需要病理标记而不只是零抽样；各语言执行器复现的是网格语义而非引擎的数值约定；DiD 菜单尚无 Callaway–Sant'Anna / Sun–Abraham；RDD 带宽不是 rdrobust 的 CCT 最优；正则扫描是筛查而非判决；公开仓库意味着 agent 读过它——请保留私有测试集并只公布其哈希承诺。

MIT 许可。
