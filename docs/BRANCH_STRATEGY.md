# Git 分支管理策略

## 设计理念

本项目是竞赛型实验项目，每次设计方案的路径和结果不可预知。
不同方案之间**不一定是增量改进关系**，可能完全推翻重来。
因此采用"独立分支 + 主线择优"的策略，而非传统的"一条主线迭代"。

## 分支模型

```
main ─────────────────────────────────────── (永远是最优提交版本，仅合并最优分支)
  │
  ├── design/v1-random-evolution            (随机进化方案，BE=-8.494)
  ├── design/v2-llm-driven                  (LLM驱动方案，score=0.202)
  ├── design/v3-structure-guided            (结构引导 + canonical修复，当前最优)
  └── design/v4-pharmacophore               (药效团设计，待启动)
```

## 分支命名规范

```
design/<版本号>-<方案关键词>
```

- 版本号：递增的整数
- 方案关键词：简短英文描述核心策略

示例：
- `design/v1-random-evolution` — 随机进化
- `design/v2-llm-driven` — LLM驱动
- `design/v3-structure-guided` — 结构引导
- `design/v4-pharmacophore` — 药效团
- `design/v5-fragment-based` — 基于片段
- `design/v6-mmp-docking` — MMP+分子对接

## Tag 命名规范

```
v<大版本>.<小版本>-<关键词>
```

| Tag | 含义 |
|-----|------|
| `v0.1-baseline` | 基线Pipeline，随机进化 |
| `v0.2-evo-2gen` | 2代进化 |
| `v0.3-evo-3gen` | 3代进化 |
| `v0.4-llm-agent` | LLM Agent方案 |
| `v0.5-deepseek` | DeepSeek LLM驱动 |
| `v0.6-hybrid` | 三阶段混合方案 |
| `v0.7-route-fix` | route_score Bug修复 |
| `v0.8-structure-guided` | 结构引导分子设计 |
| `v0.9-canonical-fix` | SMILES canonical化修复 |

## 工作流程

### 1. 启动新设计方案
```bash
# 从 main 创建新分支
git checkout main
git checkout -b design/v4-pharmacophore

# 在新分支上自由开发，不影响 main
```

### 2. 实验过程中
```bash
# 在设计分支上频繁提交
git add -A
git commit -m "feat(v4): 药效团分析完成，识别3个关键药效团特征"
git push origin design/v4-pharmacophore
```

### 3. 方案产出结果后
```bash
# 打 tag 标记里程碑
git tag -a v0.10-pharmacophore -m "v0.10: 药效团设计，binding_score=xxx"

# 如果比当前 main 更优，合并到 main
git checkout main
git merge design/v4-pharmacophore --no-ff
git push origin main
git push origin --tags
```

### 4. 如果方案失败
```bash
# 不合并到 main，分支保留作为实验记录
# 直接切回 main 或创建新分支
git checkout main
git checkout -b design/v5-fragment-based
```

## 关键规则

1. **main 只合并最优结果** — 不允许实验性代码直接提交到 main
2. **每个分支保留自己的 result.csv** — 不同方案的产出独立保存
3. **tag 标记每个里程碑** — 便于回溯和对比
4. **分支描述记录在 DECISION_LOG.md** — 每个方案的设计思路、结果、决策
5. **失败分支不要删除** — 保留完整实验记录，避免重复踩坑

## 各版本成绩汇总

| 版本 | 方案 | binding_score | route_score | 备注 |
|------|------|---------------|-------------|------|
| v0.1~v0.3 | 随机进化 | BE=-8.494 kcal/mol | N/A | LLM score=0 |
| v0.4~v0.6 | LLM驱动 | 0.202 | 有canonical问题 | 需要修复 |
| v0.7~v0.9 | 结构引导+修复 | 待提交验证 | canonical已修复 | 当前最优 |
| v4 (待做) | 药效团设计 | 目标：<-10 | 目标：满分 | 下一步 |
