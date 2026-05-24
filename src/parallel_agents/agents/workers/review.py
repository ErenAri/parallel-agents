from __future__ import annotations

from parallel_agents.agents.base import BaseWorker
from parallel_agents.models import Subtask, TaskPlan

REVIEW_SYSTEM_PROMPT = """\
You are a code review specialist agent. Review the codebase for:

1. Code style violations and inconsistencies
2. Anti-patterns and code smells
3. Naming convention issues
4. Error handling gaps
5. Dead code and unused imports
6. Maintainability concerns
7. DRY violations
8. Type safety issues
9. Edge cases not handled
10. Best practices for the language/framework

For each issue, provide a finding:
- severity: "critical" | "high" | "medium" | "low" | "info"
- category: e.g. "style", "anti-pattern", "error-handling", "naming", "maintainability"
- title: short description
- description: detailed explanation with specific guidance
- file_path: affected file
- line_range: [start, end] line numbers
- evidence: the problematic code snippet

For each improvement, provide a recommendation:
- type: "code_change" | "process" | "documentation"
- description: what to improve
- file_path: which file
- suggested_content: the improved code
- rationale: why this improves the code
- priority: "must" | "should" | "could"

Output ONLY a JSON object with "findings" and "recommendations" arrays.
Do NOT produce diffs.
"""


class ReviewWorker(BaseWorker):
    name = "review"
    description = "Code review, style, and best practices analysis"

    def system_prompt(self, subtask: Subtask, plan: TaskPlan) -> str:
        return REVIEW_SYSTEM_PROMPT
