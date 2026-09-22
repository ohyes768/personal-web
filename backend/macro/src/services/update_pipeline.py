"""Shared four-stage executor for incremental update specifications."""
from dataclasses import dataclass
from collections.abc import Awaitable, Callable
from typing import TypeVar


Input = TypeVar("Input")
Payload = TypeVar("Payload")


@dataclass(frozen=True)
class UpdateStages:
    fetch: Callable[[], Awaitable[object]]
    validate: Callable[[object], object]
    save: Callable[[object], None]
    build_payload: Callable[[object], object]


class UpdatePipeline:
    @staticmethod
    async def run(
        fetch: Callable[[], Awaitable[Input]],
        validate: Callable[[Input], Input],
        save: Callable[[Input], None],
        build_payload: Callable[[Input], Payload],
    ) -> Payload:
        data = await fetch()
        data = validate(data)
        save(data)
        return build_payload(data)

    @staticmethod
    async def run_stages(stages: UpdateStages) -> object:
        return await UpdatePipeline.run(
            stages.fetch, stages.validate, stages.save, stages.build_payload
        )
