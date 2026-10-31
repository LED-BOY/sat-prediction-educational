"""Reproducible SAT prediction experiment. Python 3.10+, standard library only.
Run: python sat_prediction_experiment.py --out DIRECTORY
Special variables are supplied as variables 1..k. All clauses have <=2 other literals.
"""
import argparse
import csv
import itertools
import json
import math
import random
import statistics
import time
from pathlib import Path


def satisfied(clauses, assignment):
    return all(any(assignment[abs(x)] == (x > 0) for x in c) for c in clauses)


def two_sat(clauses, variables):
    """Iterative Kosaraju SCC solver; return assignment or None, and edge/node work."""
    index = {v: i for i, v in enumerate(variables)}
    size = 2 * len(variables)
    graph, reverse = [[] for _ in range(size)], [[] for _ in range(size)]
    work = 0
    def node(x):
        return 2 * index[abs(x)] + (x < 0)
    for clause in clauses:
        if not clause:
            return None, work
        assert len(clause) <= 2
        a, b = node(clause[0]), node(clause[-1])
        for u, v in ((a ^ 1, b), (b ^ 1, a)):
            graph[u].append(v)
            reverse[v].append(u)
            work += 1
    seen, order = set(), []
    for root in range(size):
        if root in seen:
            continue
        seen.add(root)
        stack = [(root, 0)]
        while stack:
            u, j = stack[-1]
            work += 1
            if j == len(graph[u]):
                order.append(u)
                stack.pop()
            else:
                stack[-1] = (u, j + 1)
                v = graph[u][j]
                if v not in seen:
                    seen.add(v)
                    stack.append((v, 0))
    component = [-1] * size
    number = 0
    for root in reversed(order):
        if component[root] >= 0:
            continue
        component[root] = number
        stack = [root]
        while stack:
            u = stack.pop()
            work += 1
            for v in reverse[u]:
                work += 1
                if component[v] < 0:
                    component[v] = number
                    stack.append(v)
        number += 1
    result = {}
    for v, i in index.items():
        if component[2*i] == component[2*i+1]:
            return None, work
        result[v] = component[2*i] > component[2*i+1]
    return result, work


def reduce_formula(clauses, bits):
    reduced, visits = [], 0
    for clause in clauses:
        remainder, hit = [], False
        for literal in clause:
            visits += 1
            v = abs(literal)
            if v <= len(bits):
                hit |= bits[v-1] == (literal > 0)
            else:
                remainder.append(literal)
        if not hit:
            if not remainder:
                return None, visits
            assert len(remainder) <= 2
            reduced.append(remainder)
    return reduced, visits


def features(clauses, k):
    positive, negative = [0]*k, [0]*k
    for clause in clauses:
        for x in clause:
            if abs(x) <= k:
                (positive if x > 0 else negative)[abs(x)-1] += 1
    return [[1., (p-m)/max(1, p+m), (p-m)/32., (p+m)/64.]
            for p, m in zip(positive, negative)]


def dot(a, b):
    return sum(x*y for x, y in zip(a, b))


def sigmoid(x):
    return 1 / (1 + math.exp(-max(-35, min(35, x))))


def fit(examples):
    weights = [0.] * 4
    for _ in range(600):
        gradient = [0.] * 4
        for x, label in examples:
            error = sigmoid(dot(weights, x)) - label
            for j in range(4):
                gradient[j] += error*x[j]
        for j in range(4):
            weights[j] -= .6 * (gradient[j]/len(examples) + .001*weights[j])
    return weights


def solve(clauses, n, k, method='fixed', weights=None, seed=0):
    start = time.perf_counter_ns()
    choices = list(itertools.product((False, True), repeat=k))
    feature_visits, ranking_terms = 0, 0
    if method in ('learned', 'majority'):
        xs = features(clauses, k)
        feature_visits = sum(map(len, clauses))
        scores = [dot(weights, x) if method == 'learned' else x[2] for x in xs]
        # Independent Bernoulli log probability differs by sum(bit * logit).
        choices.sort(key=lambda bits: -sum(s*b for s, b in zip(scores, bits)))
        ranking_terms = k * len(choices)
    elif method == 'random':
        random.Random(seed).shuffle(choices)
    ordering_ns = time.perf_counter_ns() - start
    visits = graph_work = attempts = 0
    answer = None
    for bits in choices:
        attempts += 1
        residual, cost = reduce_formula(clauses, bits)
        visits += cost
        if residual is None:
            continue
        completion, cost = two_sat(residual, range(k+1, n+1))
        graph_work += cost
        if completion is not None:
            answer = {i+1: b for i, b in enumerate(bits)} | completion
            break
    elapsed_ns = time.perf_counter_ns() - start
    # Independent full-formula verification, outside timing for every method.
    assert answer is None or satisfied(clauses, answer)
    return answer, dict(attempts=attempts, literal_visits=visits,
                        graph_work=graph_work, feature_visits=feature_visits,
                        ranking_terms=ranking_terms, ordering_ns=ordering_ns,
                        elapsed_ns=elapsed_ns)


