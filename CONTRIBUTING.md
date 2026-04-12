# Contributing to sandclaw-memory

Thanks for your interest in contributing!

## Development Setup

```bash
# Clone the repo
git clone https://github.com/kokogo100/sandclaw-memory.git
cd sandclaw-memory

# Install dev dependencies
pip install -e ".[dev]"

# Run tests
python -m pytest

# Run linter
ruff check sandclaw_memory/

# Run type checker
pyright sandclaw_memory/
```

## Running Tests

```bash
# All tests
python -m pytest

# With coverage
python -m pytest --cov=sandclaw_memory

# Specific test file
python -m pytest tests/test_brain.py -v
```

## Code Style

- **Formatter**: Ruff (line length 100, double quotes)
- **Linter**: Ruff (E, F, W, I, UP, B, SIM rules)
- **Type checker**: Pyright (basic mode, Python 3.9+)
- **Comments**: English, explain WHY not WHAT

```bash
# Format
ruff format sandclaw_memory/

# Lint + auto-fix
ruff check --fix sandclaw_memory/
```

## Pull Request Guidelines

1. **One feature per PR** -- keep changes focused
2. **Add tests** -- all new code should have tests
3. **Run the full test suite** before submitting
4. **Update docstrings** if you change public API
5. **No new dependencies** -- zero-dependency is a core principle

## Architecture

```
sandclaw_memory/
  brain.py       -- BrainMemory (orchestrator)
  session.py     -- L1 SessionMemory (3-day Markdown)
  summary.py     -- L2 SummaryMemory (30-day AI summary)
  permanent.py   -- L3 ArchiveMemory (SQLite + FTS5)
  dispatcher.py  -- IntentDispatcher (depth detection)
  loader.py      -- TieredLoader (budget-aware loading)
  renderer.py    -- MarkdownRenderer (output formatting)
  types.py       -- Depth enum, MemoryEntry dataclass
  exceptions.py  -- Custom exception hierarchy
  utils.py       -- HookRegistry, helpers
```

## Reporting Issues

- Use [GitHub Issues](https://github.com/kokogo100/sandclaw-memory/issues)
- Include Python version, OS, and minimal reproduction code
- For security issues, email kokogo100@users.noreply.github.com

## License

By contributing, you agree that your contributions will be licensed under the MIT License.
