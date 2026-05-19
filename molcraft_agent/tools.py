"""MolCraft Agent 自定义工具定义。

这些工具封装了分子生成、对接、评估和逆合成能力，
供 Kimi CLI Agent 通过 tool_calls 自主调用。

每次工具调用后自动记录到 experiments.jsonl。
"""
import asyncio
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), "src"))

from pydantic import BaseModel, Field
from kimi_agent_sdk import CallableTool2, ToolError, ToolOk, ToolReturnValue

from generator import generate_molecules
from docking import batch_dock
from synthesis_v2 import plan_synthesis_v2
from evaluator import evaluate_molecule
from receptor import prepare_receptor
from evolution import run_evolution, refine_top_molecules, compute_fitness
from literature_seeds import generate_literature_seeds
from molcraft_agent.experiments import (
    append_experiment,
    get_latest_round,
    get_best_binding_energy,
)


class GenerateParams(BaseModel):
    strategy: str = Field(
        default="mutate",
        description="生成策略: mutate(变异), combine(组合), random(随机)",
    )
    n: int = Field(default=30, description="要生成的分子数量，建议 20-50")
    scaffold: str | None = Field(
        default=None,
        description="可选的种子骨架 SMILES，用于指导生成方向",
    )


class GenerateMolecules(CallableTool2):
    name: str = "generate_molecules"
    description: str = (
        "生成候选药物分子。返回分子 SMILES 列表及其关键性质（QED、MW、LogP）。"
        "运行时间取决于分子数量，通常 5-20 秒。"
    )
    params: type[BaseModel] = GenerateParams

    async def __call__(self, params: GenerateParams) -> ToolReturnValue:
        try:
            mols = await asyncio.to_thread(
                generate_molecules,
                strategy=params.strategy,
                n_molecules=params.n,
                scaffold=params.scaffold,
            )
            result = {
                "count": len(mols),
                "molecules": [
                    {
                        "smiles": m["smiles"],
                        "qed": m["qed"],
                        "mw": m["mw"],
                        "logp": m["logp"],
                        "sa_score": m["sa_score"],
                    }
                    for m in mols
                ],
            }
            # 自动记录实验
            append_experiment(
                tool="generate_molecules",
                round_num=get_latest_round() + 1,
                params={"strategy": params.strategy, "n": params.n, "scaffold": params.scaffold},
                result={"output_count": len(mols), "top_qed": mols[0]["qed"] if mols else None},
            )
            return ToolOk(output=json.dumps(result, ensure_ascii=False))
        except Exception as exc:
            return ToolError(
                output="",
                message=str(exc),
                brief="分子生成失败",
            )


class DockParams(BaseModel):
    smiles_list: list[str] = Field(
        description="要对接的分子 SMILES 列表，建议一次不超过 25 个",
    )


class DockMolecules(CallableTool2):
    name: str = "dock_molecules"
    description: str = (
        "批量对分子进行分子对接，计算与靶点的结合自由能（binding_energy，kcal/mol）。"
        "结合能越低（越负）越好，<-7 为优秀。运行时间与分子数量成正比，每个分子约 5-15 秒。"
    )
    params: type[BaseModel] = DockParams

    async def __call__(self, params: DockParams) -> ToolReturnValue:
        try:
            await asyncio.to_thread(prepare_receptor)
            mols = [{"smiles": s} for s in params.smiles_list]
            results = await asyncio.to_thread(batch_dock, mols)
            successful = [r for r in results if r.get("success")]
            successful.sort(key=lambda x: x.get("binding_energy", 999))
            top_be = [r.get("binding_energy") for r in successful[:5]]
            output = {
                "total_submitted": len(params.smiles_list),
                "successful": len(successful),
                "failed": len(params.smiles_list) - len(successful),
                "best_be": top_be[0] if top_be else None,
                "top_results": [
                    {
                        "smiles": r["smiles"],
                        "binding_energy": r.get("binding_energy"),
                        "qed": r.get("qed"),
                    }
                    for r in successful[:10]
                ],
            }
            # 自动记录实验
            append_experiment(
                tool="dock_molecules",
                round_num=get_latest_round(),
                params={"n": len(params.smiles_list)},
                result={
                    "successful": len(successful),
                    "failed": len(params.smiles_list) - len(successful),
                    "best_be": top_be[0] if top_be else None,
                    "top5_be": top_be,
                },
            )
            return ToolOk(output=json.dumps(output, ensure_ascii=False))
        except Exception as exc:
            return ToolError(
                output="",
                message=str(exc),
                brief="分子对接失败",
            )


