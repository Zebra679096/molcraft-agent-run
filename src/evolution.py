"""进化搜索引擎：多代种群进化 + 对接引导选择。

核心思想（来自第一性原理推导的混合方案）：
  - 种群多样性保证搜索广度
  - 对接打分作为适应度函数提供方向
  - RDKit 变异提供化学合理的分子操作
  - 精英保留 + 锦标赛选择平衡探索与利用

与 pipeline.py 的 generate_with_docking_guidance 的关键区别：
  1. 支持多种子冷启动（从文献/RAG获取）
  2. 锦标赛选择替代简单 top-K 截断（保持多样性）
  3. 综合适应度 = binding_energy + QED + SA（而非仅 binding_energy）
  4. 种群隔离机制（精英区 + 探索区）
  5. 自适应变异强度（早期高变异探索，后期低变异精修）
  6. 完整的统计输出供 Agent 决策

文献依据:
  - MOOSE-Chem (Yang et al., 2025): 进化算法导航组合空间
  - MolLEO (Wang et al., 2024b): LLM作为变异算子
  - Deep Lead Optimization (JACS): 骨架跃迁+侧链装饰策略
"""
import random
import sys
import time
from typing import Callable, Optional

from rdkit import Chem, rdBase
from rdkit.Chem import Descriptors, QED

from evaluator import evaluate_molecule, passes_filters
from generator import random_mutate_smiles, SCAFFOLDS
from docking import dock_molecule, batch_dock
from receptor import prepare_receptor

rdBase.DisableLog('rdApp.error')
rdBase.DisableLog('rdApp.warning')


# ============================================================
# 适应度函数
# ============================================================

def compute_fitness(mol_info: dict, w_binding: float = 0.5, w_qed: float = 0.3, w_sa: float = 0.2) -> float:
    """计算综合适应度得分（越高越好）。

    归一化策略：
      - binding_energy: 典型范围 [-12, -4]，取负归一化到 [0, 1]
      - QED: 已经在 [0, 1]
      - SA: 典型范围 [1, 6]，取反归一化到 [0, 1]（越低越好）

    Args:
        mol_info: 包含 binding_energy, qed, sa_score 的字典
        w_binding: 结合能权重
        w_qed: QED 权重
        w_sa: SA score 权重

    Returns:
        float: 综合适应度 [0, 1]
    """
    be = mol_info.get("binding_energy", 0)
    qed = mol_info.get("qed", 0)
    sa = mol_info.get("sa_score", 6)

    # 归一化 binding_energy: [-12, -4] → [1, 0]，越负越好
    be_norm = max(0, min(1, (-be - 4) / 8)) if be < 0 else 0
    # 归一化 SA: [1, 6] → [1, 0]，越低越好
    sa_norm = max(0, min(1, (6 - sa) / 5))

    fitness = w_binding * be_norm + w_qed * qed + w_sa * sa_norm
    return round(fitness, 4)


# ============================================================
# 选择算子
# ============================================================

def tournament_select(population: list[dict], k: int = 3) -> dict:
    """锦标赛选择：随机选 k 个，返回适应度最高的。

    相比简单 top-K 截断，锦标赛选择能保持种群多样性，
    避免早熟收敛到单一最优解附近。
    """
    candidates = random.sample(population, min(k, len(population)))
    return max(candidates, key=lambda x: x.get("fitness", 0))


def elitist_select(population: list[dict], n_elite: int) -> list[dict]:
    """精英选择：直接保留适应度最高的 n_elite 个个体。"""
    sorted_pop = sorted(population, key=lambda x: x.get("fitness", 0), reverse=True)
    return sorted_pop[:n_elite]


# ============================================================
# 变异算子
# ============================================================

def adaptive_mutate(smiles: str, generation: int, max_generations: int) -> Optional[str]:
    """自适应变异：早期高变异探索，后期低变异精修。

    变异强度随代数递减：
      - 前 30% 代数: n_mut = 3-5 (强变异，探索)
      - 中 40% 代数: n_mut = 2-3 (中变异，平衡)
      - 后 30% 代数: n_mut = 1-2 (弱变异，精修)
    """
    progress = generation / max(max_generations, 1)

    if progress < 0.3:
        n_mut = random.randint(3, 5)
    elif progress < 0.7:
        n_mut = random.randint(2, 3)
    else:
        n_mut = random.randint(1, 2)

    return random_mutate_smiles(smiles, n_mut)


# ============================================================
# 进化主循环
# ============================================================

