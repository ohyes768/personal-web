"""Shared four-stage executor for incremental update specifications."""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime
from logging import Logger
from typing import TYPE_CHECKING, TypeVar

from src.config import Settings
from src.models import UpdateResponse

if TYPE_CHECKING:
    from src.services.update_registry import UpdateSpec


Input = TypeVar("Input")
Payload = TypeVar("Payload")


@dataclass(frozen=True)
class UpdateStages:
    fetch: Callable[[], Awaitable[object]]
    validate: Callable[[object], object]
    save: Callable[[object], None]
    build_payload: Callable[[object], object]


class NoNewData(Exception):
    """A validated empty increment with the source's existing no-op semantics."""


class UpdateNoOp(Exception):
    """Preparation found an already-current store without needing a fetch."""

    def __init__(self, response: UpdateResponse):
        super().__init__(response.message)
        self.response = response


@dataclass(frozen=True)
class UpdatePlan:
    stages: UpdateStages
    on_no_data: Callable[[], UpdateResponse] | None = None


@dataclass(frozen=True)
class UpdateContext:
    """Explicit dependencies shared by historical routes and incremental updates.

    Factories stay lazy: constructing a context never opens an unused source.
    Lock callbacks use the same process-wide state as historical fetch routes.
    """

    settings: Settings
    logger: Logger
    is_updating: Callable[[], bool]
    acquire_update_lock: Callable[[], Awaitable[None]]
    release_update_lock: Callable[[], None]
    get_data_service: Callable
    get_fred_service: Callable
    get_vix_service: Callable
    get_hibor_service: Callable
    get_dr007_service: Callable
    get_dr001_service: Callable
    get_baostock_service: Callable
    get_margin_service: Callable
    get_fund_flow_service: Callable
    get_china_bond_service: Callable
    get_commodity_service: Callable
    get_index_service: Callable
    fetch_us_treasuries: Callable
    fetch_oecd_bonds: Callable
    fetch_exchange_rates: Callable
    compute_incremental_start: Callable
    has_observations: Callable
    empty_increment_is_current: Callable
    empty_increment_fail_message: Callable
    build_response_data_with_rates: Callable
    exchange_rebuild_msg: str


class UpdatePipeline:
    @staticmethod
    async def execute(spec: "UpdateSpec", context: UpdateContext) -> UpdateResponse:
        if context.is_updating():
            return UpdateResponse(
                success=False,
                message="数据更新正在进行中，请稍后再试",
                error_code="UPDATE_IN_PROGRESS",
            )

        await context.acquire_update_lock()
        try:
            plan = spec.build_stages(context)
            try:
                payload = await UpdatePipeline.run_stages(plan.stages)
            except NoNewData:
                if plan.on_no_data is None:
                    raise
                return plan.on_no_data()
            context.logger.info(spec.success_message)
            return UpdateResponse(
                success=True,
                message=spec.success_message,
                data=payload,
                updated_at=datetime.now().isoformat(),
            )
        except UpdateNoOp as no_op:
            return no_op.response
        except Exception as error:
            message = f"{spec.failure_message}: {error}"
            context.logger.error(message)
            return UpdateResponse(
                success=False,
                message=message,
                error_code="UPDATE_FAILED",
            )
        finally:
            context.release_update_lock()

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
