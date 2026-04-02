"""角色状态回写节点

将结构化提取出的角色状态按权重规则合并回角色卡。
"""

from __future__ import annotations

from typing import AsyncIterator

from pydantic import BaseModel, Field

from app.schemas.entity import UpdateCharacterState
from app.services.memory_service import MemoryService
from app.services.workflow.nodes.base import BaseNode
from app.services.workflow.registry import register_node


class CharacterStateUpdateInput(BaseModel):
    project_id: int = Field(..., description="项目ID")
    data: UpdateCharacterState = Field(..., description="角色状态更新结果")


class CharacterStateUpdateOutput(BaseModel):
    success: bool = Field(..., description="是否更新成功")
    updated_card_count: int = Field(..., description="更新的角色卡数量")


@register_node
class CharacterStateUpdateNode(BaseNode[CharacterStateUpdateInput, CharacterStateUpdateOutput]):
    node_type = "Data.CharacterStateUpdate"
    category = "data"
    label = "更新角色状态"
    description = "按角色权重规则将最新角色状态合并回角色卡，仅保留最近有效记录"

    input_model = CharacterStateUpdateInput
    output_model = CharacterStateUpdateOutput

    async def execute(self, inputs: CharacterStateUpdateInput) -> AsyncIterator[CharacterStateUpdateOutput]:
        svc = MemoryService(self.context.session)
        result = svc.update_character_state(
            project_id=inputs.project_id,
            data=inputs.data,
        )
        yield CharacterStateUpdateOutput(
            success=result.get("success", False),
            updated_card_count=result.get("updated_card_count", 0),
        )
