"""结构引导的分子设计模块 — 基于蛋白质口袋药效团分析。

核心思想（来自竞赛群听云的洞察）:
  当前方案是"让agent自行读论文然后试各种模型抽卡"，
  等同于让猴子敲出莎士比亚全集。关键缺失是：
  1. 蛋白质空腔残基分析
  2. 分子构象分析

本模块基于口袋分析结果，生成药效团导向的分子：

口袋关键特征:
  - 净正电荷 +6.0 → 配体必须含酸性基团 (COOH/四唑)
  - ASN734 (1.83Å), ASN739 (1.90Å) → 需要H键受体/供体
  - HIS732 (3.56Å) → π-堆积 (芳香核心)
  - ARG738 (5.08Å), ARG775 (7.87Å) → 盐桥 (COO⁻-胍基)
  - VAL735, LEU757, ILE740 → 疏水相互作用
  - ASP759 (5.63Å), GLU806 (8.02Å) → 胺类正电荷相互作用

设计策略:
  1. 芳香核心 (喹唑啉/苯并咪唑/吲哚) → π-堆积HIS732
  2. 羧酸/四唑基团 → 盐桥ARG775/LYS642/HIS732
  3. H键供体/受体 → 互补ASN734/739
  4. 疏水取代基 → 填充VAL735/LEU757/ILE740口袋
  5. 碱性胺 → 互补远端ASP759/GLU806

决策引用: D007 — 结构引导设计取代盲目生成
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from rdkit import Chem, rdBase
from rdkit.Chem import Descriptors, QED
from evaluator import evaluate_molecule, passes_filters, estimate_sa_score

rdBase.DisableLog('rdApp.error')
rdBase.DisableLog('rdApp.warning')


# ======================================================================
# 药效团导向的分子模板库
#
# 设计原则（决策引用: D007）:
#   每个模板都针对口袋的特定药效团需求设计:
#   - 芳香核心 → π-堆积HIS732 (3.56Å)
#   - COOH/四唑 → 盐桥ARG738(5Å)/ARG775(8Å)/LYS642(9Å)
#   - H键供体/受体 → 互补ASN734(2Å)/ASN739(2Å)
#   - 疏水基团 → 填充VAL735/LEU757/ILE740
# ======================================================================

# 策略1: 芳香核心 + COOH (盐桥 + π-堆积)
# 这些分子同时具有芳香核心(π-堆积)和COOH(盐桥)
SCAFFOLD_ACIDIC = [
    # 喹唑啉-COOH (最强盐桥+π-堆积候选)
    "O=C(O)c1ccc2ncncc2c1",               # 喹唑啉-4-羧酸 (CAS 53000-61-0, 商业可得)
    "O=C(O)c1ccc2nc(N)nc2c1",             # 2-氨基-喹唑啉-4-羧酸
    "O=C(O)c1ccc2ncnc2c1F",               # 氟代喹唑啉-4-羧酸

    # 吲哚-COOH
    "O=C(O)c1ccc2[nH]ccc2c1",             # 吲哚-3-羧酸 (商业可得)
    "O=C(O)c1ccc2c(c1)[nH]c2",            # 吲哚-2-羧酸

    # 苯并咪唑-COOH
    "O=C(O)c1ccc2[nH]cnc2c1",             # 苯并咪唑-5-羧酸
    "O=C(O)c1ccc2nc[nH]c2c1",             # 苯并咪唑-4-羧酸

    # 吡啶-COOH
    "O=C(O)c1ccncc1",                     # 吡啶-2-羧酸 (皮考林酸)
    "O=C(O)c1cccnc1",                     # 吡啶-3-羧酸 (烟酸)
    "O=C(O)c1cc(C)ncc1",                  # 6-甲基-吡啶-2-羧酸

    # 联苯-COOH
    "O=C(O)c1ccc(cc1)c2ccccc2",           # 联苯-4-羧酸
    "O=C(O)c1ccc(cc1)c2ccc(F)cc2",        # 4'-氟-联苯-4-羧酸

    # 萘-COOH
    "O=C(O)c1ccc2ccccc2c1",               # 1-萘甲酸
    "O=C(O)c1ccc2ccccc2c1Cl",             # 氯代萘甲酸
]

# 策略2: 芳香核心 + 胺/酰胺 + COOH (同时靶向正负电荷区)
# 近端: COOH与ARG/LYS盐桥; 远端: 胺与ASP/GLU相互作用
DUAL_CHARGE_SCAFFOLDS = [
    # 氨基苯甲酸类 (近端COOH + 远端NH2)
    "O=C(O)c1ccccc1N",                    # 邻氨基苯甲酸 (anthranilic acid, 商业可得)
    "O=C(O)c1ccc(N)cc1",                  # 对氨基苯甲酸 (PABA)
    "O=C(O)c1ccc(N)c(F)c1",              # 3-氟-4-氨基苯甲酸

    # 含胺的杂环-COOH
    "O=C(O)c1ccc2nc(N)cc2c1",            # 2-氨基-4-喹唑啉羧酸
    "Nc1ccc2[nH]ccc2c1C(=O)O",            # 5-氨基吲哚-3-羧酸
]

# 策略3: 四唑替代COOH (生物电子等排体，更好的药代动力学)
TETRAZOLE_SCAFFOLDS = [
    "c1ccc(cc1)c2nnnn2",                  # 苯基四唑 (COOH生物等排体)
    "c1ccc2c(c1)ncnc2c3nnnn3",            # 喹唑啉-四唑
    "Fc1ccc(cc1)c2nnnn2",                 # 氟苯基四唑
    "Clc1ccc(cc1)c2nnnn2",                # 氯苯基四唑
]

# 策略4: 酰胺/磺酰胺连接的双功能分子
# 一个片段负责π-堆积+盐桥，另一个片段负责疏水填充
BIFUNCTIONAL_SCAFFOLDS = [
    # 酰胺连接: 芳香酸 + 胺 → 酰胺
    # 设计: 芳香-COOH部分靠近HIS732/ARG775，胺部分靠近疏水区
    "O=C(O)c1ccc2ncncc2c1",               # 喹唑啉-COOH (与哌啶/吗啉偶联)
    "O=C(O)c1ccc2[nH]ccc2c1",             # 吲哚-COOH (与哌啶/吗啉偶联)

    # 磺酰胺连接: 芳香磺酰胺
    "O=S(=O)(N)c1ccc2ncncc2c1",           # 喹唑啉-4-磺酰胺
    "O=S(=O)(N)c1ccc2[nH]ccc2c1",         # 吲哚-磺酰胺
]


# ======================================================================
# 分子构建工具函数
# ======================================================================

def canonicalize(smiles: str) -> str | None:
    """将SMILES canonical化，返回None如果无效。"""
    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        return None
    return Chem.MolToSmiles(mol, canonical=True)


def check_molecule(smiles: str) -> dict | None:
    """评估分子是否满足所有硬约束，返回性质字典或None。"""
    props = evaluate_molecule(smiles)
    if not props.get("valid"):
        return None
    if not passes_filters(props, max_sa=6.0):
        return None
    # 额外CNS过滤: TPSA不宜太高（COOH会增加TPSA）
    if props.get("tpsa", 0) > 140:
        return None
    return props


def add_substituent_to_acid(acid_smiles: str, amine_smiles: str) -> str | None:
    """通过酰胺偶联将COOH与胺连接，但保留一个COOH（如果有的话）。

    注意: 这不是直接偶联（会失去COOH），而是设计一种分子
    同时包含COOH和酰胺键。
    """
    # 这个函数是占位符 — 实际分子构建用模板方式
    return None


# ======================================================================
# 结构引导的分子生成
# ======================================================================

def generate_pocket_guided_molecules() -> list[dict]:
    """基于口袋分析结果，生成药效团导向的候选分子。

    返回: list[dict]，每个元素包含smiles, qed, sa_score, source, pharmacophore_features
    """
    all_molecules = []
    seen_smiles = set()

    def _add_mol(smiles: str, source: str, features: list[str]):
        """添加分子到候选列表（去重+验证）。"""
        canon = canonicalize(smiles)
        if canon is None or canon in seen_smiles:
            return
        props = check_molecule(canon)
        if props is None:
            return
        seen_smiles.add(canon)
        all_molecules.append({
            "smiles": canon,
            "qed": props["qed"],
            "sa_score": props["sa_score"],
            "mw": props["mw"],
            "logp": props["logp"],
            "tpsa": props.get("tpsa", 0),
            "source": source,
            "pharmacophore_features": features,
        })

    # ── 1. 直接酸性骨架 (COOH + 芳香核心) ──
    for smi in SCAFFOLD_ACIDIC:
        _add_mol(smi, "scaffold_acidic", ["aromatic_core", "carboxylic_acid"])

    # ── 2. 双电荷骨架 (COOH + NH2) ──
    for smi in DUAL_CHARGE_SCAFFOLDS:
        _add_mol(smi, "dual_charge", ["carboxylic_acid", "amine", "aromatic_core"])

    # ── 3. 四唑骨架 (COOH生物等排体) ──
    for smi in TETRAZOLE_SCAFFOLDS:
        _add_mol(smi, "tetrazole", ["tetrazole", "aromatic_core"])

    # ── 4. 酸性骨架 + 卤素取代 (增强疏水+代谢稳定性) ──
    halogen_acid_variants = [
        # F取代喹唑啉-COOH
        "O=C(O)c1ccc2ncncc2c1F",          # 6-F-喹唑啉-4-COOH
        "O=C(O)c1ccc(F)c2ncncc2c1",        # 7-F-喹唑啉-4-COOH
        # Cl取代喹唑啉-COOH
        "O=C(O)c1ccc2ncncc2c1Cl",          # 6-Cl-喹唑啉-4-COOH
        # F取代吲哚-COOH
        "O=C(O)c1ccc2[nH]ccc2c1F",         # 5-F-吲哚-3-COOH
        "O=C(O)c1ccc2c(c1F)[nH]c2",        # 4-F-吲哚-2-COOH
        # F取代苯并咪唑-COOH
        "O=C(O)c1ccc2[nH]cnc2c1F",         # F-苯并咪唑-COOH
        # 卤代吡啶-COOH
        "O=C(O)c1ccc(F)nc1",               # 5-F-吡啶-3-COOH
        "O=C(O)c1c(F)ccnc1F",              # 二氟吡啶-COOH
    ]
    for smi in halogen_acid_variants:
        _add_mol(smi, "halogen_acid", ["carboxylic_acid", "aromatic_core", "halogen"])

    # ── 5. 酸性骨架 + 疏水取代基 (靶向VAL735/LEU757/ILE740) ──
    hydrophobic_acid_variants = [
        # 甲基/乙基取代
        "O=C(O)c1ccc2ncnc2c1C",            # 甲基喹唑啉-COOH
        "O=C(O)c1ccc(C)c2[nH]ccc2c1",      # 甲基吲哚-COOH
        "O=C(O)c1ccc2ncnc2c1CC",            # 乙基喹唑啉-COOH

        # 环丙基/环己基 (更强的疏水填充)
        "O=C(O)c1ccc2ncnc2c1C3CCC3",        # 环丙基喹唑啉-COOH
        "O=C(O)c1ccc2[nH]ccc2c1C3CCCC3",    # 环戊基吲哚-COOH
    ]
    for smi in hydrophobic_acid_variants:
        _add_mol(smi, "hydrophobic_acid", ["carboxylic_acid", "aromatic_core", "hydrophobic"])

    # ── 6. 酸性骨架 + 胺类取代 (靶向远端ASP759/GLU806) ──
    amine_acid_variants = [
        # 喹唑啉-COOH + 哌啶 (经典CNS药物骨架 + COOH)
        "O=C(O)c1ccc2nc(N3CCCCC3)cc2c1",    # 哌啶-喹唑啉-COOH
        "O=C(O)c1ccc2nc(N3CCOCC3)cc2c1",    # 吗啉-喹唑啉-COOH
        "O=C(O)c1ccc2nc(N3CCNCC3)cc2c1",    # 哌嗪-喹唑啉-COOH

        # 吲哚-COOH + 哌啶
        "O=C(O)c1ccc2[nH]c(c2c1)N3CCCCC3",  # 哌啶-吲哚-COOH (需验证)
        "O=C(O)c1ccc2[nH]c(c2c1)N3CCOCC3",  # 吗啉-吲哚-COOH (需验证)

        # 吡啶-COOH + 胺
        "O=C(O)c1cc(N2CCCCC2)ccn1",          # 哌啶-吡啶-COOH
        "O=C(O)c1cc(N2CCOCC2)ccn1",          # 吗啉-吡啶-COOH
    ]
    for smi in amine_acid_variants:
        _add_mol(smi, "amine_acid", ["carboxylic_acid", "aromatic_core", "amine"])

    # ── 7. 酰胺连接的双功能分子 (COOH + 酰胺键) ──
    amide_acid_variants = [
        # COOH-苯甲酰 + 胺 → 保留COOH的酰胺
        "O=C(O)c1ccc(C(=O)N2CCCCC2)cc1",    # COOH-苯甲酰-哌啶 (COOH在苯环上)
        "O=C(O)c1ccc(C(=O)N2CCOCC2)cc1",    # COOH-苯甲酰-吗啉
        "O=C(O)c1ccc(C(=O)Nc2ccncc2)cc1",   # COOH-苯甲酰-氨基吡啶

        # COOH-吲哚 + 酰胺
        "O=C(O)c1ccc2[nH]c(C(=O)N3CCCCC3)c2c1", # COOH-吲哚-酰胺-哌啶

        # 磺酰胺 + COOH
        "O=C(O)c1ccc(S(=O)(=O)N2CCCCC2)cc1", # COOH-苯磺酰-哌啶
        "O=C(O)c1ccc(S(=O)(=O)N2CCOCC2)cc1", # COOH-苯磺酰-吗啉
    ]
    for smi in amide_acid_variants:
        _add_mol(smi, "amide_acid", ["carboxylic_acid", "amide", "aromatic_core", "amine"])

    # ── 8. 磺酰胺类 (当前已有高分分子类型 + 新增COOH) ──
    sulfonamide_acid_variants = [
        "O=C(O)c1ccc2c(c1)CCN2S(=O)(=O)c3ccc(F)cc3", # 四氢异喹啉磺酰胺+COOH
        "O=C(O)c1ccc2c(c1)CCN2S(=O)(=O)c3cc(F)c(F)cc3", # 双F变体
    ]
    for smi in sulfonamide_acid_variants:
        _add_mol(smi, "sulfonamide_acid", ["carboxylic_acid", "sulfonamide", "aromatic_core"])

    # ── 9. 原有高分分子保留 (无COOH但binding好) ──
    legacy_molecules = [
        # 之前最好的喹唑啉-哌嗪类型
        "Fc1ccc2c(c1)ncnc2N3CCNCC3",         # F-喹唑啉-哌嗪
        "Fc1ccc2c(c1)ncnc2N3CCN(C)CC3",       # F-喹唑啉-N-甲基哌嗪

        # 之前最好的吲哚-酰胺类型
        "c1ccc2c(c1)[nH]cc2C(=O)Nc3ccncc3",   # 吲哚-酰胺-吡啶
        "c1ccc2c(c1)[nH]cc2C(=O)Nc3cc(F)ccc3F", # 吲哚-酰胺-二氟苯

        # 苯并异噁唑-哌啶-酰胺
        "c1ccc(cc1)C(=O)N2CCC(c3noc4cc(F)ccc34)CC2", # 当前最高分之一

        # 磺酰胺类型
        "O=S(=O)(Nc1ccc(F)cc1)N2CCNCC2",      # F-苯磺酰胺-哌嗪
        "O=S(=O)(Nc1ccc(Cl)cc1)N2CCNCC2",      # Cl-苯磺酰胺-哌嗪
    ]
    for smi in legacy_molecules:
        _add_mol(smi, "legacy_best", ["aromatic_core", "h_bond"])

    # ── 10. 大分子设计 (填充更大的口袋区域) ──
    larger_molecules = [
        # 喹唑啉-COOH + 酰胺 + 哌啶 (三功能: COOH + 酰胺H键 + 哌啶碱)
        "O=C(O)c1ccc2nc(NCCCC(=O)c3ccncc3)cc2c1",  # 喹唑啉-COOH + 酰胺连接吡啶

        # 联苯-COOH + 胺 (更大π体系 + 盐桥)
        "O=C(O)c1ccc(cc1)c2ccc(N3CCCCC3)cc2",      # 联苯-COOH + 哌啶
        "O=C(O)c1ccc(cc1)c2ccc(N3CCOCC3)cc2",      # 联苯-COOH + 吗啉
        "O=C(O)c1ccc(cc1)c2ccc(N3CCNCC3)cc2",      # 联苯-COOH + 哌嗪

        # 萘-COOH + 胺
        "O=C(O)c1ccc2ccccc2c1N3CCCCC3",              # 萘-COOH + 哌啶 (需验证)
        "O=C(O)c1ccc2ccccc2c1N3CCOCC3",              # 萘-COOH + 吗啉 (需验证)
    ]
    for smi in larger_molecules:
        _add_mol(smi, "larger_molecule", ["carboxylic_acid", "aromatic_core", "amine"])

    # 按QED排序（作为初步排序，后续用对接打分重新排序）
    all_molecules.sort(key=lambda x: x["qed"], reverse=True)

    return all_molecules


def get_pocket_pharmacophore_summary() -> dict:
    """返回口袋药效团分析摘要，供Agent prompt使用。"""
    return {
        "net_charge": +6.0,
        "key_residues": {
            "ASN734": {"dist": 1.83, "type": "polar", "interaction": "H-bond hub"},
            "ASN739": {"dist": 1.90, "type": "polar", "interaction": "H-bond hub"},
            "HIS732": {"dist": 3.56, "type": "aromatic+", "interaction": "pi-stacking + salt_bridge"},
            "VAL735": {"dist": 3.48, "type": "hydrophobic", "interaction": "van_der_waals"},
            "LEU757": {"dist": 3.83, "type": "hydrophobic", "interaction": "van_der_waals"},
            "ILE740": {"dist": 4.72, "type": "hydrophobic", "interaction": "van_der_waals"},
            "ARG738": {"dist": 5.08, "type": "positive", "interaction": "salt_bridge_target"},
            "ASP759": {"dist": 5.63, "type": "negative", "interaction": "amine_target"},
            "ARG775": {"dist": 7.87, "type": "positive", "interaction": "salt_bridge_target"},
            "LYS642": {"dist": 8.63, "type": "positive", "interaction": "salt_bridge_target"},
        },
        "design_rules": [
            "1. MUST包含酸性基团 (COOH/四唑) → 盐桥ARG738/775/LYS642/HIS732 (贡献-3~-5 kcal/mol)",
            "2. MUST包含芳香核心 → π-堆积HIS732 (贡献-1~-2 kcal/mol)",
            "3. SHOULD包含H键供体/受体 → 互补ASN734/739 (贡献-1~-2 kcal/mol)",
            "4. SHOULD包含疏水基团 → 填充VAL735/LEU757/ILE740 (贡献-0.5~-1 kcal/mol)",
            "5. CAN包含碱性胺 → 互补远端ASP759/GLU806 (贡献-1~-2 kcal/mol)",
        ],
        "estimated_binding_improvement": {
            "current_best": -10.0,
            "with_salt_bridge": -15.0,
            "with_all_features": -20.0,
            "leader_estimate": -24.0,
        },
    }


if __name__ == "__main__":
    molecules = generate_pocket_guided_molecules()
    print(f"\n生成了 {len(molecules)} 个口袋导向候选分子\n")
    print(f"{'SMILES':<60} {'QED':>5} {'SA':>5} {'MW':>6} {'TPSA':>5} {'Source'}")
    print("-" * 100)
    for m in molecules:
        print(f"{m['smiles']:<60} {m['qed']:>5.3f} {m['sa_score']:>5.2f} {m['mw']:>6.1f} {m['tpsa']:>5.1f} {m['source']}")
