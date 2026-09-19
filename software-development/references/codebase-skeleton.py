#!/usr/bin/env python3
"""
Codebase Skeleton Extractor — compress source code to signatures only.

Outputs a compact text representation of a codebase suitable for feeding
into small-context LLMs. Extracts imports, class/function signatures with
type hints, decorators, and truncated docstrings.

Usage:
    python codebase-skeleton.py /path/to/repo [options]

Examples:
    # Full skeleton
    python codebase-skeleton.py ~/my-project

    # Only Python files, max 200 lines of output
    python codebase-skeleton.py ~/my-project --ext py --max-lines 200

    # Skip test files and vendor dirs
    python codebase-skeleton.py ~/my-project --skip "*test*,vendor,third_party"

    # Show only the file tree (no signatures)
    python codebase-skeleton.py ~/my-project --tree-only

    # JSON output for programmatic use
    python codebase-skeleton.py ~/my-project --format json
"""

import ast
import argparse
import fnmatch
import json
import os
import sys
import textwrap
from pathlib import Path
from typing import Optional


# Default directories to skip
SKIP_DIRS = {
    ".git", ".svn", ".hg", "node_modules", "venv", ".venv", "__pycache__",
    ".cache", "dist", "build", ".next", ".tox", ".eggs", ".mypy_cache",
    ".pytest_cache", ".ruff_cache", "egg-info", ".idea", ".vscode",
    "vendor", "third_party", "third-party",
}

# Extensions and their comment markers
EXT_COMMENT = {
    ".py": "#",
    ".js": "//",
    ".ts": "//",
    ".tsx": "//",
    ".jsx": "//",
    ".rs": "//",
    ".go": "//",
    ".java": "//",
    ".kt": "//",
    ".c": "//",
    ".cpp": "//",
    ".h": "//",
    ".hpp": "//",
    ".rb": "#",
    ".sh": "#",
    ".lua": "--",
}

# Languages with AST support (currently only Python via stdlib ast)
AST_LANGUAGES = {".py"}


def should_skip_dir(dirname: str, extra_skips: list[str]) -> bool:
    if dirname in SKIP_DIRS:
        return True
    for pattern in extra_skips:
        if fnmatch.fnmatch(dirname, pattern):
            return True
    return False


def should_skip_file(filename: str, extra_skips: list[str]) -> bool:
    for pattern in extra_skips:
        if fnmatch.fnmatch(filename, pattern):
            return True
    return False


def truncate_docstring(docstring: str, max_lines: int = 3, max_chars: int = 200) -> str:
    if not docstring:
        return ""
    lines = docstring.strip().splitlines()
    result = []
    total = 0
    for line in lines[:max_lines]:
        if total + len(line) > max_chars:
            remaining = max_chars - total
            if remaining > 10:
                result.append(line[:remaining] + "...")
            break
        result.append(line)
        total += len(line) + 3  # +3 for "..."
    else:
        if len(lines) > max_lines:
            result[-1] = result[-1].rstrip() + "..."
    text = " ".join(result)
    if len(text) > max_chars:
        text = text[:max_chars - 3] + "..."
    return text


def format_args(args: ast.arguments, returns: Optional[ast.expr]) -> str:
    """Format function arguments and return type annotation."""
    parts = []

    # positional args with defaults
    defaults = [None] * (len(args.args) - len(args.defaults)) + args.defaults
    for arg, default in zip(args.args, defaults):
        s = arg.arg
        if arg.annotation:
            s += f": {ast.unparse(arg.annotation)}"
        if default:
            s += f" = {ast.unparse(default)}"
        parts.append(s)

    # *args
    if args.vararg:
        s = f"*{args.vararg.arg}"
        if args.vararg.annotation:
            s += f": {ast.unparse(args.vararg.annotation)}"
        parts.append(s)
    elif args.kwonlyargs:
        parts.append("*")

    # keyword-only args
    kw_defaults = [None] * (len(args.kwonlyargs) - len(args.kw_defaults)) + args.kw_defaults
    for arg, default in zip(args.kwonlyargs, kw_defaults):
        s = f"{arg.arg}"
        if arg.annotation:
            s += f": {ast.unparse(arg.annotation)}"
        if default:
            s += f" = {ast.unparse(default)}"
        parts.append(s)

    # **kwargs
    if args.kwarg:
        s = f"**{args.kwarg.arg}"
        if args.kwarg.annotation:
            s += f": {ast.unparse(args.kwarg.annotation)}"
        parts.append(s)

    sig = f"({', '.join(parts)})"
    if returns:
        sig += f" -> {ast.unparse(returns)}"
    return sig


def extract_decorators(node: ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef) -> list[str]:
    return [f"@{ast.unparse(d)}" for d in node.decorator_list]


def get_docstring(node: ast.AST) -> str:
    ds = ast.get_docstring(node, clean=True)
    return truncate_docstring(ds) if ds else ""


