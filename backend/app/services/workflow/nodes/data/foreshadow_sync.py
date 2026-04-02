"""伏笔同步节点

将工作流中整理好的伏笔条目同步到 ForeshadowItem 表。
"""

from __future__ import annotations

from typing import AsyncIterator, List, Literal

from pydantic import BaseModel, Field

from app.services.foreshadow_service import ForeshadowService
from app.services.workflow.nodes.base import BaseNode
from app.services.workflow.registry import register_node


class ForeshadowSyncItem(BaseModel):
    title: str = Field(..., description="伏笔标题")
    foreshadow_id: str | None = Field(None, description="伏笔稳定编号")
    display_title: str | None = Field(None, description="伏笔展示标题")
    type: Literal["item", "goal", "person", "other"] = Field("other", description="伏笔类型")
    note: str | None = Field(None, description="伏笔备注")
    chapter_id: int | None = Field(None, description="关联章节ID")
    status: Literal["open", "resolved"] = Field("open", description="伏笔状态")
    due_chapter_number: int | None = Field(None, description="最晚回收章节")
    first_chapter_number: int | None = Field(None, description="首次登记章节")
    last_chapter_number: int | None = Field(None, description="最后出现章节")


class ForeshadowSyncInput(BaseModel):
    project_id: int = Field(..., description="项目ID")
    items: List[ForeshadowSyncItem] = Field(default_factory=list, description="伏笔条目列表")


class ForeshadowSyncOutput(BaseModel):
    count: int = Field(..., description="写入条目数量")
    ids: List[int] = Field(default_factory=list, description="写入后的伏笔ID列表")


@register_node
class ForeshadowSyncNode(BaseNode[ForeshadowSyncInput, ForeshadowSyncOutput]):
    node_type = "Data.ForeshadowSync"
    category = "data"
    label = "同步伏笔条目"
    description = "将伏笔条目写入 ForeshadowItem 登记表"

    input_model = ForeshadowSyncInput
    output_model = ForeshadowSyncOutput

    async def execute(self, inputs: ForeshadowSyncInput) -> AsyncIterator[ForeshadowSyncOutput]:
        svc = ForeshadowService(self.context.session)
        saved = svc.register(inputs.project_id, [item.model_dump() for item in inputs.items])

        yield ForeshadowSyncOutput(
            count=len(saved),
            ids=[item.id for item in saved if item.id is not None],
        )
