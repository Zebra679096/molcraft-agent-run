# 代码演进记录 Round 1

## 假设ID
H002

## 修改目标
解决分子生成与分子对接脱节的问题，引入对接引导生成机制。

## 修改文件
1. `src/generator.py` — 新增 `generate_with_docking_guidance()` 函数
2. `tools/pipeline.py` — 集成对接引导生成到 pipeline 中

## 修改内容摘要

### src/generator.py
- 新增 `generate_with_docking_guidance()` 函数，实现小批量生成→对接→选择→变异的微循环
- 参数设计：
  - `batch_size=10`: 每批生成10个候选分子，避免盲生成大量分子
  - `n_generations=3`: 3轮微循环迭代
  - `top_k=5`: 每代选择结合能最优的5个作为种子
  - 后续代变异强度降低（n_mut=1-3），保持分子稳定性
- 保留原有 `generate_molecules()` 接口不变

### tools/pipeline.py
- 新增 `use_docking_guidance` 参数
- 初始代可选择使用对接引导生成或传统生成
- 新增 `--docking-guidance` CLI 参数

## 文献依据
- MOOSE-Chem (Yang et al., 2025): 进化算法导航组合空间
- Coscientist (Boiko et al., 2023): 基于实验结果的迭代反思
- 综述第4.2节: Post-Execution Feedback 策略

## 代码自检结果
- `python3 -m py_compile src/generator.py tools/pipeline.py` — 通过
- `python3 -c "from generator import generate_with_docking_guidance; print('import ok')"` — 通过
