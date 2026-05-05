#!/usr/bin/env python3
"""MolCraft Agent 入口 —— 使用 Kimi Agent SDK 启动自主药物研发智能体。

本脚本遵循 autoresearch 架构模式：
- program.md：人类编辑的 Agent 指令书（唯一人机接口）
- docs/iteration_log.jsonl：Agent 主动报告的迭代记录
- main.py：只负责读取 program.md 并启动 Agent，自身不携带业务逻辑

运行方式:
    cd molcraft-agent
    source .venv/bin/activate
    python main.py                    # 默认 1 次迭代，最长 90 分钟
    python main.py --iterations 3     # 迭代 3 次
    python main.py --max-minutes 60   # 最长 60 分钟
    python main.py --max-steps 1000   # 每轮最多 1000 步
"""
import argparse
import asyncio
import json
import sys
import time
from datetime import datetime
from pathlib import Path

from kimi_agent_sdk import prompt


AGENT_YAML = Path(__file__).parent / "agent.yaml"
PROGRAM_MD = Path(__file__).parent / "program.md"
OUTPUT_DIR = Path(__file__).parent / "output"
ITERATION_LOG = Path(__file__).parent / "docs" / "iteration_log.jsonl"


def load_program() -> str:
    """读取 program.md，这是人类与 Agent 交互的唯一接口。"""
    if not PROGRAM_MD.exists():
        raise FileNotFoundError(
            f"{PROGRAM_MD} 不存在。这是 Agent 的指令书，必须创建后才能运行。"
        )
    return PROGRAM_MD.read_text(encoding="utf-8")


class TeeLogger:
    """同时输出到终端和文件的日志记录器。"""

    def __init__(self, log_path: Path):
        self.terminal = sys.stdout
        self.log_file = open(log_path, "w", encoding="utf-8")

    def write(self, message: str) -> None:
        self.terminal.write(message)
        self.log_file.write(message)
        self.log_file.flush()

    def flush(self) -> None:
        self.terminal.flush()
        self.log_file.flush()

    def close(self) -> None:
        self.log_file.close()


def count_iterations() -> int:
    """统计 Agent 已报告的迭代次数。

    Agent 每完成一轮「文献→诊断→改代码→实验验证」闭环后，
    会主动调用 report_iteration 工具，写入一条记录到 docs/iteration_log.jsonl。
    """
    if not ITERATION_LOG.exists():
        return 0
    count = 0
    try:
        with open(ITERATION_LOG, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    count += 1
    except Exception:
        pass
    return count


async def monitor(stop_event: asyncio.Event, max_iterations: int, max_seconds: float):
    """独立协程：每 30 秒检查迭代次数和时间限制。"""
    start_time = time.time()
    limit_printed = False

    while not stop_event.is_set():
        await asyncio.sleep(30)

        elapsed = time.time() - start_time

        # 时间上限
        if elapsed > max_seconds:
            print(
                f"\n\n[{datetime.now().isoformat()}] 达到最大运行时间 "
                f"({int(max_seconds // 60)} 分钟)，正在退出...",
                flush=True,
            )
            stop_event.set()
            return

        # 迭代次数上限
        if max_iterations > 0 and not limit_printed:
            current = count_iterations()
            print(
                f"\n[{datetime.now().isoformat()}] 迭代进度: {current}/{max_iterations}",
                flush=True,
            )
            if current >= max_iterations:
                print(
                    f"\n[{datetime.now().isoformat()}] 已达到最大迭代次数 "
                    f"({max_iterations} 次)，60 秒后退出...",
                    flush=True,
                )
                limit_printed = True
                await asyncio.sleep(60)
                stop_event.set()
                return


async def main() -> None:
    parser = argparse.ArgumentParser(description="MolCraft Agent 启动器")
    parser.add_argument(
        "--iterations",
        type=int,
        default=1,
        help="最大迭代次数。默认 1 次。设为 0 表示不限制。",
    )
    parser.add_argument(
        "--max-minutes",
        type=int,
        default=90,
        help="最大运行时间（分钟）。默认 90 分钟。",
    )
    parser.add_argument(
        "--max-steps",
        type=int,
        default=1000,
        help="每轮最大步数。默认 1000 步。",
    )
    args = parser.parse_args()

    program = load_program()

    # 确保输出目录存在
    OUTPUT_DIR.mkdir(exist_ok=True)
    log_path = OUTPUT_DIR / "result.log"

    # 重定向 stdout 到终端 + 文件
    tee = TeeLogger(log_path)
    original_stdout = sys.stdout
    sys.stdout = tee

    stop_event = asyncio.Event()
    max_seconds = args.max_minutes * 60

    # 启动独立监控协程
    monitor_task = asyncio.create_task(
        monitor(stop_event, args.iterations, max_seconds)
    )

    try:
        print(f"[{datetime.now().isoformat()}] MolCraft Agent 启动")
        print("=" * 60)
        print("模式: autoresearch（LLM 自主迭代实验）")
        print(f"指令书: {PROGRAM_MD}")
        print(f"迭代记录: {ITERATION_LOG}")
        print(f"日志文件: {log_path}")
        print(f"配置: 最大 {args.iterations} 次迭代 | 最长 {args.max_minutes} 分钟")
        print("(yolo 模式下自动批准所有操作)")
        print()

        async for msg in prompt(
            program,
            agent_file=AGENT_YAML,
            yolo=True,
            max_steps_per_turn=args.max_steps,
        ):
            if stop_event.is_set():
                break

            text = msg.extract_text()
            if text:
                print(text, end="", flush=True)

        print()
        print()
        print("=" * 60)
        print(f"[{datetime.now().isoformat()}] MolCraft Agent 执行结束")
        print("请检查:")
        print("  - output/result.csv（最终候选分子与合成路线）")
        print(f"  - {log_path}（详细结果日志）")
        print(f"  - {ITERATION_LOG}（迭代记录）")
        print("=" * 60)
    finally:
        stop_event.set()
        if not monitor_task.done():
            monitor_task.cancel()
            try:
                await monitor_task
            except asyncio.CancelledError:
                pass
        sys.stdout = original_stdout
        tee.close()


if __name__ == "__main__":
    asyncio.run(main())
