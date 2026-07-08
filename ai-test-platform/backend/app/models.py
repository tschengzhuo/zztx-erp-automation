# AI Test Platform - Database Models
# 需求、用例、测试点、追溯链、实体注册表

import enum
import uuid
from datetime import datetime
from typing import Optional, List

from sqlalchemy import (
    String, Text, Integer, Float, Boolean, DateTime,
    ForeignKey, UniqueConstraint, Index, JSON, func
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.config import settings

# 跨数据库兼容：PostgreSQL 用 JSONB/UUID 原生类型，SQLite 用 JSON/String
if settings.is_sqlite:
    # SQLite 模式：UUID 存为 String(36)，JSON 用 core JSON
    def _uuid_column(**kw):
        return String(36, **kw)
    _json_type = JSON
else:
    try:
        from sqlalchemy.dialects.postgresql import UUID as PG_UUID, JSONB
        def _uuid_column(**kw):
            return PG_UUID(as_uuid=False, **kw)
        _json_type = JSONB
    except ImportError:
        def _uuid_column(**kw):
            return String(36, **kw)
        _json_type = JSON

from app.database import Base


# ==================== 枚举 ====================

class RequirementStatus(str, enum.Enum):
    """需求状态"""
    DRAFT = "draft"
    PARSED = "parsed"           # Stage 1 完成
    TEST_POINTS_GENERATED = "test_points_generated"  # Stage 2 完成
    CASES_GENERATED = "cases_generated"              # Stage 3 完成
    REVIEWED = "reviewed"       # QA 审核通过
    ARCHIVED = "archived"


class Priority(str, enum.Enum):
    """用例/测试点优先级"""
    P0 = "P0"  # 冒烟
    P1 = "P1"  # 核心
    P2 = "P2"  # 一般
    P3 = "P3"  # 边缘


class CaseType(str, enum.Enum):
    """用例类型"""
    UI = "UI"         # UI 自动化用例
    API = "API"       # 接口用例
    BOTH = "BOTH"     # 双形态


class EntityType(str, enum.Enum):
    """实体注册表类型"""
    PAGE = "page"
    API = "api"
    ROLE = "role"
    BUSINESS_TERM = "business_term"


class SyncAction(str, enum.Enum):
    """同步动作"""
    CREATE = "create"
    UPDATE = "update"
    DELETE = "delete"
    CONFLICT = "conflict"


# ==================== 需求相关表 ====================

class Requirement(Base):
    """需求实体 - Stage 1 产物"""
    __tablename__ = "requirements"

    id: Mapped[str] = mapped_column(_uuid_column(), primary_key=True, default=lambda: str(uuid.uuid4()))
    version: Mapped[int] = mapped_column(Integer, default=1)
    parent_version_id: Mapped[Optional[str]] = mapped_column(_uuid_column(), ForeignKey("requirements.id"), nullable=True)

    # 核心字段
    title: Mapped[str] = mapped_column(String(500), nullable=False, index=True)
    module: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    source: Mapped[str] = mapped_column(String(50), default="manual")  # manual | jira | feishu | confluence

    # 结构化实体 (Stage 1 LLM 解析)
    description: Mapped[Optional[str]] = mapped_column(Text)
    functional_points: Mapped[Optional[dict]] = mapped_column(_json_type, default=list)
    participants: Mapped[Optional[dict]] = mapped_column(_json_type, default=list)
    trigger_conditions: Mapped[Optional[dict]] = mapped_column(_json_type, default=list)
    expected_outcomes: Mapped[Optional[dict]] = mapped_column(_json_type, default=list)
    constraints: Mapped[Optional[dict]] = mapped_column(_json_type, default=list)
    data_scope: Mapped[Optional[dict]] = mapped_column(_json_type, default=list)

    # 需求指纹 (横切机制A)
    feature_id: Mapped[Optional[str]] = mapped_column(String(300), index=True)
    extracted_entities: Mapped[Optional[dict]] = mapped_column(_json_type)  # {pages, apis, roles, business_terms}
    summary_text: Mapped[Optional[str]] = mapped_column(Text)  # 结构化摘要，供向量化

    # 向量 embedding
    embedding: Mapped[Optional[list]] = mapped_column(_json_type)  # 摘要的向量表示

    # 显式关联 (L1)
    related_req_ids: Mapped[Optional[list]] = mapped_column(_json_type, default=list)

    # 原始文本
    raw_text: Mapped[Optional[str]] = mapped_column(Text)

    # 状态
    status: Mapped[str] = mapped_column(String(30), default=RequirementStatus.DRAFT)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    # 审计
    created_by: Mapped[Optional[str]] = mapped_column(String(100))
    reviewed_by: Mapped[Optional[str]] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), onupdate=func.now())

    # 关系
    test_points: Mapped[List["TestPoint"]] = relationship(back_populates="requirement", cascade="all, delete-orphan")
    test_cases: Mapped[List["TestCase"]] = relationship(back_populates="requirement", cascade="all, delete-orphan")

    __table_args__ = (
        Index("idx_req_module_status", "module", "status"),
        Index("idx_req_feature_id", "feature_id"),
        Index("idx_req_active", "is_active"),
    )

    def __repr__(self):
        return f"<Requirement {self.title} v{self.version}>"


