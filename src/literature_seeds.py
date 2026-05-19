"""文献驱动的种子分子提取模块（RAG冷启动）。

核心思想：
  不从零设计分子，而是从已知药物/文献中提取活性骨架作为起点，
  LLM 在此基础上进行适配性修改，效率比从10^60化学空间盲目搜索高一个数量级。

本模块实现两种种子来源：
  1. 预定义的药物化学知识库（常见药效团和活性骨架模式）
  2. 从 papers/summary.md 中解析的关键骨架信息

文献依据:
  - Deep Lead Optimization (JACS): 骨架跃迁+侧链装饰策略
  - Coscientist (Nature): 基于实验结果的迭代反思
  - Autonomous Agents 综述: RAG规划+模板预定义策略
"""
import os
import re
from typing import Optional

from rdkit import Chem, rdBase
from rdkit.Chem import AllChem, Descriptors, QED
from rdkit.DataStructs import TanimotoSimilarity
from rdkit import DataStructs
from rdkit.Chem import rdMolDescriptors

from evaluator import evaluate_molecule, passes_filters
from generator import SCAFFOLDS, random_mutate_smiles

rdBase.DisableLog('rdApp.error')
rdBase.DisableLog('rdApp.warning')


# ============================================================
# 药效团知识库：基于药物化学常识的活性骨架模式
# ============================================================

# 常见药物药效团模式（SMARTS）
PHARMACOPHORE_PATTERNS = {
    "h_bond_donor": "[N;!H0]",          # 氢键供体（胺类）
    "h_bond_acceptor": "[O;!H0]",       # 氢键受体（羟基/羰基）
    "aromatic_ring": "c1ccccc1",         # 芳香环（π-π堆积）
    "hetero_aromatic": "c1ccncc1",       # 杂芳环（吡啶类）
    "sulfonamide": "S(=O)(=O)N",         # 磺酰胺（常见药效团）
    "amide": "C(=O)N",                   # 酰胺键
    "amine": "[NX3;H1,H2]",             # 胺基
    "fluorine": "F",                      # 氟取代（代谢稳定性）
    "chlorine": "Cl",                     # 氯取代
    "hydroxyl": "[OH]",                   # 羟基
    "methoxy": "COc",                     # 甲氧基
    "piperidine": "C1CCNCC1",             # 哌啶（碱性胺）
    "morpholine": "C1COCCN1",             # 吗啉（水溶性）
    "piperazine": "C1CNCCN1",             # 哌嗪（碱性双胺）
    "indole": "c1ccc2c(c1)[nH]cc2",       # 吲哚
    "quinazoline": "c1ccc2ncncc2c1",      # 喹唑啉（激酶抑制剂常见）
    "benzimidazole": "c1ccc2[nH]cnc2c1", # 苯并咪唑
}

# 基于竞赛靶点（CNS相关）的高概率活性骨架
# CNS药物特征：MW<450, LogP<5, HBD≤3, TPSA<90
CNS_FAVORABLE_SCAFFOLDS = [
    # 吲哚类（5-HT受体常见）
    "c1ccc2c(c1)CCN2",         # 四氢吲哚
    "c1ccc2c(c1)[nH]c2",       # 吲哚
    "c1ccc2c(c1)c[nH]2",       # 吲唑
    # 含氮稠环（激酶/GPCR）
    "c1ccc2ncncc2c1",           # 喹唑啉
    "c1ccc2c(c1)ncn2",          # 苯并咪唑
    "c1ccc2c(c1)nccn2",         # 喹唑啉变体
    "c1ncc2ccccc2n1",           # 喹唑啉
    # 哌啶/吗啉类（CNS渗透性好）
    "c1ccc(cc1)N2CCOCC2",       # 苯基吗啉
    "c1ccc(cc1)N2CCCCC2",       # 苯基哌啶
    "c1ccc(cc1)N2CCNCC2",       # 苯基哌嗪
    # 磺酰胺类（经典药效团）
    "c1ccc(cc1)S(=O)(=O)N",     # 苯磺酰胺
    "c1ccc(cc1)S(=O)(=O)NC",    # N-甲基苯磺酰胺
    # 酰胺类
    "c1ccc(cc1)C(=O)N2CCCC2",   # 苯甲酰吡咯烷
    "c1ccc(cc1)NC(=O)C",        # 乙酰苯胺
    # 氟代芳烃（代谢稳定性）
    "c1ccc(cc1F)N",             # 氟苯胺
    "c1ccc(cc1F)O",             # 氟苯酚
    # 杂环组合
    "c1ccncc1C(=O)N",           # 烟酰胺
    "c1ccc2c(c1)NCC2",          # 二氢吲哚
    "c1ccc(cc1)C(=O)Nc2ccncc2", # 苯甲酰氨基吡啶
]