class SynthesizeParams(BaseModel):
    smiles: str = Field(description="目标分子的 SMILES 字符串")


class PlanSynthesis(CallableTool2):
    name: str = "plan_synthesis"
    description: str = (
        "为目标分子规划逆合成路线，返回 SMILES>>SMILES 格式的反应路线。"
        "支持酰胺、磺酰胺、酯、醚等常见反应类型。"
    )
    params: type[BaseModel] = SynthesizeParams

    async def __call__(self, params: SynthesizeParams) -> ToolReturnValue:
        try:
            result = await asyncio.to_thread(plan_synthesis_v2, params.smiles)
            output = {
                "smiles": params.smiles,
                "success": result.get("success"),
                "route": result.get("route"),
                "steps": result.get("steps"),
            }
            # 自动记录实验
            append_experiment(
                tool="plan_synthesis",
                round_num=get_latest_round(),
                params={"smiles": params.smiles},
                result={"route": result.get("route"), "steps": result.get("steps")},
            )
            return ToolOk(output=json.dumps(output, ensure_ascii=False))
        except Exception as exc:
            return ToolError(
                output="",
                message=str(exc),
                brief="逆合成规划失败",
            )


class EvaluateParams(BaseModel):
    smiles: str = Field(description="要评估的分子的 SMILES 字符串")


class EvaluateMolecule(CallableTool2):
    name: str = "evaluate_molecule"
    description: str = (
        "评估单个分子的药物相似性和理化性质，包括 QED、分子量、LogP、"
        "氢键供体/受体数、可旋转键数、SA score 和 Lipinski 五规则通过情况。"
    )
    params: type[BaseModel] = EvaluateParams

    async def __call__(self, params: EvaluateParams) -> ToolReturnValue:
        try:
            result = await asyncio.to_thread(evaluate_molecule, params.smiles)
            output = {
                "smiles": params.smiles,
                "valid": result.get("valid"),
                "qed": result.get("qed"),
                "mw": result.get("mw"),
                "logp": result.get("logp"),
                "tpsa": result.get("tpsa"),
                "sa_score": result.get("sa_score"),
                "lipinski_pass": result.get("lipinski_pass"),
            }
            # 自动记录实验
            append_experiment(
                tool="evaluate_molecule",
                round_num=get_latest_round(),
                params={"smiles": params.smiles},
                result={
                    "qed": result.get("qed"),
                    "mw": result.get("mw"),
                    "logp": result.get("logp"),
                    "sa_score": result.get("sa_score"),
                },
            )
            return ToolOk(output=json.dumps(output, ensure_ascii=False))
        except Exception as exc:
            return ToolError(
                output="",
                message=str(exc),
                brief="分子评估失败",
            )


class ReportIterationParams(BaseModel):
    round_num: int = Field(description="当前迭代轮次（从1开始）")
    hypothesis_id: str = Field(description="本轮验证的假设ID，如 H001")
    success: bool = Field(description="假设是否被验证成功")
    summary: str = Field(
        description="迭代结果摘要，包含关键指标变化（如结合能、QED、trivial route比例）",
    )


class ReportIteration(CallableTool2):
    name: str = "report_iteration"
    description: str = (
        "报告当前迭代已完成。每完成一轮「文献→诊断→改代码→实验验证」的完整闭环后必须调用一次，"
        "main.py 通过此工具的调用来统计迭代次数并控制运行终止。"
    )
    params: type[BaseModel] = ReportIterationParams

    async def __call__(self, params: ReportIterationParams) -> ToolReturnValue:
        try:
            record = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "round": params.round_num,
                "hypothesis_id": params.hypothesis_id,
                "success": params.success,
                "summary": params.summary,
            }
            log_path = Path("docs/iteration_log.jsonl")
            log_path.parent.mkdir(exist_ok=True)
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")

            output = {
                "status": "recorded",
                "round": params.round_num,
                "message": f"第 {params.round_num} 轮迭代已记录",
            }
            return ToolOk(output=json.dumps(output, ensure_ascii=False))
        except Exception as exc:
            return ToolError(
                output="",
                message=str(exc),
                brief="迭代记录失败",
            )


