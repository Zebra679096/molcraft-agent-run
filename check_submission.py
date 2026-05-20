#!/usr/bin/env python3
"""提交前自动合规检查脚本 (Pre-submission Compliance Check)

用途: 在提交 result.zip 到竞赛平台前，自动检查所有致命性指标。
     任何一项 FAIL 都会导致竞赛零分或严重扣分。

运行方式:
    cd molcraft-agent
    source .venv/bin/activate
    python check_submission.py

决策引用: D006 — 项目协作规范要求提交前运行合规检查
"""

import csv
import sys
import os
from collections import Counter
from pathlib import Path

# 添加项目路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "molcraft_agent"))

from rdkit import Chem
from synthesis_v2 import _check_atom_balance, _get_atom_counts


# ======================================================================
# 检查函数
# ======================================================================

def check_file_format(csv_path: str) -> dict:
    """检查1: 输出文件格式是否与比赛要求一致。"""
    result = {"name": "文件格式", "checks": [], "pass": True}

    if not os.path.exists(csv_path):
        result["checks"].append(("CSV文件存在", "FAIL", f"{csv_path} 不存在"))
        result["pass"] = False
        return result

    result["checks"].append(("CSV文件存在", "PASS", ""))

    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    # 检查列名
    if reader.fieldnames != ["mol_smiles", "route"]:
        result["checks"].append(("列名正确", "FAIL", f"期望 [mol_smiles, route], 实际 {reader.fieldnames}"))
        result["pass"] = False
    else:
        result["checks"].append(("列名正确", "PASS", ""))

    # 检查行数
    if len(rows) == 0:
        result["checks"].append(("分子数量>0", "FAIL", "CSV为空"))
        result["pass"] = False
    else:
        result["checks"].append(("分子数量>0", "PASS", f"共 {len(rows)} 个分子"))

    # 检查mol_smiles和route列不为空
    empty_mol = sum(1 for r in rows if not r.get("mol_smiles", "").strip())
    empty_route = sum(1 for r in rows if not r.get("route", "").strip())
    if empty_mol > 0:
        result["checks"].append(("mol_smiles非空", "FAIL", f"{empty_mol} 个空SMILES"))
        result["pass"] = False
    else:
        result["checks"].append(("mol_smiles非空", "PASS", ""))
    if empty_route > 0:
        result["checks"].append(("route非空", "FAIL", f"{empty_route} 个空路线"))
        result["pass"] = False
    else:
        result["checks"].append(("route非空", "PASS", ""))

    result["rows"] = rows
    return result


def check_validity(rows: list) -> dict:
    """检查2: 致命性指标 — SMILES有效性、QED、SA。"""
    result = {"name": "分子有效性", "checks": [], "pass": True, "details": []}

    # 延迟导入（避免循环依赖）
    from evaluator import evaluate_molecule, passes_filters

    n_invalid = 0
    n_qed_fail = 0
    n_sa_fail = 0

    for i, row in enumerate(rows):
        smi = row.get("mol_smiles", "").strip()
        mol = Chem.MolFromSmiles(smi)
        if mol is None:
            n_invalid += 1
            result["details"].append(f"  Row {i+1}: 无效SMILES: {smi}")
            continue

        props = evaluate_molecule(smi)
        if not props.get("valid"):
            n_invalid += 1
            result["details"].append(f"  Row {i+1}: 评估失败: {smi}")
            continue

        qed = props.get("qed", 0)
        sa = props.get("sa_score", 10)

        if qed < 0.3:
            n_qed_fail += 1
            result["details"].append(f"  Row {i+1}: QED={qed:.3f} < 0.3 → 零分: {smi}")

        if sa > 6.0:
            n_sa_fail += 1
            result["details"].append(f"  Row {i+1}: SA={sa:.1f} > 6.0 → 零分: {smi}")

    # SMILES有效性
    if n_invalid > 0:
        result["checks"].append(("SMILES有效性", "FAIL", f"{n_invalid} 个无效SMILES"))
        result["pass"] = False
    else:
        result["checks"].append(("SMILES有效性", "PASS", "全部有效"))

    # QED检查
    if n_qed_fail > 0:
        result["checks"].append(("QED >= 0.3", "FAIL", f"{n_qed_fail} 个QED < 0.3（零分）"))
        result["pass"] = False
    else:
        result["checks"].append(("QED >= 0.3", "PASS", "全部通过"))

    # SA检查
    if n_sa_fail > 0:
        result["checks"].append(("SAScore <= 6.0", "FAIL", f"{n_sa_fail} 个SA > 6.0（零分）"))
        result["pass"] = False
    else:
        result["checks"].append(("SAScore <= 6.0", "PASS", "全部通过"))

    return result


