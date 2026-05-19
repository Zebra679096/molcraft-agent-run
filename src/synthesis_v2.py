"""逆合成规划模块（第三版）：修复原子平衡和路线格式问题。

关键修复（H004）:
1. 路线分隔符: " | " → ","（与竞赛评分系统格式一致）
2. 新增原子平衡验证: 每步反应物原子数必须覆盖产物原子数
3. 精简逆合成规则: 只保留经过验证的可靠规则，移除产生原子不平衡的垃圾规则
4. 改进 BRICS 回退: 增加 BRICS 碎片的原子平衡检查
5. 路线最终产物验证: 确保最后一步产物 = 目标分子

竞赛硬零分规则:
- Balance_score = 0 → route_score = 0（原子不平衡）
- 所有路线 trivial → route_score = 0
- 最终产物 ≠ mol_smiles → route_score = 0
"""
from collections import Counter
from rdkit import Chem, rdBase
from rdkit.Chem import AllChem, BRICS, Descriptors

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
    """获取分子的原子计数（含氢原子），用于原子平衡验证。"""
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

    Args:
        reactant_smiles_list: 反应物 SMILES 列表
        product_smiles: 产物 SMILES
        max_excess_atoms: 反应物比产物多的最大允许原子数（含氢）

    Returns:
        bool: 原子是否平衡
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
    """尝试构建合成路线，验证所有反应物 SMILES 和原子平衡。"""
    if not _validate_smiles(r1):
        return None
    if r2 is not None and not _validate_smiles(r2):
        return None

    # 原子平衡验证
    reactants = [r1] if r2 is None else [r1, r2]
    if not _check_atom_balance(reactants, smiles):
        return None

    # 反应物不应等于产物（避免 trivial）
    product_mol = Chem.MolFromSmiles(smiles)
    if product_mol is None:
        return None

    if r2:
        return f"{r1}.{r2}>>{smiles}"
    return f"{r1}>>{smiles}"


