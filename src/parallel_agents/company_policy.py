from __future__ import annotations

import re
from typing import Any

from pydantic import BaseModel, Field, field_validator


DEFAULT_LABEL_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9 _./:-]{0,49}$"
DEFAULT_MILESTONE_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9 _./:-]{0,79}$"


class CompanyApplyPolicy(BaseModel):
    repo_allowlist: list[str] = Field(default_factory=list)
    label_allowlist: list[str] = Field(default_factory=list)
    milestone_allowlist: list[str] = Field(default_factory=list)
    label_pattern: str = DEFAULT_LABEL_PATTERN
    milestone_pattern: str = DEFAULT_MILESTONE_PATTERN

    @field_validator("repo_allowlist", "label_allowlist", "milestone_allowlist")
    @classmethod
    def _normalize_string_list(cls, value: list[str]) -> list[str]:
        seen: set[str] = set()
        normalized: list[str] = []
        for item in value:
            raw = str(item).strip()
            if not raw:
                continue
            lowered = raw.lower()
            if lowered in seen:
                continue
            seen.add(lowered)
            normalized.append(raw)
        return normalized

    @field_validator("label_pattern", "milestone_pattern")
    @classmethod
    def _validate_regex(cls, value: str) -> str:
        re.compile(value)
        return value


def derive_policy_from_issue_plan(repo_ref: str, issue_plan: list[Any]) -> CompanyApplyPolicy:
    label_allowlist: set[str] = set()
    milestone_allowlist: set[str] = set()

    for issue in issue_plan:
        raw_labels = _issue_field(issue, "labels", [])
        labels = list(raw_labels) if isinstance(raw_labels, list) else []
        for label in labels:
            cleaned = str(label).strip()
            if cleaned:
                label_allowlist.add(cleaned)

        milestone_name = str(_issue_field(issue, "milestone", "")).strip()
        if milestone_name:
            milestone_allowlist.add(milestone_name)

    return CompanyApplyPolicy(
        repo_allowlist=[repo_ref],
        label_allowlist=sorted(label_allowlist, key=str.lower),
        milestone_allowlist=sorted(milestone_allowlist, key=str.lower),
    )


def validate_issue_plan_against_policy(
    *,
    repo_ref: str,
    issue_plan: list[Any],
    policy: CompanyApplyPolicy,
) -> list[str]:
    violations: list[str] = []

    repo_allow = {_normalize(item) for item in policy.repo_allowlist}
    if repo_allow and _normalize(repo_ref) not in repo_allow:
        violations.append(
            f"Repository '{repo_ref}' is not in repo_allowlist: {sorted(policy.repo_allowlist)}"
        )

    label_allow = {_normalize(item) for item in policy.label_allowlist}
    milestone_allow = {_normalize(item) for item in policy.milestone_allowlist}

    label_regex = re.compile(policy.label_pattern)
    milestone_regex = re.compile(policy.milestone_pattern)

    for idx, issue in enumerate(issue_plan, start=1):
        issue_title = str(_issue_field(issue, "title", "")).strip() or f"issue-{idx}"
        raw_labels = _issue_field(issue, "labels", [])
        labels = list(raw_labels) if isinstance(raw_labels, list) else []
        for label in labels:
            cleaned_label = str(label).strip()
            if not cleaned_label:
                continue
            if label_allow and _normalize(cleaned_label) not in label_allow:
                violations.append(
                    f"Issue '{issue_title}' uses disallowed label '{cleaned_label}'"
                )
            if not label_regex.match(cleaned_label):
                violations.append(
                    f"Issue '{issue_title}' label '{cleaned_label}' violates label_pattern"
                )

        milestone_name = str(_issue_field(issue, "milestone", "")).strip()
        if milestone_name:
            if milestone_allow and _normalize(milestone_name) not in milestone_allow:
                violations.append(
                    f"Issue '{issue_title}' uses disallowed milestone '{milestone_name}'"
                )
            if not milestone_regex.match(milestone_name):
                violations.append(
                    f"Issue '{issue_title}' milestone '{milestone_name}' violates milestone_pattern"
                )

    return violations


def _issue_field(issue: Any, key: str, default: Any) -> Any:
    if isinstance(issue, dict):
        return issue.get(key, default)
    return getattr(issue, key, default)


def _normalize(value: str) -> str:
    return value.strip().lower()
