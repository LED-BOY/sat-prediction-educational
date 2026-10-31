# Predicting the search order in restricted SAT

This is a synthetic proof-of-concept, not evidence for P = NP. The special-variable set is supplied. A learned logistic model ranks assignments; an exact 2-SAT solver checks them.

## Results

| Test group | Ordering | Mean assignments tried | Worst assignments tried | Total time (ms) | Ordering/prediction (ms) |
|---|---|---:|---:|---:|---:|
| familiar (40) | fixed | 13.90 | 31 | 76.25 | 0.07 |
| familiar (40) | random | 15.45 | 31 | 85.83 | 0.59 |
| familiar (40) | majority | 8.62 | 25 | 47.66 | 1.99 |
| familiar (40) | learned | 7.95 | 27 | 44.73 | 2.11 |
| larger (32) | fixed | 63.16 | 125 | 833.48 | 0.15 |
| larger (32) | random | 65.66 | 128 | 870.15 | 1.16 |
| larger (32) | majority | 31.44 | 103 | 415.78 | 5.20 |
| larger (32) | learned | 28.66 | 113 | 382.27 | 5.39 |
| shifted (40) | fixed | 15.57 | 31 | 138.45 | 0.10 |
| shifted (40) | random | 14.65 | 32 | 129.44 | 0.67 |
| shifted (40) | majority | 32.00 | 32 | 281.72 | 2.94 |
| shifted (40) | learned | 32.00 | 32 | 281.95 | 3.08 |
| unsatisfiable (24) | fixed | 32.00 | 32 | 108.36 | 0.06 |
| unsatisfiable (24) | random | 32.00 | 32 | 109.72 | 0.40 |
| unsatisfiable (24) | majority | 32.00 | 32 | 109.85 | 1.25 |
| unsatisfiable (24) | learned | 32.00 | 32 | 109.89 | 1.36 |

Total time is the sum of per-instance medians from three repetitions. It includes formula simplification, SCC solving, feature extraction, candidate construction, scoring, and sorting. It excludes a separate full-answer verification that all successful answers pass. Runtime ratios are specific to this Python implementation and machine. Random ordering uses one fixed permutation per instance across repetitions.

## Data and what the model learns

Training uses 240 satisfiable formulas, with 20 base variables and 5 supplied special variables, plus auxiliary variables. Labels are obtained by running the exact baseline solver, not taken from hidden test labels. Each special variable is forced by 1–3 four-clause gadgets. Opposite-polarity distractor clauses add noise, while a planted assignment ensures satisfiability. Thus each satisfiable formula has a unique special-variable assignment, but possibly many full solutions.

The model is logistic regression, trained from scratch using gradient descent. Its inputs are a bias, normalized positive-minus-negative occurrence count, scaled raw difference, and total occurrence count. It scores each special bit independently; joint assignment ranking uses the sum of selected logits. A majority heuristic uses raw polarity counts without training. Both use the same candidate-scoring and sorting machinery.

Familiar tests contain new formulas generated like training. Larger tests have 100 base variables and 7 special variables. Shifted tests increase opposite-polarity distractors from 0–12 to 20–35 per special variable, deliberately breaking the learned correlation. Unsatisfiable tests append an independent two-variable contradiction that is unsatisfiable for every special-variable assignment. All groups are synthetic, and the shift is a constructed stress test, not a claim about natural SAT distributions.

## Interpretation

- **familiar:** learned ordering uses 7.95 assignments on average versus 13.90 fixed and 8.62 majority. Fixed/learned elapsed-time ratio: 1.70; majority/learned ratio: 1.07. A ratio above 1 favors learned ordering.
- **larger:** learned ordering uses 28.66 assignments on average versus 63.16 fixed and 31.44 majority. Fixed/learned elapsed-time ratio: 2.18; majority/learned ratio: 1.09. A ratio above 1 favors learned ordering.
- **shifted:** learned ordering uses 32.00 assignments on average versus 15.57 fixed and 32.00 majority. Fixed/learned elapsed-time ratio: 0.49; majority/learned ratio: 1.00. A ratio above 1 favors learned ordering.
- **unsatisfiable:** learned ordering uses 32.00 assignments on average versus 32.00 fixed and 32.00 majority. Fixed/learned elapsed-time ratio: 0.99; majority/learned ratio: 1.00. A ratio above 1 favors learned ordering.