def generate(rng, rest=20, k=5, shifted=False, unsat=False):
    """Synthetic planted data, deliberately containing a learnable polarity signal.
    Four clauses (s OR +/-a OR +/-b) force special literal s.
    Opposite-polarity distractors are satisfied by the planted rest assignment.
    Shifted data increases distractors, reversing the training correlation.
    """
    planted = {v: bool(rng.getrandbits(1)) for v in range(1, rest+k+1)}
    clauses, n = [], rest+k
    pool = list(range(k+1, n+1))
    for _ in range(2*rest):
        a, b = rng.sample(pool, 2)
        clause = [a if rng.getrandbits(1) else -a, b if rng.getrandbits(1) else -b]
        if not any(planted[abs(x)] == (x > 0) for x in clause):
            clause[rng.randrange(2)] *= -1
        clauses.append(tuple(clause))
    for v in range(1, k+1):
        s = v if planted[v] else -v
        for _ in range(rng.randint(1, 3)):
            a, b = n+1, n+2
            n += 2
            planted[a] = planted[b] = False
            clauses.extend((s, sa*a, sb*b) for sa in (-1, 1) for sb in (-1, 1))
        decoys = rng.randint(20, 35) if shifted else rng.randint(0, 12)
        for _ in range(decoys):
            a, b = rng.sample(pool, 2)
            # One rest literal is guaranteed true in the planted assignment.
            clauses.append((-s, a if planted[a] else -a,
                            b if rng.getrandbits(1) else -b))
    if unsat:
        a, b = n+1, n+2
        n += 2
        clauses.extend((sa*a, sb*b) for sa in (-1, 1) for sb in (-1, 1))
    rng.shuffle(clauses)
    clauses = [tuple(rng.sample(list(c), len(c))) for c in clauses]
    assert all(sum(abs(x) > k for x in c) <= 2 for c in clauses)
    assert unsat or satisfied(clauses, planted)
    return clauses, n, k, planted


def brute(clauses, n):
    for bits in itertools.product((False, True), repeat=n):
        assignment = dict(enumerate(bits, 1))
        if satisfied(clauses, assignment):
            return assignment
    return None


def counterexample(weights):
    """Scalable satisfiable family that this fitted model ranks last."""
    k = 8
    clauses, n = [], k
    for v in range(1, k+1):
        a, b = n+1, n+2
        n += 2
        clauses.extend((v, sa*a, sb*b) for sa in (-1, 1) for sb in (-1, 1))
        for _ in range(20):
            a, b = n+1, n+2
            n += 2
            clauses.append((-v, a, b))
    assert satisfied(clauses, {v: True for v in range(1, n+1)})
    logits = [dot(weights, x) for x in features(clauses, k)]
    assert max(logits) < 0
    # Four-clause gadgets force all special bits true. All logits are negative,
    # making that assignment uniquely last. Features do not depend on k.
    answer, stats = solve(clauses, n, k, 'learned', weights)
    assert answer is not None and stats['attempts'] == 2**k
    return dict(logit=logits[0], checked_k=k, checked_attempts=stats['attempts'],
                positive_occurrences=4, negative_occurrences=20,
                clauses_per_special=24, variables_per_special=43,
                assignments_tried='2^k for every positive integer k')