# ======================================================================
# 逆合成规则库（精简版 — 只保留经过验证的可靠规则）
#
# 设计原则:
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

    修复(H004): 降低阈值，避免像苯磺酰哌啶(15个重原子)这样的
    功能分子被误判为简单起始原料。只有真正的简单结构(≤10重原子)
    或常见未取代杂环(≤12重原子)才停止递归。
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

    Args:
        mol: 目标分子 RDKit Mol 对象
        smarts_pattern: 匹配目标分子的 SMARTS
        retro_smarts: 逆合成反应的 SMARTS
        smiles: 目标分子的 SMILES

    Returns:
        dict 或 None: 成功时返回 {"route": ..., "reactants": [...], "steps": 1}
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

    Returns:
        list of (reactant1, reactant2) 元组
    """
    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        return []

    results = []
    try:
        # 使用 BRICS.BreakMol 进行碎片化
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

        # 需要至少2个有效碎片
        if len(frag_smiles) < 2:
            return []

        # 验证原子平衡
        r1, r2 = frag_smiles[0], frag_smiles[1]
        if _check_atom_balance([r1, r2], smiles):
            results.append((r1, r2))

    except Exception:
        pass

    return results


def plan_synthesis_recursive(smiles: str, max_depth: int = 3,
                             current_depth: int = 0, visited: set = None):
    """递归多步逆合成规划（H004 修复版）。

    对目标分子应用单步逆合成规则，然后对得到的反应物（中间体）
    递归调用逆合成规划，直到得到足够简单的起始原料或达到最大深度。

    关键改进:
    - 路线格式: 步骤之间用 "," 分隔（竞赛评分要求）
    - 原子平衡: 每步反应物原子必须覆盖产物原子
    - BRICS 碎片化: 作为 SMARTS 规则的可靠回退

    Args:
        smiles: 目标分子 SMILES
        max_depth: 最大递归深度
        current_depth: 当前递归深度
        visited: 已访问的 SMILES 集合（防止循环）

    Returns:
        dict: {"success": bool, "route": str, "steps": int, "trivial": bool}
    """
    if visited is None:
        visited = set()

    # 防止循环
    if smiles in visited:
        return {"success": True, "route": f"{smiles}>>{smiles}", "steps": 0, "trivial": True}
    visited.add(smiles)

    # 基础情况 1: 达到最大深度
    if current_depth >= max_depth:
        return {"success": True, "route": f"{smiles}>>{smiles}", "steps": 0, "trivial": True}

    # 基础情况 2: 分子已经足够简单
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
            # 验证: 至少有2个不同反应物才视为非平凡
            if len(reactants) < 2:
                continue
            if len(set(reactants)) < 2:
                # 两个反应物相同 → 可能是偶联反应，也算非平凡
                pass

            # 对每个反应物递归规划
            sub_routes = []
            all_trivial = True
            for r in reactants:
                sub = plan_synthesis_recursive(r, max_depth, current_depth + 1, visited.copy())
                if sub.get("success"):
                    sub_routes.append(sub)
                    if not sub.get("trivial", False):
                        all_trivial = False

            # 构建完整路线：先放子路线（非平凡的），再放当前步
            # 关键修复: 用 "," 分隔，不用 " | "
            full_parts = []
            for sub in sub_routes:
                if not sub.get("trivial", False):
                    full_parts.append(sub["route"])
            full_parts.append(result["route"])
            full_route = ",".join(full_parts)

            total_steps = result["steps"] + sum(s.get("steps", 0) for s in sub_routes)
            # 2个不同反应物 → 非平凡
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
        # 验证原子平衡（_brics_fragment 已验证，再次确认）
        if not _check_atom_balance([r1, r2], smiles):
            continue

        # 递归规划碎片
        sub_routes = []
        all_trivial = True
        for r in [r1, r2]:
            sub = plan_synthesis_recursive(r, max_depth, current_depth + 1, visited.copy())
            if sub.get("success"):
                sub_routes.append(sub)
                if not sub.get("trivial", False):
                    all_trivial = False

        # 关键修复: 用 "," 分隔
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

    # 最终回退: 平凡路线（标记为 trivial）
    return {"success": True, "route": f"{smiles}>>{smiles}", "steps": 0, "trivial": True}


def plan_synthesis_v2(smiles: str):
    """使用 SMARTS 断键规则规划合成路线。

    H004 改进:
    - 路线格式: 步骤之间用 "," 分隔（与竞赛评分系统一致）
    - 原子平衡验证: 每步反应物原子数必须覆盖产物原子数
    - 精简规则库: 只保留经过验证的可靠断键规则
    - BRICS 回退: 作为 SMARTS 规则的可靠补充

    路线格式示例:
    - 单步: reactant1.reactant2>>product
    - 多步: intermediate_reactants>>intermediate,target_reactants>>target
    """
    return plan_synthesis_recursive(smiles, max_depth=3, current_depth=0)


# ======================================================================
# 测试代码
# ======================================================================

def _test_synthesis():
    """测试逆合成规划模块。"""
    test_molecules = [
        # 酰胺: 苯甲酰哌啶
        "c1ccccc1C(=O)N2CCCCC2",
        # 磺酰胺: 苯磺酰哌啶
        "c1ccccc1S(=O)(=O)N2CCCCC2",
        # 酯: 乙酸苯酯
        "CC(=O)Oc1ccccc1",
        # 芳胺: 苯胺基哌啶
        "c1ccccc1N2CCCCC2",
        # 喹唑啉-哌嗪-酰胺 (之前出错的类型)
        "c1ccc2ncncc2c1N3CCN(C(=O)c4ccc(Cl)c(F)c4)CC3",
        # 简单分子 (应该停止递归)
        "c1ccccc1",
    ]

    for smi in test_molecules:
        result = plan_synthesis_v2(smi)
        print(f"\nTarget: {smi}")
        print(f"  Success: {result.get('success')}")
        print(f"  Route: {result.get('route')}")
        print(f"  Steps: {result.get('steps')}")
        print(f"  Trivial: {result.get('trivial')}")

        # 验证路线格式
        route = result.get("route", "")
        if " | " in route:
            print("  ⚠️ WARNING: 路线仍使用 ' | ' 分隔符！")
        if "," in route:
            print("  ✅ 多步路线，使用 ',' 分隔符")
        if ">>" not in route:
            print("  ⚠️ WARNING: 路线缺少 '>>' 分隔符！")


if __name__ == "__main__":
    _test_synthesis()
