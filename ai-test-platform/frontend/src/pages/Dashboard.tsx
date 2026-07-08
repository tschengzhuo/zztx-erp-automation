import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Card, Row, Col, Statistic, Typography, Steps, Space, Button, Tag, Spin } from 'antd';
import {
  FileTextOutlined,
  ExperimentOutlined,
  BugOutlined,
  ThunderboltOutlined,
  ArrowRightOutlined,
} from '@ant-design/icons';
import { platformApi, requirementApi } from '../api/client';

const Dashboard: React.FC = () => {
  const navigate = useNavigate();
  const [stats, setStats] = useState<any>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const load = async () => {
      try {
        const [s, r] = await Promise.all([
          platformApi.stats(),
          requirementApi.list({ page_size: 5 }),
        ]);
        setStats({ ...s.data, recentReqs: r.data.items });
      } catch (e) {
        // fallback
      }
      setLoading(false);
    };
    load();
  }, []);

  if (loading) return <Spin size="large" style={{ display: 'block', margin: '100px auto' }} />;

  return (
    <div>
      <Typography.Title level={3}>AI 测试平台 · 仪表盘</Typography.Title>
      <Typography.Paragraph type="secondary">
        需求读取 → 精准定位 → 测试点生成 → 结构化用例（Phase 1 MVP）
      </Typography.Paragraph>

      {/* 7 阶段流水线 */}
      <Card title="7 阶段流水线" style={{ marginBottom: 24 }}>
        <Steps
          current={2}
          size="small"
          items={[
            { title: '需求读取', description: '结构化+指纹' },
            { title: '测试点生成', description: '7维度覆盖' },
            { title: '用例转换', description: 'UI+API双形态' },
            { title: 'UI执行', description: 'Playwright' },
            { title: '接口执行', description: 'API请求' },
            { title: '失败分析', description: 'LLM多模态' },
            { title: '回归资产', description: 'CI闭环' },
          ]}
        />
        <div style={{ marginTop: 12 }}>
          <Tag color="green">Phase 1: 1-3 已实现</Tag>
          <Tag color="default">Phase 2: 4-5 规划中</Tag>
          <Tag color="default">Phase 3+: 6-7 规划中</Tag>
        </div>
      </Card>

      {/* 统计卡片 */}
      <Row gutter={16} style={{ marginBottom: 24 }}>
        <Col span={6}>
          <Card>
            <Statistic title="需求总数" value={stats?.recentReqs?.length || 0} prefix={<FileTextOutlined />} />
          </Card>
        </Col>
        <Col span={6}>
          <Card>
            <Statistic title="测试点生成" value="—" prefix={<ExperimentOutlined />} />
          </Card>
        </Col>
        <Col span={6}>
          <Card>
            <Statistic title="用例总数" value="—" prefix={<BugOutlined />} />
          </Card>
        </Col>
        <Col span={6}>
          <Card>
            <Statistic title="LLM Provider" value={stats?.llm_provider || '—'} prefix={<ThunderboltOutlined />} />
          </Card>
        </Col>
      </Row>

      {/* 快捷操作 */}
      <Card title="快捷操作">
        <Space size="large">
          <Button type="primary" icon={<FileTextOutlined />} size="large"
            onClick={() => navigate('/requirements')}>
            上传需求文档
          </Button>
          <Button icon={<ExperimentOutlined />} size="large"
            onClick={() => navigate('/requirements')}>
            查看测试点
          </Button>
          <Button icon={<BugOutlined />} size="large"
            onClick={() => navigate('/requirements')}>
            查看用例
          </Button>
        </Space>
      </Card>

      {/* 平台能力 */}
      <Card title="当前阶段能力" style={{ marginTop: 24 }}>
        <Row gutter={16}>
          <Col span={8}>
            <Card size="small" style={{ background: '#E6F1FB', borderColor: '#B5D4F4' }}>
              <Typography.Title level={5} style={{ color: '#185FA5' }}>Stage 1: 需求读取</Typography.Title>
              <Typography.Paragraph type="secondary" style={{ fontSize: 13 }}>
                上传需求文档 → LLM 结构化解析 → 生成 feature_id + 指纹 + 抽取实体
              </Typography.Paragraph>
            </Card>
          </Col>
          <Col span={8}>
            <Card size="small" style={{ background: '#E1F5EE', borderColor: '#9FE1CB' }}>
              <Typography.Title level={5} style={{ color: '#0F6E56' }}>Stage 2: 测试点生成</Typography.Title>
              <Typography.Paragraph type="secondary" style={{ fontSize: 13 }}>
                7维度穷举 + RAG历史增强 → 具体可执行的测试点清单
              </Typography.Paragraph>
            </Card>
          </Col>
          <Col span={8}>
            <Card size="small" style={{ background: '#EEEDFE', borderColor: '#CECBF6' }}>
              <Typography.Title level={5} style={{ color: '#534AB7' }}>Stage 3: 用例转换</Typography.Title>
              <Typography.Paragraph type="secondary" style={{ fontSize: 13 }}>
                UI+API双形态 → 步骤级标记 → 支持XMind导出
              </Typography.Paragraph>
            </Card>
          </Col>
        </Row>
      </Card>
    </div>
  );
};

export default Dashboard;
