# Contributing to AI Empire

Thanks for your interest in contributing! AI Empire is a community project.

## Code of Conduct
Be respectful. Help others. No harassment.

## How to Contribute

### Reporting Bugs
Use the [bug report template](.github/ISSUE_TEMPLATE/bug_report.md).

### Suggesting Features
Use the [feature request template](.github/ISSUE_TEMPLATE/feature_request.md).

### Submitting Pull Requests
1. Fork the repo
2. Create a branch: `git checkout -b feature/my-feature`
3. Make your changes
4. Add tests
5. Run the test suite: `pytest tests/`
6. Commit: `git commit -m "feat: add my feature"`
7. Push: `git push origin feature/my-feature`
8. Open a PR using the [PR template](.github/PULL_REQUEST_TEMPLATE.md)

## Development Setup

```bash
# Clone
git clone https://github.com/GrupoANDevelopment-m/ai-empire
cd ai-empire

# Install dependencies
pip install -r requirements.txt

# Set up pre-commit hooks
pre-commit install

# Run tests
pytest tests/ -v
```

## Coding Standards

- **Python**: PEP 8, type hints, max line length 100
- **YAML**: 2-space indent
- **Shell**: shellcheck clean
- **Markdown**: CommonMark
- **Commit messages**: Conventional Commits (feat:, fix:, docs:, test:, refactor:)

## Architecture
See [docs/architecture/](docs/architecture/) for ADRs and system design.

## License
By contributing, you agree that your contributions will be licensed under MIT.