def run_evolution(
    seed_smiles: Optional[list[str]] = None,
    n_generations: int = 8,
    pop_size: int = 30,
    n_elite: int = 5,
    n_explore: int = 10,
    tournament_k: int = 3,
    w_binding: float = 0.5,
    w_qed: float = 0.3,
    w_sa: float = 0.2,
    verbose: bool = True,
) -> list[dict]:
    """运行多代进化搜索。

    架构：种群分为精英区(elite) + 探索区(explore) + 变异区(mutate)
      - 精英区：直接保留上一代最优个体（保证不退化）
      - 探索区：从骨架库随机生成全新个体（注入多样性）
      - 变异区：从上一代优良个体变异产生（定向搜索）

    Args:
        seed_smiles: 种子分子列表（来自RAG冷启动或骨架库）
        n_generations: 进化代数
        pop_size: 每代种群大小
        n_elite: 精英保留数量
        n_explore: 每代注入的全新探索个体数量
        tournament_k: 锦标赛选择参数
        w_binding/w_qed/w_sa: 适应度函数权重
        verbose: 是否打印进度

    Returns:
        list[dict]: 所有评估过的分子，按适应度降序排列
    """
    # 准备受体（一次性）
    prepare_receptor()

    # 初始化种群
    if seed_smiles and len(seed_smiles) > 0:
        seeds = seed_smiles
    else:
        seeds = SCAFFOLDS

    all_history = []  # 全局历史记录（跨代累积）
    population = []   # 当前种群（带适应度）

    start_time = time.time()

    for gen in range(n_generations):
        gen_start = time.time()
        new_population = []

        # === 1. 精英保留 ===
        if population:
            elite = elitist_select(population, n_elite)
            new_population.extend(elite)
            if verbose:
                print(f"  [Gen {gen+1}] 精英保留 {len(elite)} 个", file=sys.stderr)

        # === 2. 探索区：全新随机生成 ===
        explore_count = 0
        explore_attempts = 0
        max_explore_attempts = n_explore * 30
        while explore_count < n_explore and explore_attempts < max_explore_attempts:
            explore_attempts += 1
            seed = random.choice(seeds)
            n_mut = random.randint(1, 4)
            new_smiles = random_mutate_smiles(seed, n_mut)
            if new_smiles:
                props = evaluate_molecule(new_smiles)
                if passes_filters(props, max_sa=6.0):
                    new_population.append({**props, "generation": gen, "source": "explore"})
                    explore_count += 1
        if verbose:
            print(f"  [Gen {gen+1}] 探索区生成 {explore_count} 个", file=sys.stderr)

        # === 3. 变异区：从优良个体变异 ===
        mutate_target = pop_size - len(new_population)
        mutate_count = 0
        mutate_attempts = 0
        max_mutate_attempts = mutate_target * 20
        while mutate_count < mutate_target and mutate_attempts < max_mutate_attempts:
            mutate_attempts += 1
            if not population:
                # 第一代没有种群，从种子变异
                seed = random.choice(seeds)
                new_smiles = random_mutate_smiles(seed, random.randint(1, 3))
            else:
                # 锦标赛选择父代
                parent = tournament_select(population, tournament_k)
                parent_smiles = parent.get("smiles", "")
                if not parent_smiles:
                    continue
                # 自适应变异
                new_smiles = adaptive_mutate(parent_smiles, gen, n_generations)

            if new_smiles:
                # 检查是否已存在于当前种群
                existing_smiles = {m.get("smiles") for m in new_population}
                if new_smiles in existing_smiles:
                    continue
                props = evaluate_molecule(new_smiles)
                if passes_filters(props, max_sa=6.0):
                    new_population.append({**props, "generation": gen, "source": "mutate"})
                    mutate_count += 1

        if verbose:
            print(f"  [Gen {gen+1}] 变异区生成 {mutate_count} 个", file=sys.stderr)

        # === 4. 批量对接 ===
        dock_mols = [{"smiles": m["smiles"]} for m in new_population]
        if verbose:
            print(f"  [Gen {gen+1}] 开始对接 {len(dock_mols)} 个分子...", file=sys.stderr)

        docked_results = batch_dock(dock_mols)

        # 将对接结果合并到种群
        docked_map = {}
        for r in docked_results:
            if r.get("success"):
                docked_map[r["smiles"]] = r.get("binding_energy")

        scored_population = []
        for m in new_population:
            smiles = m["smiles"]
            if smiles in docked_map:
                m["binding_energy"] = docked_map[smiles]
                m["fitness"] = compute_fitness(m, w_binding, w_qed, w_sa)
                scored_population.append(m)
                all_history.append(m)

        # 按适应度排序
        scored_population.sort(key=lambda x: x.get("fitness", 0), reverse=True)
        population = scored_population

        # 代统计
        gen_time = time.time() - gen_start
        if population:
            best = population[0]
            avg_fitness = sum(m.get("fitness", 0) for m in population) / len(population)
            if verbose:
                print(
                    f"  [Gen {gen+1}] 完成: "
                    f"种群={len(population)}, "
                    f"最佳适应度={best.get('fitness', 0):.4f}, "
                    f"最佳BE={best.get('binding_energy', 'N/A')}, "
                    f"最佳QED={best.get('qed', 'N/A')}, "
                    f"最佳SA={best.get('sa_score', 'N/A')}, "
                    f"平均适应度={avg_fitness:.4f}, "
                    f"耗时={gen_time:.1f}s",
                    file=sys.stderr,
                )

    # === 最终输出 ===
    # 去重 + 按适应度排序
    seen = set()
    unique = []
    for m in all_history:
        smi = m.get("smiles", "")
        if smi and smi not in seen:
            seen.add(smi)
            unique.append(m)
    unique.sort(key=lambda x: x.get("fitness", 0), reverse=True)

    total_time = time.time() - start_time
    if verbose:
        best = unique[0] if unique else {}
        print(
            f"\n[进化完成] 总耗时={total_time:.1f}s, "
            f"总分子数={len(unique)}, "
            f"最佳适应度={best.get('fitness', 'N/A')}, "
            f"最佳BE={best.get('binding_energy', 'N/A')}, "
            f"最佳QED={best.get('qed', 'N/A')}, "
            f"最佳SA={best.get('sa_score', 'N/A')}",
            file=sys.stderr,
        )

    return unique


