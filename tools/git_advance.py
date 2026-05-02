#!/usr/bin/env python3
"""Git 实验管理脚本 —— 参考 autoresearch 的 advance/revert 模式。

每次实验迭代后：
- 成功（结合能改善）→ git commit 保留
- 失败（结合能退化）→ git reset 回退

用法:
    python tools/git_advance.py --round 1 --best-be -7.92 --status keep
    python tools/git_advance.py --round 2 --best-be -7.50 --status discard
"""
import argparse
import subprocess
import sys
from pathlib import Path


def run(cmd: list[str]) -> str:
    """运行 shell 命令并返回 stdout。"""
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"Error: {' '.join(cmd)}\n{result.stderr}", file=sys.stderr)
        sys.exit(1)
    return result.stdout.strip()


def main():
    parser = argparse.ArgumentParser(description="Git 实验管理")
    parser.add_argument("--round", type=int, required=True, help="实验轮次")
    parser.add_argument("--best-be", type=float, required=True, help="本轮最佳结合能")
    parser.add_argument(
        "--status",
        choices=["keep", "discard", "crash"],
        required=True,
        help="keep=保留 commit, discard=回退到上一轮, crash=回退并记录失败",
    )
    args = parser.parse_args()

    # 检查是否在 git 仓库中
    try:
        run(["git", "rev-parse", "--git-dir"])
    except SystemExit:
        print("错误：当前目录不是 git 仓库。请先初始化 git。")
        sys.exit(1)

    if args.status == "keep":
        # 保留本轮实验结果
        msg = f"round-{args.round}: best_BE={args.best_be:.3f} kcal/mol"
        run(["git", "add", "-A"])
        run(["git", "commit", "-m", msg, "--allow-empty"])
        print(f"✅ 已提交: {msg}")
        print(f"   commit: {run(['git', 'rev-parse', '--short', 'HEAD'])}")

    elif args.status in ("discard", "crash"):
        # 回退到上一轮
        # 先 stash 未跟踪的文件（如 experiments.jsonl）
        run(["git", "stash", "push", "-u", "-m", f"round-{args.round}-discard"])
        # soft reset 到上一次 commit
        run(["git", "reset", "--soft", "HEAD~1"])
        status = "丢弃" if args.status == "discard" else "崩溃回退"
        print(f"🔄 已{status} round-{args.round} 的更改，回到上一轮状态")


if __name__ == "__main__":
    main()
