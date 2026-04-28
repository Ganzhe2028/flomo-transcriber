from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Sequence
    from pathlib import Path


class Severity(StrEnum):
    ERROR = "error"
    WARNING = "warning"


@dataclass(frozen=True)
class Violation:
    rule: Any
    severity: Severity
    message: str
    table: str = ""
    line: int = 0
    record_id: str = ""


@dataclass
class ValidationReport:
    violations: list[Violation] = field(default_factory=list)
    default_table: str = ""
    table_order: Sequence[str] = field(default_factory=tuple)
    include_warning_count: bool = False
    show_line_numbers: bool = True

    @property
    def errors(self) -> list[Violation]:
        return [
            violation
            for violation in self.violations
            if violation.severity == Severity.ERROR
        ]

    @property
    def warnings(self) -> list[Violation]:
        return [
            violation
            for violation in self.violations
            if violation.severity == Severity.WARNING
        ]

    @property
    def ok(self) -> bool:
        return not self.errors

    def add(self, violation: Violation) -> None:
        self.violations.append(violation)

    def format_summary(self) -> str:
        error_count = len(self.errors)
        warning_count = len(self.warnings)
        if self.ok:
            if self.include_warning_count:
                return f"Validation passed ({warning_count} warning(s))"
            return "Validation passed (0 error(s))"
        if self.include_warning_count or warning_count:
            return f"Validation failed: {error_count} error(s), {warning_count} warning(s)"
        return f"Validation failed: {error_count} error(s)"

    def format_detail(self) -> str:
        lines: list[str] = []
        by_table: dict[str, list[Violation]] = {}
        for violation in self.violations:
            table = violation.table or self.default_table
            by_table.setdefault(table, []).append(violation)

        ordered_tables = [
            table
            for table in self.table_order
            if table in by_table
        ]
        ordered_tables.extend(sorted(table for table in by_table if table not in ordered_tables))

        for table in ordered_tables:
            if table:
                lines.append(f"\n-- {table} --")
            violations = by_table[table]
            for violation in sorted(
                violations,
                key=lambda item: (item.line, _rule_value(item.rule), item.record_id),
            ):
                lines.append(self._format_violation(violation))

        lines.append("")
        lines.append(self.format_summary())
        return "\n".join(lines)

    def _format_violation(self, violation: Violation) -> str:
        record_suffix = f" [{violation.record_id}]" if violation.record_id else ""
        location = ""
        if self.show_line_numbers:
            label = f"line {violation.line}" if violation.line > 0 else "global"
            location = f" {label:>10}"
        return (
            f"  {violation.severity.value.upper():7} "
            f"{_rule_value(violation.rule):3}{location}{record_suffix}  "
            f"{violation.message}"
        )


def _rule_value(rule: Any) -> str:
    return str(getattr(rule, "value", rule))


def load_jsonl_for_validation(
    path: Path,
    *,
    report: ValidationReport,
    table: str,
    rule: Any,
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    if not path.exists():
        report.add(
            Violation(
                rule=rule,
                severity=Severity.ERROR,
                message=f"File not found: {path}",
                table=table,
                line=0,
                record_id="",
            )
        )
        return records

    for line_number, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw_line.strip()
        if not line:
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError as exc:
            report.add(
                Violation(
                    rule=rule,
                    severity=Severity.ERROR,
                    message=f"JSON parse error: {exc}",
                    table=table,
                    line=line_number,
                    record_id="",
                )
            )
            continue

        if not isinstance(payload, dict):
            report.add(
                Violation(
                    rule=rule,
                    severity=Severity.ERROR,
                    message="JSONL row must be an object",
                    table=table,
                    line=line_number,
                    record_id="",
                )
            )
            continue
        records.append(payload)
    return records


def load_json_for_validation(
    path: Path,
    *,
    report: ValidationReport,
    table: str,
    rule: Any,
) -> dict[str, Any] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        report.add(
            Violation(
                rule=rule,
                severity=Severity.ERROR,
                message=f"JSON parse error: {exc}",
                table=table,
                record_id=path.name,
            )
        )
        return None

    if not isinstance(payload, dict):
        report.add(
            Violation(
                rule=rule,
                severity=Severity.ERROR,
                message="JSON file must be an object",
                table=table,
                record_id=path.name,
            )
        )
        return None
    return payload
