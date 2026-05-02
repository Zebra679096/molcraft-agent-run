"""实验记录模块 —— 结构化记录 Agent 每次工具调用。

参考 autoresearch 的 results.tsv 设计，使用 JSON Lines 格式便于追加和解析。
"""
import json
import os
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
EXPERIMENTS_FILE = PROJECT_ROOT / "experiments.jsonl"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def append_experiment(
    tool: str,
    round_num: int,
    params: dict,
    result: dict,
) -> None:
    """记录一次工具调用到 experiments.jsonl。

    Args:
        tool: 工具名称，如 "generate_molecules"
        round_num: 当前实验轮次（从 1 开始）
        params: 调用参数
        result: 工具返回结果的关键字段
    """
    record = {
        "timestamp": _now_iso(),
        "tool": tool,
        "round": round_num,
        "params": params,
        "result": result,
    }
    with open(EXPERIMENTS_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")


def read_experiments() -> list[dict]:
    """读取全部实验记录。"""
    if not EXPERIMENTS_FILE.exists():
        return []
    records = []
    with open(EXPERIMENTS_FILE, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    return records


def get_latest_round() -> int:
    """获取当前最新实验轮次，0 表示尚未开始。"""
    records = read_experiments()
    if not records:
        return 0
    return max(r.get("round", 0) for r in records)


def get_best_binding_energy() -> float:
    """从实验记录中获取历史最佳结合能（最低值）。"""
    records = read_experiments()
    best = float("inf")
    for r in records:
        if r.get("tool") == "dock_molecules":
            be = r.get("result", {}).get("best_be")
            if be is not None and be < best:
                best = be
    return best


def summarize_round(round_num: int) -> dict | None:
    """汇总某一实验轮次的结果。"""
    records = read_experiments()
    round_records = [r for r in records if r.get("round") == round_num]
    if not round_records:
        return None

    dock_record = None
    gen_record = None
    for r in round_records:
        if r.get("tool") == "dock_molecules":
            dock_record = r
        elif r.get("tool") == "generate_molecules":
            gen_record = r

    return {
        "round": round_num,
        "generated": gen_record.get("result", {}).get("output_count") if gen_record else None,
        "docked": dock_record.get("result", {}).get("successful") if dock_record else None,
        "best_be": dock_record.get("result", {}).get("best_be") if dock_record else None,
        "strategy": gen_record.get("params", {}).get("strategy") if gen_record else None,
    }


def clear_experiments() -> None:
    """清空实验记录（谨慎使用）。"""
    if EXPERIMENTS_FILE.exists():
        EXPERIMENTS_FILE.unlink()
