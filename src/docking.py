"""分子对接模块：使用 AutoDock Vina 计算结合自由能。"""
import os
import tempfile
from rdkit import Chem, rdBase
from rdkit.Chem import AllChem
from meeko import MoleculePreparation, PDBQTWriterLegacy
from vina import Vina
from config import RECEPTOR_PDBQT, DOCKING_CENTER, DOCKING_SIZE, DOCKING_EXHAUSTIVENESS
from receptor import prepare_receptor

# 压制 RDKit 错误输出
rdBase.DisableLog('rdApp.error')
rdBase.DisableLog('rdApp.warning')


def smiles_to_pdbqt(smiles: str, output_path: str = None):
    """使用 RDKit + Meeko 将 SMILES 转换为 PDBQT 文件。"""
    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        return None

    mol = Chem.AddHs(mol)
    ret = AllChem.EmbedMolecule(mol, randomSeed=42)
    if ret != 0:
        ret = AllChem.EmbedMolecule(mol, AllChem.ETKDGv3())
    if ret != 0:
        return None
    try:
        AllChem.MMFFOptimizeMolecule(mol, maxIters=200)
    except Exception:
        pass

    preparator = MoleculePreparation()
    setup_list = preparator.prepare(mol)
    if not setup_list:
        return None

    pdbqt_string = PDBQTWriterLegacy.write_string(setup_list[0])[0]

    if output_path is None:
        fd, output_path = tempfile.mkstemp(suffix=".pdbqt")
        os.close(fd)

    with open(output_path, "w") as f:
        f.write(pdbqt_string)

    return output_path


def dock_molecule(smiles: str, center=None, size=None, exhaustiveness=None):
    """对单个分子进行对接，返回结合能（kcal/mol）。

    返回字典包含:
        - binding_energy: 最佳构象能量（负值=越好）
        - poses: 构象能量列表
        - success: 是否成功
        - error: 失败原因
    """
    receptor = prepare_receptor()
    ligand_pdbqt = smiles_to_pdbqt(smiles)
    if ligand_pdbqt is None:
        return {"success": False, "error": "配体准备失败"}

    if center is None:
        center = DOCKING_CENTER
    if size is None:
        size = DOCKING_SIZE
    if exhaustiveness is None:
        exhaustiveness = DOCKING_EXHAUSTIVENESS

    try:
        v = Vina(sf_name="vina", seed=42, verbosity=0)
        v.set_receptor(receptor)
        v.set_ligand_from_file(ligand_pdbqt)
        v.compute_vina_maps(center=center, box_size=size)
        v.dock(exhaustiveness=exhaustiveness, n_poses=5)
        energies = v.energies(n_poses=1)
        best_energy = float(energies[0][0])

        # 清理临时文件
        if ligand_pdbqt.startswith(tempfile.gettempdir()):
            os.remove(ligand_pdbqt)

        return {
            "success": True,
            "binding_energy": round(best_energy, 3),
            "poses": energies.tolist(),
        }
    except Exception as e:
        if ligand_pdbqt and ligand_pdbqt.startswith(tempfile.gettempdir()):
            try:
                os.remove(ligand_pdbqt)
            except Exception:
                pass
        return {"success": False, "error": str(e)}


def batch_dock(molecules, center=None, size=None):
    """批量对接分子并返回结果。"""
    results = []
    for i, mol_info in enumerate(molecules):
        smiles = mol_info["smiles"]
        print(f"[对接] {i+1}/{len(molecules)}: {smiles[:40]}...")
        result = dock_molecule(smiles, center, size)
        result["smiles"] = smiles
        result.update(mol_info)
        results.append(result)
    return results
