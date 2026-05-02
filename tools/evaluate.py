#!/usr/bin/env python3
"""分子评估工具：评估单个分子的药物相似性和理化性质。"""
import sys
import os
import json
import argparse

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

from evaluator import evaluate_molecule


def main():
    parser = argparse.ArgumentParser(description="评估分子性质")
    parser.add_argument("--smiles", type=str, required=True, help="分子的 SMILES")
    parser.add_argument("--output", type=str, default=None, help="输出 JSON 文件路径")
    args = parser.parse_args()

    result = evaluate_molecule(args.smiles)
    output_json = json.dumps(result, ensure_ascii=False, indent=2)

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(output_json)
    else:
        print(output_json)


if __name__ == "__main__":
    main()
