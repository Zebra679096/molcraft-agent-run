#!/usr/bin/env python3
"""环境依赖一键检查脚本。"""

import sys
import subprocess


def check(cmd: list[str], name: str) -> bool:
    """运行外部命令，返回是否成功。"""
    try:
        subprocess.run(cmd, capture_output=True, check=True)
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False


def main() -> int:
    ok = True

    # 1. uv
    if check(["uv", "--version"], "uv"):
        print("  ✓ uv 已安装")
    else:
        print("  ✗ uv 未安装，执行: curl -LsSf https://astral.sh/uv/install.sh | sh")
        ok = False

    # 2. Python 版本
    if sys.version_info >= (3, 12):
        print(f"  ✓ Python {sys.version_info.major}.{sys.version_info.minor}")
    else:
        print(f"  ✗ Python {sys.version_info.major}.{sys.version_info.minor}，需要 ≥ 3.12")
        ok = False

    # 3. 虚拟环境
    if hasattr(sys, "real_prefix") or (
        hasattr(sys, "base_prefix") and sys.base_prefix != sys.prefix
    ):
        print("  ✓ 虚拟环境已激活")
    else:
        print("  ✗ 虚拟环境未激活，执行: source .venv/bin/activate")
        ok = False

    # 4. 关键 Python 包
    packages = [
        ("rdkit", "RDKit"),
        ("vina", "Vina"),
        ("meeko", "Meeko"),
        ("openbabel", "Open Babel"),
        ("numpy", "NumPy"),
        ("pandas", "Pandas"),
        ("scipy", "SciPy"),
        ("Bio", "BioPython"),
        ("openai", "OpenAI"),
        ("kimi_agent_sdk", "kimi-agent-sdk"),
    ]

    for mod, name in packages:
        try:
            __import__(mod)
            print(f"  ✓ {name}")
        except ImportError:
            print(f"  ✗ {name} 未安装，执行: uv sync --python 3.12")
            ok = False

    print()
    if ok:
        print("全部通过，环境就绪。")
        return 0
    else:
        print("部分检查未通过，按上述提示修复后重试。")
        return 1


if __name__ == "__main__":
    sys.exit(main())