def extract_class(node: ast.ClassDef, indent: int = 2) -> dict:
    """Extract class skeleton."""
    bases = [ast.unparse(b) for b in node.bases]
    keywords = [f"{kw.arg}={ast.unparse(kw.value)}" for kw in node.keywords if kw.arg]
    inheritance = ""
    if bases or keywords:
        parts = bases + keywords
        inheritance = f"({', '.join(parts)})"

    decorators = extract_decorators(node)
    docstring = get_docstring(node)

    methods = []
    attributes = []

    for item in node.body:
        if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if item.name.startswith("_") and item.name not in ("__init__", "__call__", "__enter__", "__exit__"):
                # Skip private methods unless they're dunders
                continue
            methods.append(extract_function(item, is_method=True))
        elif isinstance(item, ast.AnnAssign) and item.target:
            # Class-level annotated attribute
            attr_name = item.target.id if isinstance(item.target, ast.Name) else ast.unparse(item.target)
            attr_type = ast.unparse(item.annotation) if item.annotation else ""
            if attr_type:
                attributes.append(f"{attr_name}: {attr_type}")

    return {
        "type": "class",
        "name": node.name,
        "bases": inheritance,
        "decorators": decorators,
        "docstring": docstring,
        "attributes": attributes,
        "methods": methods,
    }


def extract_function(node: ast.FunctionDef | ast.AsyncFunctionDef, is_method: bool = False) -> dict:
    """Extract function/method signature."""
    prefix = "async " if isinstance(node, ast.AsyncFunctionDef) else ""
    args_sig = format_args(node.args, node.returns)
    decorators = extract_decorators(node)
    docstring = get_docstring(node)

    return {
        "type": "async_function" if isinstance(node, ast.AsyncFunctionDef) else "function",
        "name": node.name,
        "prefix": prefix,
        "signature": args_sig,
        "decorators": decorators,
        "docstring": docstring,
    }


def extract_assignments(body: list[ast.stmt]) -> list[str]:
    """Extract top-level assignments that look like constants or type aliases."""
    results = []
    for node in body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id.isupper():
                    results.append(f"{target.id} = {ast.unparse(node.value)}")
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            type_str = ast.unparse(node.annotation) if node.annotation else ""
            val_str = f" = {ast.unparse(node.value)}" if node.value else ""
            results.append(f"{node.target.id}: {type_str}{val_str}")
    return results


def parse_python(filepath: str) -> dict:
    """Parse a Python file and extract its skeleton."""
    try:
        with open(filepath, "r", encoding="utf-8", errors="replace") as f:
            source = f.read()
        tree = ast.parse(source, filename=filepath)
    except SyntaxError:
        return {"error": "syntax_error"}
    except Exception:
        return {"error": "parse_error"}

    imports = []
    classes = []
    functions = []
    constants = []

    for node in ast.iter_child_nodes(tree):
        if isinstance(node, ast.Import):
            imports.append(f"import {', '.join(a.name for a in node.names)}")
        elif isinstance(node, ast.ImportFrom):
            names = ", ".join(a.name for a in node.names)
            module = node.module or ""
            level = "." * node.level
            imports.append(f"from {level}{module} import {names}")
        elif isinstance(node, ast.ClassDef):
            classes.append(extract_class(node))
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            functions.append(extract_function(node))

    constants = extract_assignments(ast.iter_child_nodes(tree))

    return {
        "language": "python",
        "imports": imports,
        "constants": constants,
        "classes": classes,
        "functions": functions,
    }


def format_skeleton_text(filepath: str, skeleton: dict, show_imports: bool = True) -> str:
    """Format a file's skeleton as readable text."""
    if "error" in skeleton:
        return f"# {filepath} [parse error: {skeleton['error']}]"

    lines = []
    lines.append(f"{'=' * 60}")
    lines.append(f"# {filepath}")
    lines.append(f"{'=' * 60}")

    if show_imports and skeleton.get("imports"):
        for imp in skeleton["imports"]:
            lines.append(imp)
        lines.append("")

    for const in skeleton.get("constants", []):
        lines.append(const)

    for cls in skeleton.get("classes", []):
        lines.append("")
        for dec in cls["decorators"]:
            lines.append(dec)
        header = f"class {cls['name']}{cls['bases']}:"
        lines.append(header)
        if cls["docstring"]:
            lines.append(f'  """{cls["docstring"]}"""')

        for attr in cls.get("attributes", []):
            lines.append(f"  {attr}")

        for method in cls.get("methods", []):
            lines.append("")
            for dec in method["decorators"]:
                lines.append(f"  {dec}")
            sig = f"  def {method['name']}{method['signature']}:"
            lines.append(sig)
            if method["docstring"]:
                lines.append(f'    """{method["docstring"]}"""')

    for func in skeleton.get("functions", []):
        lines.append("")
        for dec in func["decorators"]:
            lines.append(dec)
        sig = f"def {func['name']}{func['signature']}:"
        lines.append(sig)
        if func["docstring"]:
            lines.append(f'  """{func["docstring"]}"""')

    return "\n".join(lines)


def parse_file(filepath: str) -> dict:
    """Route file to appropriate parser based on extension."""
    ext = Path(filepath).suffix
    if ext == ".py":
        return parse_python(filepath)
    # Future: tree-sitter parsers for JS/TS/Go/Rust
    return {"language": ext.lstrip(".") or "unknown", "unsupported": True}