def extract_seeds_from_summary(summary_path: str = None) -> list[str]:
    """从 papers/summary.md 中提取可能的活性骨架信息。

    解析摘要中的 SMILES 字符串和化学结构描述，
    转化为可用于分子生成的种子 SMILES。

    Args:
        summary_path: papers/summary.md 的路径

    Returns:
        list[str]: 提取到的种子 SMILES 列表
    """
    if summary_path is None:
        summary_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "papers", "summary.md"
        )

    seeds = []

    if not os.path.exists(summary_path):
        return CNS_FAVORABLE_SCAFFOLDS  # 回退到预定义骨架

    try:
        with open(summary_path, "r", encoding="utf-8") as f:
            content = f.read()
    except Exception:
        return CNS_FAVORABLE_SCAFFOLDS

    # 尝试从文本中提取 SMILES（简单启发式）
    # 匹配看起来像 SMILES 的模式
    smiles_pattern = re.compile(
        r'(?:SMILES|smiles|骨架|scaffold|结构|structure|活性分子|active molecule)[：:=]\s*([^\s,，。.；;]+)',
        re.IGNORECASE
    )
    for match in smiles_pattern.finditer(content):
        candidate = match.group(1).strip()
        mol = Chem.MolFromSmiles(candidate)
        if mol is not None:
            canonical = Chem.MolToSmiles(mol, canonical=True)
            props = evaluate_molecule(canonical)
            if passes_filters(props, max_sa=6.0):
                seeds.append(canonical)

    # 提取文本中直接出现的可能是 SMILES 的字符串
    # SMILES 通常包含 C, c, N, O, S, [, ], (, ), =, # 等字符
    potential_smiles = re.findall(r'\b[cCnNoOsS]\S{5,80}\b', content)
    for candidate in potential_smiles:
        # 过滤明显不是 SMILES 的（包含空格、中文等）
        if any(ord(c) > 127 for c in candidate):
            continue
        if candidate in ('class', 'code', 'config', 'common'):
            continue
        try:
            mol = Chem.MolFromSmiles(candidate)
            if mol is not None:
                canonical = Chem.MolToSmiles(mol, canonical=True)
                if canonical not in seeds:
                    props = evaluate_molecule(canonical)
                    if passes_filters(props, max_sa=6.0):
                        seeds.append(canonical)
        except Exception:
            continue

    return seeds


def generate_literature_seeds(
    n_seeds: int = 20,
    summary_path: str = None,
    strategy: str = "diverse",
) -> list[dict]:
    """基于文献知识生成种子分子（RAG冷启动）。

    策略：
      - "diverse": 从CNS骨架+文献骨架中多样性采样
      - "focused": 围绕特定药效团密集采样
      - "cns": 专注CNS渗透性好的骨架

    Args:
        n_seeds: 目标种子数量
        summary_path: papers/summary.md 路径
        strategy: 生成策略

    Returns:
        list[dict]: 种子分子列表，包含 SMILES 和性质评估
    """
    # 合并文献提取骨架 + CNS骨架 + 默认骨架
    all_seeds = []

    # 1. 文献提取
    literature_seeds = extract_seeds_from_summary(summary_path)
    all_seeds.extend(literature_seeds)

    # 2. CNS 骨架
    for scaffold in CNS_FAVORABLE_SCAFFOLDS:
        if scaffold not in all_seeds:
            all_seeds.append(scaffold)

    # 3. 默认骨架（补充多样性）
    for scaffold in SCAFFOLDS:
        if scaffold not in all_seeds:
            all_seeds.append(scaffold)

    # 去重
    unique_seeds = list(dict.fromkeys(all_seeds))

    # 验证 + 评估
    validated = []
    for smiles in unique_seeds:
        mol = Chem.MolFromSmiles(smiles)
        if mol is None:
            continue
        canonical = Chem.MolToSmiles(mol, canonical=True)
        props = evaluate_molecule(canonical)
        if props.get("valid"):
            # 放宽过滤：种子只需要基本的合理性
            validated.append({**props, "source": "literature_seed"})

    # 根据策略排序和采样
    if strategy == "cns":
        # CNS策略：按 TPSA（越低CNS渗透越好）和 QED 排序
        validated.sort(key=lambda x: (x.get("tpsa", 999), -x.get("qed", 0)))
    elif strategy == "focused":
        # 聚焦策略：按药效团匹配度排序（磺酰胺/酰胺优先）
        def pharmacophore_score(m):
            smiles = m.get("smiles", "")
            mol = Chem.MolFromSmiles(smiles)
            if mol is None:
                return 0
            score = 0
            for name, pattern in PHARMACOPHORE_PATTERNS.items():
                patt = Chem.MolFromSmarts(pattern)
                if patt and mol.HasSubstructMatch(patt):
                    score += 1
            return score
        validated.sort(key=lambda x: -pharmacophore_score(x))
    else:
        # 多样性策略：按 QED 降序
        validated.sort(key=lambda x: -x.get("qed", 0))

    # 取前 n_seeds 个
    result = validated[:n_seeds]

    # 如果种子不够，用变异扩展
    if len(result) < n_seeds:
        extra_needed = n_seeds - len(result)
        existing_smiles = {m["smiles"] for m in result}
        for seed_info in list(result):
            if extra_needed <= 0:
                break
            seed_smiles = seed_info.get("smiles", "")
            if not seed_smiles:
                continue
            for _ in range(5):  # 每个种子尝试5次变异
                if extra_needed <= 0:
                    break
                new_smiles = random_mutate_smiles(seed_smiles, random.randint(1, 2))
                if new_smiles and new_smiles not in existing_smiles:
                    props = evaluate_molecule(new_smiles)
                    if passes_filters(props, max_sa=6.0):
                        result.append({**props, "source": "mutated_seed"})
                        existing_smiles.add(new_smiles)
                        extra_needed -= 1

    return result
