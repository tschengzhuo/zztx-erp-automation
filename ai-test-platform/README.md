# AI 测试平台 · Phase 1 MVP

> 需求读取 → 测试点生成 → 结构化用例 → 一键导出

基于 [AI测试平台落地方案 v2](C:/Users/49539/WorkBuddy/2026-07-07-16-52-17/AI测试平台落地方案.html) 实现的 Phase 1 MVP。

---

## 架构概览

```
ai-test-platform/
├── backend/                    # FastAPI 后端
│   ├── app/
│   │   ├── main.py             # 应用入口
│   │   ├── config.py           # 多环境配置
│   │   ├── database.py         # PostgreSQL + async SQLAlchemy
│   │   ├── models.py           # 数据模型 (需求/测试点/用例/追溯链/实体)
│   │   ├── schemas.py          # Pydantic 请求/响应 Schema
│   │   ├── llm_provider.py     # LLM 抽象层 (OpenAI/Claude/Qwen)
│   │   ├── api/                # API 路由
│   │   │   ├── requirements.py # 需求管理 API
│   │   │   ├── test_points.py  # 测试点管理 API
│   │   │   ├── test_cases.py   # 用例管理 + 导出 API
│   │   │   └── entities.py     # 实体注册表 API
│   │   └── services/           # 核心服务
│   │       ├── stage1_requirement.py  # Stage 1: 需求解析+指纹
│   │       ├── stage2_testpoints.py   # Stage 2: 测试点生成
│   │       ├── stage3_cases.py        # Stage 3: 用例转换
│   │       └── export_service.py      # 导出 (JSON/Excel/XMind/MD)
│   ├── requirements.txt
│   └── .env.example
├── frontend/                   # React + Ant Design 前端
│   ├── src/
│   │   ├── App.tsx
│   │   ├── main.tsx
│   │   ├── api/client.ts       # API 客户端
│   │   ├── layouts/MainLayout.tsx
│   │   └── pages/
│   │       ├── Dashboard.tsx         # 仪表盘
│   │       ├── RequirementList.tsx   # 需求列表
│   │       ├── RequirementDetail.tsx # 需求详情 + 阶段执行
│   │       ├── TestPointView.tsx     # 测试点审查
│   │       └── CaseView.tsx          # 用例查看+导出
│   ├── package.json
│   └── vite.config.ts
└── start.bat                   # Windows 一键启动
```

## 已实现功能

### Phase 1 MVP (Stage 1-3)

| 阶段 | 功能 | 状态 |
|------|------|------|
| Stage 1 | 需求解析：LLM 结构化提取 + feature_id + 指纹 + 实体抽取 | ✅ |
| Stage 2 | 测试点生成：7维度穷举 + RAG增强 + 测试技法注入 | ✅ |
| Stage 3 | 用例转换：UI+API双形态 + 步骤级标记(locked/last_modified_by) | ✅ |
| 追溯链 | 需求→功能点→测试点→用例的有向图 | ✅ |
| 实体注册 | 页面/接口/角色/术语统一ID管理 | ✅ |
| 导出 | JSON / Excel / XMind / Markdown 四种格式 | ✅ |

### 核心设计决策

- **LLM 抽象层**：Provider 工厂模式，OpenAI/Claude/通义千问可切换
- **用例 Schema**：统一 JSON Schema 约束，每条步骤带 locked + last_modified_by
- **SOP 防坑**：每个阶段 LLM 输出人审必过，AI 不直接入库
- **追溯底座**：提前建好 traceability_links 表，为后续横切机制A/B铺路

## 快速启动

### 前提条件

- Python 3.10+
- PostgreSQL 14+ (需手动创建数据库 `ai_test_platform`)
- Node.js 18+

### 1. 后端

```bash
cd backend

# 复制配置
cp .env.example .env
# 编辑 .env 填入 LLM API Key

# 安装依赖
pip install -r requirements.txt

# 启动 (自动建表)
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

API 文档: http://localhost:8000/docs

### 2. 前端

```bash
cd frontend

npm install
npm run dev
```

前端地址: http://localhost:3000

### 3. 一键启动 (Windows)

```bash
start.bat
```

## 使用流程

1. **上传需求** → 手动输入或上传 .txt/.md 文件
2. **Stage 1: 解析需求** → 点击按钮，LLM 提取功能点+实体+指纹
3. **Stage 2: 生成测试点** → 自动生成7维度测试点，QA 勾选确认
4. **Stage 3: 生成用例** → 从确认的测试点展开为 UI+API 用例
5. **导出** → Excel/XMind/JSON/Markdown 导出

## 技术栈

| 分层 | 选型 |
|------|------|
| 后端框架 | Python + FastAPI |
| 数据库 | PostgreSQL + SQLAlchemy 2.0 async |
| LLM | OpenAI GPT-4o / Claude / 通义千问 (可切换) |
| 前端 | React 18 + TypeScript + Ant Design 5 |
| 构建 | Vite |
| 导出 | openpyxl (Excel) + 结构化 JSON (XMind) |

## 后续规划

按方案的 9 期路线图：

| Phase | 内容 | 预计 |
|-------|------|------|
| 1.5 | 迭代同步（简）：版本化 + 新增/删除同步 | 8-10周 |
| 2 | 执行接入：Playwright UI + API 执行 | 10-14周 |
| 3 | 智能分析：LLM 失败分类 + 缺陷草稿 | 14-18周 |
| 3.5 | 迭代同步（繁）：Merge 策略 + 冲突解决 | 18-20周 |
| 4 | 回归资产：CI 闭环 + 飞轮转动 | 20-24周 |
