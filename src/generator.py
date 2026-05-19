"""增强分子生成模块：使用 RDKit 进行高级变异的分子生成。

改进点（H002）:
- 扩展变异操作类型（环化、开环、片段交换）
- 增加进化代数和种群大小
- 优化对接引导生成
- 文献依据:
  - MOOSE-Chem (Yang et al., 2025): 进化算法导航组合空间
  - Coscientist (Boiko et al., 2023): 基于实验结果的迭代反思
  - 综述第4.2节: Post-Execution Feedback 策略
"""
import random
from rdkit import Chem, rdBase
from rdkit.Chem import AllChem, Descriptors, QED, BRICS
from rdkit.DataStructs import TanimotoSimilarity
from evaluator import evaluate_molecule, passes_filters

# 压制 RDKit 错误输出
rdBase.DisableLog('rdApp.error')
rdBase.DisableLog('rdApp.warning')


# 药物样骨架和片段库（H007: 扩充至55个，覆盖更多含氮稠环和饱和杂环）
# 文献依据:
#   - MOOSE-Chem (Yang et al., 2025): "Diverse initial population is essential
#     for evolutionary search to avoid premature convergence"
#   - ChemCrow (Bran et al., 2024): 工具/库的丰富度直接决定 Agent 探索的化学空间边界
#   - 综述第3.2节: Scaffold hopping 是药物发现的核心策略之一
SCAFFOLDS = [
    # ===== 单环芳烃（6个）=====
    "c1ccc(cc1)",           # 苯环
    "c1ccccc1C",            # 甲苯
    "c1ccc(cc1)O",          # 苯酚
    "c1ccc(cc1)N",          # 苯胺
    "COc1ccc(cc1)",         # 苯甲醚
    "c1ccc(cc1)CN",         # 苄胺

    # ===== 多环芳烃（2个）=====
    "c1ccc2ccccc2c1",       # 萘
    "c1ccc2c(c1)cccc2",     # 萘变体

    # ===== 含氮单杂环（4个）=====
    "c1ccc(nc1)",           # 吡啶
    "c1cncnc1",             # 嘧啶
    "c1cnccc1",             # 吡啶变体
    "c1c[nH]cn1",           # 咪唑

    # ===== 饱和杂环（8个）=====
    "C1CCOC1",              # 四氢呋喃
    "C1CCNC1",              # 吡咯烷
    "C1CCNCC1",             # 哌啶
    "C1CNCCN1",             # 哌嗪
    "C1COCCN1",             # 吗啉
    "C1CSCN1",              # 硫代吗啉
    "C1COC1",               # 氧杂环丁烷
    "C1CNC1",               # 氮杂环丁烷

    # ===== 含氮稠环（12个）=====
    "c1ccc2c(c1)Ncnc2",     # 喹唑啉
    "c1ccc2c(c1)ncn2",      # 苯并咪唑
    "c1ccc2c(c1)cccn2",     # 吲哚
    "c1ccc2c(c1)ocn2",      # 苯并噁唑
    "c1ccc2c(c1)scn2",      # 苯并噻唑
    "c1ccc2ncccc2c1",       # 喹啉
    "c1ccc2ccncc2c1",       # 异喹啉
    "c1ccc2c(c1)[nH]c2",    # 吲哚啉（二氢吲哚）
    "c1ccc2c(c1)CCN2",      # 二氢吲哚（含N）
    "c1ccc2c(c1)CCNC2",     # 四氢异喹啉
    "c1ccc2c(c1)N=CN2",     # 苯并咪唑啉
    "c1nc2c([nH]1)cccc2",   # 苯并咪唑变体

    # ===== 药物常见骨架（6个）=====
    "c1ncnc2c1ncn2",        # 嘌呤
    "c1cnc2ncncc2n1",       # 蝶啶
    "c1ccc2c(c1)cncn2",     # 喹唑啉变体
    "c1ccc2c(c1)ncnc2",     # 喹唑啉（另一表示）
    "c1ccc2c(c1)OCCO2",     # 苯并二噁烷
    "c1ccc2c(c1)CCO2",      # 苯并呋喃烷

    # ===== 酰胺/磺酰胺类（6个）=====
    "c1ccc(cc1)C(=O)O",     # 苯甲酸
    "c1ccc(cc1)C(=O)N",     # 苯甲酰胺
    "c1ccc(cc1)S(=O)(=O)N", # 磺酰胺
    "c1ccc(cc1)C(=O)Nc2ccccc2",  # 二苯甲酮酰胺
    "c1ccc(cc1)NC(=O)c2ccccc2",  # N-苯基苯甲酰胺
    "Cc1ccc(cc1)S(=O)(=O)Nc2ccccc2",  # 对甲苯磺酰苯胺

    # ===== 卤代/其他（5个）=====
    "c1cc(ccc1F)F",         # 二氟苯
    "c1cc(ccc1Cl)Cl",       # 二氯苯
    "c1ccc(cc1)CC(=O)O",    # 苯乙酸
    "c1ccc(cc1)C(=O)c2ccccc2",  # 二苯甲酮
    "c1ccc(cc1)OCc2ccccc2",     # 二苯甲醚

    # ===== 饱和环-芳环稠合（6个）=====
    "c1ccc2c(c1)CCCC2",     # 四氢萘
    "c1ccc2c(c1)CCCCC2",    # 十氢萘骨架
    "c1ccc2c(c1)NCCC2",     # 四氢喹啉
    "c1ccc2c(c1)OCC2",      # 2,3-二氢苯并呋喃
    "c1ccc2c(c1)SCC2",      # 2,3-二氢苯并噻吩
    "c1ccc2c(c1)CCO2",      # 苯并二氢吡喃
]

