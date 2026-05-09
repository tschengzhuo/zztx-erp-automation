# ZZTX ERP Automation

智展天下 ERP 自动化系统，提供订单处理、库存管理、数据同步和报表生成等功能。

## 项目结构

```
zztx-erp-automation/
├── .github/
│   └── workflows/
│       └── automation.yml      # GitHub Actions 定时自动化
├── src/
│   ├── core/                   # 核心业务逻辑
│   │   ├── order_flow.py       # 订单处理
│   │   └── inventory.py        # 库存计算
│   ├── connectors/             # 连接器
│   │   ├── erp_api.py          # ERP API 对接
│   │   └── db_client.py        # 数据库客户端
│   ├── tasks/                  # 自动化任务
│   │   ├── daily_sync.py       # 每日数据同步
│   │   └── report_gen.py       # 报表生成
│   └── common/                 # 公共组件
│       ├── logger.py           # 日志封装
│       └── exceptions.py       # 异常处理
├── config/
│   ├── dev.yaml                # 开发环境配置
│   └── prod.yaml               # 生产环境配置
├── tests/                      # 测试用例
├── requirements.txt            # Python 依赖
└── README.md
```

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 配置环境

复制并编辑配置文件：

```bash
# 开发环境
export APP_ENV=dev
export DB_PASSWORD=your_password

# 或使用 .env 文件
cp .env.example .env
```

### 3. 运行任务

```bash
# 每日数据同步
python -m src.tasks.daily_sync

# 报表生成
python -m src.tasks.report_gen
```

## GitHub Actions 自动化

项目已配置 GitHub Actions 工作流：

- **定时触发**: 每天 UTC 02:00（北京时间 10:00）自动执行
- **手动触发**: 支持在 Actions 页面手动选择任务运行
- **任务类型**:
  - `daily_sync` - 每日数据同步
  - `report_gen` - 报表生成
  - `all` - 执行所有任务

### 需要配置的 Secrets

| Secret | 说明 |
|--------|------|
| `DB_HOST` | 数据库主机地址 |
| `DB_USER` | 数据库用户名 |
| `DB_PASSWORD` | 数据库密码 |
| `ERP_API_KEY` | ERP 系统 API 密钥 |

## 核心模块说明

### OrderFlow (订单处理)

- 订单创建与验证
- 状态流转控制（待处理 -> 已确认 -> 处理中 -> 已发货 -> 已完成）
- 金额计算

### Inventory (库存管理)

- 库存查询与更新
- 库存预占/释放/扣减
- 低库存预警

### ERP API Connector

- 统一的 HTTP 请求封装
- 自动重试机制
- 异常处理

### DB Client

- 基于 SQLAlchemy 的数据库操作
- 连接池管理
- 事务支持

## 测试

```bash
# 运行所有测试
pytest

# 带覆盖率报告
pytest --cov=src --cov-report=html
```

## 许可证

MIT
