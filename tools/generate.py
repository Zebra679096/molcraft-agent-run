#!/usr/bin/env python3
"""分子生成工具：生成候选药物分子并输出为 JSON。"""
import sys
import os
import json
import argparse

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

from generator import generate_molecules


def main():
    parser = argparse.ArgumentParser(description="生成候选药物分子")
    parser.add_argument("--strategy", choices=["mutate", "combine", "random"], default="mutate",
                        help="生成策略 (默认: mutate)")
    parser.add_argument("--n", type=int, default=30, help="生成分子数量 (默认: 30)")
    parser.add_argument("--scaffold", type=str, default=None, help="种子骨架 SMILES")
    parser.add_argument("--output", type=str, default=None, help="输出 JSON 文件路径")
    args = parser.parse_args()

    print(f"[generate] 开始生成分子: strategy={args.strategy}, n={args.n}", file=sys.stderr)
    mols = generate_molecules(strategy=args.strategy, n_molecules=args.n, scaffold=args.scaffold)
    print(f"[generate] 成功生成 {len(mols)} 个分子", file=sys.stderr)

    # 只保留关键字段输出
    result = {
        "count": len(mols),
        "molecules": [
            {
                "smiles": m["smiles"],
                "qed": m["qed"],
                "mw": m["mw"],
                "logp": m["logp"],
                "sa_score": m["sa_score"],
                "lipinski_pass": m["lipinski_pass"],
            }
            for m in mols
        ]
    }

    output_json = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(output_json)
        print(f"[generate] 结果已保存到 {args.output}", file=sys.stderr)
    else:
        print(output_json)


if __name__ == "__main__":
    main()
