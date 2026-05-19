"""受体准备模块：将 PDB 转换为对接所需的 PDBQT 格式。"""
import os
from openbabel import openbabel
from config import TARGET_PDB, RECEPTOR_PDBQT


def prepare_receptor(force=False):
    """将 PDB 文件转换为 PDBQT 格式（刚性受体）。"""
    if os.path.exists(RECEPTOR_PDBQT) and not force:
        print(f"[Receptor] 使用已存在的受体文件 {RECEPTOR_PDBQT}")
        return RECEPTOR_PDBQT

    print(f"[Receptor] 正在准备受体 {TARGET_PDB} -> {RECEPTOR_PDBQT}")
    obConversion = openbabel.OBConversion()
    obConversion.SetInAndOutFormats("pdb", "pdbqt")
    obConversion.AddOption("r", openbabel.OBConversion.OUTOPTIONS)

    mol = openbabel.OBMol()
    obConversion.ReadFile(mol, TARGET_PDB)
    obConversion.WriteFile(mol, RECEPTOR_PDBQT)
    print(f"[Receptor] 受体准备完成，共 {mol.NumAtoms()} 个原子")
    return RECEPTOR_PDBQT


def get_protein_center_size():
    """返回推荐的对接盒子中心和大小。"""
    from config import DOCKING_CENTER, DOCKING_SIZE
    return {"center": DOCKING_CENTER, "size": DOCKING_SIZE}
