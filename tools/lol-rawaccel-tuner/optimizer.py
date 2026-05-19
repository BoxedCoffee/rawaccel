import math
import random


class CemTuner:
    def __init__(self, bounds, population, elite, generations, seed=0, start=None):
        self.bounds = bounds
        self.population = int(population)
        self.elite = int(elite)
        self.generations_total = int(generations)
        self.rng = random.Random(int(seed))

        self.generation = 0
        self.member = 0

        self._mean = {k: (v[0] + v[1]) / 2.0 for k, v in bounds.items()}
        self._std = {k: (v[1] - v[0]) / 2.5 for k, v in bounds.items()}

        if isinstance(start, dict):
            for k, v in start.items():
                if k not in self.bounds:
                    continue
                lo, hi = self.bounds[k]
                x = float(v)
                if x < lo:
                    x = lo
                if x > hi:
                    x = hi
                self._mean[k] = x

        self._candidates = []
        self._scores = []
        self._awaiting = None

    def next_candidate(self):
        if self._awaiting is not None:
            raise RuntimeError("candidate awaiting score")

        if self.generation >= self.generations_total:
            return None

        if not self._candidates:
            self._candidates = self._sample_population()
            self._scores = []
            self.member = 0

        cand = self._candidates[self.member]
        self._awaiting = cand
        return dict(cand)

    def report_result(self, score):
        if self._awaiting is None:
            raise RuntimeError("no candidate awaiting score")

        self._scores.append(float(score))
        self._awaiting = None
        self.member += 1

        if self.member < self.population:
            return

        self._update_distribution()
        self.generation += 1
        self._candidates = []
        self._scores = []
        self.member = 0

    def _sample_population(self):
        keys = list(self.bounds.keys())
        pop = []
        pop.append({k: float(self._mean[k]) for k in keys})
        for _ in range(self.population - 1):
            cand = {}
            for k in keys:
                mu = self._mean[k]
                sd = max(self._std[k], 1e-9)
                x = self.rng.gauss(mu, sd)
                lo, hi = self.bounds[k]
                if x < lo:
                    x = lo
                if x > hi:
                    x = hi
                cand[k] = float(x)
            pop.append(cand)
        return pop

    def _update_distribution(self):
        paired = list(zip(self._candidates, self._scores))
        paired = [(c, s) for c, s in paired if math.isfinite(s)]
        if not paired:
            for k, (lo, hi) in self.bounds.items():
                self._std[k] = max(self._std[k], (hi - lo) / 2.5)
            return

        paired.sort(key=lambda x: x[1], reverse=True)
        elites = [c for c, _ in paired[: max(1, min(self.elite, len(paired)) )]]

        keys = list(self.bounds.keys())
        new_mean = {}
        new_std = {}
        for k in keys:
            vals = [c[k] for c in elites]
            mu = sum(vals) / len(vals)
            var = 0.0
            for v in vals:
                var += (v - mu) ** 2
            var = var / max(1, (len(vals) - 1))
            sd = math.sqrt(var) if len(vals) > 1 else self._std[k] * 0.7

            lo, hi = self.bounds[k]
            floor_sd = (hi - lo) * 0.02

            new_mean[k] = float(min(hi, max(lo, mu)))
            new_std[k] = float(max(floor_sd, min((hi - lo) / 2.0, sd)))

        self._mean = new_mean
        self._std = new_std
