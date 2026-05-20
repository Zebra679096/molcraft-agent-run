# Code Evolution - Round 1

## Hypothesis: H001 - Expand RETRO_RULES for Fewer Trivial Routes

### Changes Made

**File: `src/synthesis_v2.py`**

1. **Added heterocycle retro rules** (pyrazole, triazole, benzothiadiazole):
   - Pyrazole: `c1cn[nH]c1>>N.N.C=O`
   - Triazole: `c1n[nH]nn1>>N.N.N`
   - Benzothiadiazole: `c1ccc2nsnc2c1>>Nc1ccccc1N.S`

2. **Added Negishi coupling** variant for biaryl synthesis

3. **Added N-alkyl sulfonamide rule** for better sulfonamide coverage

4. **Added N-oxide and sulfoxide reduction rules**:
   - N-oxide: `[n+]([O-])>>[n].O`
   - Sulfoxide: `[S](=O)>>[S].O`
   - Aryl sulfone: `[c][S](=O)(=O)[c]>>[c][S][c].O`

5. **Added acetal/ketal hydrolysis rules**

6. **Fixed trivial route detection logic**:
   - Previously: trivial if all sub-routes trivial AND single reactant == original smiles
   - Now: also detects trivial if fragment list only contains the original molecule
   - BRICS break with 2+ different fragments → always non-trivial
   - Single non-simple reactant → non-trivial

### Validation
- `generate_molecules`: OK
- `plan_synthesis_v2('c1ccc(cc1)S(=O)(=O)Nc2ccccc2')`: Non-trivial route via sulfonyl chloride + aniline ✓

### Expected Impact
- Fewer molecules falling back to trivial routes
- More diverse, realistic synthesis pathways
- Higher route_score (30% of total)
