# Experiment Log — v4 Pharmacophore-Driven Iteration

Baseline from v3 (structure-guided + canonical fix):
- Best BE: -8.524 kcal/mol
- COOH molecules: 8 (BE range: -8.524 to -6.742)
- Legacy molecules: 12 (BE: N/A, from previous iterations)
- Trivial route %: 0%
- All SMILES canonical, all routes atom-balanced

---

## Experiment E001 — Baseline with 5HT1A Pharmacophore Design

**Hypothesis**: H001 — (to be defined by Agent)
**Date**: (auto)
**Previous best**: BE = -8.524 kcal/mol

### Changes
- New program.md with pharmacophore-driven iteration framework
- 5HT1A-specific pharmacophore model (P1-P5)
- Hypothesis-based design instead of random exploration

### Results
| Metric | Value | Previous (v3) | Delta |
|--------|-------|---------------|-------|
| Best BE | | -8.524 | |
| Avg BE (top 10) | | N/A | |
| QED mean | | N/A | |
| SA mean | | N/A | |
| Trivial route % | | 0% | |
| Molecules submitted | | 20 | |

### Analysis
(Agent will fill this after running)

### Decision
- [ ] CONFIRMED
- [ ] INCONCLUSIVE
- [ ] REJECTED
