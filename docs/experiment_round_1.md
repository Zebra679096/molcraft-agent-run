# 实验验证记录 Round 1

## 假设ID
H002: 对接引导生成（docking-guided generation）

## 实验配置
- 基线: `python3 tools/pipeline.py --n-generate 30 --n-top 10 --strategy mutate --n-generations 2 --n-offspring 3`
- 改进: `python3 tools/pipeline.py --n-generate 30 --n-top 10 --strategy mutate --n-generations 2 --n-offspring 3 --docking-guidance`

## 实验结果

### 基线（传统pipeline）
| 指标 | 数值 |
|------|------|
| Top 10 平均结合能 | -7.959 kcal/mol |
| 最佳结合能 | -8.598 kcal/mol |
| Trivial route 比例 | 2/10 (20.0%) |

### H002 改进后
| 指标 | 数值 |
|------|------|
| Top 10 平均结合能 | -7.884 kcal/mol |
| 最佳结合能 | -8.086 kcal/mol |
| Trivial route 比例 | 2/10 (20.0%) |

## 对比分析
- 平均结合能变化: -7.959 → -7.884（**下降 0.075 kcal/mol，约 0.9%**）
- 最佳结合能变化: -8.598 → -8.086（**下降 0.512 kcal/mol**）
- Trivial route 比例: 无变化（20.0%）

## 结论
**假设 H002 验证失败。**

## 失败原因分析
1. **样本量不足**: docking guidance 每代只生成10个分子，3代共30个候选，远少于传统方法的60+个
2. **过早收敛**: 每代选择top 5作为种子，缺乏多样性保持机制，容易陷入局部最优
3. **batch_size 太小**: 对接评估存在噪声，小样本下选择不稳定
4. **参数未调优**: batch_size=10, top_k=5 可能不是最优配置，但规则禁止在同一假设上反复调参

## 下一步行动
标记 H002 为 **REJECTED**，转向下一个假设 **H003: 逆合成多步递归规划**。