LINKERS = [
    "",                     # 直接连接
    "C",                    # 亚甲基
    "CC",                   # 亚乙基
    "O",                    # 醚键
    "NH",                   # 胺键
    "C(=O)",               # 羰基
    "C(=O)N",              # 酰胺
    "C(=O)O",              # 酯键
    "S(=O)(=O)",           # 砜
    "S(=O)(=O)N",          # 磺酰胺
    "NHC(=O)",             # 反向酰胺
    "OC(=O)",              # 反向酯键
    "C#C",                 # 炔键
    "C=C",                 # 烯键
]


def random_mutate_smiles(smiles: str, n_mutations: int = 1):
    """对 SMILES 字符串应用随机变异。"""
    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        return None

    for _ in range(n_mutations):
        mol = _mutate_mol(mol)
        if mol is None:
            return None

    new_smiles = Chem.MolToSmiles(mol, canonical=True)
    return new_smiles


def _mutate_mol(mol):
    """增强的单次变异：添加/替换/删除/环化/开环等操作。"""
    choice = random.random()
    try:
        if choice < 0.25:
            mol = _add_substituent(mol)
        elif choice < 0.5:
            mol = _replace_atom(mol)
        elif choice < 0.65:
            mol = _remove_terminal(mol)
        elif choice < 0.75:
            mol = _insert_linker(mol)
        elif choice < 0.85:
            mol = _ring_formation(mol)
        elif choice < 0.95:
            mol = _ring_opening(mol)
        else:
            mol = _fragment_exchange(mol)
    except Exception:
        return None
    if mol is None:
        return None
    # 返回前验证分子有效性
    try:
        Chem.SanitizeMol(mol)
        # 测试 SMILES 往返
        s = Chem.MolToSmiles(mol, canonical=True)
        m2 = Chem.MolFromSmiles(s)
        if m2 is None:
            return None
    except Exception:
        return None
    return mol


def _add_substituent(mol):
    """在随机碳原子上添加小取代基（F, Cl, OH, NH2, CH3）。"""
    substituents = ["F", "Cl", "[OH]", "[NH2]", "C"]
    subst = random.choice(substituents)
    subst_mol = Chem.MolFromSmiles(subst)
    if subst_mol is None:
        return mol

    # 查找候选原子（非氢、非末端碳原子）
    atoms = [a for a in mol.GetAtoms() if a.GetAtomicNum() == 6 and a.GetDegree() < 4]
    if not atoms:
        return mol
    atom = random.choice(atoms)

    # 将取代基连接到分子上
    combo = Chem.CombineMols(mol, subst_mol)
    emol = Chem.EditableMol(combo)
    new_bond_idx = combo.GetNumAtoms() - 1
    emol.AddBond(atom.GetIdx(), new_bond_idx, Chem.BondType.SINGLE)
    new_mol = emol.GetMol()
    Chem.SanitizeMol(new_mol)
    return new_mol


