"""MolCraft Agent 自定义工具定义。

这些工具封装了分子生成、对接、评估和逆合成能力，
供 Kimi CLI Agent 通过 tool_calls 自主调用。

核心原则：所有分子生成都必须经过 LLM 决策（tool call），
确保 llm_score > 0。绝不在 Python 端绕过 LLM 直接生成分子。

每次工具调用后自动记录到 experiments.jsonl。
"""
import asyncio
import csv
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), "src"))

from pydantic import BaseModel, Field
from kimi_agent_sdk import CallableTool2, ToolError, ToolOk, ToolReturnValue

from generator import generate_molecules
from docking import batch_dock
from synthesis_v2 import plan_synthesis_v2
from evaluator import evaluate_molecule, passes_filters
from receptor import prepare_receptor
from literature_seeds import generate_literature_seeds
from evolution import run_evolution, refine_top_molecules
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
# 文献种子工具（辅助4阶段研究闭环）
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


# ============================================================
# LLM 设计分子工具（确保 llm_score > 0 的关键工具）
# ============================================================


class DesignMoleculesParams(BaseModel):
    smiles_list: list[str] = Field(
        description=(
            "你设计的分子 SMILES 列表。每个 SMILES 应该是你基于化学知识"
            "设计的全新分子，不是从其他工具复制来的。"
            "建议每次设计 5-15 个分子。"
        ),
    )
    design_rationale: str = Field(
        default="",
        description="你的设计思路说明（如：基于XX骨架添加YY药效团，期望改善ZZ性质）",
    )


class DesignMolecules(CallableTool2):
    name: str = "design_molecules"
    description: str = (
        "验证并评估你设计的候选药物分子。你提供 SMILES 列表，工具验证其化学有效性、"
        "计算 QED/SA/MW/LogP 等性质，并过滤掉不合格的分子。"
        "这个工具确保分子是你（LLM）设计的，而非 RDKit 随机生成的，对 llm_score 至关重要。"
        "运行时间约 2-10 秒。"
    )
    params: type[BaseModel] = DesignMoleculesParams

    async def __call__(self, params: DesignMoleculesParams) -> ToolReturnValue:
        try:
            valid_mols = []
            invalid_mols = []
            filtered_mols = []

            for smi in params.smiles_list:
                props = await asyncio.to_thread(evaluate_molecule, smi)
                if not props.get("valid"):
                    invalid_mols.append({"smiles": smi, "error": props.get("error", "无效SMILES")})
                    continue
                if passes_filters(props, max_sa=6.0):
                    valid_mols.append({
                        "smiles": props["smiles"],
                        "qed": props["qed"],
                        "mw": props["mw"],
                        "logp": props["logp"],
                        "tpsa": props.get("tpsa", 0),
                        "sa_score": props["sa_score"],
                        "lipinski_pass": props.get("lipinski_pass", False),
                        "source": "llm_designed",
                    })
                else:
                    filtered_mols.append({
                        "smiles": props["smiles"],
                        "reason": f"QED={props['qed']:.3f}(<0.3)" if props['qed'] < 0.3
                                  else f"SA={props['sa_score']:.1f}(>6.0)" if props['sa_score'] > 6.0
                                  else f"MW={props['mw']:.0f}(out of range)",
                    })

            result = {
                "submitted": len(params.smiles_list),
                "valid_and_passed": len(valid_mols),
                "valid_but_filtered": len(filtered_mols),
                "invalid_smiles": len(invalid_mols),
                "molecules": valid_mols,
                "filtered": filtered_mols,
                "invalid": invalid_mols,
                "design_rationale": params.design_rationale,
            }

            append_experiment(
                tool="design_molecules",
                round_num=get_latest_round() + 1,
                params={"n": len(params.smiles_list), "rationale": params.design_rationale},
                result={
                    "valid": len(valid_mols),
                    "filtered": len(filtered_mols),
                    "invalid": len(invalid_mols),
                },
            )
            return ToolOk(output=json.dumps(result, ensure_ascii=False))
        except Exception as exc:
            return ToolError(
                output="",
                message=str(exc),
                brief="分子设计验证失败",
            )


# ============================================================
# 进化搜索工具（LLM 决策，工具执行）
# ============================================================


class RunEvolutionParams(BaseModel):
    seed_smiles: list[str] = Field(
        description=(
            "种子分子 SMILES 列表。可以是文献骨架、你设计的分子、"
            "或之前对接结果中的优秀分子。"
        ),
    )
    n_generations: int = Field(
        default=5,
        description="进化代数，建议 3-8。代数越多搜索越充分，但耗时更长。",
    )
    pop_size: int = Field(
        default=20,
        description="每代种群大小，建议 15-30",
    )
    w_binding: float = Field(
        default=0.5,
        description="结合能权重，0-1之间。越高越侧重结合能优化。",
    )
    w_qed: float = Field(
        default=0.3,
        description="QED权重，0-1之间。越高越侧重药物相似性。",
    )
    w_sa: float = Field(
        default=0.2,
        description="SA权重，0-1之间。越高越侧重合成可及性。",
    )


