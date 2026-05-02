# PyPI release checklist (NAQSHA)

This is an operational checklist for maintainers. It does not claim compliance with any registry policy beyond common practice.

## Before tagging

- [ ] `uv run --extra dev ruff check .` is clean.
- [ ] `uv run --extra dev pytest` passes (includes wheel/sdist install smoke tests).
- [ ] `uv build` (or `python -m build`) produces a wheel and sdist without warnings you care about.
- [ ] `README.md` and `docs/handoff/0001-v1-development-workflow.md` match shipping behavior for this version.
- [ ] Version in `pyproject.toml` matches the intended **public** distribution name **`naqsha`** (not `naqsh`).

## Versioning

- Follow [semantic versioning](https://semver.org/) for public API and CLI expectations: bump **MAJOR** for incompatible behavior or contract changes, **MINOR** for backward-compatible additions, **PATCH** for fixes.
- After a change to the persisted **QAOA Trace** shape, bump `QAOA_TRACE_SCHEMA_VERSION` per `protocols/qaoa.py`; release notes should call out trace compatibility.

## Build and upload

- Prefer a clean tree: `git status` should show no unintended artifacts.
- Build: `uv build` (outputs under `dist/`).
- Upload (after configuring [PyPI trusted publishing](https://docs.pypi.org/trusted-publishers/) or API tokens):

  ```bash
  python -m pip install twine
  twine check dist/*
  twine upload dist/*
  ```

- Optionally validate on [TestPyPI](https://test.pypi.org/) first with the same `twine check` / `twine upload --repository testpypi dist/*` flow.

## After release

- [ ] Push the git tag that matches `pyproject.toml` version (if you tag releases).
- [ ] Confirm `pip install naqsha==<version>` imports `naqsha` and `naqsha run --profile local-fake "ping"` works with no API keys.
