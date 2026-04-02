"""角色库同步节点."""

from __future__ import annotations

from typing import AsyncIterator, Optional

from pydantic import BaseModel, Field
from app.schemas.wizard import ChapterCharacterDiscoveryResult
from app.services.character_roster_service import sync_character_roster
from app.services.workflow.nodes.base import BaseNode
from app.services.workflow.registry import register_node


class CharacterRosterSyncInput(BaseModel):
    project_id: int = Field(..., description="项目ID")
    parent_id: Optional[int] = Field(default=None, description="角色卡父节点ID")
    data: ChapterCharacterDiscoveryResult = Field(..., description="章节角色识别结果")


class CharacterRosterSyncOutput(BaseModel):
    success: bool = Field(..., description="是否执行成功")
    assigned_code_count: int = Field(default=0, description="补齐角色编号的角色卡数量")
    updated_card_count: int = Field(default=0, description="更新已有角色卡数量")
    created_card_count: int = Field(default=0, description="新建角色卡数量")


@register_node
class CharacterRosterSyncNode(BaseNode[CharacterRosterSyncInput, CharacterRosterSyncOutput]):
    node_type = "Data.CharacterRosterSync"
    category = "data"
    label = "同步角色库"
    description = "为角色卡补编号、归并别称，并把章节中新发现的角色建成角色卡"

    input_model = CharacterRosterSyncInput
    output_model = CharacterRosterSyncOutput

    async def execute(self, inputs: CharacterRosterSyncInput) -> AsyncIterator[CharacterRosterSyncOutput]:
        result = sync_character_roster(
            self.context.session,
            project_id=inputs.project_id,
            parent_id=inputs.parent_id,
            data=inputs.data,
        )

        yield CharacterRosterSyncOutput(
            success=result.success,
            assigned_code_count=result.assigned_code_count,
            updated_card_count=result.updated_card_count,
            created_card_count=result.created_card_count,
        )
