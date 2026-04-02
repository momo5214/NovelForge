from __future__ import annotations

from typing import Any, Dict

from sqlmodel import Session, select
from sqlalchemy import delete

from app.db.models import Card, NodeExecutionState
from app.schemas.entity import (
    CharacterStateSummaryResult,
    KeyEventItem,
    PositionTrackItem,
    UpdateCharacterState,
    CharacterStateUpdate,
)
from app.services.card_params_service import merge_effective_ai_params


POSTPROCESS_WORKFLOW_NAME = "增强章节后处理闭环"
POSTPROCESS_RESUME_INVALIDATE_NODES = [
    "selected_llm_config_id",
    "llm",
]


def resolve_manual_params_for_workflow_run(
    *,
    session: Session,
    workflow_name: str,
    manual_params: Dict[str, Any] | None,
    resume: bool = False,
    existing_params: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    params = dict(existing_params or {})
    params.update(manual_params or {})

    if workflow_name != POSTPROCESS_WORKFLOW_NAME:
        return params

    target_card_id = int(params.get("target_card_id") or 0)
    if target_card_id <= 0:
        if resume and existing_params:
            return params
        params["resolved_llm_config_source"] = "manual_params"
        return params

    card = session.get(Card, target_card_id)
    if not card:
        if resume and existing_params:
            return params
        params["resolved_llm_config_source"] = "manual_params"
        return params

    effective = merge_effective_ai_params(session, card)
    llm_config_id = effective.get("llm_config_id")
    if llm_config_id is not None:
        resolved_llm_config_id = int(llm_config_id)
        params["llm_config_id"] = resolved_llm_config_id
        params["resolved_llm_config_id"] = resolved_llm_config_id
        params["resolved_llm_config_source"] = (
            "card_effective_ai_params_resume"
            if resume
            else "card_effective_ai_params"
        )
    else:
        manual_llm_config_id = params.get("llm_config_id")
        if manual_llm_config_id is not None:
            params["resolved_llm_config_id"] = int(manual_llm_config_id)
        if "resolved_llm_config_source" not in params:
            params["resolved_llm_config_source"] = "manual_params"

    return params


def build_character_state_update_from_summary(
    summary_data: Dict[str, Any] | CharacterStateSummaryResult | None,
    *,
    volume_number: int,
    chapter_number: int,
) -> Dict[str, Any]:
    summary = (
        summary_data
        if isinstance(summary_data, CharacterStateSummaryResult)
        else CharacterStateSummaryResult.model_validate(summary_data or {"summary_list": []})
    )

    state_list: list[CharacterStateUpdate] = []
    for item in summary.summary_list:
        payload: Dict[str, Any] = {
            "name": item.name,
        }
        if item.aliases:
            payload["aliases"] = item.aliases
        if item.role_weight is not None:
            payload["role_weight"] = item.role_weight
        if item.life_state is not None:
            payload["life_state"] = item.life_state
        if item.inventory_items:
            payload["inventory_items"] = item.inventory_items
        if item.techniques:
            payload["techniques"] = item.techniques
        if item.relationship_network:
            payload["relationship_network"] = item.relationship_network
        if item.behavior_decision_pattern is not None:
            payload["behavior_decision_pattern"] = item.behavior_decision_pattern
        if item.dialogue_style_keywords is not None:
            payload["dialogue_style_keywords"] = item.dialogue_style_keywords
        if item.romance_state is not None:
            payload["romance_state"] = item.romance_state

        if item.latest_position is not None:
            payload["position_tracks"] = [
                PositionTrackItem(
                    volume_number=volume_number,
                    chapter_number=chapter_number,
                    location=item.latest_position.location,
                    event=item.latest_position.event,
                    companions=item.latest_position.companions,
                    purpose=item.latest_position.purpose,
                )
            ]

        if item.latest_event is not None:
            payload["key_event_records"] = [
                KeyEventItem(
                    volume_number=volume_number,
                    chapter_number=chapter_number,
                    event_type=item.latest_event.event_type,
                    summary=item.latest_event.summary,
                )
            ]

        state_list.append(CharacterStateUpdate.model_validate(payload))

    return UpdateCharacterState(state_list=state_list).model_dump(mode="json")


def invalidate_resume_node_states_for_workflow(
    *,
    session: Session,
    workflow_name: str,
    run_id: int,
) -> list[str]:
    if workflow_name != POSTPROCESS_WORKFLOW_NAME or run_id <= 0:
        return []

    stmt = select(NodeExecutionState.node_id).where(
        NodeExecutionState.run_id == run_id,
        NodeExecutionState.node_id.in_(POSTPROCESS_RESUME_INVALIDATE_NODES),
    )
    existing_node_ids = session.exec(stmt).all()
    if not existing_node_ids:
        return []

    session.exec(
        delete(NodeExecutionState).where(
            NodeExecutionState.run_id == run_id,
            NodeExecutionState.node_id.in_(POSTPROCESS_RESUME_INVALIDATE_NODES),
        )
    )
    session.commit()

    ordered = [node_id for node_id in POSTPROCESS_RESUME_INVALIDATE_NODES if node_id in existing_node_ids]
    return ordered