def check_routes(rows: list) -> dict:
    """检查3: 路线格式、原子平衡、非trivial。"""
    result = {"name": "逆合成路线", "checks": [], "pass": True, "details": []}

    n_trivial = 0
    n_pipe_sep = 0
    n_no_arrow = 0
    n_product_mismatch = 0
    n_atom_imbalance = 0
    n_valid_routes = 0

    for i, row in enumerate(rows):
        smi = row.get("mol_smiles", "").strip()
        route = row.get("route", "").strip()

        # 检查: 包含 >>
        if ">>" not in route:
            n_no_arrow += 1
            result["details"].append(f"  Row {i+1}: 路线缺少 >>: {smi}")
            continue

        # 检查: 不使用 | 分隔符
        if " | " in route:
            n_pipe_sep += 1
            result["details"].append(f"  Row {i+1}: 路线使用 | 分隔符（应用 ,）: {smi[:50]}")

        # 检查: 非trivial
        if route == f"{smi}>>{smi}":
            n_trivial += 1
            result["details"].append(f"  Row {i+1}: trivial路线: {smi}")
            continue

        # 检查: 最后一步产物 = mol_smiles
        last_step = route.split(",")[-1]
        parts = last_step.split(">>")
        if len(parts) == 2:
            prod_mol = Chem.MolFromSmiles(parts[1])
            target_mol = Chem.MolFromSmiles(smi)
            if prod_mol and target_mol:
                if Chem.MolToSmiles(prod_mol) != Chem.MolToSmiles(target_mol):
                    n_product_mismatch += 1
                    result["details"].append(f"  Row {i+1}: 最后产物≠目标分子: {smi}")
                    continue

        # 检查: 每步原子平衡
        steps = route.replace(" | ", ",").split(",")
        step_balanced = True
        for step in steps:
            sp = step.split(">>")
            if len(sp) != 2:
                continue
            reactants = sp[0].split(".")
            if not _check_atom_balance(reactants, sp[1]):
                step_balanced = False
                n_atom_imbalance += 1
                result["details"].append(f"  Row {i+1}: 原子不平衡步骤: {step[:60]}")
                break

        if step_balanced:
            n_valid_routes += 1

    # 汇总
    if n_pipe_sep > 0:
        result["checks"].append(("路线分隔符(,而非|)", "FAIL", f"{n_pipe_sep} 个路线使用 | 分隔"))
        result["pass"] = False
    else:
        result["checks"].append(("路线分隔符(,而非|)", "PASS", "全部使用 , 分隔"))

    if n_trivial > 0:
        result["checks"].append(("非trivial路线", "WARN", f"{n_trivial} 个trivial路线（扣分）"))
    else:
        result["checks"].append(("非trivial路线", "PASS", "全部非trivial"))

    if n_product_mismatch > 0:
        result["checks"].append(("最后产物=目标分子", "FAIL", f"{n_product_mismatch} 个不匹配（零分）"))
        result["pass"] = False
    else:
        result["checks"].append(("最后产物=目标分子", "PASS", "全部匹配"))

    if n_atom_imbalance > 0:
        result["checks"].append(("原子平衡", "FAIL", f"{n_atom_imbalance} 个步骤不平衡（零分）"))
        result["pass"] = False
    else:
        result["checks"].append(("原子平衡", "PASS", "全部平衡"))

    result["checks"].append(("有效路线总计", "INFO", f"{n_valid_routes}/{len(rows)}"))

    if n_valid_routes == 0:
        result["checks"].append(("至少1条有效路线", "FAIL", "全部无效（route_score=0）"))
        result["pass"] = False

    return result


