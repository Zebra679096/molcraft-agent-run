"""逆合成规划模块（v3）：修复原子平衡和路线格式问题。

关键修复（H004, 决策引用: D003, D004）:
1. 路线分隔符: " | " → ","（与竞赛评分系统格式一致）
2. 新增原子平衡验证: 每步反应物原子数必须覆盖产物原子数
3. 精简逆合成规则: 只保留经过验证的可靠规则，移除产生原子不平衡的垃圾规则
4. 改进 BRICS 回退: 增加 BRICS 碎片的原子平衡检查
5. _is_simple_molecule 降低阈值: 避免功能分子被误判为简单起始原料

竞赛硬零分规则:
- Balance_score = 0 → route_score = 0（原子不平衡）
- 所有路线 trivial → route_score = 0
- 最终产物 ≠ mol_smiles → route_score = 0
"""
from collections import Counter
from rdkit import Chem, rdBase
from rdkit.Chem import AllChem, BRICS

rdBase.DisableLog('rdApp.error')
rdBase.DisableLog('rdApp.warning')


# ======================================================================
# 工具函数
# ======================================================================

def _validate_smiles(smiles: str) -> bool:
    """验证 SMILES 字符串是否有效且可解析。"""
    if not smiles or len(smiles) < 1:
        return False
    if smiles in ('[H]', '[H][H]', 'H', '[Br]', '[Cl]', '[I]', '[F]'):
        return False
    mol = Chem.MolFromSmiles(smiles)
    return mol is not None


def _get_atom_counts(smiles: str) -> Counter | None:
    """获取分子的原子计数（含氢原子），用于原子平衡验证。

    输入: SMILES 字符串
    输出: Counter 对象（元素符号→原子数），无效SMILES返回None
    依赖: rdkit.Chem
    决策引用: D004 — 原子不平衡是route_score=0的直接原因
    """
    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        return None
    mol_h = Chem.AddHs(mol)
    counts = Counter()
    for atom in mol_h.GetAtoms():
        counts[atom.GetSymbol()] += 1
    return counts


def _check_atom_balance(reactant_smiles_list: list, product_smiles: str,
                        max_excess_atoms: int = 8) -> bool:
    """验证反应的原子平衡：反应物原子必须覆盖产物原子。

    对于有效的合成反应:
    - 反应物中每种元素的原子数 >= 产物中对应元素的原子数
    - 反应物总原子数与产物总原子数之差应在合理范围内
      （允许 H2O、HCl 等小分子副产物的原子差）

    输入: reactant_smiles_list(反应物列表), product_smiles(产物), max_excess_atoms(最大允许多余原子数)
    输出: bool (True=平衡)
    依赖: _get_atom_counts
    决策引用: D004 — balance_score=0 → route_score=0
    """
    reactant_counts = Counter()
    for s in reactant_smiles_list:
        c = _get_atom_counts(s)
        if c is None:
            return False
        reactant_counts += c

    product_counts = _get_atom_counts(product_smiles)
    if product_counts is None:
        return False

    # 条件1: 反应物中每种元素 >= 产物中对应元素
    for element, count in product_counts.items():
        if reactant_counts.get(element, 0) < count:
            return False

    # 条件2: 总原子数差在合理范围内
    total_reactant = sum(reactant_counts.values())
    total_product = sum(product_counts.values())
    if total_reactant < total_product:
        return False
    if total_reactant > total_product + max_excess_atoms:
        return False

    return True


def _try_route(smiles: str, r1: str, r2: str = None) -> str | None:
    """尝试构建合成路线，验证所有反应物 SMILES 和原子平衡。

    输入: smiles(产物), r1(反应物1), r2(反应物2,可选)
    输出: 路线字符串 或 None
    依赖: _validate_smiles, _check_atom_balance
    决策引用: D004 — 每步都必须通过原子平衡检查
    """
    if not _validate_smiles(r1):
        return None
    if r2 is not None and not _validate_smiles(r2):
        return None

    # 原子平衡验证
    reactants = [r1] if r2 is None else [r1, r2]
    if not _check_atom_balance(reactants, smiles):
        return None

    if r2:
        return f"{r1}.{r2}>>{smiles}"
    return f"{r1}>>{smiles}"


# ======================================================================
# 逆合成规则库（精简版 — 只保留经过验证的可靠规则）
#
# 设计原则（决策引用: D004）:
#   1. 每条规则必须有正确的原子映射，保证原子平衡
#   2. 优先匹配更具体的结构（放在前面）
#   3. 反应物应为商业可得的简单分子
#   4. 所有规则在 _run_retro_rule 中额外通过原子平衡验证
# ======================================================================

