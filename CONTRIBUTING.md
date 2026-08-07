# Contributing to ${repo}

## Development Setup

```bash
# Clone
git clone <repo-url>
cd ${repo}

# Install dependencies
pip install -e ".[dev]" 2>/dev/null || pip install -e . 2>/dev/null || npm install

# Run tests
python3 -m pytest -v 2>/dev/null || npm test
```

## Code Style

- Python: follow PEP 8, use type hints for public functions
- Tests: every new feature needs test coverage
- Commits: conventional commits (feat:, fix:, test:, docs:, chore:)

## Architecture

See README.md for the component's role in the Slackwater fleet.

## Pull Request Checklist

- [ ] Tests pass locally
- [ ] New code has test coverage
- [ ] No secrets or credentials committed
- [ ] Documentation updated if behavior changed
