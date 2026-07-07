# AI Test Platform - Pydantic Schemas
# API 请求/响应模型

from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field


# ==================== 需求 ====================

class RequirementCreate(BaseModel):
    """上传需求"""
    title: str = Field(..., max_length=500, description="需求标题")
    module: str = Field(..., max_length=200, description="所属模块")
    raw_text: str = Field(..., description="需求文档原文")
    source: str = Field(default="manual", description="来源: manual|jira|feishu|confluence")


class RequirementUpdate(BaseModel):
    """更新需求（迭代）"""
    title: Optional[str] = None
    raw_text: Optional[str] = None


class FunctionalPoint(BaseModel):
    """功能点"""
    feature_id: str
    name: str
    description: str
    trigger: Optional[str] = None
    expected: Optional[str] = None
    constraints: Optional[List[str]] = None


class EntityExtraction(BaseModel):
    """抽取的实体"""
    pages: List[str] = Field(default_factory=list)
    apis: List[str] = Field(default_factory=list)
    roles: List[str] = Field(default_factory=list)
    business_terms: List[str] = Field(default_factory=list)


class RequirementFingerprint(BaseModel):
    """需求指纹"""
    feature_id: str
    summary_text: str
    entities: EntityExtraction


class RequirementResponse(BaseModel):
    """需求响应"""
    id: str
    version: int
    title: str
    module: str
    source: str
    status: str
    feature_id: Optional[str] = None
    functional_points: Optional[Any] = None
    participants: Optional[Any] = None
    trigger_conditions: Optional[Any] = None
    expected_outcomes: Optional[Any] = None
    constraints: Optional[Any] = None
    data_scope: Optional[Any] = None
    summary_text: Optional[str] = None
    extracted_entities: Optional[dict] = None
    created_by: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


# ==================== 测试点 ====================

class TestPointItem(BaseModel):
    """测试点条目"""
    title: str = Field(..., description="测试点标题")
    dimension: str = Field(..., description="覆盖维度")
    scenario_desc: str = Field(..., description="场景描述")
    technique: str = Field(..., description="测试技法")
    priority: str = Field(default="P1")
    feature_id: Optional[str] = None


class TestPointGenerateRequest(BaseModel):
    """生成测试点请求"""
    requirement_id: str
    max_points: int = Field(default=30, ge=10, le=50)


class TestPointResponse(BaseModel):
    """测试点响应"""
    id: str
    requirement_id: str
    title: str
    feature_id: Optional[str] = None
    dimension: str
    scenario_desc: str
    technique: str
    priority: str
    is_confirmed: bool
    created_by: str
    created_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class TestPointConfirmRequest(BaseModel):
    """QA 确认测试点"""
    confirmed_ids: List[str] = Field(..., description="确认的测试点 ID")
    deleted_ids: List[str] = Field(default_factory=list, description="删除的测试点 ID")


# ==================== 用例 ====================

class CaseStep(BaseModel):
    """用例步骤"""
    action: str = Field(..., description="动作类型: navigate|fill|click|assert|wait|api_request")
    target: Optional[str] = Field(None, description="目标选择器/URL")
    value: Optional[str] = Field(None, description="输入值")
    expected: Optional[str] = Field(None, description="步骤级预期")
    locked: bool = Field(default=False, description="人工锁定")
    last_modified_by: str = Field(default="AI", description="最后修改者: AI|human")


class TestCaseCreate(BaseModel):
    """生成用例请求"""
    requirement_id: str
    test_point_ids: List[str] = Field(..., description="关联的测试点 ID")
    generate_both: bool = Field(default=True, description="是否同时生成 UI 和 API 用例")


class TestCaseUpdate(BaseModel):
    """QA 修改用例"""
    title: Optional[str] = None
    precondition: Optional[str] = None
    steps: Optional[List[CaseStep]] = None
    expected_result: Optional[str] = None
    test_data: Optional[dict] = None
    priority: Optional[str] = None
    tags: Optional[List[str]] = None
    case_type: Optional[str] = None


class TestCaseResponse(BaseModel):
    """用例响应"""
    id: str
    case_id: str
    requirement_id: str
    test_point_id: Optional[str] = None
    title: str
    precondition: Optional[str] = None
    steps: List[dict]
    expected_result: Optional[str] = None
    test_data: Optional[dict] = None
    case_type: str
    priority: str
    tags: Optional[List[str]] = None
    is_confirmed: bool
    is_active: bool
    sync_status: Optional[str] = None
    created_by: str
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


# ==================== 实体注册表 ====================

class EntityCreate(BaseModel):
    """创建实体"""
    entity_type: str = Field(..., description="page|api|role|business_term")
    module: str
    name: str
    unified_id: Optional[str] = None
    aliases: List[str] = Field(default_factory=list)
    description: Optional[str] = None
    metadata_: Optional[dict] = Field(default=None, alias="metadata")


class EntityResponse(BaseModel):
    """实体响应"""
    id: str
    entity_type: str
    module: str
    name: str
    unified_id: str
    aliases: Optional[List[str]] = None
    description: Optional[str] = None
    metadata_: Optional[dict] = None
    is_confirmed: bool

    model_config = {"from_attributes": True}


# ==================== 通用 ====================

class PaginationParams(BaseModel):
    """分页参数"""
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)


class PaginatedResponse(BaseModel):
    """分页响应"""
    items: List[Any]
    total: int
    page: int
    page_size: int
    total_pages: int


class APIResponse(BaseModel):
    """统一 API 响应"""
    success: bool = True
    message: str = "ok"
    data: Any = None


class StageResult(BaseModel):
    """阶段执行结果"""
    stage: int
    status: str  # success | failed | pending_review
    message: str
    data: Any = None


# ==================== 需求对比 (横切机制B) ====================

class DiffRequest(BaseModel):
    """需求 diff 请求"""
    old_requirement_id: str
    new_requirement_id: str


class DiffItem(BaseModel):
    """diff 条目"""
    feature_id: str
    change_type: str  # added | modified | removed | unchanged
    old_detail: Optional[dict] = None
    new_detail: Optional[dict] = None
    confidence: float = 1.0
    affected_case_ids: List[str] = Field(default_factory=list)


class DiffResponse(BaseModel):
    """diff 响应"""
    requirement_id: str
    old_version: int
    new_version: int
    changes: List[DiffItem]
    summary: Dict[str, int]  # {added: N, modified: N, removed: N, unchanged: N}


# ==================== 导出 ====================

class ExportRequest(BaseModel):
    """导出请求"""
    requirement_id: str
    format: str = Field(default="xlsx", description="json|xlsx|xmind|markdown")
    include_summary: bool = Field(default=True)
