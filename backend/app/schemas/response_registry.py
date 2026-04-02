from __future__ import annotations

from typing import Dict, Any

# 统一集中导出所有需要在 OpenAPI 中暴露的响应/嵌套模型
from app.schemas.wizard import (
    Text,
	WorldBuilding, Blueprint,
	VolumeOutline, EnhancedVolumeOutline, ChapterOutline, EnhancedChapterOutline,
	SpecialAbilityResponse, OneSentence, ParagraphOverview,
	CharacterCard, SceneCard, StoryLine, StageLine,
	Tags, WorldviewTemplate, Chapter,
    WritingGuide,
    OrganizationsExtract,
    Step4CharacterExtractBlueprint,
    Step4CharacterExtractResult,
    ChapterCharacterDiscoveryResult,
    ChapterCharacterPlanningResult,
    EnhancedStageLine,
    EnhancedChapterBlueprint,
)
from app.schemas.entity import OrganizationCard, UpdateCharacterState, CharacterStateSummaryResult
from app.schemas.workflow_models import BookStageChunkPlan, BookStageFinalPlan


RESPONSE_MODEL_MAP: Dict[str, Any] = {
    "Text": Text,
	'Tags': Tags,
	'SpecialAbilityResponse': SpecialAbilityResponse,
	'OneSentence': OneSentence,
	'ParagraphOverview': ParagraphOverview,
	'WorldBuilding': WorldBuilding,
	'WorldviewTemplate': WorldviewTemplate,
	'Blueprint': Blueprint,
	'Step4CharacterExtractBlueprint': Step4CharacterExtractBlueprint,
	'Step4CharacterExtractResult': Step4CharacterExtractResult,
	'ChapterCharacterDiscoveryResult': ChapterCharacterDiscoveryResult,
	'ChapterCharacterPlanningResult': ChapterCharacterPlanningResult,
	# 使用未包装模型
	'EnhancedVolumeOutline': EnhancedVolumeOutline,
	'EnhancedStageLine': EnhancedStageLine,
	'EnhancedChapterBlueprint': EnhancedChapterBlueprint,
	'EnhancedChapterOutline': EnhancedChapterOutline,
	'VolumeOutline': VolumeOutline,
 	'WritingGuide': WritingGuide,
	'OrganizationsExtract': OrganizationsExtract,
	'ChapterOutline': ChapterOutline,
	'Chapter': Chapter,
	# 基础schema，自动包含在OpenAPI中
	'CharacterCard': CharacterCard,
	'SceneCard': SceneCard,
	'OrganizationCard': OrganizationCard,
	'UpdateCharacterState': UpdateCharacterState,
	'CharacterStateSummaryResult': CharacterStateSummaryResult,
	# 显式导出嵌套类型，便于前端字段树解析
	'StageLine': StageLine,
	'StoryLine': StoryLine,
	# 工作流专用结构模型
	'BookStageChunkPlan': BookStageChunkPlan,
	'BookStageFinalPlan': BookStageFinalPlan,
} 