# ============================================================
# 新增工具：RAG冷启动 + 进化搜索 + 精修
# ============================================================


class SeedFromLiteratureParams(BaseModel):
    n_seeds: int = Field(
        default=20,
        description="目标种子数量，建议 15-30",
    )
    strategy: str = Field(
        default="diverse",
        description="种子生成策略: diverse(多样性), cns(CNS渗透性优先), focused(药效团聚焦)",
    )


class SeedFromLiterature(CallableTool2):
    name: str = "seed_from_literature"
    description: str = (
        "从文献和药物化学知识库中提取活性骨架作为种子分子（RAG冷启动）。"
        "包含CNS药物常见骨架（吲哚、喹唑啉、哌啶、磺酰胺等），以及从竞赛论文中提取的信息。"
        "运行时间约 5-15 秒。返回种子分子的 SMILES 和性质评估。"
    )
    params: type[BaseModel] = SeedFromLiteratureParams

    async def __call__(self, params: SeedFromLiteratureParams) -> ToolReturnValue:
        try:
            seeds = await asyncio.to_thread(
                generate_literature_seeds,
                n_seeds=params.n_seeds,
                strategy=params.strategy,
            )
            result = {
                "count": len(seeds),
                "strategy": params.strategy,
                "seeds": [
                    {
                        "smiles": s["smiles"],
                        "qed": s["qed"],
                        "sa_score": s["sa_score"],
                        "mw": s["mw"],
                        "tpsa": s.get("tpsa", 0),
                    }
                    for s in seeds
                ],
            }
            append_experiment(
                tool="seed_from_literature",
                round_num=get_latest_round() + 1,
                params={"n_seeds": params.n_seeds, "strategy": params.strategy},
                result={"seed_count": len(seeds)},
            )
            return ToolOk(output=json.dumps(result, ensure_ascii=False))
        except Exception as exc:
            return ToolError(
                output="",
                message=str(exc),
                brief="文献种子生成失败",
            )


class EvolveParams(BaseModel):
    seed_smiles: list[str] | None = Field(
        default=None,
        description="种子分子SMILES列表（来自seed_from_literature或之前的结果），为空则使用默认骨架",
    )
    n_generations: int = Field(
        default=8,
        description="进化代数，建议 6-10。代数越多搜索越充分但耗时越长",
    )
    pop_size: int = Field(
        default=30,
        description="每代种群大小，建议 20-40",
    )
    n_elite: int = Field(
        default=5,
        description="每代精英保留数量，建议 3-8",
    )
    n_explore: int = Field(
        default=10,
        description="每代注入的全新探索个体数量，建议 5-15",
    )
    w_binding: float = Field(
        default=0.5,
        description="结合能权重(0-1)，越高越重视结合能优化",
    )
    w_qed: float = Field(
        default=0.3,
        description="QED权重(0-1)，越高越重视药物相似性",
    )
    w_sa: float = Field(
        default=0.2,
        description="SA score权重(0-1)，越高越重视可合成性",
    )


