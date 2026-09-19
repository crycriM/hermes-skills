# Starlette 1.0 TemplateResponse API Change

## The Problem

Starlette 1.0 (shipped with FastAPI ≥0.115+) changed the `Jinja2Templates.TemplateResponse` method signature. Existing FastAPI documentation and tutorials use the old API, which causes a runtime error on any system with the new version.

## Error Message

```
TypeError: Jinja2Templates.TemplateResponse() missing 1 required positional argument: 'request'
```

## Old API (Starlette ≤0.45)

```python
from fastapi.templating import Jinja2Templates

templates = Jinja2Templates(directory="templates")

@app.get("/")
async def dashboard(request: Request):
    return templates.TemplateResponse(
        "dashboard.html",
        {"request": request, "key": value}   # request inside context dict
    )
```

## New API (Starlette 1.0+)

```python
templates = Jinja2Templates(directory="templates")

@app.get("/")
async def dashboard(request: Request):
    return templates.TemplateResponse(
        request,            # NEW: first positional arg — the request object
        "dashboard.html",   # second: template name
        {"key": value},     # third: context dict (no 'request' key needed)
    )
```

## Key Differences

| Aspect | Old (≤0.45) | New (1.0+) |
|--------|-------------|------------|
| Signature | `(name, context)` | `(request, name, context)` |
| Request in context | Yes — `{"request": request}` | No — auto-injected |
| Starlette version | `0.44.x` | `1.0.x` |
| FastAPI version | `<0.115` | `≥0.115` |

## How to Detect

```python
import starlette
print(starlette.__version__)
# If it prints 1.x.x, use the new API
```

## Compatibility Hack

If you need to support both versions (e.g., shared code), you can check at import time:

```python
from starlette import __version__ as starlette_version
USE_OLD_API = starlette_version.startswith("0.")
```
