"""分子性质评估模块：使用 RDKit 计算药物相似性和理化性质。"""
import math
from rdkit import Chem
from rdkit.Chem import Descriptors, QED, Lipinski
from rdkit.Chem import RDConfig
import os


def evaluate_molecule(smiles: str):
    """评估分子的药物相似性和基本理化性质。"""
    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        return {"valid": False, "error": "无效的 SMILES"}

    mol = Chem.AddHs(mol)
    mw = Descriptors.MolWt(mol)
    logp = Descriptors.MolLogP(mol)
    tpsa = Descriptors.TPSA(mol)
    hbd = Lipinski.NumHDonors(mol)
    hba = Lipinski.NumHAcceptors(mol)
    rotb = Descriptors.NumRotatableBonds(mol)
    rings = Descriptors.RingCount(mol)
    qed = QED.qed(mol)

    # 合成可及性估算（非常粗略）
    sa = estimate_sa_score(mol)

    # 类药五规则检查
    lipinski_violations = 0
    if mw > 500: lipinski_violations += 1
    if logp > 5: lipinski_violations += 1
    if hbd > 5: lipinski_violations += 1
    if hba > 10: lipinski_violations += 1
    lipinski_ok = lipinski_violations <= 1  # 允许违反 1 条

    return {
        "valid": True,
        "smiles": smiles,
        "mw": round(mw, 2),
        "logp": round(logp, 2),
        "tpsa": round(tpsa, 2),
        "hbd": hbd,
        "hba": hba,
        "rotatable_bonds": rotb,
        "rings": rings,
        "qed": round(qed, 3),
        "sa_score": round(sa, 2),
        "lipinski_pass": lipinski_ok,
    }


def estimate_sa_score(mol):
    """非常粗略的合成可及性估算（0-10，越低越好）。
    基于片段复杂度和环系分析。
    """
    # 统计稠环数量
    ri = mol.GetRingInfo()
    atom_rings = ri.AtomRings()
    n_rings = len(atom_rings)

    # 螺环中心
    spiro = Chem.rdMolDescriptors.CalcNumSpiroAtoms(mol)

    # 桥头原子
    bridge = Chem.rdMolDescriptors.CalcNumBridgeheadAtoms(mol)

    # 手性中心
    stereo = Chem.rdMolDescriptors.CalcNumAtomStereoCenters(mol)

    # 基础启发式公式
    score = 1.0 + n_rings * 0.5 + spiro * 1.0 + bridge * 1.5 + stereo * 0.5
    score += Descriptors.NumRotatableBonds(mol) * 0.1
    return min(score, 10.0)


def passes_filters(props: dict, min_qed=0.3, max_mw=500, min_mw=150, max_logp=5.0, max_sa=6.0):
    """检查分子是否通过基础类药性质过滤。

    注意: max_sa 默认 6.0，与竞赛硬零分条件一致（SAScore>6 零分）。
    之前版本误用 8.0，现已修正。
    """
    if not props.get("valid"):
        return False
    if props["qed"] < min_qed:
        return False
    if not (min_mw <= props["mw"] <= max_mw):
        return False
    if props["logp"] > max_logp:
        return False
    if props["sa_score"] > max_sa:
        return False
    return True
