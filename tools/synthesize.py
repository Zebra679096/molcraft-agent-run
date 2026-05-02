#!/usr/bin/env python3
"""逆合成规划工具：为目标分子生成合成路线。"""
import sys
import os
import json
import argparse

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

from synthesis_v2 import plan_synthesis_v2


def main():
    parser = argparse.ArgumentParser(description="逆合成路线规划")
    parser.add_argument("--smiles", type=str, required=True, help="目标分子的 SMILES")
    parser.add_argument("--output", type=str, default=None, help="输出 JSON 文件路径")
    args = parser.parse_args()

    print(f"[synthesize] 规划合成路线: {args.smiles}", file=sys.stderr)
    result = plan_synthesis_v2(args.smiles)

    output = {
        "smiles": args.smiles,
        "success": result.get("success"),
        "route": result.get("route"),
        "steps": result.get("steps"),
        "error": result.get("error"),
    }

    output_json = json.dumps(output, ensure_ascii=False, indent=2)
    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(output_json)
        print(f"[synthesize] 结果已保存到 {args.output}", file=sys.stderr)
    else:
        print(output_json)


if __name__ == "__main__":
    main()
