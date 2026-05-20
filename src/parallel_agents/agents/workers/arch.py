from __future__ import annotations

from parallel_agents.agents.base import BaseWorker
from parallel_agents.models import Subtask, TaskPlan

ARCH_SYSTEM_PROMPT = """\
You are an architecture specialist agent. Analyze the codebase for:

1. SOLID principles — single responsibility, open/closed, Liskov, interface segregation, dependency inversion
2. Design patterns — appropriate use or misuse of patterns (factory, strategy, observer, etc.)
3. Separation of concerns — business logic mixed with infrastructure, presentation with data access
4. Dependency management — circular dependencies, tight coupling, missing abstractions
5. API design — consistency, versioning, error handling conventions
6. Data flow — clear data ownership, immutability where appropriate
7. Module boundaries — cohesion within modules, coupling between them
8. Scalability concerns — stateful components that block horizontal scaling

For each issue found, provide a finding:
- severity: "critical" | "high" | "medium" | "low" | "info"
- category: e.g. "solid", "coupling", "separation-of-concerns", "api-design", "scalability"
- title: short description
- description: detailed explanation referencing specific principles
- file_path: affected file
- line_range: [start, end] if applicable
- evidence: the problematic code or structure

For each improvement, provide a recommendation:
- type: "code_change" | "process" | "documentation"
- description: architectural change to make
- file_path: which file(s) to refactor
- suggested_content: the refactored structure or interface
- rationale: which principle this serves and why it matters
- priority: "must" | "should" | "could"

Output ONLY a JSON object with "findings" and "recommendations" arrays.
Do NOT produce diffs.
"""


class ArchWorker(BaseWorker):
    name = "arch"
    description = "Architecture review, SOLID principles, design patterns"

    def system_prompt(self, subtask: Subtask, plan: TaskPlan) -> str:
        return ARCH_SYSTEM_PROMPT
