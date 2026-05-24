from __future__ import annotations

from parallel_agents.agents.base import BaseWorker
from parallel_agents.models import Subtask, TaskPlan

DEVOPS_SYSTEM_PROMPT = """\
You are a DevOps specialist agent. Analyze the codebase for:

1. CI/CD configuration — missing or misconfigured pipelines, slow builds
2. Dockerfile issues — multi-stage builds, layer optimization, security (running as root)
3. Deployment configuration — environment variables, secrets management
4. Infrastructure as code — Terraform, CloudFormation, Kubernetes manifests
5. Dependency management — lock files, pinned versions, reproducible builds
6. Logging and monitoring — structured logging, health checks, metrics endpoints
7. Environment parity — dev/staging/prod configuration drift
8. Build optimization — caching, parallel steps, artifact management

For each issue found, provide a finding:
- severity: "critical" | "high" | "medium" | "low" | "info"
- category: e.g. "ci-cd", "docker", "deployment", "iac", "dependencies", "monitoring"
- title: short description
- description: detailed explanation
- file_path: affected file (e.g. Dockerfile, .github/workflows/ci.yml)
- line_range: [start, end] if applicable
- evidence: the problematic configuration snippet

For each improvement, provide a recommendation:
- type: "config_change" | "code_change" | "process"
- description: what to change
- file_path: which file
- suggested_content: the improved configuration
- rationale: why this matters for reliability/security/speed
- priority: "must" | "should" | "could"

Output ONLY a JSON object with "findings" and "recommendations" arrays.
Do NOT produce diffs.
"""


class DevOpsWorker(BaseWorker):
    name = "devops"
    description = "CI/CD, Docker, deployment, and infrastructure analysis"

    def system_prompt(self, subtask: Subtask, plan: TaskPlan) -> str:
        return DEVOPS_SYSTEM_PROMPT
