"""Bounded typed planning and source-aware DAG, with no effect rights."""
from pydantic import BaseModel, ConfigDict, Field
from .core import Blocked


class ToolCall(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str
    arguments: dict


class Task(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(min_length=1, max_length=64)
    dependencies: list[str] = Field(max_length=16)
    source_ids: list[str] = Field(max_length=128)
    tool: ToolCall


class Plan(BaseModel):
    model_config = ConfigDict(extra="forbid")
    tasks: list[Task] = Field(min_length=1, max_length=32)


from .public_batch_contract import PUBLIC_TOOLS as TOOLS, tool_schemas


def validate_plan(plan, source_ids):
    tasks = {t.id: t for t in plan.tasks}
    if len(tasks) != len(plan.tasks): raise Blocked("DUPLICATE_TASK")
    for task in tasks.values():
        if task.tool.name not in TOOLS: raise Blocked("TOOL_NOT_ADMITTED")
        if any(d not in tasks for d in task.dependencies) or any(s not in source_ids for s in task.source_ids):
            raise Blocked("MISSING_DEPENDENCY")
    order, visited, active = [], set(), set()
    def visit(key):
        if key in active: raise Blocked("DAG_CYCLE")
        if key in visited: return
        active.add(key)
        for dep in tasks[key].dependencies: visit(dep)
        active.remove(key)
        visited.add(key)
        order.append(key)
    for key in tasks: visit(key)
    return order
