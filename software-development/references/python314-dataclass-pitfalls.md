# Python 3.14 Dataclass Pitfalls

## Mutable default in nested dataclass

Python 3.14 enforces the mutable-default check at class creation time. Using another dataclass instance as a field default raises:

```
ValueError: mutable default <class 'mm_core.regime.GateConfig'> for field gate is not allowed: use default_factory
```

**Wrong:**
```python
from dataclasses import dataclass

@dataclass
class DLMMConfig:
    gate: GateConfig = GateConfig()
    risk: RiskConfig = RiskConfig()
```

**Right:**
```python
from dataclasses import dataclass, field

@dataclass
class DLMMConfig:
    gate: GateConfig = field(default_factory=GateConfig)
    risk: RiskConfig = field(default_factory=RiskConfig)
```

This hits any `@dataclass` that embeds another `@dataclass` as a default value. The error is raised during class definition (import time), so it breaks test collection entirely — no tests run until the import is fixed.

## EMA convergence in tests

EMA with `alpha = dt / (dt + tau_h)` converges slowly when `tau_h >> dt`. With `tau_h=100` and `dt=1`, alpha ≈ 0.0099, so after 1000 iterations the EMA has only reached ~67% of the target. For test convergence:

- Use `tau_h=10` (alpha ≈ 0.091), 5000+ iterations — converges to within 0.1
- Or use `tau_h=1` (alpha = 0.5), 20 iterations — converges to within 0.01
- Never use `tau_h=100` with only 1000 iterations and assert `< 0.01` tolerance