"""Optimizer settings (Phase 5). Assumed values, documented in docs/ASSUMPTIONS.md."""

# objective weight per train type: weighted arrival delay = weight x minutes late
PRIORITY_WEIGHTS = {"EXPRESS": 3, "PASSENGER": 2, "FREIGHT": 1}
# the same weights by priority (1 = highest), used everywhere: SIMULATED types map EXPRESS/PASSENGER/
# FREIGHT = priority 1/2/3; REAL types PREMIUM/SUPERFAST/EXPRESS = ASSUMED priority 1/2/3.
WEIGHT_BY_PRIORITY = {1: 3, 2: 2, 3: 1}


def weight(train) -> int:
    return WEIGHT_BY_PRIORITY[train.priority]

# added to the objective for every reroute, in weighted minutes
REROUTE_PENALTY = 1

# rolling horizon: only trips planned to start within this many minutes are re-planned
HORIZON_MIN = 120

# latest time the solver may schedule anything, measured from state time
PLANNING_WINDOW_MIN = 24 * 60

# solver settings: single worker + fixed seed = deterministic results
TIME_LIMIT_S = 10.0
NUM_WORKERS = 1
RANDOM_SEED = 0

# extra headway per risky trip when the optional ML risk buffers are used
RISK_BUFFER_MIN = 1