class RequirementVersion(Base):
    """需求版本快照 - 支持迭代回滚"""
    __tablename__ = "requirement_versions"

    id: Mapped[str] = mapped_column(_uuid_column(), primary_key=True, default=lambda: str(uuid.uuid4()))
    requirement_id: Mapped[str] = mapped_column(_uuid_column(), ForeignKey("requirements.id"), nullable=False, index=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    snapshot: Mapped[dict] = mapped_column(_json_type, nullable=False)  # 完整快照
    change_summary: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())

    __table_args__ = (
        UniqueConstraint("requirement_id", "version", name="uq_req_version"),
    )


# ==================== 测试点相关表 ====================

class TestPoint(Base):
    """测试点 - Stage 2 产物"""
    __tablename__ = "test_points"

    id: Mapped[str] = mapped_column(_uuid_column(), primary_key=True, default=lambda: str(uuid.uuid4()))
    requirement_id: Mapped[str] = mapped_column(_uuid_column(), ForeignKey("requirements.id"), nullable=False, index=True)

    # 核心字段
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    feature_id: Mapped[Optional[str]] = mapped_column(String(300), index=True)
    dimension: Mapped[str] = mapped_column(String(50), nullable=False)  # 功能正常/边界值/异常输入/权限/并发/兼容/数据完整性
    scenario_desc: Mapped[str] = mapped_column(Text, nullable=False)
    technique: Mapped[str] = mapped_column(String(100))  # 等价类划分/边界值分析/决策表/状态迁移
    priority: Mapped[str] = mapped_column(String(10), default=Priority.P1)

    # 状态
    is_confirmed: Mapped[bool] = mapped_column(Boolean, default=False)  # QA 确认

    # 审计
    created_by: Mapped[str] = mapped_column(String(50), default="AI")
    reviewed_by: Mapped[Optional[str]] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), onupdate=func.now())

    # 关系
    requirement: Mapped["Requirement"] = relationship(back_populates="test_points")
    test_cases: Mapped[List["TestCase"]] = relationship(back_populates="test_point", cascade="all, delete-orphan")

    __table_args__ = (
        Index("idx_tp_req_dimension", "requirement_id", "dimension"),
    )

    def __repr__(self):
        return f"<TestPoint {self.title} [{self.dimension}]>"


# ==================== 用例相关表 ====================

