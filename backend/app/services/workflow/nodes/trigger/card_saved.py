"""卡片保存触发器节点"""
from typing import Optional
from pydantic import BaseModel, Field

from ..base import BaseNode
from ...registry import register_node


class TriggerCardSavedInput(BaseModel):
    """卡片保存触发器输入"""
    card_type: Optional[str] = Field(
        None,
        description="卡片类型名称（可选）。只触发指定类型的卡片保存，如 '核心蓝图'。留空则匹配所有类型"
    )
    on_create: bool = Field(
        False,
        description="是否在卡片创建时触发"
    )
    on_update: bool = Field(
        True,
        description="是否在卡片更新时触发"
    )
    step: Optional[int] = Field(
        None,
        description="步骤号过滤。适用于内容中带 step 字段的卡片，如小说架构步骤。留空则不按步骤过滤"
    )
    title: Optional[str] = Field(
        None,
        description="卡片标题过滤。留空则不按标题过滤"
    )
    prompt_name: Optional[str] = Field(
        None,
        description="content.prompt_name 过滤。留空则不按提示词名过滤"
    )
    step_name: Optional[str] = Field(
        None,
        description="content.step_name 过滤。留空则不按步骤名过滤"
    )


class TriggerCardSavedOutput(BaseModel):
    """卡片保存触发器输出"""
    card_id: int = Field(..., description="卡片ID")
    project_id: int = Field(..., description="项目ID")
    card_type: Optional[str] = Field(None, description="卡片类型名称")
    is_created: bool = Field(..., description="是否是新创建的卡片（true=创建，false=更新）")
    step: Optional[int] = Field(None, description="步骤号（若事件卡片内容中存在 step 字段）")
    title: Optional[str] = Field(None, description="卡片标题")
    prompt_name: Optional[str] = Field(None, description="content.prompt_name")
    step_name: Optional[str] = Field(None, description="content.step_name")


@register_node
class TriggerCardSavedNode(BaseNode):
    """卡片保存触发器
    
    当卡片保存时触发工作流（包括创建和更新）。
    
    输出字段：
        - card_id: 卡片ID
        - project_id: 项目ID
        - card_type: 卡片类型名称
        - is_created: 是否是新创建的卡片
    
    过滤条件：
        - card_type: 只触发指定类型的卡片（可选）
        - on_create: 是否在创建时触发（默认 false）
        - on_update: 是否在更新时触发（默认 true）
    
    示例:
        # 监听所有卡片保存
        trigger = Trigger.CardSaved()
        
        # 只监听核心蓝图卡片的更新
        trigger = Trigger.CardSaved(
            card_type="核心蓝图",
            on_create=false,
            on_update=true
        )
        
        # 使用触发器输出
        card = Card.Get(card_id=trigger.card_id)
        
        # 提取关系
        relations = AI.ExtractRelations(
            card_id=trigger.card_id,
            project_id=trigger.project_id
        )
    """
    
    node_type = "Trigger.CardSaved"
    category = "trigger"
    label = "卡片保存触发器"
    description = "当卡片保存时触发"
    
    input_model = TriggerCardSavedInput
    output_model = TriggerCardSavedOutput
    
    async def execute(self, inputs: TriggerCardSavedInput):
        """从上下文中读取触发器数据并输出
        
        触发器数据在工作流启动时通过 initial_context["__trigger_data__"] 注入，
        可以通过 self.context.variables 访问。
        """
        # 从上下文的 variables 中获取触发器数据
        trigger_data = self.context.variables.get("__trigger_data__", {})

        card_type = trigger_data.get("card_type")
        if card_type is None:
            card_type = inputs.card_type
        
        yield TriggerCardSavedOutput(
            card_id=trigger_data.get("card_id"),
            project_id=trigger_data.get("project_id"),
            card_type=card_type,
            is_created=trigger_data.get("is_created", False),
            step=trigger_data.get("step", inputs.step),
            title=trigger_data.get("title", inputs.title),
            prompt_name=trigger_data.get("prompt_name", inputs.prompt_name),
            step_name=trigger_data.get("step_name", inputs.step_name),
        )