def collect_files(root: str, extensions: list[str], extra_skips: list[str]) -> list[str]:
    """Walk directory tree and collect matching files."""
    files = []
    for dirpath, dirnames, filenames in os.walk(root):
        # Filter dirs in-place to prevent recursion into skipped dirs
        dirnames[:] = [
            d for d in dirnames
            if not should_skip_dir(d, extra_skips)
        ]
        for filename in sorted(filenames):
            if should_skip_file(filename, extra_skips):
                continue
            ext = Path(filename).suffix
            if extensions and ext not in extensions:
                continue
            if not extensions and ext not in EXT_COMMENT and ext not in AST_LANGUAGES:
                # Skip files we can't parse
                continue
            files.append(os.path.join(dirpath, filename))
    return files


def build_file_tree(root: str, files: list[str]) -> str:
    """Build a compact file tree representation."""
    root_path = Path(root).resolve()
    lines = [f"{root_path.name}/"]

    # Build tree structure
    tree = {}
    for f in files:
        rel = os.path.relpath(f, root)
        parts = Path(rel).parts
        node = tree
        for part in parts[:-1]:
            node = node.setdefault(part + "/", {})
        node[parts[-1]] = None

    def render_tree(node, prefix=""):
        items = sorted(node.items(), key=lambda x: (x[1] is not None, x[0]))
        for i, (name, children) in enumerate(items):
            is_last = i == len(items) - 1
            connector = "└── " if is_last else "├── "
            lines.append(f"{prefix}{connector}{name}")
            if children is not None:
                extension = "    " if is_last else "│   "
                render_tree(children, prefix + extension)

    render_tree(tree)
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(
        description="Extract codebase skeleton — signatures only, no bodies.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent("""
            Output modes:
              text   — human-readable signatures (default)
              json   — structured JSON for programmatic use
              tree   — file tree only, no signatures
        """),
    )
    parser.add_argument("path", help="Root directory of the codebase")
    parser.add_argument("--ext", nargs="+", default=[], help="File extensions to include (e.g. py js ts). Default: all supported")
    parser.add_argument("--skip", nargs="+", default=[], help="Additional glob patterns to skip (dirs and files)")
    parser.add_argument("--no-imports", action="store_true", help="Omit import statements")
    parser.add_argument("--max-lines", type=int, default=0, help="Truncate output to N lines (0=unlimited)")
    parser.add_argument("--tree-only", action="store_true", help="Show file tree only, no signatures")
    parser.add_argument("--format", choices=["text", "json", "tree"], default="text", help="Output format")
    parser.add_argument("--output", "-o", help="Write to file instead of stdout")
    parser.add_argument("--stats", action="store_true", help="Append token/line statistics")

    args = parser.parse_args()

    if not os.path.isdir(args.path):
        print(f"Error: {args.path} is not a directory", file=sys.stderr)
        sys.exit(1)

    extensions = [f".{e.lstrip('.')}" for e in args.ext] if args.ext else []
    files = collect_files(args.path, extensions, args.skip)

    if not files:
        print("No matching files found.", file=sys.stderr)
        sys.exit(1)

    # Tree-only mode
    if args.tree_only or args.format == "tree":
        tree_str = build_file_tree(args.path, files)
        if args.output:
            Path(args.output).write_text(tree_str + "\n")
        else:
            print(tree_str)
        return

    # Parse all files
    skeletons = []
    for filepath in files:
        skel = parse_file(filepath)
        rel_path = os.path.relpath(filepath, args.path)
        skel["filepath"] = rel_path
        skeletons.append(skel)

    # JSON output
    if args.format == "json":
        output = json.dumps(skeletons, indent=2, ensure_ascii=False)
    else:
        # Text output
        parts = []
        # File tree header
        parts.append(build_file_tree(args.path, files))
        parts.append("")
        parts.append("=" * 60)
        parts.append("SIGNATURES")
        parts.append("=" * 60)
        parts.append("")

        for skel in skeletons:
            if skel.get("unsupported"):
                parts.append(f"# {skel['filepath']} [{skel['language']} — unsupported]")
                parts.append("")
                continue
            parts.append(format_skeleton_text(skel["filepath"], skel, show_imports=not args.no_imports))
            parts.append("")

        output = "\n".join(parts)

    # Stats
    if args.stats:
        total_lines = output.count("\n") + 1
        # Rough token estimate (~4 chars per token)
        total_tokens = len(output) // 4
        stats = f"\n--- Stats: {len(files)} files, {total_lines} lines, ~{total_tokens} tokens ---"
        output += stats

    # Truncate
    if args.max_lines > 0:
        lines = output.splitlines(keepends=True)
        if len(lines) > args.max_lines:
            output = "".join(lines[:args.max_lines])
            output += f"\n... truncated ({len(lines) - args.max_lines} more lines)"

    # Write output
    if args.output:
        Path(args.output).write_text(output)
        print(f"Written to {args.output} ({len(output)} chars)", file=sys.stderr)
    else:
        print(output)


if __name__ == "__main__":
    main()