RETRO_RULES = [
    # ------------------- 磺酰胺类 (最可靠的断键) -------------------
    # 芳基磺酰胺 — 磺酰氯 + 胺 → 磺酰胺 + HCl
    ("[c][S;D4](=[O])(=[O])[N]", "[c:1][S:2](=[O])(=[O])[N:3]>>[c:1][S:2](=[O])(=[O])Cl.[N:3]"),

    # ------------------- 酰胺类 (用简单可靠的 SMARTS) -------------------
    # 通用酰胺断键 — 羧酸 + 胺 → 酰胺 + H2O
    #   匹配所有 C(=O)-N 键（包括芳基-酰胺和烷基-酰胺）
    #   原子平衡验证在 _run_retro_rule 中确保只有有效断键被接受
    ("[C](=[O])[N;H0]", "[C:1](=[O])[N:2]>>[C:1](=O)O.[N:2]"),
    ("[C](=[O])[N;H1]", "[C:1](=[O])[N:2]>>[C:1](=O)O.[N:2]"),

    # ------------------- 酯类 -------------------
    # 酯 — 羧酸 + 醇 → 酯 + H2O
    ("[C](=[O])O[C;!c]", "[C:1](=[O])O[C:2]>>[C:1](=O)O.[C:2]O"),

    # ------------------- 芳基胺 (Buchwald-Hartwig) -------------------
    # 芳基仲胺 — 芳基溴 + 伯胺 → 芳胺 + HBr
    ("[c][NX3;H1]", "[c:1][N;H1:2]>>[c:1]Br.[N;H1:2]"),
    # 芳基叔胺 — 芳基溴 + 仲胺 → 芳胺 + HBr
    ("[c][NX3;H0]", "[c:1][N;H0:2]>>[c:1]Br.[N;H0:2]"),

    # ------------------- 芳基醚 (Ullmann/SNAr) -------------------
    # 芳基烷基醚 — 芳基溴 + 醇 → 芳基醚 + HBr
    ("[c]O[C;!c]", "[c:1]O[C:2]>>[c:1]Br.[C:2]O"),

    # ------------------- 脲类 -------------------
    # 脲 — 异氰酸酯 + 胺 → 脲
    ("[N]C(=O)[N]", "[N:1]C(=O)[N:2]>>[N:1]C=O.[N:2]"),

    # ------------------- 芳基磺酰胺（烷基磺酰胺） -------------------
    # 烷基磺酰胺 — 磺酰氯 + 胺 → 磺酰胺 + HCl
    ("[C][S;D4](=[O])(=[O])[N]", "[C:1][S:2](=[O])(=[O])[N:3]>>[C:1][S:2](=[O])(=[O])Cl.[N:3]"),
]


# 简单分子阈值
_SIMPLE_SCAFFOLDS_SMARTS = [
    "c1ccccc1",      # 苯
    "c1ccncc1",      # 吡啶
    "c1cccnc1",      # 吡啶变体
    "C1CCOC1",       # THF
    "C1CCCCC1",      # 环己烷
    "C1CCNC1",       # 吡咯烷
    "C1CCNCC1",      # 哌啶
    "C1COCCN1",      # 吗啉
]


def _is_simple_molecule(smiles: str) -> bool:
    """判断分子是否为足够简单的起始原料，无需继续逆合成。

    修复(H004, 决策引用: D004): 降低阈值，避免像苯磺酰哌啶(15个重原子)这样的
    功能分子被误判为简单起始原料。只有真正的简单结构(≤10重原子)
    或常见未取代杂环(≤12重原子)才停止递归。

    输入: SMILES 字符串
    输出: bool
    """
    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        return False
    n_atoms = mol.GetNumAtoms()
    # 重原子数 <= 10 视为简单起始原料
    if n_atoms <= 10:
        return True
    # 匹配常见未取代杂环骨架（允许少量取代基，但总原子数 ≤ 12）
    for s in _SIMPLE_SCAFFOLDS_SMARTS:
        patt = Chem.MolFromSmarts(s)
        if patt and mol.HasSubstructMatch(patt):
            if n_atoms <= 12:
                return True
    return False


def _run_retro_rule(mol, smarts_pattern, retro_smarts, smiles):
    """通用逆合成规则执行函数（带原子平衡验证）。

    输入: mol(RDKit Mol), smarts_pattern(匹配模式), retro_smarts(逆合成SMARTS), smiles(目标SMILES)
    输出: dict{"success", "route", "reactants", "steps"} 或 None
    依赖: _check_atom_balance, _try_route
    决策引用: D004 — 每个产物集都必须通过原子平衡验证
    """
    patt = Chem.MolFromSmarts(smarts_pattern)
    if patt is None or not mol.HasSubstructMatch(patt):
        return None
    rxn = AllChem.ReactionFromSmarts(retro_smarts)
    if rxn is None:
        return None
    ps = rxn.RunReactants((mol,))
    if not ps:
        return None

    # 遍历所有可能的产物集，找到第一个通过原子平衡验证的
    for product_set in ps:
        if not product_set:
            continue
        if len(product_set) >= 2:
            r1 = Chem.MolToSmiles(product_set[0])
            r2 = Chem.MolToSmiles(product_set[1])
            # 原子平衡验证
            if not _check_atom_balance([r1, r2], smiles):
                continue
            route = _try_route(smiles, r1, r2)
            if route:
                return {"success": True, "route": route, "reactants": [r1, r2], "steps": 1}
        else:
            r1 = Chem.MolToSmiles(product_set[0])
            # 单反应物也需要原子平衡
            if not _check_atom_balance([r1], smiles):
                continue
            route = _try_route(smiles, r1)
            if route:
                return {"success": True, "route": route, "reactants": [r1], "steps": 1}

    return None


