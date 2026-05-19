# Diagnosis - Round 1

## Hypothesis H001: Improve Retro-Synthesis Route Quality by Expanding RETRO_RULES

### Observation
The synthesis_v2.py module has 50+ retro rules, but analysis of the trivial route behavior in `plan_synthesis_recursive` shows that:
1. When a molecule cannot be matched by any retro rule, it falls back to a trivial route (`{smiles}>>{smiles}`)
2. The BRICS fallback often produces fragments that are themselves treated as trivial
3. Many complex molecules that could be broken down with additional rules end up with trivial routes

### Proposed Improvement
Expand the RETRO_RULES in `synthesis_v2.py` to add more specific reaction types that cover:
- **Suzuki coupling** (biaryl formation): Already has one rule but can be improved
- **C-N coupling** (Buchwald-Hartwig): Already present but patterns can be refined
- **Ether cleavage** and **reductive amination**: Better SMARTS patterns
- **Nitrile hydrolysis**: Already present
- **More heterocycle synthesis rules**: Expanded thiazole, imidazole, oxazole patterns

### Expected Impact
- **Trivial route ratio**: Reduce from estimated ~40% to ~20%
- **Route score**: Increase by ~15-20% (routes are a major scoring component)
- **Total score**: Moderate improvement through route_score (30% weight)

### Risk Assessment
- Low risk: Adding more retro rules cannot cause errors, only additional matching opportunities
- If rules are too aggressive, some may not produce chem valid intermediates → gracefully handled by validation