def checks():
    rng = random.Random(1401)
    # Independent exhaustive oracle on arbitrary small 2-SAT formulas.
    for _ in range(500):
        n = rng.randint(1, 7)
        clauses = [tuple(rng.choice((-1, 1))*rng.randint(1, n)
                         for _ in range(rng.randint(0, 2)))
                   for _ in range(rng.randint(0, 18))]
        result, _ = two_sat(clauses, range(1, n+1))
        expected = brute(clauses, n)
        assert (result is None) == (expected is None)
        assert result is None or satisfied(clauses, result)
    # Arbitrary restricted formulas, including contradictions, duplicate literals,
    # empty formulas/clauses, multiple solutions, and all-special clauses.
    for _ in range(200):
        n, k = 7, 2
        clauses = []
        for _ in range(rng.randint(0, 20)):
            special = [rng.choice((-1, 1))*rng.randint(1, k)
                       for _ in range(rng.randint(0, 2))]
            rest = [rng.choice((-1, 1))*rng.randint(k+1, n)
                    for _ in range(rng.randint(0, 2))]
            clauses.append(tuple(special+rest))
        expected = brute(clauses, n)
        for method in ('fixed', 'random', 'majority', 'learned'):
            answer, _ = solve(clauses, n, k, method, [0., 1., 1., 0.])
            assert (answer is None) == (expected is None)
    # No special variables and no variables at all.
    assert solve([], 0, 0)[0] == {}
    assert solve([()], 0, 0)[0] is None
    assert solve([(1,)], 1, 0)[0][1]
    return '500 exhaustive 2-SAT checks; 200 restricted-formula checks across four methods; 3 boundary checks'


