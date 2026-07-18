"""Deterministic workflow shell for world generation.

The orchestrator owns node lifecycle, budgets, contract validation, repair
records and stop decisions.  LLM builders remain pure workers and cannot mark a
run successful on their own.
"""
from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import structlog
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from llm.usage_context import current_usage_accumulator, usage_context
from models.generation_task import (
    GenerationAction,
    GenerationNodeRun,
    GenerationTask,
    GenerationViolation,
)
from schemas.world_generation import (
    ContractViolation,
    DirectorAction,
    DirectorActionType,
    ViolationSeverity,
    WorldSpec,
)
from utils import utcnow

logger = structlog.get_logger()


class GenerationBudgetExceeded(RuntimeError):
    pass


class GenerationContractError(RuntimeError):
    def __init__(self, violations: list[ContractViolation]):
        self.violations = violations
        super().__init__("; ".join(v.message for v in violations))


class WorldGenerationOrchestrator:
    def __init__(
        self,
        *,
        session_factory: async_sessionmaker[AsyncSession] | None,
        task_id: str | None,
    ) -> None:
        self.session_factory = session_factory
        self.task_id = task_id
        self.spec: WorldSpec | None = None
        self.generation_run_id = task_id or "unpersisted"
        self.completed_nodes = 0
        self.actual_calls = 0
        self.planned_calls = 0

    async def initialize(self) -> str:
        if self.session_factory is None or self.task_id is None:
            return self.generation_run_id
        async with self.session_factory() as session:
            task = await session.get(GenerationTask, self.task_id)
            if task is None:
                return self.generation_run_id
            self.generation_run_id = str(task.generation_run_id or task.id)
        return self.generation_run_id

    async def set_spec(self, spec: WorldSpec) -> None:
        self.spec = spec
        self._check_budget()
        if self.session_factory is None or self.task_id is None:
            return
        async with self.session_factory() as session:
            task = await session.get(GenerationTask, self.task_id)
            if task is None:
                return
            task.world_spec = spec.model_dump(mode="json")
            task.world_spec_version = spec.version
            await session.commit()

    async def stream_node(
        self,
        node_id: str,
        source: AsyncIterator[dict],
        *,
        estimated_calls: int = 1,
        count_calls: bool = True,
        actual_call_floor: int = 0,
    ) -> AsyncIterator[dict]:
        self._check_budget(projected_calls=estimated_calls)
        self.planned_calls += estimated_calls
        node_run_id = await self._start_node(node_id, estimated_calls)
        accumulator = current_usage_accumulator()
        before_calls = len(accumulator.entries) if accumulator is not None else 0
        try:
            with usage_context(phase=node_id):
                async for event in source:
                    yield event
            after_calls = len(accumulator.entries) if accumulator is not None else before_calls
            observed_calls = max(0, after_calls - before_calls) if count_calls else 0
            # Grok web_search does not emit token usage. Let deterministic
            # external-call nodes supply a floor so persisted metrics do not
            # under-report real provider traffic.
            actual_calls = max(actual_call_floor, observed_calls)
            self.actual_calls += actual_calls
            self.completed_nodes += 1
            await self._finish_node(node_run_id, "succeeded", actual_calls=actual_calls)
            self._check_budget()
        except Exception as exc:
            after_calls = len(accumulator.entries) if accumulator is not None else before_calls
            observed_calls = max(0, after_calls - before_calls) if count_calls else 0
            reported_calls = getattr(exc, "actual_calls", None)
            failed_calls = max(
                observed_calls,
                int(reported_calls) if reported_calls is not None else actual_call_floor,
            )
            self.actual_calls += failed_calls
            await self._finish_node(
                node_run_id,
                "failed",
                actual_calls=failed_calls,
                reason=str(exc),
            )
            await self.record_action(
                DirectorAction(
                    action_type=DirectorActionType.STOP,
                    target_node=node_id,
                    reason=f"node failed: {type(exc).__name__}",
                ),
                node_run_id=node_run_id,
            )
            raise

    async def run_value_node(
        self,
        node_id: str,
        awaitable: Any,
        *,
        estimated_calls: int = 1,
    ) -> Any:
        self._check_budget(projected_calls=estimated_calls)
        self.planned_calls += estimated_calls
        node_run_id = await self._start_node(node_id, estimated_calls)
        accumulator = current_usage_accumulator()
        before_calls = len(accumulator.entries) if accumulator is not None else 0
        try:
            with usage_context(phase=node_id):
                value = await awaitable
            after_calls = len(accumulator.entries) if accumulator is not None else before_calls
            actual_calls = max(0, after_calls - before_calls)
            self.actual_calls += actual_calls
            self.completed_nodes += 1
            await self._finish_node(node_run_id, "succeeded", actual_calls=actual_calls)
            self._check_budget()
            return value
        except Exception as exc:
            await self._finish_node(node_run_id, "failed", reason=str(exc))
            raise

    def _check_budget(self, *, projected_calls: int = 0) -> None:
        if self.spec is None:
            return
        if self.completed_nodes > self.spec.node_budget:
            raise GenerationBudgetExceeded(
                f"node budget exceeded: {self.completed_nodes}/{self.spec.node_budget}"
            )
        used_calls = max(self.actual_calls, self.planned_calls)
        if used_calls + projected_calls > self.spec.text_call_budget:
            raise GenerationBudgetExceeded(
                "LLM call budget exceeded: "
                f"{used_calls}+{projected_calls}/{self.spec.text_call_budget}"
            )

    async def validate_and_repair_payload(
        self, payload: dict, *, final: bool = False
    ) -> list[ContractViolation]:
        """Run deterministic repairs once, persist violations, then revalidate."""
        # Standalone builder unit tests intentionally run without persistence
        # and use one-character fixtures. Production tasks always provide the
        # session factory, which is where the contract is authoritative.
        if self.spec is None or self.session_factory is None:
            return []
        initial = self.validate_payload(payload, final=final)
        repairable = [v for v in initial if v.repairable]
        if repairable:
            self._repair_payload(payload)
            action_id = await self.record_action(
                DirectorAction(
                    action_type=DirectorActionType.REPAIR,
                    target_node="contract_validation",
                    reason="deterministic contract normalization",
                    payload={"codes": [v.code for v in repairable]},
                )
            )
        else:
            action_id = None

        violations = self.validate_payload(payload, final=final)
        remaining_codes = {v.code for v in violations}
        await self.record_violations(
            initial,
            resolved_codes={v.code for v in initial if v.code not in remaining_codes},
            resolved_by_action_id=action_id,
        )
        if action_id and not violations:
            logger.info("world_contract_repaired", action_id=action_id)
        blocking = [v for v in violations if v.severity == ViolationSeverity.BLOCKING]
        if blocking:
            await self.record_action(
                DirectorAction(
                    action_type=DirectorActionType.STOP,
                    target_node="contract_validation",
                    reason="blocking contract violations remain",
                    payload={"codes": [v.code for v in blocking]},
                )
            )
            raise GenerationContractError(blocking)
        return violations

    def validate_payload(self, payload: dict, *, final: bool = False) -> list[ContractViolation]:
        assert self.spec is not None
        out: list[ContractViolation] = []
        chars = [c for c in payload.get("world_characters") or [] if isinstance(c, dict)]
        names = [str(c.get("name") or "").strip() for c in chars]
        name_set = {n for n in names if n}
        locations = [x for x in payload.get("locations") or [] if isinstance(x, dict)]
        loc_names = {str(x.get("name") or "").strip() for x in locations if x.get("name")}
        playable = [x for x in payload.get("playable") or [] if isinstance(x, dict)]
        playable_names = {str(x.get("name") or "").strip() for x in playable if x.get("name")}

        def add(code: str, severity: ViolationSeverity, path: str, message: str, repairable: bool = False) -> None:
            out.append(ContractViolation(code=code, severity=severity, path=path, message=message, repairable=repairable))

        if not str(payload.get("name") or "").strip():
            add("world_name_missing", ViolationSeverity.BLOCKING, "name", "世界名为空")
        if len(chars) < self.spec.scale.active_roles_min:
            add(
                "active_roles_below_min",
                ViolationSeverity.BLOCKING,
                "world_characters",
                f"角色数 {len(chars)} 低于 WorldSpec 下限 {self.spec.scale.active_roles_min}",
            )
        if len(names) != len(name_set):
            add("character_name_duplicate", ViolationSeverity.BLOCKING, "world_characters", "角色名重复", True)
        missing = [n for n in self.spec.must_have_characters if n not in name_set]
        if missing:
            add("must_have_missing", ViolationSeverity.BLOCKING, "world_characters", f"缺少必含角色：{', '.join(missing)}")
        if len(playable_names) < self.spec.scale.playable_min:
            add("playable_below_min", ViolationSeverity.BLOCKING, "playable", "可玩角色不足")
        if not playable_names.issubset(name_set):
            add("playable_unknown_character", ViolationSeverity.BLOCKING, "playable", "可玩角色不在角色表", True)

        unknown_locations: list[str] = []
        for c in chars:
            refs = [c.get("initial_location")] + list((c.get("schedule") or {}).values())
            for ref in refs:
                if ref and str(ref) not in loc_names:
                    unknown_locations.append(str(ref))
        if unknown_locations:
            add("location_reference_unknown", ViolationSeverity.WARNING, "world_characters.schedule", "角色引用了未登记地点", True)

        if final:
            if len(payload.get("events_data") or []) < max(3, self.spec.scale.events_target // 2):
                add("events_below_min", ViolationSeverity.BLOCKING, "events_data", "可触发事件不足")
            if not payload.get("cover_image") or not payload.get("hero_image"):
                add("world_images_missing", ViolationSeverity.WARNING, "cover_image", "世界图片缺失")
        return out

    def _repair_payload(self, payload: dict) -> None:
        chars = [c for c in payload.get("world_characters") or [] if isinstance(c, dict)]
        seen: set[str] = set()
        deduped: list[dict] = []
        for char in chars:
            name = str(char.get("name") or "").strip()
            if not name or name in seen:
                continue
            seen.add(name)
            deduped.append(char)
        payload["world_characters"] = deduped

        playable_names = {
            str(p.get("name") or "").strip()
            for p in payload.get("playable") or []
            if isinstance(p, dict) and p.get("name")
        }
        payload["playable"] = [p for p in payload.get("playable") or [] if isinstance(p, dict) and p.get("name") in seen]
        for char in deduped:
            name = str(char.get("name") or "")
            char["playable_role"] = name in playable_names
            char["portrait_target"] = bool(char.get("portrait_target", char.get("is_image_target", False)))
            char["is_image_target"] = char["portrait_target"]

        locations = [x for x in payload.get("locations") or [] if isinstance(x, dict)]
        loc_names = {str(x.get("name") or "") for x in locations if x.get("name")}
        for char in deduped:
            refs = [char.get("initial_location")] + list((char.get("schedule") or {}).values())
            for ref in refs:
                if ref and str(ref) not in loc_names:
                    locations.append({"name": str(ref), "description": ""})
                    loc_names.add(str(ref))
        payload["locations"] = locations

    async def _start_node(self, node_id: str, estimated_calls: int) -> str | None:
        if self.session_factory is None or self.task_id is None:
            return None
        async with self.session_factory() as session:
            attempt = (
                await session.execute(
                    select(func.count()).select_from(GenerationNodeRun).where(
                        GenerationNodeRun.task_id == self.task_id,
                        GenerationNodeRun.node_id == node_id,
                    )
                )
            ).scalar_one() + 1
            row = GenerationNodeRun(
                generation_run_id=self.generation_run_id,
                task_id=self.task_id,
                node_id=node_id,
                attempt=attempt,
                estimated_calls=estimated_calls,
                spec_version=self.spec.version if self.spec else 0,
            )
            session.add(row)
            await session.commit()
            return str(row.id)

    async def _finish_node(self, node_run_id: str | None, status: str, *, actual_calls: int = 0, reason: str | None = None) -> None:
        if self.session_factory is None or node_run_id is None:
            return
        async with self.session_factory() as session:
            row = await session.get(GenerationNodeRun, node_run_id)
            if row is None:
                return
            row.status = status
            row.actual_calls = actual_calls
            row.reason = reason
            row.finished_at = utcnow()
            await session.commit()

    async def record_action(self, action: DirectorAction, *, node_run_id: str | None = None) -> str | None:
        if self.session_factory is None or self.task_id is None:
            return None
        async with self.session_factory() as session:
            row = GenerationAction(
                generation_run_id=self.generation_run_id,
                task_id=self.task_id,
                node_run_id=node_run_id,
                action_type=action.action_type.value,
                target_node=action.target_node,
                reason=action.reason,
                payload=action.payload,
            )
            session.add(row)
            await session.commit()
            return str(row.id)

    async def record_violations(
        self,
        violations: list[ContractViolation],
        *,
        resolved_codes: set[str] | None = None,
        resolved_by_action_id: str | None = None,
    ) -> None:
        if self.session_factory is None or self.task_id is None or not violations:
            return
        async with self.session_factory() as session:
            session.add_all(
                [
                    GenerationViolation(
                        generation_run_id=self.generation_run_id,
                        task_id=self.task_id,
                        code=v.code,
                        severity=v.severity.value,
                        path=v.path,
                        message=v.message,
                        repairable=v.repairable,
                        resolved=v.code in (resolved_codes or set()),
                        resolved_by_action_id=(
                            resolved_by_action_id if v.code in (resolved_codes or set()) else None
                        ),
                    )
                    for v in violations
                ]
            )
            await session.commit()