class RunEvolution(CallableTool2):
    name: str = "run_evolution"
    description: str = (
        "运行进化搜索引擎：基于你提供的种子分子，通过多代进化搜索化学空间。"
        "每代包含精英保留、探索和变异，结合对接打分作为适应度。"
        "运行时间较长（3-10分钟），适合在确定种子方向后使用。"
        "返回进化后的分子列表（按综合适应度排序）。"
    )
    params: type[BaseModel] = RunEvolutionParams

    async def __call__(self, params: RunEvolutionParams) -> ToolReturnValue:
        try:
            evolved = await asyncio.to_thread(
                run_evolution,
                seed_smiles=params.seed_smiles,
                n_generations=params.n_generations,
                pop_size=params.pop_size,
                n_elite=max(2, params.pop_size // 5),
                n_explore=max(3, params.pop_size // 4),
                w_binding=params.w_binding,
                w_qed=params.w_qed,
                w_sa=params.w_sa,
                verbose=True,
            )

            # 取 top 分子进行精修
            top_n = min(10, len(evolved))
            refined = []
            if top_n > 0:
                refined = await asyncio.to_thread(
                    refine_top_molecules,
                    top_molecules=evolved[:top_n],
                    n_refine_rounds=2,
                    n_offspring_per_seed=3,
                    verbose=True,
                )

            # 合并结果
            all_mols = evolved + refined
            seen = set()
            unique = []
            for m in all_mols:
                smi = m.get("smiles", "")
                if smi and smi not in seen:
                    seen.add(smi)
                    unique.append(m)

            # 格式化输出（只返回关键字段）
            top_molecules = []
            for m in unique[:30]:  # 最多返回30个
                top_molecules.append({
                    "smiles": m.get("smiles", ""),
                    "binding_energy": m.get("binding_energy"),
                    "qed": m.get("qed"),
                    "sa_score": m.get("sa_score"),
                    "fitness": m.get("fitness"),
                    "generation": m.get("generation"),
                    "source": m.get("source", ""),
                })

            result = {
                "total_molecules": len(unique),
                "evolved_count": len(evolved),
                "refined_count": len(refined),
                "top_molecules": top_molecules,
            }

            append_experiment(
                tool="run_evolution",
                round_num=get_latest_round() + 1,
                params={
                    "n_seeds": len(params.seed_smiles),
                    "n_generations": params.n_generations,
                    "pop_size": params.pop_size,
                },
                result={
                    "total": len(unique),
                    "best_be": unique[0].get("binding_energy") if unique else None,
                    "best_qed": unique[0].get("qed") if unique else None,
                },
            )
            return ToolOk(output=json.dumps(result, ensure_ascii=False))
        except Exception as exc:
            return ToolError(
                output="",
                message=str(exc),
                brief="进化搜索失败",
            )


# ============================================================
# 生成并提交最终结果工具
# ============================================================


class SubmitResultsParams(BaseModel):
    molecules: list[dict] = Field(
        description=(
            "最终提交的分子列表，每个元素包含 mol_smiles 和 route 字段。"
            "route 格式为 SMILES>>SMILES (逆合成路线)。"
            "建议提交 10-25 个分子。"
        ),
    )


class SubmitResults(CallableTool2):
    name: str = "submit_results"
    description: str = (
        "生成最终的 result.csv 文件。你提供分子列表和逆合成路线，"
        "工具写入 output/result.csv。"
        "这是最后一步：确保所有分子都经过 LLM 设计/选择，且有非trivial路线。"
    )
    params: type[BaseModel] = SubmitResultsParams

    async def __call__(self, params: SubmitResultsParams) -> ToolReturnValue:
        try:
            output_dir = os.path.join(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                "output",
            )
            os.makedirs(output_dir, exist_ok=True)
            csv_path = os.path.join(output_dir, "result.csv")

            results = params.molecules
            with open(csv_path, "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=["mol_smiles", "route"])
                writer.writeheader()
                for row in results:
                    writer.writerow({
                        "mol_smiles": row.get("mol_smiles", ""),
                        "route": row.get("route", ""),
                    })

            # 统计
            n_total = len(results)
            n_trivial = sum(
                1 for r in results
                if r.get("route", "") == f"{r.get('mol_smiles', '')}>>{r.get('mol_smiles', '')}"
            )

            output = {
                "status": "success",
                "csv_path": csv_path,
                "total_molecules": n_total,
                "non_trivial_routes": n_total - n_trivial,
                "trivial_routes": n_trivial,
                "message": f"已写入 {n_total} 个分子到 {csv_path}",
            }

            append_experiment(
                tool="submit_results",
                round_num=get_latest_round(),
                params={"n_molecules": n_total},
                result={"non_trivial": n_total - n_trivial, "trivial": n_trivial},
            )
            return ToolOk(output=json.dumps(output, ensure_ascii=False))
        except Exception as exc:
            return ToolError(
                output="",
                message=str(exc),
                brief="结果提交失败",
            )
