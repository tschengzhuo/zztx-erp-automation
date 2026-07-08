# AI Test Platform - LLM Abstraction Layer
# Provider 可切换: OpenAI / Claude / 通义千问
# 统一接口 + JSON Schema 约束输出

import json
import logging
from abc import ABC, abstractmethod
from typing import Optional, Dict, Any, Type

from openai import AsyncOpenAI
try:
    from anthropic import AsyncAnthropic
except ImportError:
    AsyncAnthropic = None  # type: ignore

from app.config import settings

logger = logging.getLogger(__name__)


# ==================== LLM Provider 抽象 ====================

class LLMProvider(ABC):
    """LLM Provider 抽象基类"""

    provider_name: str

    @abstractmethod
    async def chat(
        self,
        messages: list[dict],
        temperature: float = 0.3,
        max_tokens: int = 4096,
        response_format: Optional[dict] = None,
    ) -> str:
        """发送对话请求，返回文本响应"""
        pass

    @abstractmethod
    async def chat_structured(
        self,
        messages: list[dict],
        schema: Optional[dict] = None,
        temperature: float = 0.3,
        max_tokens: int = 4096,
        model: Optional[str] = None,
    ) -> dict:
        """发送对话请求，返回结构化 JSON（带 schema 约束）"""
        pass

    async def embed(self, text: str) -> list[float]:
        """文本向量化（子类可选覆盖）"""
        raise NotImplementedError(f"{self.provider_name} does not support embedding")


