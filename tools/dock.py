#!/usr/bin/env python3
"""分子对接工具：计算分子与靶点的结合自由能。"""
import sys
import os
import json
import argparse

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

from docking import dock_molecule, batch_dock
from receptor import prepare_receptor


def main():
    parser = argparse.ArgumentParser(description="分子对接打分")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--smiles", type=str, help="单个分子的 SMILES")
    group.add_argument("--input", type=str, help="包含 SMILES 列表的 JSON 文件路径")
    parser.add_argument("--output", type=str, default=None, help="输出 JSON 文件路径")
    parser.add_argument("--center", type=str, default=None,
                        help="对接盒子中心坐标，格式: x,y,z (默认使用蛋白质质心)")
    parser.add_argument("--size", type=str, default=None,
                        help="对接盒子大小，格式: sx,sy,sz (默认: 30,30,30)")
    args = parser.parse_args()

    # 解析中心坐标和大小
    center = None
    size = None
    if args.center:
        center = [float(x) for x in args.center.split(",")]
    if args.size:
        size = [float(x) for x in args.size.split(",")]

    # 准备受体
    prepare_receptor()

    if args.smiles:
        print(f"[dock] 对接单个分子: {args.smiles}", file=sys.stderr)
        result = dock_molecule(args.smiles, center=center, size=size)
        result["smiles"] = args.smiles
        results = [result]
    else:
        with open(args.input, "r", encoding="utf-8") as f:
            data = json.load(f)
        smiles_list = [m["smiles"] for m in data.get("molecules", [])]
        print(f"[dock] 批量对接 {len(smiles_list)} 个分子", file=sys.stderr)
        mols = [{"smiles": s} for s in smiles_list]
        results = batch_dock(mols, center=center, size=size)

    # 排序：结合能从低到高
    successful = [r for r in results if r.get("success")]
    successful.sort(key=lambda x: x.get("binding_energy", 999))

    output = {
        "total": len(results),
        "successful": len(successful),
        "results": [
            {
                "smiles": r["smiles"],
                "binding_energy": r.get("binding_energy"),
                "success": r.get("success"),
                "error": r.get("error"),
            }
            for r in successful
        ]
    }

    output_json = json.dumps(output, ensure_ascii=False, indent=2)
    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(output_json)
        print(f"[dock] 结果已保存到 {args.output}", file=sys.stderr)
    else:
        print(output_json)


if __name__ == "__main__":
    main()