class TestCase(Base):
    """结构化用例 - Stage 3 产物"""
    __tablename__ = "test_cases"

    id: Mapped[str] = mapped_column(_uuid_column(), primary_key=True, default=lambda: str(uuid.uuid4()))
    case_id: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)  # TC-2026-XXXX
    requirement_id: Mapped[str] = mapped_column(_uuid_column(), ForeignKey("requirements.id"), nullable=False, index=True)
    test_point_id: Mapped[Optional[str]] = mapped_column(_uuid_column(), ForeignKey("test_points.id"), index=True)

    # 核心字段
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    precondition: Mapped[Optional[str]] = mapped_column(Text)
    steps: Mapped[List[dict]] = mapped_column(_json_type, nullable=False, default=list)
    expected_result: Mapped[Optional[str]] = mapped_column(Text)
    test_data: Mapped[Optional[dict]] = mapped_column(_json_type)

    # 元信息
    case_type: Mapped[str] = mapped_column(String(10), default=CaseType.UI)
    priority: Mapped[str] = mapped_column(String(10), default=Priority.P1)
    tags: Mapped[Optional[list]] = mapped_column(_json_type, default=list)

    # 步骤级标记 (供迭代同步 Merge 使用)
    # steps 数组中每个步骤带: {"locked": false, "last_modified_by": "AI"}
    # locked: 人工锁定 = true, AI 可修改 = false
    # last_modified_by: "AI" | "human"

    # 状态
    is_confirmed: Mapped[bool] = mapped_column(Boolean, default=False)  # QA 确认
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    # 同步标记
    sync_status: Mapped[Optional[str]] = mapped_column(String(30))  # synced | conflict | pending_review
    sync_action: Mapped[Optional[str]] = mapped_column(String(30))  # create | update | delete

    # 审计
    created_by: Mapped[str] = mapped_column(String(50), default="AI")
    reviewed_by: Mapped[Optional[str]] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), onupdate=func.now())

    # 关系
    requirement: Mapped["Requirement"] = relationship(back_populates="test_cases")
    test_point: Mapped["TestPoint"] = relationship(back_populates="test_cases")

    __table_args__ = (
        Index("idx_tc_req_type", "requirement_id", "case_type"),
        Index("idx_tc_priority", "priority"),
    )

    def __repr__(self):
        return f"<TestCase {self.case_id} {self.title}>"


class CaseVersion(Base):
    """用例版本 - 支持回归资产版本化"""
    __tablename__ = "case_versions"

    id: Mapped[str] = mapped_column(_uuid_column(), primary_key=True, default=lambda: str(uuid.uuid4()))
    test_case_id: Mapped[str] = mapped_column(_uuid_column(), ForeignKey("test_cases.id"), nullable=False, index=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    steps: Mapped[List[dict]] = mapped_column(_json_type, nullable=False)
    expected_result: Mapped[Optional[str]] = mapped_column(Text)
    change_reason: Mapped[Optional[str]] = mapped_column(Text)  # 需求变更/自愈/人工修改
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())

    __table_args__ = (
        UniqueConstraint("test_case_id", "version", name="uq_case_version"),
    )


class ExecutionResult(Base):
    """用例执行记录 - Stage 4/5 产物"""
    __tablename__ = "execution_results"

    id: Mapped[str] = mapped_column(_uuid_column(), primary_key=True, default=lambda: str(uuid.uuid4()))
    test_case_id: Mapped[str] = mapped_column(_uuid_column(), ForeignKey("test_cases.id"), nullable=False, index=True)

    status: Mapped[str] = mapped_column(String(20), nullable=False)  # passed | failed | error | skipped
    duration_ms: Mapped[Optional[int]] = mapped_column(Integer)
    error_type: Mapped[Optional[str]] = mapped_column(String(50))  # product_bug | case_bug | env_issue | data_issue | flaky
    error_message: Mapped[Optional[str]] = mapped_column(Text)
    analysis: Mapped[Optional[str]] = mapped_column(Text)  # LLM 分析结果
    evidence: Mapped[Optional[dict]] = mapped_column(_json_type)  # 截图/DOM/HAR 路径
    executed_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())

    __table_args__ = (
        Index("idx_ex_result_time", "executed_at"),
    )


# ==================== 追溯链与关联 ====================

class TraceabilityLink(Base):
    """追溯链：需求→功能点→测试点→用例→步骤的有向图"""
    __tablename__ = "traceability_links"

    id: Mapped[str] = mapped_column(_uuid_column(), primary_key=True, default=lambda: str(uuid.uuid4()))

    source_type: Mapped[str] = mapped_column(String(30), nullable=False)  # requirement | feature_point | test_point | test_case
    source_id: Mapped[str] = mapped_column(String(100), nullable=False)
    target_type: Mapped[str] = mapped_column(String(30), nullable=False)
    target_id: Mapped[str] = mapped_column(String(100), nullable=False)

    relation: Mapped[str] = mapped_column(String(30), default="derives_from")  # derives_from | influences | relates_to
    confidence: Mapped[float] = mapped_column(Float, default=1.0)
    created_by: Mapped[str] = mapped_column(String(50), default="system")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())

    __table_args__ = (
        Index("idx_trace_src", "source_type", "source_id"),
        Index("idx_trace_tgt", "target_type", "target_id"),
        UniqueConstraint("source_type", "source_id", "target_type", "target_id", name="uq_trace_link"),
    )