class OpenAIProvider(LLMProvider):
    """OpenAI Provider (GPT-4o / GPT-4o-mini)"""

    provider_name = "openai"

    def __init__(self):
        self.client = AsyncOpenAI(
            api_key=settings.OPENAI_API_KEY,
            base_url=settings.OPENAI_BASE_URL,
            timeout=settings.LLM_REQUEST_TIMEOUT,
        )

    async def chat(
        self,
        messages: list[dict],
        temperature: float = 0.3,
        max_tokens: int = 4096,
        response_format: Optional[dict] = None,
    ) -> str:
        response = await self.client.chat.completions.create(
            model=settings.OPENAI_MODEL_STRONG,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        return response.choices[0].message.content or ""

    async def chat_structured(
        self,
        messages: list[dict],
        schema: Optional[dict] = None,
        temperature: float = 0.3,
        max_tokens: int = 4096,
        model: Optional[str] = None,
    ) -> dict:
        # OpenAI 原生支持 JSON mode / structured output
        kwargs = {
            "model": model or settings.OPENAI_MODEL_STRONG,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if schema:
            kwargs["response_format"] = {"type": "json_schema", "json_schema": {
                "name": "response",
                "schema": schema,
                "strict": True,
            }}
        else:
            kwargs["response_format"] = {"type": "json_object"}

        response = await self.client.chat.completions.create(**kwargs)
        content = response.choices[0].message.content or "{}"
        return json.loads(content)

    async def embed(self, text: str) -> list[float]:
        response = await self.client.embeddings.create(
            model=settings.OPENAI_EMBEDDING_MODEL,
            input=text,
        )
        return response.data[0].embedding


class AnthropicProvider(LLMProvider):
    """Anthropic Claude Provider"""

    provider_name = "anthropic"

    def __init__(self):
        self.client = AsyncAnthropic(
            api_key=settings.ANTHROPIC_API_KEY,
            timeout=settings.LLM_REQUEST_TIMEOUT,
        )

    async def chat(
        self,
        messages: list[dict],
        temperature: float = 0.3,
        max_tokens: int = 4096,
        response_format: Optional[dict] = None,
    ) -> str:
        # Anthropic 格式转换: 提取 system 消息
        system_msg = ""
        user_msgs = []
        for m in messages:
            if m["role"] == "system":
                system_msg = m["content"]
            else:
                user_msgs.append(m)

        response = await self.client.messages.create(
            model=settings.ANTHROPIC_MODEL_STRONG,
            system=system_msg if system_msg else None,
            messages=user_msgs,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        return response.content[0].text

    async def chat_structured(
        self,
        messages: list[dict],
        schema: Optional[dict] = None,
        temperature: float = 0.3,
        max_tokens: int = 4096,
        model: Optional[str] = None,
    ) -> dict:
        # Claude 通过 prompt 约束 JSON 格式
        if schema:
            schema_text = json.dumps(schema, ensure_ascii=False, indent=2)
            constraint = f"\n\n请严格按照以下 JSON Schema 输出，只输出 JSON，不要包含其他文字：\n```json\n{schema_text}\n```"
            for m in reversed(messages):
                if m["role"] == "user":
                    m["content"] += constraint
                    break

        text = await self.chat(messages, temperature, max_tokens)
        # 提取 JSON
        text = text.strip()
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0].strip()
        elif "```" in text:
            text = text.split("```")[1].split("```")[0].strip()
        return json.loads(text)


class QwenProvider(LLMProvider):
    """通义千问 Provider - 使用 OpenAI 兼容模式"""

    provider_name = "qwen"

    def __init__(self):
        self.client = AsyncOpenAI(
            api_key=settings.QWEN_API_KEY,
            base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
            timeout=settings.LLM_REQUEST_TIMEOUT,
        )

    async def chat(
        self,
        messages: list[dict],
        temperature: float = 0.3,
        max_tokens: int = 4096,
        response_format: Optional[dict] = None,
    ) -> str:
        response = await self.client.chat.completions.create(
            model=settings.QWEN_MODEL_STRONG,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        return response.choices[0].message.content or ""

    async def chat_structured(
        self,
        messages: list[dict],
        schema: Optional[dict] = None,
        temperature: float = 0.3,
        max_tokens: int = 4096,
        model: Optional[str] = None,
    ) -> dict:
        # 千问兼容模式需要 prompt 中包含 "json" 字样才能用 json_object
        # 在最后一次 user 消息末尾追加约束
        json_hint = "\n\n请严格按照以下JSON Schema输出，只输出有效JSON对象：\n" + json.dumps(schema or {}, ensure_ascii=False)
        for m in reversed(messages):
            if m["role"] == "user":
                m["content"] += json_hint
                break

        kwargs: dict[str, Any] = {
            "model": model or settings.QWEN_MODEL_STRONG,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            # 不用 response_format json_object，Qwen 处理复杂 schema 极慢
            # 通过 prompt 中的 schema 提示来约束格式即可
        }

        logger.info(f"[Qwen] chat_structured 请求: model={kwargs['model']}, max_tokens={max_tokens}")

        response = await self.client.chat.completions.create(**kwargs)
        content = response.choices[0].message.content or "{}"

        # 提取 JSON（兼容 markdown 包裹的情况）
        content = content.strip()
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0].strip()
        elif "```" in content:
            content = content.split("```")[1].split("```")[0].strip()

        try:
            return json.loads(content)
        except json.JSONDecodeError as e:
            logger.warning(f"[Qwen] JSON 解析失败 (尝试修复): {e}")

            # 尝试提取最外层 {...}
            brace_start = content.find("{")
            brace_end = content.rfind("}")
            if brace_start != -1 and brace_end > brace_start:
                try:
                    return json.loads(content[brace_start:brace_end + 1])
                except json.JSONDecodeError:
                    pass

            # 尝试修复截断的 JSON：补齐未闭合的字符串和结构
            repaired = _repair_truncated_json(content)
            if repaired:
                try:
                    result = json.loads(repaired)
                    salvaged = len(result.get("cases", [])) if isinstance(result, dict) else "N/A"
                    logger.warning(f"[Qwen] JSON 截断修复成功，抢救了 {salvaged} 条数据")
                    return result
                except json.JSONDecodeError as e2:
                    logger.error(f"[Qwen] JSON 修复失败: {e2}")

            raise Exception(f"Qwen 结构化输出解析失败: {content[:200]}")


# ==================== 截断 JSON 修复 ====================

def _repair_truncated_json(text: str) -> Optional[str]:
    """尝试修复被 max_tokens 截断的不完整 JSON。
    策略：找到最后一个完整的 cases 数组元素，关闭未闭合的结构。
    """
    text = text.strip()
    if not text.startswith("{"):
        return None

    # 1. 找到 "cases" 数组的起始位置
    cases_key = '"cases"'
    cases_idx = text.find(cases_key)
    if cases_idx == -1:
        return None

    # 2. 找到 cases 数组内容结束的位置：最后一个完整的 } 后面跟 , 或 ] 的位置
    # 从后往前扫描，找到一个完整的 JSON 对象结束符
    # 简化策略：截断 200 字符后尝试用括号补齐
    balance = 0
    in_string = False
    escape_next = False
    last_complete_pos = 0

    for i, ch in enumerate(text):
        if escape_next:
            escape_next = False
            continue
        if ch == '\\':
            escape_next = True
            continue
        if ch == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if ch in '{[':
            balance += 1
        elif ch in '}]':
            balance -= 1
            if balance == 0:
                last_complete_pos = i + 1

    # 3. 如果 last_complete_pos 有意义（至少解析到 cases: [ 之后）
    if last_complete_pos > cases_idx + len(cases_key) + 3:
        # 截取到最后一个完整结构的结束位置
        truncated = text[:last_complete_pos]
        # 闭合剩余结构
        if truncated.strip().endswith("}"):
            truncated += "]}"  # 闭合 cases 数组和外层对象
        elif truncated.strip().endswith("]"):
            truncated += "}"   # 闭合外层对象
        else:
            truncated += "}]}"
        return truncated

    # 4. 降级方案：逐个查找 cases 数组中完整的 case 对象
    # 找到 "test_point_title" 作为每个 case 的标记
    # 收集所有能完整闭合的 case
    result_parts = []
    search_from = cases_idx + len(cases_key) + 2  # 跳过 "cases": [
    bracket_start = text.find("[", search_from - 2)
    if bracket_start == -1:
        return None

    # 在 cases 数组范围内找完整的 JSON 对象
    pos = bracket_start + 1
    depth = 0
    in_str = False
    esc = False
    obj_start = -1
    complete_objects = []

    for i in range(pos, len(text)):
        ch = text[i]
        if esc:
            esc = False
            continue
        if ch == '\\':
            esc = True
            continue
        if ch == '"':
            in_str = not in_str
            continue
        if in_str:
            continue
        if ch == '{':
            if depth == 0:
                obj_start = i
            depth += 1
        elif ch == '}':
            depth -= 1
            if depth == 0 and obj_start >= 0:
                # 找到一个完整的对象
                complete_objects.append(text[obj_start:i + 1])
                obj_start = -1

    if complete_objects:
        repaired = '{"cases": [' + ",".join(complete_objects) + "]}"
        logger.info(f"[Qwen] 从截断 JSON 中恢复了 {len(complete_objects)} 个完整的 case 对象")
        return repaired

    return None


# ==================== Provider 工厂 ====================

PROVIDER_MAP = {
    "openai": OpenAIProvider,
    "anthropic": AnthropicProvider,
    "qwen": QwenProvider,
}


def get_llm_provider(provider_name: Optional[str] = None) -> LLMProvider:
    """获取 LLM Provider 实例"""
    name = provider_name or settings.LLM_PROVIDER
    provider_cls = PROVIDER_MAP.get(name)
    if not provider_cls:
        raise ValueError(f"Unknown LLM provider: {name}. Available: {list(PROVIDER_MAP.keys())}")
    return provider_cls()


# ==================== 结构化输出辅助 ====================

# JSON Schema 定义 - 用于 LLM 结构化输出约束

REQUIREMENT_ENTITY_SCHEMA = {
    "type": "object",
    "properties": {
        "title": {"type": "string", "description": "需求标题"},
        "module": {"type": "string", "description": "所属业务模块"},
        "feature_id": {"type": "string", "description": "功能点唯一标识，格式: 业务域.功能名。如 order.cart.coupon_stack_rule"},
        "description": {"type": "string", "description": "需求一句话描述"},

        "functional_points": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "feature_id": {"type": "string"},
                    "name": {"type": "string"},
                    "description": {"type": "string"},
                    "trigger": {"type": "string"},
                    "expected": {"type": "string"},
                    "constraints": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["feature_id", "name", "description"],
            }
        },

        "participants": {
            "type": "array",
            "items": {"type": "object", "properties": {
                "role": {"type": "string"},
                "type": {"type": "string", "enum": ["user", "system", "admin", "external"]},
            }}
        },

        "trigger_conditions": {
            "type": "array",
            "items": {"type": "object", "properties": {
                "condition": {"type": "string"},
                "type": {"type": "string", "enum": ["user_action", "system_event", "schedule", "api_call"]},
            }}
        },

        "expected_outcomes": {
            "type": "array",
            "items": {"type": "object", "properties": {
                "outcome": {"type": "string"},
                "type": {"type": "string", "enum": ["success", "error", "edge_case"]},
            }}
        },

        "constraints": {
            "type": "array",
            "items": {"type": "object", "properties": {
                "constraint": {"type": "string"},
                "type": {"type": "string", "enum": ["business_rule", "technical", "legal", "performance"]},
            }}
        },

        "data_scope": {
            "type": "object",
            "properties": {
                "affects_tables": {"type": "array", "items": {"type": "string"}},
                "required_data": {"type": "array", "items": {"type": "string"}},
                "data_boundary": {"type": "string"},
            }
        },

        "extracted_entities": {
            "type": "object",
            "properties": {
                "pages": {"type": "array", "items": {"type": "string"}, "description": "涉及的页面"},
                "apis": {"type": "array", "items": {"type": "string"}, "description": "涉及的接口"},
                "roles": {"type": "array", "items": {"type": "string"}, "description": "涉及的角色"},
                "business_terms": {"type": "array", "items": {"type": "string"}, "description": "业务术语"},
            }
        },

        "summary_text": {"type": "string", "description": "结构化摘要，用于向量检索，包含核心业务逻辑和关键实体"},
    },
    "required": ["title", "feature_id", "description", "functional_points", "summary_text", "extracted_entities"],
}


