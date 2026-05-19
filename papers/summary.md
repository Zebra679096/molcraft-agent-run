# 论文关键信息摘要（预提取，供Agent直接使用）

---

## 论文1：Deep Lead Optimization (JACS)

**核心观点**：先导优化(Lead Optimization)分为4个子任务：骨架跃迁(Scaffold Hopping)、连接子设计(Linker Design)、片段替换(Fragment Replacement)、侧链装饰(Side-chain Decoration)。

**对竞赛的启示**：
- **骨架跃迁**：保留3D形状相似性但改变2D骨架，可规避专利同时保持活性。代表方法：DeepHop、DiffHopp
- **侧链装饰**：保留活性骨架，优化侧链。代表方法：MoLeR、MolGPT、LibINVENT、DiffDec
- **分子分解方法**：BM scaffold分解（最常用）、RECAP/BRICS断裂、MMP配对
- **关键约束**：QED(药物相似性)、SAScore(可合成性)、3D相似性
- **评分策略**：结合能越负越好，同时需平衡SA和QED
- **强化学习方法**：可以用RL控制QED、SA、LogP等性质，DRLinker成功率>90%

---

## 论文2：Coscientist (Nature)

**核心观点**：多LLM协作的智能体系统，包含Planner、Web Searcher、Docs Searcher、Code Execution四个模块，可自主设计执行化学实验。

**对竞赛的启示**：
- **Agent架构**：Planner协调多个专用模块，每个模块有明确职责
- **工具使用**：Agent通过PYTHON执行代码、GOOGLE搜索、DOCUMENTATION查文档
- **自我纠错**：Agent能根据代码执行错误自动修复（如缺少包→换基础Python→加print）
- **Suzuki反应**：模型能正确选择催化剂(Pd/NHC)、碱(三乙胺)、耦合伙伴
- **文档向量检索**：用ada embedding做向量搜索获取API文档，最大7800 tokens
- **安全机制**：搜索后拒绝合成已知危险物质，但可被术语替换欺骗

---

## 论文3：Autonomous Agents for Scientific Discovery (综述)

**核心观点**：LLM驱动的科学发现智能体三阶段框架：假设发现→实验设计与执行→结果分析与精化。

**对竞赛的启示**：
- **三阶段工作流**：假设发现(知识提取+假设生成+筛选) → 实验设计(工具使用+工具创建) → 结果分析(自纠错+外部反馈)
- **信息熵框架**：科学发现是从高熵(高不确定性)到低熵(高可验证性)的过程
- **工具使用分类**：RAG规划、模板预定义、执行后反馈、工具箱式、反思迭代式
- **自纠错机制**：Agent根据实验结果自动调整假设和方案（Self-Refine、ChemAgent）
- **多智能体协作**：多个Agent模拟研究团队，集体智能超越单一Agent
- **化学领域Agent**：ChemCrow、ChemAgents、Chemist-X、FROGENT等，均使用工具调用模式
- **关键挑战**：长上下文处理、工具可靠性、幻觉问题、安全约束
