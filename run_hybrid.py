#!/usr/bin/env python3
"""三阶段混合方案：RAG冷启动 → 进化搜索 → 精修提交

纯 Python 脚本，不依赖 LLM Agent，直接运行进化流水线。
绕过 DeepSeek API 超时问题。
"""
import sys
import os
import csv
import json
import time
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "src"))

from literature_seeds import generate_literature_seeds
from evolution import run_evolution, refine_top_molecules, compute_fitness
from synthesis_v2 import plan_synthesis_v2
from evaluator import evaluate_molecule, passes_filters
from receptor import prepare_receptor


def log(msg):
    ts = datetime.now().isoformat()
    print(f"[{ts}] {msg}", flush=True)


def main():
    start_time = time.time()
    
    log("=" * 60)
    log("三阶段混合方案：RAG冷启动 → 进化搜索 → 精修提交")
    log("=" * 60)
    
    # ==========================================
    # 阶段1：RAG冷启动
    # ==========================================
    log("\n" + "=" * 60)
    log("阶段1：RAG冷启动 - 从文献知识库提取种子分子")
    log("=" * 60)
    
    seeds = generate_literature_seeds(n_seeds=20, strategy="diverse")
    seed_smiles = [s["smiles"] for s in seeds]
    log(f"获取 {len(seeds)} 个种子分子")
    log(f"种子 QED 范围: {min(s['qed'] for s in seeds):.3f} - {max(s['qed'] for s in seeds):.3f}")
    log(f"种子 SA 范围: {min(s['sa_score'] for s in seeds):.1f} - {max(s['sa_score'] for s in seeds):.1f}")
    
    # ==========================================
    # 阶段2：进化搜索
    # ==========================================
    log("\n" + "=" * 60)
    log("阶段2：进化搜索 - 多代进化搜索化学空间")
    log("=" * 60)
    
    # 准备受体
    prepare_receptor()
    
    # 运行进化搜索（5代，种群20）
    evolved = run_evolution(
        seed_smiles=seed_smiles,
        n_generations=5,
        pop_size=20,
        n_elite=4,
        n_explore=8,
        w_binding=0.5,
        w_qed=0.3,
        w_sa=0.2,
        verbose=True,
    )
    log(f"进化搜索完成：{len(evolved)} 个分子")
    
    if evolved:
        best = evolved[0]
        log(f"最佳适应度: {best.get('fitness', 'N/A')}")
        log(f"最佳结合能: {best.get('binding_energy', 'N/A')} kcal/mol")
        log(f"最佳QED: {best.get('qed', 'N/A')}")
        log(f"最佳SA: {best.get('sa_score', 'N/A')}")
    
    # ==========================================
    # 阶段2.5：精修搜索
    # ==========================================
    log("\n" + "=" * 60)
    log("阶段2.5：精修搜索 - 对top分子进行局部搜索")
    log("=" * 60)
    
    # 取 top-10 进行精修
    top_for_refine = evolved[:10]
    top_smiles = [m["smiles"] for m in top_for_refine]
    
    refined = refine_top_molecules(
        top_molecules=top_for_refine,
        n_refine_rounds=2,
        n_offspring_per_seed=3,
        verbose=True,
    )
    log(f"精修完成：{len(refined)} 个分子")
    
    # 合并进化 + 精修结果
    all_molecules = evolved + refined
    
    # 去重
    seen = set()
    unique = []
    for m in all_molecules:
        smi = m.get("smiles", "")
        if smi and smi not in seen:
            seen.add(smi)
            unique.append(m)
    
    # 按适应度排序
    unique.sort(key=lambda x: x.get("fitness", 0), reverse=True)
    log(f"合并去重后：{len(unique)} 个独特分子")
    
    # ==========================================
    # 阶段3：逆合成验证 + 提交
    # ==========================================
    log("\n" + "=" * 60)
    log("阶段3：逆合成验证 + 提交")
    log("=" * 60)
    
    # 筛选满足硬约束的分子
    valid_molecules = []
    for m in unique:
        if m.get("binding_energy") is None:
            continue
        if m.get("binding_energy", 0) >= -7.0:
            continue  # 结合能不够好
        if m.get("qed", 0) < 0.3:
            continue
        if m.get("sa_score", 10) > 6.0:
            continue
        valid_molecules.append(m)
    
    log(f"满足硬约束的分子: {len(valid_molecules)} (binding<-7, QED>=0.3, SA<=6.0)")
    
    # 如果满足硬约束的分子不够25个，放宽结合能要求
    if len(valid_molecules) < 25:
        log("满足硬约束的分子不足25个，放宽结合能要求...")
        valid_molecules = []
        for m in unique:
            if m.get("binding_energy") is None:
                continue
            if m.get("qed", 0) < 0.3:
                continue
            if m.get("sa_score", 10) > 6.0:
                continue
            valid_molecules.append(m)
        log(f"放宽后满足约束的分子: {len(valid_molecules)}")
    
    # 逆合成规划
    results = []
    trivial_count = 0
    for i, mol in enumerate(valid_molecules[:40]):  # 多规划一些，以备替换
        smiles = mol["smiles"]
        log(f"逆合成规划 {i+1}/{min(len(valid_molecules), 40)}: {smiles[:50]}...")
        syn = plan_synthesis_v2(smiles)
        route = syn.get("route", f"{smiles}>>{smiles}") if syn.get("success") else f"{smiles}>>{smiles}"
        is_trivial = syn.get("trivial", False) or route == f"{smiles}>>{smiles}"
        
        if not is_trivial:
            results.append({
                "mol_smiles": smiles,
                "route": route,
                "binding_energy": mol.get("binding_energy"),
                "qed": mol.get("qed"),
                "sa_score": mol.get("sa_score"),
                "fitness": mol.get("fitness"),
            })
        else:
            trivial_count += 1
            log(f"  [TRIVIAL] 跳过")
        
        if len(results) >= 25:
            break
    
    log(f"逆合成完成：{len(results)} 个非trivial, {trivial_count} 个trivial")
    
    # 如果非trivial不够25个，添加trivial的也行（总比没有好）
    if len(results) < 25:
        log("非trivial分子不足25个，添加trivial路线的分子...")
        for mol in valid_molecules[:40]:
            smiles = mol["smiles"]
            if any(r["mol_smiles"] == smiles for r in results):
                continue
            syn = plan_synthesis_v2(smiles)
            route = syn.get("route", f"{smiles}>>{smiles}") if syn.get("success") else f"{smiles}>>{smiles}"
            results.append({
                "mol_smiles": smiles,
                "route": route,
                "binding_energy": mol.get("binding_energy"),
                "qed": mol.get("qed"),
                "sa_score": mol.get("sa_score"),
                "fitness": mol.get("fitness"),
            })
            if len(results) >= 25:
                break
    
    # 最终取25个
    final_results = results[:25]
    
    # ==========================================
    # 写入 result.csv
    # ==========================================
    output_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output")
    os.makedirs(output_dir, exist_ok=True)
    csv_path = os.path.join(output_dir, "result.csv")
    
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["mol_smiles", "route"])
        writer.writeheader()
        for row in final_results:
            writer.writerow({"mol_smiles": row["mol_smiles"], "route": row["route"]})
    
    log(f"\n结果已写入 {csv_path}")
    
    # ==========================================
    # 统计输出
    # ==========================================
    log("\n" + "=" * 60)
    log("最终统计")
    log("=" * 60)
    
    energies = [r["binding_energy"] for r in final_results if r.get("binding_energy")]
    qeds = [r["qed"] for r in final_results if r.get("qed")]
    sas = [r["sa_score"] for r in final_results if r.get("sa_score")]
    n_trivial = sum(1 for r in final_results if r["route"] == f"{r['mol_smiles']}>>{r['mol_smiles']}")
    
    log(f"总分子数: {len(final_results)}")
    if energies:
        log(f"结合能范围: {min(energies):.3f} ~ {max(energies):.3f} kcal/mol")
        log(f"平均结合能: {sum(energies)/len(energies):.3f} kcal/mol")
    if qeds:
        log(f"QED范围: {min(qeds):.3f} ~ {max(qeds):.3f}")
        log(f"平均QED: {sum(qeds)/len(qeds):.3f}")
    if sas:
        log(f"SA范围: {min(sas):.1f} ~ {max(sas):.1f}")
        log(f"平均SA: {sum(sas)/len(sas):.1f}")
    log(f"非trivial路线: {len(final_results) - n_trivial}/{len(final_results)}")
    
    total_time = time.time() - start_time
    log(f"\n总耗时: {total_time/60:.1f} 分钟")
    log("完成！")


if __name__ == "__main__":
    main()