TEST_POINTS_SCHEMA = {
    "type": "object",
    "properties": {
        "test_points": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "title": {"type": "string", "maxLength": 30, "description": "测试点标题，具体到输入数据和预期"},
                    "feature_id": {"type": "string", "description": "所属功能点ID"},
                    "dimension": {"type": "string", "enum": [
                        "功能正常", "边界值", "异常输入", "权限控制",
                        "并发场景", "兼容性", "数据完整性"
                    ]},
                    "scenario_desc": {"type": "string", "description": "具体场景描述，含输入数据和预期行为"},
                    "technique": {"type": "string", "enum": [
                        "等价类划分", "边界值分析", "决策表",
                        "状态迁移", "场景法", "错误推测"
                    ]},
                    "priority": {"type": "string", "enum": ["P0", "P1", "P2", "P3"]},
                    "expected_behavior": {"type": "string", "description": "预期行为"},
                },
                "required": ["title", "dimension", "scenario_desc", "technique", "priority"],
            }
        },
        "coverage_summary": {"type": "string", "description": "覆盖总结"},
    },
    "required": ["test_points"],
}


STRUCTURED_CASE_SCHEMA = {
    "type": "object",
    "properties": {
        "cases": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "test_point_title": {"type": "string", "description": "对应测试点标题"},
                    "ui_case": {
                        "type": "object",
                        "properties": {
                            "title": {"type": "string"},
                            "precondition": {"type": "string"},
                            "steps": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "action": {"type": "string", "enum": ["导航", "输入", "点击", "断言", "等待", "选择", "悬停", "滚动"]},
                                        "target": {"type": "string", "description": "业务操作描述：谁+在什么页面/模块+做什么。禁止出现代码字段/技术标识，如 snake_case 页面名(order_summary_page)、CSS选择器、URL、API路径、字段名(batch_no)等，必须使用业务名称(商品汇总页、批次号)。"},
                                        "value": {"type": "string", "description": "输入值/期望值。禁止出现代码字段/技术标识，必须使用业务名称或具体业务数据。"},
                                        "expected": {"type": "string", "description": "步骤级预期结果。重要步骤（assert/fill/click）必须填写，严格依据需求文档原文。非关键步骤可留空。"},
                                        "locked": {"type": "boolean", "default": False},
                                        "last_modified_by": {"type": "string", "default": "AI"},
                                    },
                                    "required": ["action", "target"],
                                }
                            },
                            "expected_result": {"type": "string"},
                            "test_data": {"type": "object"},
                            "priority": {"type": "string", "enum": ["P0", "P1", "P2", "P3"]},
                            "tags": {"type": "array", "items": {"type": "string"}},
                        },
                        "required": ["title", "steps", "expected_result"],
                    },
                    "api_case": {
                        "type": "object",
                        "properties": {
                            "title": {"type": "string"},
                            "precondition": {"type": "string"},
                            "steps": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "action": {"type": "string", "enum": ["接口请求"]},
                                        "target": {"type": "string", "description": "API路径或业务操作描述。建议写成'业务说明(路径)'的格式，例如'查询商品汇总数据(/api/v1/order_summary)'，避免只出现纯技术路径而无业务说明。"},
                                        "method": {"type": "string", "enum": ["GET", "POST", "PUT", "DELETE", "PATCH"]},
                                        "headers": {"type": "object"},
                                        "body": {"type": "object"},
                                        "expected": {"type": "string", "description": "步骤级预期结果。关键步骤必须填写，严格依据需求文档原文。"},
                                        "expect_status": {"type": "integer"},
                                        "expect_schema": {"type": "object"},
                                        "locked": {"type": "boolean", "default": False},
                                        "last_modified_by": {"type": "string", "default": "AI"},
                                    },
                                    "required": ["action", "target", "method"],
                                }
                            },
                            "expected_result": {"type": "string"},
                            "test_data": {"type": "object"},
                            "priority": {"type": "string", "enum": ["P0", "P1", "P2", "P3"]},
                            "tags": {"type": "array", "items": {"type": "string"}},
                        },
                        "required": ["title", "steps", "expected_result"],
                    },
                },
                "required": ["test_point_title", "ui_case"],
            }
        },
    },
    "required": ["cases"],
}