Across this mixed test suite, fixed ordering totals 1156.54 ms and learned inference totals 818.84 ms. Label generation plus training cost 1454.39 ms, exceeding the inference savings of 337.70 ms. Including that setup, this run has no end-to-end speedup over fixed ordering.

Any advantage over fixed order must be compared with majority: a learned model can rediscover a cheap existing signal. No result here establishes that learning is necessary. Unsatisfiable instances require all branches in this implementation regardless of ordering. A production solver could detect the independent unsatisfiable core before enumeration; that optimization is absent for every method.

## Explicit worst-case failure of this learned model

For each special variable z, include the four clauses (z OR +/-a OR +/-b), using all four sign combinations. These force z=true. Add twenty clauses (NOT z OR u_j OR v_j), with fresh ordinary variables. All ordinary variables can be set true, so the formula is satisfiable. Each special variable has exactly 4 positive and 20 negative occurrences, independent of k.

The fitted model assigns each such variable logit -1.651745, strictly below zero. Every special variable must be true, yet the model prefers false for all of them. The unique satisfying special-variable assignment ranks last: the solver tries exactly 2^k branches. The formula has 24k clauses and 43k variables, so the branch count is exponential in the number of variables and superpolynomial in the encoded formula size when k grows freely. This is a counterexample to this fitted predictor and search strategy, not a lower bound for all predictors or SAT algorithms. The code checks the construction at k=8; identical per-variable features establish the argument for every k. Freely growing k is outside the constant/logarithmic-k polynomial guarantee.

Training and labeling are not included in inference times. Across 240 training formulas, exact label generation cost 644.85 ms, and gradient fitting cost 809.55 ms. These setup costs must be amortized before claiming an end-to-end benefit. Testing-data generation and correctness checks are also excluded from benchmark timing.

## The proven guarantee

Let L be the encoded formula size (including the variable information), and let S be the supplied set of k special variables. Assume every clause has at most two literals whose variables lie outside S. For each assignment to S, remove satisfied clauses and falsified special literals. The residual is 2-CNF, so it can be decided and a witness constructed in O(L) time. Enumerating all assignments therefore decides the original formula in O(2^k L) time. Every full assignment belongs to one enumerated branch, establishing completeness; checking a returned witness establishes soundness.

The reference implementation uses Python dictionaries and iterative SCC traversal. It materializes and sorts all 2^k candidates when ranking, requiring O(k 2^k) candidate space and conservatively O(k^2 2^k) ranking time. Its conservative bound is O(2^k (L+k^2)), rather than the tighter bound for unsorted streaming enumeration. Feature extraction and fixed-model prediction are polynomial. These implementation costs do not change polynomiality for fixed or logarithmic k.

For constant k, enumeration is polynomial in L. More generally, if k <= c log2 L for a fixed c, the streaming baseline costs O(L^(c+1)); the ranked implementation has at most an additional polynomial/logarithmic overhead. This guarantee comes from the formula restriction, independently of model accuracy.

A predictor can choose the k special bits first and then use the exact residual solver to complete a satisfiable branch. Some solution path then needs at most k overrides. The bound is constant only when k is constant. With logarithmic k, enumeration remains polynomial by exploiting the special-variable structure; this does not give polynomial generic discrepancy search at logarithmically many arbitrary decision positions.

## Validation and reproducibility

500 exhaustive 2-SAT checks; 200 restricted-formula checks across four methods; 3 boundary checks. Every benchmark decision is checked against the generator guarantee, and every successful assignment is evaluated against the original formula. Small tests use independent exhaustive enumeration as the oracle. This validates implementation behavior, not the theorem by experiment.

Run with Python 3.10 or newer, no external packages:

```text
python sat_prediction_experiment.py --out rerun
```

Seed: 20261031. Raw per-instance metrics are in per_case.csv; aggregate metrics and fitted weights are in results.json. Literal visits, graph operations, feature visits, and ranking terms are separate work counters, not interchangeable CPU-operation units; elapsed time includes their combined implementation cost.

## Next useful research question

Try benchmark formulas with less artificial structure, and test whether learning can identify a small special-variable set efficiently. The current experiment receives that set for free. Neither a universal efficient method for finding small sets nor a universal constant-override predictor is established here.

Background: [2-SAT and implication graphs](https://users.ece.utexas.edu/~garg/publicCompanion/chapter18-classical.html); [limited discrepancy search](https://ijcai.org/proceedings/1995/80).