# ==================== 实体注册表 ====================

class EntityRegistry(Base):
    """全局实体注册表：页面、接口、角色、业务术语"""
    __tablename__ = "entity_registry"

    id: Mapped[str] = mapped_column(_uuid_column(), primary_key=True, default=lambda: str(uuid.uuid4()))
    entity_type: Mapped[str] = mapped_column(String(20), nullable=False, index=True)  # page | api | role | business_term
    module: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    unified_id: Mapped[str] = mapped_column(String(300), unique=True, nullable=False)  # 统一ID
    aliases: Mapped[Optional[list]] = mapped_column(_json_type, default=list)  # 别名列表
    description: Mapped[Optional[str]] = mapped_column(Text)
    metadata_: Mapped[Optional[dict]] = mapped_column("metadata", _json_type)  # API: {method, path, params}

    is_confirmed: Mapped[bool] = mapped_column(Boolean, default=False)  # QA 确认
    created_by: Mapped[str] = mapped_column(String(50), default="AI")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())

    __table_args__ = (
        Index("idx_entity_type_module", "entity_type", "module"),
    )

    def __repr__(self):
        return f"<Entity {self.entity_type}:{self.name}>"


# ==================== 同步与变更 ====================

class SyncRecord(Base):
    """需求迭代同步记录"""
    __tablename__ = "sync_records"

    id: Mapped[str] = mapped_column(_uuid_column(), primary_key=True, default=lambda: str(uuid.uuid4()))

    requirement_id: Mapped[str] = mapped_column(_uuid_column(), ForeignKey("requirements.id"), nullable=False, index=True)
    old_version: Mapped[int] = mapped_column(Integer, nullable=False)
    new_version: Mapped[int] = mapped_column(Integer, nullable=False)

    change_type: Mapped[str] = mapped_column(String(30), nullable=False)  # feature_added | feature_modified | feature_removed
    affected_feature_id: Mapped[Optional[str]] = mapped_column(String(300))
    affected_case_count: Mapped[int] = mapped_column(Integer, default=0)

    diff_summary: Mapped[Optional[dict]] = mapped_column(_json_type)
    action: Mapped[str] = mapped_column(String(30), default="pending")  # pending | synced | reviewed | conflicted

    confirmed_by: Mapped[Optional[str]] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())


# ==================== 模块分类树 ====================

class ModuleCategory(Base):
    """模块分类树 - 支持多层级分类管理需求"""
    __tablename__ = "module_categories"

    id: Mapped[str] = mapped_column(_uuid_column(), primary_key=True, default=lambda: str(uuid.uuid4()))
    name: Mapped[str] = mapped_column(String(200), nullable=False, comment="分类名称")
    parent_id: Mapped[Optional[str]] = mapped_column(
        _uuid_column(), ForeignKey("module_categories.id", ondelete="CASCADE"),
        nullable=True, index=True, comment="父分类ID"
    )
    sort_order: Mapped[int] = mapped_column(Integer, default=0, comment="排序序号")
    description: Mapped[Optional[str]] = mapped_column(Text, comment="分类描述")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), onupdate=func.now())

    # 自引用关系
    parent: Mapped[Optional["ModuleCategory"]] = relationship(
        "ModuleCategory", remote_side=[id], back_populates="children"
    )
    children: Mapped[List["ModuleCategory"]] = relationship(
        "ModuleCategory", back_populates="parent", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("idx_mc_parent_id", "parent_id"),
        Index("idx_mc_active", "is_active"),
    )

    def __repr__(self):
        return f"<ModuleCategory {self.name}>"


# ==================== 用户认证 ====================

class User(Base):
    """平台用户"""
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(_uuid_column(), primary_key=True, default=lambda: str(uuid.uuid4()))
    username: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    display_name: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    password_hash: Mapped[str] = mapped_column(String(256), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), onupdate=func.now())

    def __repr__(self):
        return f"<User {self.username}>"