def _replace_atom(mol):
    """随机替换一个杂原子或碳原子为另一种原子。"""
    replacements = {6: [7, 8, 9, 16], 7: [6, 8], 8: [6, 7, 16], 16: [6, 8]}
    atoms = [a for a in mol.GetAtoms() if a.GetAtomicNum() in replacements]
    if not atoms:
        return mol
    atom = random.choice(atoms)
    new_atom_num = random.choice(replacements[atom.GetAtomicNum()])
    atom.SetAtomicNum(new_atom_num)
    Chem.SanitizeMol(mol)
    return mol


def _remove_terminal(mol):
    """删除一个末端原子。"""
    terminals = [a for a in mol.GetAtoms() if a.GetDegree() == 1 and not a.IsInRing()]
    if not terminals:
        return mol
    atom = random.choice(terminals)
    emol = Chem.EditableMol(mol)
    emol.RemoveAtom(atom.GetIdx())
    new_mol = emol.GetMol()
    Chem.SanitizeMol(new_mol)
    return new_mol


def _insert_linker(mol):
    """在两个片段之间插入一个小连接子。"""
    linkers = ["C", "O", "N"]
    linker = random.choice(linkers)
    linker_mol = Chem.MolFromSmiles(linker)
    if linker_mol is None:
        return mol

    combo = Chem.CombineMols(mol, linker_mol)
    emol = Chem.EditableMol(combo)
    atoms = list(mol.GetAtoms())
    if len(atoms) < 2:
        return mol
    a1, a2 = random.sample(atoms, 2)
    linker_idx = combo.GetNumAtoms() - 1
    emol.AddBond(a1.GetIdx(), linker_idx, Chem.BondType.SINGLE)
    emol.AddBond(a2.GetIdx(), linker_idx, Chem.BondType.SINGLE)
    new_mol = emol.GetMol()
    try:
        Chem.SanitizeMol(new_mol)
    except Exception:
        return mol
    return new_mol


def _ring_formation(mol):
    """环化反应：在两个原子之间形成环。"""
    # 查找可以形成环的原子对
    atoms = [a for a in mol.GetAtoms() if a.GetAtomicNum() == 6 and a.GetDegree() < 4]
    if len(atoms) < 2:
        return mol
    
    # 尝试形成3-6元环
    for ring_size in [3, 4, 5, 6]:
        if len(atoms) >= ring_size:
            selected_atoms = random.sample(atoms, ring_size)
            try:
                emol = Chem.EditableMol(mol)
                # 连接第一个和最后一个原子
                emol.AddBond(selected_atoms[0].GetIdx(), selected_atoms[-1].GetIdx(), Chem.BondType.SINGLE)
                new_mol = emol.GetMol()
                Chem.SanitizeMol(new_mol)
                return new_mol
            except Exception:
                continue
    return mol


def _ring_opening(mol):
    """开环反应：打开一个小环。"""
    # 查找小环（3-6元环）
    rings = mol.GetRingInfo()
    ring_atoms = []
    for i in range(rings.NumRings()):
        ring = rings.GetRingAtoms(i)
        if 3 <= len(ring) <= 6:
            ring_atoms.extend(ring)
    
    if not ring_atoms:
        return mol
    
    # 随机选择一个环中的一个原子进行开环
    atom_idx = random.choice(ring_atoms)
    emol = Chem.EditableMol(mol)
    
    # 找到与该原子相连的环键并删除
    atom = mol.GetAtomWithIdx(atom_idx)
    for bond in atom.GetBonds():
        neighbor = bond.GetOtherAtom(atom)
        if neighbor.GetIdx() in ring_atoms:
            # 检查是否是环键
            if bond.IsInRing():
                emol.RemoveBond(atom.GetIdx(), neighbor.GetIdx())
                break
    
    new_mol = emol.GetMol()
    try:
        Chem.SanitizeMol(new_mol)
        return new_mol
    except Exception:
        return mol


