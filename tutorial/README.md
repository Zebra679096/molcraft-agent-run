# AI4S 智能体 CNS 挑战赛：靶向分子研发与合成规划

这是参加 AI4S 智能体 CNS 挑战赛任务 2 的项目。赛题要求构建一个 **自主科研 Agent**，能够自主完成文献阅读、瓶颈诊断、代码演进、实验验证的科研闭环。

## 教程三件套

按顺序阅读，不要跳章。

| 章节 | 内容 | 读完的状态 |
|------|------|-----------|
| [00-跑 Baseline](00-baseline.md) | 环境配置 → 启动 Agent → 理解产出 → 打包提交 | 拿到第一个由 Agent 自主产出的 result.zip |
| [01-赛事解读](01-understanding.md) | Agent 4 阶段闭环 → 底层引擎 → 评分维度 → 短板分析 | 搞懂 Agent 在做什么、评分为何这样设计 |
| [02-提分教程](02-improvement.md) | 优化 program.md → 实验记录 → 三档提升方向 | 知道如何让 Agent 迭代得更有效 |

用户旅程：先动手跑 Agent → 再理解原理 → 再精进策略。

## 快速开始

```bash
cd molcraft-agent
source .venv/bin/activate

# 配置 API Key（三选一：Kimi CLI 自带 / 环境变量 / 修改 src/config.py）
export KIMI_API_KEY="your-api-key"

# 启动自主科研 Agent（核心模式）
python main.py

# Pipeline 模式（仅用于快速验证底层引擎，非比赛模式）
python tools/pipeline.py --n-generate 50 --n-top 10
```

## 项目结构

```
molcraft-agent/
├── main.py              # Agent 启动入口
├── program.md           # Agent 指令书（人机交互接口，可编辑）
├── agent.yaml           # 工具注册表
├── src/                 # 化学计算引擎（生成、对接、评估、逆合成）
├── molcraft_agent/      # Agent SDK 集成层（工具封装、实验记录）
├── tools/               # CLI 脚本（pipeline.py 为一次性验证脚本）
├── papers/              # 参考论文，Agent 会自主阅读
├── docs/                # Agent 产出的分析报告（文献分析、诊断、代码演进、实验）
├── data/                # 靶点 PDB 文件
└── output/              # result.csv / result.log（提交文件）
```

## 核心设计理念

- **`main.py` 零业务逻辑**：只负责读取 `program.md` 并启动 LLM，所有决策由 Agent 自主执行
- **`program.md` 是唯一人机接口**：调整 Agent 行为只需编辑这个文件
- **一次只改一个假设**：便于归因，避免多变量混淆
- **过程即分数**：完整的"假设-验证"科研闭环本身就是最大的得分点
