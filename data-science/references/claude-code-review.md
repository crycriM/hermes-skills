# Claude Code CLI Integration for Code Review

Claude Code (`claude` CLI) is installed at `~/.local/bin/claude` (v2.1.152).
Can be used for external code review of implementation decisions.

## Review Triggers (when to use)

Claude Code is particularly effective at catching:
- **PnL math bugs**: cumulative vs delta marking, double-counting unrealized returns, compounding errors
- **Look-ahead bias**: signals using future data, feature computation crossing fold boundaries
- **State leakage**: signal state persisting across folds, walk-forward isolation violations
- **Architecture smell**: overloaded functions, missing abstractions, hardcoded constants

Example from Vanta SN8 backtester review: Claude Code found that daily PnL was adding cumulative position PnL every day (double-counting) instead of computing day-over-day deltas. This inflated returns by 33× (+212% → +6.4%).

## Usage Pattern

```bash
# Prepare review context as a markdown file
cat > /tmp/review_prompt.md << 'EOF'
[problem description, architecture, results, specific questions]
EOF

# Copy code files to temp dir
mkdir -p /tmp/review && cp path/to/files /tmp/review/

# Run Claude Code review (non-interactive)
cd /tmp/review && claude --model claude-sonnet-4-20250514 --max-turns 10 -p "$(cat /tmp/review_prompt.md)

Please read the code files and provide your review. Be specific and actionable."
```

## Model Selection

- `claude-sonnet-4-20250514`: Good for code review (fast, strong analysis). ~10 turns needed for thorough review.
- `claude-opus-4-20250514`: Best quality but slower. May need `--max-turns 15` for full review.
- `claude-haiku-4-20250514`: Too terse for substantive review — misses architectural issues.

## Pitfalls

- **Max turns hit silently**: If `--max-turns` is too low, Claude Code exits with "Error: Reached max turns" without producing output. Bump to 10+ for review tasks.
- **Not interactive by default**: Use `-p` flag for single-prompt mode. Without it, Claude Code waits for stdin.
- **Model names change**: Check available models with `claude --help` or the Anthropic docs.
- **Works better with code files in working dir**: Put code files in `pwd` so Claude Code can `cat` them. Passing file paths in the prompt alone may not work — Claude Code needs access.