def _fragment_exchange(mol):
    """片段交换：用一个小片段替换分子的一部分。"""
    # 从骨架库中随机选择一个小片段
    small_scaffolds = ["C", "O", "N", "c1ccccc1", "C1CCOC1"]
    fragment = random.choice(small_scaffolds)
    fragment_mol = Chem.MolFromSmiles(fragment)
    if fragment_mol is None:
        return mol
    
    # 在分子中随机选择一个键进行替换
    bonds = [mol.GetBondWithIdx(i) for i in range(mol.GetNumBonds())]
    if not bonds:
        return mol
    
    bond = random.choice(bonds)
    atom1 = bond.GetBeginAtom()
    atom2 = bond.GetEndAtom()
    
    # 删除这个键
    emol = Chem.EditableMol(mol)
    emol.RemoveBond(atom1.GetIdx(), atom2.GetIdx())
    
    # 添加片段
    combo = Chem.CombineMols(emol.GetMol(), fragment_mol)
    new_emol = Chem.EditableMol(combo)
    
    # 连接片段到原来的两个原子
    fragment_idx = combo.GetNumAtoms() - fragment_mol.GetNumAtoms()
    new_emol.AddBond(atom1.GetIdx(), fragment_idx, Chem.BondType.SINGLE)
    new_emol.AddBond(atom2.GetIdx(), fragment_idx + 1, Chem.BondType.SINGLE)
    
    new_mol = new_emol.GetMol()
    try:
        Chem.SanitizeMol(new_mol)
        return new_mol
    except Exception:
        return mol


def generate_molecules(strategy="mutate", n_molecules=50, scaffold=None, n_generations=3, n_offspring=3):
    """生成候选药物分子。

    策略:
        - "mutate": 从种子骨架变异（增强版）
        - "combine": 用连接子组合骨架
        - "random": 随机 SMILES 生成（非常基础）
    
    新增参数:
        - n_generations: 进化代数（默认3，原来为2）
        - n_offspring: 每个种子的后代数量（默认3）
    """
    molecules = set()
    attempts = 0
    max_attempts = n_molecules * 20

    if strategy == "mutate":
        seeds = SCAFFOLDS if scaffold is None else [scaffold]
        
        # 多代进化
        for gen in range(n_generations):
            new_molecules = set()
            while len(new_molecules) < min(n_molecules * (gen + 1), n_molecules) and attempts < max_attempts:
                attempts += 1
                seed = random.choice(seeds)
                n_mut = random.randint(1, 4)
                new_smiles = random_mutate_smiles(seed, n_mut)
                if new_smiles and new_smiles not in molecules and new_smiles not in new_molecules:
                    props = evaluate_molecule(new_smiles)
                    if passes_filters(props):
                        new_molecules.add(new_smiles)
            
            # 更新种子库，选择最好的分子
            molecules.update(new_molecules)
            if len(molecules) > n_offspring:
                # 按QED排序，选择前n_offspring个作为下一代种子
                sorted_mols = sorted(molecules, key=lambda x: evaluate_molecule(x)["qed"], reverse=True)
                seeds = sorted_mols[:n_offspring]

    elif strategy == "combine":
        while len(molecules) < n_molecules and attempts < max_attempts:
            attempts += 1
            n_frag = random.randint(2, 3)
            frags = random.sample(SCAFFOLDS, n_frag)
            linkers = random.sample(LINKERS, n_frag - 1)

            # 用连接子将片段拼接成 SMILES
            parts = []
            for i, frag in enumerate(frags):
                parts.append(frag)
                if i < len(linkers):
                    parts.append(linkers[i])
            combined = "".join(parts)

            mol = Chem.MolFromSmiles(combined)
            if mol is not None:
                smiles = Chem.MolToSmiles(mol, canonical=True)
                if smiles not in molecules:
                    props = evaluate_molecule(smiles)
                    if passes_filters(props):
                        molecules.add(smiles)

    elif strategy == "random":
        # 非常基础：随机组合片段
        while len(molecules) < n_molecules and attempts < max_attempts:
            attempts += 1
            frag = random.choice(SCAFFOLDS)
            new_smiles = random_mutate_smiles(frag, random.randint(2, 5))
            if new_smiles and new_smiles not in molecules:
                props = evaluate_molecule(new_smiles)
                if passes_filters(props):
                    molecules.add(new_smiles)

    result = [evaluate_molecule(s) for s in molecules]
    result.sort(key=lambda x: x["qed"], reverse=True)
    return result