def _brics_fragment(smiles: str) -> list:
    """使用 BRICS 碎片化生成原子平衡的逆合成步骤。

    BRICS 是 RDKit 内置的碎片化方法，基于化学合理的断键规则，
    产生的碎片天然满足原子平衡要求。

    输入: 目标分子 SMILES
    输出: list of (reactant1, reactant2) 元组
    依赖: _check_atom_balance
    """
    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        return []

    results = []
    try:
        frags = BRICS.BreakMol(mol)
        if not frags or len(frags) < 2:
            return []

        frag_smiles = []
        for f in frags:
            if f is None:
                continue
            s = Chem.MolToSmiles(f)
            if _validate_smiles(s):
                frag_smiles.append(s)

        if len(frag_smiles) < 2:
            return []

        r1, r2 = frag_smiles[0], frag_smiles[1]
        if _check_atom_balance([r1, r2], smiles):
            results.append((r1, r2))

    except Exception:
        pass

    return results


def plan_synthesis_recursive(smiles: str, max_depth: int = 3,
                             current_depth: int = 0, visited: set = None):
    """递归多步逆合成规划（H004 修复版）。

    关键改进（决策引用: D003, D004）:
    - 路线格式: 步骤之间用 "," 分隔（竞赛评分要求）
    - 原子平衡: 每步反应物原子必须覆盖产物原子
    - BRICS 碎片化: 作为 SMARTS 规则的可靠回退

    输入: smiles(目标SMILES), max_depth(最大递归深度), current_depth(当前深度), visited(防循环)
    输出: dict{"success", "route", "steps", "trivial"}
    """
    if visited is None:
        visited = set()

    if smiles in visited:
        return {"success": True, "route": f"{smiles}>>{smiles}", "steps": 0, "trivial": True}
    visited.add(smiles)

    if current_depth >= max_depth:
        return {"success": True, "route": f"{smiles}>>{smiles}", "steps": 0, "trivial": True}

    if _is_simple_molecule(smiles):
        return {"success": True, "route": f"{smiles}>>{smiles}", "steps": 0, "trivial": True}

    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        return {"success": False, "error": "无效的 SMILES"}

    # 尝试 SMARTS 逆合成规则
    for smarts_pattern, retro_smarts in RETRO_RULES:
        result = _run_retro_rule(mol, smarts_pattern, retro_smarts, smiles)
        if result:
            reactants = result.get("reactants", [])
            if len(reactants) < 2:
                continue

            sub_routes = []
            all_trivial = True
            for r in reactants:
                sub = plan_synthesis_recursive(r, max_depth, current_depth + 1, visited.copy())
                if sub.get("success"):
                    sub_routes.append(sub)
                    if not sub.get("trivial", False):
                        all_trivial = False

            # 关键修复(D003): 用 "," 分隔，不用 " | "
            full_parts = []
            for sub in sub_routes:
                if not sub.get("trivial", False):
                    full_parts.append(sub["route"])
            full_parts.append(result["route"])
            full_route = ",".join(full_parts)

            total_steps = result["steps"] + sum(s.get("steps", 0) for s in sub_routes)
            is_trivial = len(reactants) < 2 or (len(reactants) == 2 and reactants[0] == reactants[1] and all_trivial)

            return {
                "success": True,
                "route": full_route,
                "steps": total_steps,
                "trivial": is_trivial,
            }

    # 回退: 用 BRICS 碎片化
    brics_results = _brics_fragment(smiles)
    for r1, r2 in brics_results:
        route = f"{r1}.{r2}>>{smiles}"
        if not _check_atom_balance([r1, r2], smiles):
            continue

        sub_routes = []
        for r in [r1, r2]:
            sub = plan_synthesis_recursive(r, max_depth, current_depth + 1, visited.copy())
            if sub.get("success"):
                sub_routes.append(sub)

        # 关键修复(D003): 用 "," 分隔
        full_parts = []
        for sub in sub_routes:
            if not sub.get("trivial", False):
                full_parts.append(sub["route"])
        full_parts.append(route)
        full_route = ",".join(full_parts)
        total_steps = 1 + sum(s.get("steps", 0) for s in sub_routes)

        return {
            "success": True,
            "route": full_route,
            "steps": total_steps,
            "trivial": False,
        }

    return {"success": True, "route": f"{smiles}>>{smiles}", "steps": 0, "trivial": True}


def plan_synthesis_v2(smiles: str):
    """使用 SMARTS 断键规则规划合成路线。

    H004 改进（决策引用: D003, D004）:
    - 路线格式: 步骤之间用 "," 分隔（与竞赛评分系统一致）
    - 原子平衡验证: 每步反应物原子数必须覆盖产物原子数
    - 精简规则库: 只保留经过验证的可靠断键规则

    输入: 目标分子 SMILES
    输出: dict{"success", "route", "steps", "trivial"}
    """
    return plan_synthesis_recursive(smiles, max_depth=3, current_depth=0)