class EvolveMolecules(CallableTool2):
    name: str = "evolve_molecules"
    description: str = (
        "运行多代进化搜索：种群多样性保证搜索广度，对接打分提供方向，"
        "自适应变异从探索过渡到精修。"
        "每次调用运行 n_generations 代进化，每代包含生成+对接+选择。"
        "运行时间取决于代数和种群大小，通常 10-30 分钟。"
        "返回所有评估过的分子，按综合适应度降序排列。"
    )
    params: type[BaseModel] = EvolveParams

    async def __call__(self, params: EvolveParams) -> ToolReturnValue:
        try:
            result = await asyncio.to_thread(
                run_evolution,
                seed_smiles=params.seed_smiles,
                n_generations=params.n_generations,
                pop_size=params.pop_size,
                n_elite=params.n_elite,
                n_explore=params.n_explore,
                w_binding=params.w_binding,
                w_qed=params.w_qed,
                w_sa=params.w_sa,
            )
            # 汇总输出（限制返回 top-50 以免过大）
            top_results = result[:50]
            output = {
                "total_molecules": len(result),
                "n_generations": params.n_generations,
                "pop_size": params.pop_size,
                "best_fitness": top_results[0]["fitness"] if top_results else None,
                "best_binding_energy": top_results[0].get("binding_energy") if top_results else None,
                "best_qed": top_results[0].get("qed") if top_results else None,
                "best_sa": top_results[0].get("sa_score") if top_results else None,
                "top_results": [
                    {
                        "smiles": m["smiles"],
                        "binding_energy": m.get("binding_energy"),
                        "qed": m.get("qed"),
                        "sa_score": m.get("sa_score"),
                        "fitness": m.get("fitness"),
                        "mw": m.get("mw"),
                        "generation": m.get("generation"),
                        "source": m.get("source"),
                    }
                    for m in top_results
                ],
            }
            append_experiment(
                tool="evolve_molecules",
                round_num=get_latest_round() + 1,
                params={
                    "n_generations": params.n_generations,
                    "pop_size": params.pop_size,
                    "n_elite": params.n_elite,
                    "seed_count": len(params.seed_smiles) if params.seed_smiles else 0,
                },
                result={
                    "total_molecules": len(result),
                    "best_be": output["best_binding_energy"],
                    "best_fitness": output["best_fitness"],
                },
            )
            return ToolOk(output=json.dumps(output, ensure_ascii=False))
        except Exception as exc:
            return ToolError(
                output="",
                message=str(exc),
                brief="进化搜索失败",
            )


class RefineParams(BaseModel):
    top_smiles: list[str] = Field(
        description="待精修的top分子SMILES列表，建议 5-15 个",
    )
    n_rounds: int = Field(
        default=3,
        description="精修轮次，建议 2-4",
    )
    n_offspring: int = Field(
        default=5,
        description="每个种子每轮产生的变体数，建议 3-8",
    )


class RefineMolecules(CallableTool2):
    name: str = "refine_molecules"
    description: str = (
        "对top分子进行精修搜索：低变异强度 + 严格过滤。"
        "在最优分子附近微调，期望找到结合能更好且性质更优的变体。"
        "运行时间通常 5-15 分钟。返回精修后的分子列表。"
    )
    params: type[BaseModel] = RefineParams

    async def __call__(self, params: RefineParams) -> ToolReturnValue:
        try:
            top_molecules = [{"smiles": s} for s in params.top_smiles]
            result = await asyncio.to_thread(
                refine_top_molecules,
                top_molecules=top_molecules,
                n_refine_rounds=params.n_rounds,
                n_offspring_per_seed=params.n_offspring,
            )
            top_results = result[:30]
            output = {
                "total_molecules": len(result),
                "n_rounds": params.n_rounds,
                "best_fitness": top_results[0]["fitness"] if top_results else None,
                "best_binding_energy": top_results[0].get("binding_energy") if top_results else None,
                "top_results": [
                    {
                        "smiles": m["smiles"],
                        "binding_energy": m.get("binding_energy"),
                        "qed": m.get("qed"),
                        "sa_score": m.get("sa_score"),
                        "fitness": m.get("fitness"),
                    }
                    for m in top_results
                ],
            }
            append_experiment(
                tool="refine_molecules",
                round_num=get_latest_round(),
                params={"n_molecules": len(params.top_smiles), "n_rounds": params.n_rounds},
                result={
                    "total": len(result),
                    "best_be": output["best_binding_energy"],
                },
            )
            return ToolOk(output=json.dumps(output, ensure_ascii=False))
        except Exception as exc:
            return ToolError(
                output="",
                message=str(exc),
                brief="分子精修失败",
            )