def generate_with_docking_guidance(
    docking_fn,
    n_molecules=50,
    batch_size=10,
    n_generations=4,  # 增加到4代
    top_k=5,
    strategy="mutate",
    scaffold=None,
):
    """增强的对接引导分子生成（H002）。

    核心思想：将分子对接作为适应度函数，嵌入生成循环中。
    每批生成少量分子 → 对接评估 → 选择结合能最优的作为种子 → 变异产生下一代。
    这避免了盲生成大量低质量分子，显著提升计算效率。

    Args:
        docking_fn: 对接函数，接收 SMILES 字符串，返回 dict 包含 "binding_energy"
        n_molecules: 目标生成分子总数
        batch_size: 每批生成的候选分子数
        n_generations: 进化代数（增加到4）
        top_k: 每代选择 top_k 作为种子
        strategy: 初始生成策略
        scaffold: 可选种子骨架

    Returns:
        list[dict]: 通过过滤且对接成功的分子信息列表，按结合能排序
    """
    import sys

    all_evaluated = []  # 所有经过对接评估的分子
    current_seeds = None

    for gen in range(n_generations):
        batch_mols = []
        attempts = 0
        max_attempts = batch_size * 30

        if gen == 0:
            # 初始代：用传统策略生成
            seeds = SCAFFOLDS if scaffold is None else [scaffold]
            while len(batch_mols) < batch_size and attempts < max_attempts:
                attempts += 1
                seed = random.choice(seeds)
                n_mut = random.randint(1, 4)
                new_smiles = random_mutate_smiles(seed, n_mut)
                if new_smiles and new_smiles not in {m["smiles"] for m in batch_mols}:
                    props = evaluate_molecule(new_smiles)
                    if passes_filters(props):
                        batch_mols.append(props)
        else:
            # 后续代：从种子变异（使用增强的变异）
            seed_smiles_list = [s["smiles"] for s in current_seeds]
            while len(batch_mols) < batch_size and attempts < max_attempts:
                attempts += 1
                seed_smiles = random.choice(seed_smiles_list)
                n_mut = random.randint(1, 3)  # 后续代变异强度略低，保持稳定性
                new_smiles = random_mutate_smiles(seed_smiles, n_mut)
                if new_smiles and new_smiles not in {m["smiles"] for m in batch_mols}:
                    props = evaluate_molecule(new_smiles)
                    if passes_filters(props):
                        batch_mols.append(props)

        # 对接评估
        docked_batch = []
        for mol_info in batch_mols:
            smiles = mol_info["smiles"]
            try:
                dock_result = docking_fn(smiles)
                if dock_result.get("success"):
                    mol_info["binding_energy"] = dock_result.get("binding_energy")
                    mol_info["docking_success"] = True
                    docked_batch.append(mol_info)
            except Exception:
                continue

        # 按结合能排序（越低越好）
        docked_batch.sort(key=lambda x: x.get("binding_energy", 999))

        # 累积到全局池
        all_evaluated.extend(docked_batch)

        # 选择种子
        n_seeds = min(top_k, len(docked_batch))
        current_seeds = docked_batch[:n_seeds]

        print(
            f"[H002] Gen {gen+1}/{n_generations}: generated {len(batch_mols)}, "
            f"docked {len(docked_batch)}, best {docked_batch[0]['binding_energy'] if docked_batch else 'N/A'}",
            file=sys.stderr,
        )

    # 全局去重 + 排序
    seen = set()
    unique = []
    for m in all_evaluated:
        smi = m["smiles"]
        if smi not in seen:
            seen.add(smi)
            unique.append(m)

    unique.sort(key=lambda x: x.get("binding_energy", 999))
    return unique[:n_molecules]