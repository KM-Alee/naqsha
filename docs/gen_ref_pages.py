"""Generate API reference stubs for MkDocs (mkdocs-gen-files + mkdocstrings)."""

from __future__ import annotations

import mkdocs_gen_files

# One page per domain package (V2 layout) plus flat public package.
PACKAGES: list[tuple[str, str, str]] = [
    ("naqsha", "naqsha", "Public package (`from naqsha import …`)"),
    ("core", "naqsha.core", "Headless Core Runtime, Event Bus, policy, budgets"),
    ("models", "naqsha.models", "NAP V2 and Thin Model Adapters"),
    ("tools", "naqsha.tools", "Decorator-Driven API and tool execution"),
    ("memory", "naqsha.memory", "Dynamic Memory Engine and Memory Port adapters"),
    ("orchestration", "naqsha.orchestration", "Team topology and Tool-Based Delegation"),
    ("tracing", "naqsha.tracing", "Hierarchical QAOA Trace span helpers"),
    ("reflection", "naqsha.reflection", "Reflection Loop and Automated Rollback Manager"),
    ("tui", "naqsha.tui", "Workbench TUI (optional dependency)"),
]


def _write_module_page(slug: str, module: str, blurb: str) -> None:
    path = f"reference/{slug}.md"
    with mkdocs_gen_files.open(path, "w") as f:
        f.write(f"# `{module}`\n\n{blurb}\n\n")
        f.write(f"::: {module}\n")


def _write_index() -> None:
    with mkdocs_gen_files.open("reference/index.md", "w") as f:
        f.write("# API reference\n\n")
        f.write(
            "These pages are generated from Python docstrings using "
            "[mkdocstrings](https://mkdocstrings.github.io/). "
            "Import from the `naqsha` package in application code; domain subpackages "
            "mirror the architecture described in **Concepts**.\n\n"
        )
        for slug, module, blurb in PACKAGES:
            title = module if slug != "naqsha" else "naqsha (flat exports)"
            f.write(f"- [{title}]({slug}.md) — {blurb}\n")


_write_index()
for slug, module, blurb in PACKAGES:
    _write_module_page(slug, module, blurb)