def main(out):
    out.mkdir(parents=True, exist_ok=True)
    validation = checks()
    rng = random.Random(20261031)
    start = time.perf_counter_ns()
    training = [generate(rng) for _ in range(240)]
    examples = []
    training_attempts = 0
    for clauses, n, k, _ in training:
        answer, stats = solve(clauses, n, k)
        assert answer is not None
        training_attempts += stats['attempts']
        examples.extend(zip(features(clauses, k), [int(answer[v]) for v in range(1, k+1)]))
    label_ns = time.perf_counter_ns() - start
    start = time.perf_counter_ns()
    weights = fit(examples)
    fit_ns = time.perf_counter_ns() - start
    specs = [('familiar', 40, 20, 5, False, False),
             ('larger', 32, 100, 7, False, False),
             ('shifted', 40, 20, 5, True, False),
             ('unsatisfiable', 24, 20, 5, False, True)]
    rows = []
    methods = ['fixed', 'random', 'majority', 'learned']
    # Each formula is independent of training. Three timing repetitions with
    # shuffled method execution order; report median time per formula/method.
    for group, count, rest, k, shifted, unsat in specs:
        print('Testing', group, flush=True)
        for case in range(count):
            clauses, n, _, planted = generate(rng, rest, k, shifted, unsat)
            by_method = {m: [] for m in methods}
            for repeat in range(3):
                execution_order = methods[:]
                rng.shuffle(execution_order)
                for method in execution_order:
                    answer, stats = solve(clauses, n, k, method, weights, seed=10000+case)
                    assert (answer is None) == unsat
                    by_method[method].append(stats)
            xs = features(clauses, k)
            errors = sum((dot(weights, x) >= 0) != planted[v]
                         for v, x in enumerate(xs, 1))
            for method in methods:
                stats = by_method[method][0].copy()
                for key in ('elapsed_ns', 'ordering_ns'):
                    stats[key] = statistics.median(s[key] for s in by_method[method])
                rows.append(dict(group=group, case=case, method=method,
                                 variables=n, special_variables=k, clauses=len(clauses),
                                 predictor_bit_errors=errors, **stats))
    summary = []
    for group, count, *_ in specs:
        for method in methods:
            subset = [r for r in rows if r['group'] == group and r['method'] == method]
            summary.append(dict(group=group, method=method, cases=count,
                                mean_attempts=statistics.mean(r['attempts'] for r in subset),
                                max_attempts=max(r['attempts'] for r in subset),
                                total_ms=sum(r['elapsed_ns'] for r in subset)/1e6,
                                ordering_ms=sum(r['ordering_ns'] for r in subset)/1e6,
                                literal_visits=sum(r['literal_visits'] for r in subset),
                                graph_work=sum(r['graph_work'] for r in subset),
                                feature_visits=sum(r['feature_visits'] for r in subset),
                                ranking_terms=sum(r['ranking_terms'] for r in subset),
                                mean_bit_errors=statistics.mean(r['predictor_bit_errors'] for r in subset)))
    metadata = dict(seed=20261031, training_formulas=240, training_labels=len(examples),
                    training_attempts=training_attempts, label_generation_ms=label_ns/1e6,
                    training_ms=fit_ns/1e6, weights=weights, checks=validation,
                    counterexample=counterexample(weights),
                    timing='Median of 3 runs per formula/method; randomized method order; includes ordering and prediction, excludes independent final verification')
    (out/'results.json').write_text(json.dumps(dict(metadata=metadata, summary=summary), indent=2), encoding='utf-8')
    with (out/'per_case.csv').open('w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    write_report(out, metadata, summary)
    print(json.dumps(dict(metadata=metadata, summary=summary), indent=2), flush=True)


def write_report(out, metadata, summary):
    lines = ['# Predicting the search order in restricted SAT', '',
             'This is a synthetic proof-of-concept, not evidence for P = NP. The special-variable set is supplied. A learned logistic model ranks assignments; an exact 2-SAT solver checks them.', '',
             '## Results', '',
             '| Test group | Ordering | Mean assignments tried | Worst assignments tried | Total time (ms) | Ordering/prediction (ms) |',
             '|---|---|---:|---:|---:|---:|']
    for r in summary:
        lines.append(f"| {r['group']} ({r['cases']}) | {r['method']} | {r['mean_attempts']:.2f} | {r['max_attempts']} | {r['total_ms']:.2f} | {r['ordering_ms']:.2f} |")
    lines += ['', 'Total time is the sum of per-instance medians from three repetitions. It includes formula simplification, SCC solving, feature extraction, candidate construction, scoring, and sorting. It excludes a separate full-answer verification that all successful answers pass. Runtime ratios are specific to this Python implementation and machine. Random ordering uses one fixed permutation per instance across repetitions.', '',
              '## Data and what the model learns', '',
              'Training uses 240 satisfiable formulas, with 20 base variables and 5 supplied special variables, plus auxiliary variables. Labels are obtained by running the exact baseline solver, not taken from hidden test labels. Each special variable is forced by 1–3 four-clause gadgets. Opposite-polarity distractor clauses add noise, while a planted assignment ensures satisfiability. Thus each satisfiable formula has a unique special-variable assignment, but possibly many full solutions.', '',
              'The model is logistic regression, trained from scratch using gradient descent. Its inputs are a bias, normalized positive-minus-negative occurrence count, scaled raw difference, and total occurrence count. It scores each special bit independently; joint assignment ranking uses the sum of selected logits. A majority heuristic uses raw polarity counts without training. Both use the same candidate-scoring and sorting machinery.', '',
              'Familiar tests contain new formulas generated like training. Larger tests have 100 base variables and 7 special variables. Shifted tests increase opposite-polarity distractors from 0–12 to 20–35 per special variable, deliberately breaking the learned correlation. Unsatisfiable tests append an independent two-variable contradiction that is unsatisfiable for every special-variable assignment. All groups are synthetic, and the shift is a constructed stress test, not a claim about natural SAT distributions.', '',
              '## Interpretation', '']
    for group in ('familiar', 'larger', 'shifted', 'unsatisfiable'):
        data = {r['method']: r for r in summary if r['group'] == group}
        fixed, learned, majority = data['fixed'], data['learned'], data['majority']
        ratio = fixed['total_ms']/learned['total_ms']
        versus_majority = majority['total_ms']/learned['total_ms']
        lines.append(f"- **{group}:** learned ordering uses {learned['mean_attempts']:.2f} assignments on average versus {fixed['mean_attempts']:.2f} fixed and {majority['mean_attempts']:.2f} majority. Fixed/learned elapsed-time ratio: {ratio:.2f}; majority/learned ratio: {versus_majority:.2f}. A ratio above 1 favors learned ordering.")
    fixed_total = sum(r['total_ms'] for r in summary if r['method'] == 'fixed')
    learned_total = sum(r['total_ms'] for r in summary if r['method'] == 'learned')
    setup = metadata['label_generation_ms'] + metadata['training_ms']
    lines += ['', f'Across this mixed test suite, fixed ordering totals {fixed_total:.2f} ms and learned inference totals {learned_total:.2f} ms. Label generation plus training cost {setup:.2f} ms, exceeding the inference savings of {fixed_total-learned_total:.2f} ms. Including that setup, this run has no end-to-end speedup over fixed ordering.']
    lines += ['', 'Any advantage over fixed order must be compared with majority: a learned model can rediscover a cheap existing signal. No result here establishes that learning is necessary. Unsatisfiable instances require all branches in this implementation regardless of ordering. A production solver could detect the independent unsatisfiable core before enumeration; that optimization is absent for every method.', '',
              '## Explicit worst-case failure of this learned model', '',
              'For each special variable z, include the four clauses (z OR +/-a OR +/-b), using all four sign combinations. These force z=true. Add twenty clauses (NOT z OR u_j OR v_j), with fresh ordinary variables. All ordinary variables can be set true, so the formula is satisfiable. Each special variable has exactly 4 positive and 20 negative occurrences, independent of k.', '',
              f"The fitted model assigns each such variable logit {metadata['counterexample']['logit']:.6f}, strictly below zero. "
              'Every special variable must be true, yet the model prefers false for all of them. The unique satisfying special-variable assignment ranks last: the solver tries exactly 2^k branches. The formula has 24k clauses and 43k variables, so the branch count is exponential in the number of variables and superpolynomial in the encoded formula size when k grows freely. This is a counterexample to this fitted predictor and search strategy, not a lower bound for all predictors or SAT algorithms. The code checks the construction at k=8; identical per-variable features establish the argument for every k. Freely growing k is outside the constant/logarithmic-k polynomial guarantee.', '',
              'Training and labeling are not included in inference times. Across 240 training formulas, exact label generation cost '
              f"{metadata['label_generation_ms']:.2f} ms, and gradient fitting cost {metadata['training_ms']:.2f} ms. "
              'These setup costs must be amortized before claiming an end-to-end benefit. Testing-data generation and correctness checks are also excluded from benchmark timing.', '',
              '## The proven guarantee', '',
              'Let L be the encoded formula size (including the variable information), and let S be the supplied set of k special variables. Assume every clause has at most two literals whose variables lie outside S. For each assignment to S, remove satisfied clauses and falsified special literals. The residual is 2-CNF, so it can be decided and a witness constructed in O(L) time. Enumerating all assignments therefore decides the original formula in O(2^k L) time. Every full assignment belongs to one enumerated branch, establishing completeness; checking a returned witness establishes soundness.', '',
              'The reference implementation uses Python dictionaries and iterative SCC traversal. It materializes and sorts all 2^k candidates when ranking, requiring O(k 2^k) candidate space and conservatively O(k^2 2^k) ranking time. Its conservative bound is O(2^k (L+k^2)), rather than the tighter bound for unsorted streaming enumeration. Feature extraction and fixed-model prediction are polynomial. These implementation costs do not change polynomiality for fixed or logarithmic k.', '',
              'For constant k, enumeration is polynomial in L. More generally, if k <= c log2 L for a fixed c, the streaming baseline costs O(L^(c+1)); the ranked implementation has at most an additional polynomial/logarithmic overhead. This guarantee comes from the formula restriction, independently of model accuracy.', '',
              'A predictor can choose the k special bits first and then use the exact residual solver to complete a satisfiable branch. Some solution path then needs at most k overrides. The bound is constant only when k is constant. With logarithmic k, enumeration remains polynomial by exploiting the special-variable structure; this does not give polynomial generic discrepancy search at logarithmically many arbitrary decision positions.', '',
              '## Validation and reproducibility', '',
              metadata['checks'] + '. Every benchmark decision is checked against the generator guarantee, and every successful assignment is evaluated against the original formula. Small tests use independent exhaustive enumeration as the oracle. This validates implementation behavior, not the theorem by experiment.', '',
              'Run with Python 3.10 or newer, no external packages:', '',
              '```text', 'python sat_prediction_experiment.py --out rerun', '```', '',
              'Seed: 20261031. Raw per-instance metrics are in per_case.csv; aggregate metrics and fitted weights are in results.json. Literal visits, graph operations, feature visits, and ranking terms are separate work counters, not interchangeable CPU-operation units; elapsed time includes their combined implementation cost.', '',
              '## Next useful research question', '',
              'Try benchmark formulas with less artificial structure, and test whether learning can identify a small special-variable set efficiently. The current experiment receives that set for free. Neither a universal efficient method for finding small sets nor a universal constant-override predictor is established here.', '',
              'Background: [2-SAT and implication graphs](https://users.ece.utexas.edu/~garg/publicCompanion/chapter18-classical.html); [limited discrepancy search](https://ijcai.org/proceedings/1995/80).', '']
    (out/'REPORT.md').write_text('\n'.join(lines), encoding='utf-8')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, default=Path(__file__).resolve().parent)
    main(parser.parse_args().out)
