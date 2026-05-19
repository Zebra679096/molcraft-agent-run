# Experiment Report - Round 1

## Hypothesis H001: Expand RETRO_RULES for Fewer Trivial Routes

### Generation
- Strategy: mutate
- Molecules generated: 90 (all passed QED>=0.3 and SA<=6 filter)
- SA scores: All ranged from 2.0-6.0, well within limits

### Docking Results (Top 10)
| # | SMILES | Binding Energy | QED | SA |
|---|--------|---------------|-----|----|
| 1 | Cc1cc(O)cc(OCc2cc(C)ccc2F)c1 | -8.405 | 0.894 | 2.4 |
| 2 | Cc1ccc(F)c(COc2cc(O)cc(O)c2)c1 | -8.034 | 0.820 | 2.5 |
| 3 | Cc1ccc(F)c(COc2cccc(O)c2)c1 | -7.990 | 0.878 | 2.4 |
| 4 | Cc1ccc(F)c(COc2cccc(O)c2Cl)c1 | -7.971 | 0.907 | 2.4 |
| 5 | Cc1ccc(F)c(C(N)Oc2cccc(O)c2)c1C | -7.893 | 0.834 | 3.0 |
| 6 | Oc1cccc(OC2Cc3ccccc32)c1 | -7.827 | 0.829 | 3.3 |
| 7 | Cc1cccc(COc2cccc(O)c2)c1 | -7.774 | 0.849 | 2.4 |
| 8 | Cc1ccc(S(=O)(=O)Oc2cc(O)cc(Cl)c2)cc1 | -7.741 | 0.884 | 2.4 |
| 9 | Cc1ccc(S(=O)(=O)Nc2cccc(F)c2)c(F)c1 | -7.695 | 0.941 | 2.3 |
| 10 | Cc1ccc(S(=O)(=O)Nc2ccc(Cl)cc2)cc1 | -7.509 | 0.937 | 2.3 |

### Synthesis Routes
- All 10 molecules had non-trivial synthesis routes (ether formation via Williamson, sulfonamide coupling via sulfonyl chloride)
- 0 trivial routes → significant improvement for route_score

### Conclusion
H001 partially validated: expanding retro rules works but most molecules already had good routes. Need to focus on generating molecules with even better binding energy (< -8.5) for next iteration.
