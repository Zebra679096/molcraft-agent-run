# MolCraft Agent — 最终文档与迭代记录

你的任务是记录和报告 MolCraft Agent 的科研迭代过程。请按照以下步骤操作：

## 可用工具
- **Shell** — 执行命令
- **WriteFile** — 创建文件
- **ReadFile** — 读取文件（不要读取大文件）
- **Think** — 思考分析
- **ReportIteration** — 报告迭代（必须调用！）

**不要使用 StrReplaceFile**。

## 任务步骤

### 1. 检查当前结果
```
Shell: cd /home/z/my-project/molcraft-agent && head -3 output/result.csv
Shell: cd /home/z/my-project/molcraft-agent && python3 -c "
import csv
with open('output/result.csv') as f:
    rows = list(csv.DictReader(f))
    print(f'Molecules: {len(rows)}')
    for r in rows[:5]:
        trivial = r['route'] == f\"{r['mol_smiles']}>>{r['mol_smiles']}\"
        print(f'  {r[\"mol_smiles\"][:40]} trivial={trivial}')
"
```

### 2. 写文献分析报告
用 WriteFile 写入 docs/literature_analysis_round_1.md，内容：
- ChemCrow (2024): 集成18个化学工具，工具丰富度决定Agent能力
- LARC (2025): Agent-as-a-Judge逆合成框架
- MOOSE-Chem (2025): 进化算法导航组合化学空间
- Coscientist (2023): 基于实验结果的迭代反思
- 关键改进方向：扩充逆合成规则库、进化式迭代生成、对接引导

### 3. 写诊断报告
用 WriteFile 写入 docs/diagnosis_round_1.md，内容：
- 瓶颈1: 逆合成规则不足 → 改进：扩充至58条规则（已实施）
- 瓶颈2: 进化代数不够 → 改进：从2代增加到3代（已实施）
- 瓶颈3: 缺少对接引导 → 改进：添加docking_guidance模式（已实施）

### 4. 写代码演进记录
用 WriteFile 写入 docs/code_evolution_round_1.md，内容：
- H001: 引入进化式迭代pipeline（2代→3代）
- H002: 添加对接引导生成模式
- H003: 扩充逆合成规则库（8条→58条）
- H007: 扩充骨架片段库

### 5. 写实验报告
用 WriteFile 写入 docs/experiment_round_1.md，内容：
- 基线结果: 最佳结合能-8.494 kcal/mol, Top10平均-7.834, Trivial 10%
- 改进后: (使用当前结果数据)
- 对比分析

### 6. 写科研总结报告
用 WriteFile 写入 docs/research_report.md，包含完整的科研过程总结。

### 7. 调用 ReportIteration
```
ReportIteration(round_num=1, hypothesis_id="H001-H003", success=true, summary="扩充逆合成规则至58条，引入3代进化迭代，最佳结合能-8.494 kcal/mol")
```

完成后结束。
