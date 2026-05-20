"""Example: Run the parallel agent pipeline on a local repo with a free-text task."""

import asyncio

from parallel_agents import Pipeline, PipelineConfig
from parallel_agents.config import WorkerConfig


async def main() -> None:
    config = PipelineConfig(
        workers={
            "security": WorkerConfig(enabled=True),
            "code": WorkerConfig(enabled=True, model="opus"),
            "review": WorkerConfig(enabled=True),
        },
        max_parallel_workers=3,
    )

    pipeline = Pipeline(config)
    result = await pipeline.run(
        "Review this project for security issues and code quality",
        repo_path=".",
        on_status=print,
    )

    print(f"\nSummary: {result.summary}")
    print(f"Findings: {len(result.risk_report)}")
    if result.patch:
        print(f"\nPatch:\n{result.patch}")


if __name__ == "__main__":
    asyncio.run(main())