def refine_top_molecules(
    top_molecules: list[dict],
    n_refine_rounds: int = 3,
    n_offspring_per_seed: int = 5,
    verbose: bool = True,
) -> list[dict]:
    """对 top 分子进行精修：低变异强度 + 严格过滤。

    精修阶段专注于局部搜索，在最优分子附近微调，
    期望找到结合能更好且性质更优的变体。

    Args:
        top_molecules: 待精修的 top 分子列表
        n_refine_rounds: 精修轮次
        n_offspring_per_seed: 每个种子每轮产生的变体数

    Returns:
        list[dict]: 精修后的分子列表，按适应度降序
    """
    prepare_receptor()

    current_seeds = top_molecules
    all_refined = list(top_molecules)

    for round_idx in range(n_refine_rounds):
        new_mols = []
        for seed in current_seeds:
            seed_smiles = seed.get("smiles", "")
            if not seed_smiles:
                continue

            for _ in range(n_offspring_per_seed):
                # 精修用弱变异：1-2个突变点
                new_smiles = random_mutate_smiles(seed_smiles, random.randint(1, 2))
                if new_smiles and new_smiles != seed_smiles:
                    props = evaluate_molecule(new_smiles)
                    if passes_filters(props, max_sa=6.0):
                        new_mols.append(props)

        if not new_mols:
            continue

        # 对接评估
        dock_mols = [{"smiles": m["smiles"]} for m in new_mols]
        docked_results = batch_dock(dock_mols)

        docked_map = {}
        for r in docked_results:
            if r.get("success"):
                docked_map[r["smiles"]] = r.get("binding_energy")

        scored = []
        for m in new_mols:
            smiles = m["smiles"]
            if smiles in docked_map:
                m["binding_energy"] = docked_map[smiles]
                m["fitness"] = compute_fitness(m)
                scored.append(m)

        all_refined.extend(scored)

        # 更新种子为当前轮最优
        if scored:
            scored.sort(key=lambda x: x.get("fitness", 0), reverse=True)
            current_seeds = scored[:len(current_seeds)]

        if verbose and scored:
            print(
                f"  [精修轮 {round_idx+1}] 生成 {len(new_mols)}, "
                f"对接成功 {len(scored)}, "
                f"最佳BE={scored[0].get('binding_energy', 'N/A')}",
                file=sys.stderr,
            )

    # 去重 + 排序
    seen = set()
    unique = []
    for m in all_refined:
        smi = m.get("smiles", "")
        if smi and smi not in seen:
            seen.add(smi)
            unique.append(m)
    unique.sort(key=lambda x: x.get("fitness", 0), reverse=True)

    return unique
