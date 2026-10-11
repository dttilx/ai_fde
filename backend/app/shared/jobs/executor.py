from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class JobTicket:
    job_id: str
    resource_id: str
    actor_id: str
    fence: int
    payload: dict


@dataclass(frozen=True)
class ExecutionResult:
    result_kind: Literal["PAUSED", "COMPLETED"]
    data: dict


Handler = Callable[[JobTicket], Awaitable[ExecutionResult]]


class ExecutorRegistry:
    def __init__(self):
        self.handlers: dict[str, Handler] = {}

    def register(self, kind: str, handler: Handler) -> None:
        self.handlers[kind] = handler

    async def execute(self, kind: str, ticket: JobTicket) -> ExecutionResult:
        handler = self.handlers.get(kind)
        if handler is None:
            raise RuntimeError("UNREGISTERED_EXECUTOR")
        return await handler(ticket)
