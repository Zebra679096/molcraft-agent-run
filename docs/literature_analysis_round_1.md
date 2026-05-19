# Literature Analysis - Round 1

## Summary of Papers

### Paper 1: Deep Lead Optimization (JACS)
- **Core concept**: Lead optimization has 4 subtasks: scaffold hopping, linker design, fragment replacement, and side-chain decoration
- **Key strategies for molcraft**:
  - Scaffold hopping: Keep 3D shape similarity while changing 2D scaffold → avoid patent constraints while maintaining activity
  - Side-chain decoration: Keep active scaffold, optimize side chains
  - Molecular decomposition: BM scaffold decomposition, RECAP/BRICS fragmentation, MMP pairing
  - Key constraints: QED (drug-likeness), SAScore (synthesizability), 3D similarity
  - Reinforcement learning: Use RL to control QED, SA, LogP (DRLinker success rate >90%)

### Paper 2: Coscientist (Nature)
- **Core concept**: Multi-LLM collaborative agent system with Planner, Web Searcher, Docs Searcher, Code Execution modules
- **Key strategies for molcraft**:
  - Agent architecture: Planner coordinates specialized modules with clear responsibilities
  - Self-correction: Agent can auto-fix based on code execution errors
  - Document vector retrieval: Use vector search for API documentation (max 7800 tokens)
  - Safety mechanism: Reject synthesis of known hazardous substances

### Paper 3: Autonomous Agents for Scientific Discovery (Review)
- **Core concept**: Three-stage framework: Hypothesis Discovery → Experiment Design & Execution → Result Analysis & Refinement
- **Key strategies for molcraft**:
  - Information entropy framework: Scientific discovery progresses from high entropy (uncertainty) to low entropy (verifiability)
  - Tool use taxonomy: RAG planning, template predefinition, post-execution feedback, toolbox, reflective iterative
  - Self-correction: Agent auto-adjusts hypotheses based on experimental results
  - Multi-agent collaboration: Multiple agents simulate research team, collective intelligence > single agent

## Applicable Strategies for MolCraft

1. **Scaffold Hopping & Side-chain Decoration**: Use CNS-relevant scaffolds (indole, quinazoline, piperidine) as starting points and optimize via mutation
2. **Post-Execution Feedback**: After docking results, use binding energy as fitness function to guide next generation
3. **Diverse Initial Population**: Essential for evolutionary search to avoid premature convergence (MOOSE-Chem)
4. **Rule Coverage Expansion**: More retro-synthesis rules → fewer trivial routes → higher route_score
5. **SA Score Improvement**: SA score is a rough heuristic; try to generate molecules with SA <= 5 to stay well below the SA>6 hard zero
