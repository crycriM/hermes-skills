# pyvinecopulib API Notes (v0.7.6)

Installed via pip. Nanobind-based — no Python signature introspection possible
(`inspect.signature()` raises `ValueError` for builtin types).

## Import

```python
from pyvinecopulib import Bicop, FitControlsBicop, BicopFamily
```

## Available Families (Enum)

List all: `list(BicopFamily)`

Members: `indep`(0), `gaussian`(1), `student`(2), `clayton`(3), `gumbel`(4),
`frank`(5), `joe`(6), `bb1`(7), `bb6`(8), `bb7`(9), `bb8`(10), `tawn`(11),
`tll`(12)

Access: `BicopFamily.gaussian`, `BicopFamily.student`, etc.

## Fitting: Use .select(), Not Constructor

**WRONG:**
```python
Bicop(data=u_margins, controls=BicopControls(family_set=[...]))
# BicopControls doesn't exist — it's FitControlsBicop
# Constructor doesn't fit — use .select()
```

**CORRECT:**
```python
controls = FitControlsBicop(
    family_set=[
        BicopFamily.gaussian, BicopFamily.student,
        BicopFamily.clayton, BicopFamily.gumbel, BicopFamily.frank
    ]
)
cop = Bicop()
cop.select(u_margins, controls)  # u_margins: (n, 2) np.ndarray
```

## Model Properties After Fitting

```python
cop.family       # BicopFamily enum
cop.parameters   # np.ndarray of copula parameters
cop.aic()        # float
cop.bic()        # float
cop.tau()        # Kendall's tau
cop.nobs         # int
```

## CDF: Requires (n, 2) Fortran-Order Array

**WRONG:**
```python
cop.cdf(u1, u2)  # TypeError: incompatible function arguments
```

**CORRECT:**
```python
cdf_input = np.array([[u1, u2]], dtype=np.float64, order='F')
result = float(cop.cdf(cdf_input)[0])
```

The CDF expects shape `(n, 2)` with Fortran (column-major) memory layout.
Returns shape `(n,)`.

## Other Common Methods

```python
# PDF
pdf_input = np.array([[u1, u2]], dtype=np.float64, order='F')
pdf_val = float(cop.pdf(pdf_input)[0])

# h-functions (conditional distribution functions)
h1 = cop.hfunc1(np.array([[u1]], order='F'), np.array([u2]))
h2 = cop.hfunc2(np.array([[u1]], order='F'), np.array([u2]))

# Inverse h-functions
hinv1 = cop.hinv1(...)
hinv2 = cop.hinv2(...)

# Simulation
samples = cop.simulate(n=1000)  # Returns (1000, 2) Fortran-order array
```

## Serialization

```python
cop.to_json("copula.json")       # Save
cop2 = Bicop.from_json("copula.json")  # Load
```
