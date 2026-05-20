from __future__ import annotations

from parallel_agents.config import PipelineConfig
from parallel_agents.models import Subtask, TaskPlan


def split_tasks(plan: TaskPlan, config: PipelineConfig) -> list[list[Subtask]]:
    """Split a TaskPlan into batches of parallelizable subtasks.

    Returns a list of batches. Subtasks within a batch can run in parallel.
    Batches must be executed sequentially (each batch may depend on prior ones).
    """
    enabled_workers = {
        name for name, wc in config.workers.items() if wc.enabled
    }
    subtasks = [s for s in plan.subtasks if s.assigned_worker in enabled_workers]

    if not subtasks:
        return []

    subtask_map = {s.id: s for s in subtasks}
    completed: set[str] = set()
    batches: list[list[Subtask]] = []

    remaining = set(subtask_map.keys())
    while remaining:
        batch: list[Subtask] = []
        for sid in list(remaining):
            st = subtask_map[sid]
            deps_met = all(d in completed or d not in subtask_map for d in st.dependencies)
            if deps_met:
                batch.append(st)

        if not batch:
            batch = [subtask_map[sid] for sid in remaining]
            remaining.clear()
        else:
            for st in batch:
                remaining.discard(st.id)

        batch.sort(key=lambda s: -s.priority)
        batches.append(batch)
        completed.update(s.id for s in batch)

    return batches
