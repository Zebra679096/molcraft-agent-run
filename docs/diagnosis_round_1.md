# 瓶颈诊断报告 Round 1

## 诊断日期
2026-05-02

## 代码全面分析结果

### 瓶颈 H002：分子生成与分子对接严重脱节
**目标文件**: `src/generator.py`, `tools/pipeline.py`
**根本问题**: 
- `generate_molecules()` 仅以 QED 作为排序依据，完全不考虑靶点特异性结合能
- 每代生成50个分子后才批量对接，大量计算浪费在不可能结合好的分子上
- 进化迭代虽然有2代，但每代内部的50个分子仍是"盲生成"

**量化证据**:
- generator.py line 239: `result.sort(key=lambda x: x["qed"], reverse=True)` — 仅用QED排序
- pipeline.py line 77: 先生成50个，再对接 — 生成与对接完全解耦

**文献支撑**: 
- MOOSE-Chem (Yang et al., 2025): "Evolutionary search guided by fitness function"
- Coscientist (Boiko et al., 2023): "The Agent corrects its own code based on automatically generated outputs"
- 综述第4.2节: "Post-Execution Feedback" 策略强调实验结果应反馈到下一步设计

**验证指标**: 
- 改进前 top10 平均结合能（基线）
- 改进后 top10 平均结合能
- 成功标准：平均结合能降低 > 0.3 kcal/mol 或相对提升 > 5%

### 瓶颈 H003：逆合成缺乏多步递归规划
**目标文件**: `src/synthesis_v2.py`
**根本问题**:
- 35条规则都是单步断键，复杂分子一步断键后中间体仍很复杂
- 没有递归继续断键的能力
- 某些规则在合成方向上不合理（如 `[c:1]F>>[c:1]Cl.F`）

**文献支撑**:
- LARC (Baker et al., 2025): Agent-as-a-Judge 强调路线需要多步评审

### 瓶颈 H004：缺乏自适应反馈闭环
**目标文件**: `tools/pipeline.py`（整体 workflow）
**根本问题**:
- 运行结束后结果仅被记录，没有自动分析失败原因
- 如果 trivial route 比例高，不会自动增加逆合成规则
- 如果结合能不够好，不会自动增加进化代数

**文献支撑**:
- 综述第5.2节: "Iterative Result Validation and Refinement" 是科学发现的关键
- OSDA Agent: Actor-Evaluator-Reflector 循环

## Round 1 选定假设

**假设ID**: H002
**瓶颈**: 分子生成与对接脱节，生成阶段不利用对接信息
**改进方案**: 在 `src/generator.py` 中新增 `generate_with_docking_guidance()` 函数，实现小批量生成→对接→选择top→变异→再对接的微循环
**验证指标**: top10 平均结合能对比
**风险**: 低。新增函数，不破坏原有接口
