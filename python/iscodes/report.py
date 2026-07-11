"""Clause-referenced markdown calculation reports."""

from __future__ import annotations

from . import DISCLAIMER, tables


class Report:
    def __init__(self, title: str, code_refs: list[str] | None = None):
        self.title = title
        self.code_refs = code_refs or []
        self._parts: list[str] = []

    def add_section(self, heading: str) -> "Report":
        self._parts.append(f"\n## {heading}\n")
        return self

    def add_line(self, text: str) -> "Report":
        self._parts.append(text + "\n")
        return self

    def add_check(self, name: str, ok: bool, detail: str = "") -> "Report":
        mark = "✓" if ok else "✗"
        line = f"- {mark} {name}"
        if detail:
            line += f" — {detail}"
        self._parts.append(line + "\n")
        return self

    def add_checks(self, checks: list) -> "Report":
        for name, ok in checks:
            self.add_check(name, ok)
        return self

    def add_table(self, headers: list, rows: list) -> "Report":
        self._parts.append("| " + " | ".join(str(h) for h in headers) + " |\n")
        self._parts.append("|" + "---|" * len(headers) + "\n")
        for row in rows:
            self._parts.append("| " + " | ".join(str(c) for c in row) + " |\n")
        return self

    def add_figure(self, path: str, caption: str) -> "Report":
        self._parts.append(f"\n![{caption}]({path})\n*{caption}*\n")
        return self

    def render(self) -> str:
        out = [f"# {self.title}\n"]
        out += self._parts
        if self.code_refs:
            out.append("\n## Code references\n")
            for ref in self.code_refs:
                ed = tables.CODE_EDITIONS.get(ref, "")
                out.append(f"- {ref}" + (f" — {ed}" if ed else "") + "\n")
        out.append(f"\n---\n*{DISCLAIMER}*\n")
        return "".join(out)

    def save(self, path: str) -> str:
        with open(path, "w", encoding="utf-8") as f:
            f.write(self.render())
        return path


def summarize_checks(checks: list) -> tuple:
    fails = [name for name, ok in checks if not ok]
    return len(checks) - len(fails), len(fails), fails
