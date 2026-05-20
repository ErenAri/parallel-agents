"""Example: Run the parallel agent pipeline from a GitHub issue URL."""

import asyncio

from parallel_agents import Pipeline, PipelineConfig


async def main() -> None:
    config = PipelineConfig()
    pipeline = Pipeline(config)

    result = await pipeline.run(
        "https://github.com/your-org/your-repo/issues/42",
        repo_path="/path/to/local/clone",
        on_status=print,
    )

    print(f"\nSummary: {result.summary}")
    print(f"PR Summary:\n{result.pr_summary}")


if __name__ == "__main__":
    asyncio.run(main())
