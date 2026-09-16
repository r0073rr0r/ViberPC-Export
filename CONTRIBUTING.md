# Contributing to ViberPC-Export

Thanks for taking the time to contribute! 🎉

This is a small, focused tool for reading **your own** Viber Desktop database on
**your own** machine. Contributions that keep it simple, local, and safe are
very welcome.

## Ground rules

- **Scope.** This project only supports accessing data that belongs to you, on
  your own computer. Pull requests that add features for accessing other
  people's data, remote exfiltration, or bypassing another person's device will
  be rejected. See the [Code of Conduct](CODE_OF_CONDUCT.md).
- **License.** By contributing you agree that your contribution is licensed
  under the [GNU GPL-3.0](LICENSE).

## Getting started

```bash
git clone https://github.com/r0073rr0r/ViberPC-Export.git
cd ViberPC-Export
python -m venv .venv && .venv\Scripts\activate   # Windows
pip install -r requirements.txt
python viber.py doctor
```

## Development workflow

1. Create a branch from `main`: `git checkout -b feature/my-change`.
2. Make your change. Keep it small and focused.
3. Run the tests and the linter locally — CI runs both on Python 3.10–3.13:
   ```bash
   pip install pytest "pylint==4.0.8"
   pytest -q
   pylint $(git ls-files '*.py')
   ```
   The build requires green tests and a clean lint (score 10/10 with the repo's `.pylintrc`).
4. Never commit real data. `export/`, `*.db`, `*.txt` dumps and `.env` are
   already git-ignored — please keep it that way.
5. Open a pull request against `main` and fill in the template.

## Style

- Python 3.10+.
- Follow the existing style; the repo ships a `.pylintrc` that encodes it.
- Prefer clear, small functions. Lazy-import heavy/optional dependencies
  (`frida`, `sqlcipher3`) the way the existing code does.

## Reporting bugs / requesting features

Use the [issue templates](https://github.com/r0073rr0r/ViberPC-Export/issues/new/choose).
For anything security-related, follow the [Security Policy](SECURITY.md) instead
of opening a public issue.