def check_consistency(rows: list) -> dict:
    """检查4: 最终产物与中间结果的一致性。"""
    result = {"name": "一致性检查", "checks": [], "pass": True}

    # 检查重复分子
    smiles_set = set()
    duplicates = 0
    for row in rows:
        smi = row.get("mol_smiles", "").strip()
        mol = Chem.MolFromSmiles(smi)
        if mol:
            canon = Chem.MolToSmiles(mol)
            if canon in smiles_set:
                duplicates += 1
            smiles_set.add(canon)

    if duplicates > 0:
        result["checks"].append(("无重复分子", "WARN", f"{duplicates} 个重复（浪费提交名额）"))
    else:
        result["checks"].append(("无重复分子", "PASS", ""))

    # 检查分子数量范围
    n = len(rows)
    if n < 10:
        result["checks"].append(("分子数量(10-25)", "WARN", f"仅 {n} 个，建议提交10-25个"))
    elif n > 30:
        result["checks"].append(("分子数量(10-25)", "WARN", f"共 {n} 个，过多可能降低平均分"))
    else:
        result["checks"].append(("分子数量(10-25)", "PASS", f"共 {n} 个"))

    return result


# ======================================================================
# 主函数
# ======================================================================

def main():
    csv_path = os.path.join(os.path.dirname(__file__), "output", "result.csv")

    print("=" * 60)
    print("  提交前合规检查 (Pre-submission Compliance Check)")
    print("=" * 60)
    print()

    all_pass = True

    # 检查1: 文件格式
    r1 = check_file_format(csv_path)
    print(f"📋 {r1['name']}")
    for name, status, detail in r1["checks"]:
        icon = "✅" if status == "PASS" else "❌" if status == "FAIL" else "⚠️"
        print(f"  {icon} {name}: {detail if detail else 'OK'}")
    if not r1["pass"]:
        all_pass = False
    print()

    if "rows" not in r1:
        print("❌ 无法继续检查（CSV文件不存在或格式错误）")
        sys.exit(1)

    rows = r1["rows"]

    # 检查2: 分子有效性
    r2 = check_validity(rows)
    print(f"📋 {r2['name']}")
    for name, status, detail in r2["checks"]:
        icon = "✅" if status == "PASS" else "❌" if status == "FAIL" else "⚠️"
        print(f"  {icon} {name}: {detail if detail else 'OK'}")
    if not r2["pass"]:
        all_pass = False
    if r2["details"]:
        for d in r2["details"][:5]:
            print(f"    {d}")
        if len(r2["details"]) > 5:
            print(f"    ... 还有 {len(r2['details'])-5} 条")
    print()

    # 检查3: 路线
    r3 = check_routes(rows)
    print(f"📋 {r3['name']}")
    for name, status, detail in r3["checks"]:
        icon = "✅" if status == "PASS" else "❌" if status == "FAIL" else "⚠️" if status == "WARN" else "ℹ️"
        print(f"  {icon} {name}: {detail if detail else 'OK'}")
    if not r3["pass"]:
        all_pass = False
    if r3["details"]:
        for d in r3["details"][:8]:
            print(f"    {d}")
        if len(r3["details"]) > 8:
            print(f"    ... 还有 {len(r3['details'])-8} 条")
    print()

    # 检查4: 一致性
    r4 = check_consistency(rows)
    print(f"📋 {r4['name']}")
    for name, status, detail in r4["checks"]:
        icon = "✅" if status == "PASS" else "❌" if status == "FAIL" else "⚠️"
        print(f"  {icon} {name}: {detail if detail else 'OK'}")
    if not r4["pass"]:
        all_pass = False
    print()

    # 总结
    print("=" * 60)
    if all_pass:
        print("  ✅ 全部检查通过！可以提交。")
    else:
        print("  ❌ 存在致命问题！请修复后再提交。")
        print()
        print("  关键指标说明:")
        print("  - QED < 0.3: 药物相似性过低，mol_score 直接为 0")
        print("  - SA > 6.0: 合成难度太高，mol_score 直接为 0")
        print("  - 原子不平衡: 反应物原子不能覆盖产物原子，route_score 为 0")
        print("  - trivial路线: 路线等于 SMILES>>SMILES，不算有效路线")
        print("  - | 分隔符: 评分系统无法解析，route_score 为 0")
    print("=" * 60)

    sys.exit(0 if all_pass else 1)


if __name__ == "__main__":
    main()
