# Can predictive text inspire faster problem solving?

An educational, reproducible experiment in **learning to order a SAT solver's search**.

The starting question was: predictive text suggests a likely next word; could a predictor similarly suggest promising choices in a difficult problem, while an exact solver checks the results?

We built a small experiment to explore that question. It illustrates both a practical benefit and a mathematical limitation. It does not solve P versus NP, establish a new general SAT algorithm, or claim that learned search guidance is a new idea.

## What the experiment does

SAT asks whether true/false values can satisfy every clause in a logical formula. The experiment uses a restricted family: a supplied set of `k` special variables leaves a 2-SAT problem after those variables are assigned. Each clause has at most two literals outside that set.

The exact solver enumerates assignments to those special variables and solves each residual formula with an implication graph and strongly connected components. Four strategies choose the assignment order:

- **Fixed:** false-first lexicographic order.
- **Random:** a reproducible random permutation.
- **Majority:** a simple, untrained count of positive versus negative occurrences.
- **Learned:** logistic regression trained from scratch to predict the special-variable values, then rank complete assignments.

The model guides the order only. Every returned solution is checked against the original formula. Searching all assignments preserves correctness regardless of prediction quality.

## Run it

Requires **Python 3.10 or newer**. Uses the standard library only; no package installation, account, model download, or GPU is needed.

```sh
python sat_prediction_experiment.py --out rerun
```

This validates the solver, generates training labels with the exact baseline, trains the predictor, runs the benchmarks, and writes a report plus JSON and CSV results to `rerun/`. Allow roughly a few seconds to a minute, depending on your machine. The supplied snapshot was measured with Python 3.13.5 on Windows.

To run just the small correctness checks:

```sh
python -c "from sat_prediction_experiment import checks; print(checks())"
```

## What happened in the supplied run?

Training: **240 synthetic formulas**, producing 1,200 bit labels. Testing: **136 unseen formulas**. Timings include prediction and ordering overhead, but exclude training and separate final-answer verification. Each per-instance time is the median of three repetitions.

| Test group | Formulas | Mean branches: fixed | Mean branches: learned | Learned inference versus fixed |
|---|---:|---:|---:|---|
| New formulas like training | 40 | 13.90 | 7.95 | 1.70x faster |
| Larger formulas | 32 | 63.16 | 28.66 | 2.18x faster |
| Deliberately changed distribution | 40 | 15.57 | 32.00 | About 2x slower |
| Unsatisfiable formulas | 24 | 32.00 | 32.00 | No meaningful improvement |

The majority heuristic captured most of the gain: learned inference was only about 1.07x and 1.09x faster than majority on familiar and larger tests. These small timing differences are descriptive, not statistically established superiority.

Across the complete mixed test suite, learned inference saved about **0.338 seconds** versus fixed ordering. Label generation and training cost about **1.454 seconds**, so **there was no end-to-end speedup for this run**. Reusing a trained model could amortize that cost, depending on the future workload.

All data is synthetic. The generator deliberately embeds a noisy polarity signal. These results do not demonstrate improvement on industrial SAT, scheduling, routing, or software verification. No comparison with a production SAT solver has been made. The special-variable set is supplied for free, and obvious structural simplifications are not optimized away. The unsatisfiable group contains an independent unsatisfiable core that a better solver could detect before enumeration.

## What can we prove?

For a supplied set of `k` special variables and formula size `L`, unsorted enumeration plus exact 2-SAT solving takes `O(2^k L)` time under the usual graph-operation model.

- Fixed `k` gives polynomial time.
- Even `k <= c log2 L`, for a fixed constant `c`, gives polynomial time.
- This guarantee comes from the structural restriction, independently of learning.

The ranked Python implementation materializes and sorts candidate assignments. A conservative bound including ranking is `O(2^k (L + k^2))`; this remains polynomial for constant or logarithmic `k`.

We also give an explicit satisfiable family where **this fitted model ranks the correct special-variable assignment last**, requiring exactly `2^k` branches. The construction was executed at `k=8` (256 branches), and identical local features prove the result for arbitrary `k`. This is a counterexample to this predictor and search strategy, not a proof that every predictor must fail.

See [REPORT.md](REPORT.md) for the reasoning, construction, measurements, and limitations.

## Files

| File | Purpose |
|---|---|
| [sat_prediction_experiment.py](sat_prediction_experiment.py) | Generator, learned model, exact solver, checks, benchmark, and report generation |
| [REPORT.md](REPORT.md) | Detailed explanation and runtime argument |
| [results.json](results.json) | Aggregate measurements, seed, fitted weights, and counterexample check |
| [per_case.csv](per_case.csv) | Per-instance work counters and timings |

Seed: `20261031`. Branch counts and fitted weights are reproducible; wall-clock times vary. The report distinguishes work counters instead of treating different operations as identical CPU costs.

Correctness checks compare 500 small 2-SAT formulas against exhaustive enumeration, then check 200 restricted formulas across all four strategies, plus three boundary cases. Every successful benchmark assignment is evaluated independently against its original formula.

## How this relates to existing work

Learning to guide exact solvers and searching near heuristic choices are established research directions. This repository is an educational implementation and investigation, not a novelty claim.

- [Harvey and Ginsberg: Limited Discrepancy Search (1995)](https://ijcai.org/proceedings/1995/80)
- [Selsam and colleagues: Learning a SAT Solver from Single-Bit Supervision](https://arxiv.org/abs/1802.03685)
- [Enhancing SAT solvers with glue variable predictions](https://arxiv.org/abs/2007.02559)
- [University of Texas: 2-SAT and implication graphs](https://users.ece.utexas.edu/~garg/publicCompanion/chapter18-classical.html)
- [Clay Mathematics Institute: P versus NP](https://www.claymath.org/millennium/p-vs-np/)

## Useful extensions

- Try more realistic formula families and stronger solver baselines.
- Learn to find small special-variable sets instead of receiving them as input.
- Add confidence-based fallback strategies and measure their overhead.
- Test different random seeds and uncertainty across runs.
- Include all setup costs when evaluating a particular application's benefit.

## Project origin and reuse

The motivating question came from LED-BOY's analogy between predictive text and searching for solutions. The code, analysis, and documentation were developed with assistance from OpenAI's Codex. The reported measurements come from executing the included experiment. This attribution does not establish research novelty or peer review.

Released under the [MIT License](LICENSE) for educational reuse and modification. Contributions that reproduce, challenge, or extend the results are welcome.
