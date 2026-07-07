import React, { useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import {
  Card, Button, Descriptions, Tag, Typography, Space, Spin,
  Steps, message, Alert, Collapse, Table, Empty,
} from 'antd';
import {
  PlayCircleOutlined, ExperimentOutlined, BugOutlined,
  ArrowRightOutlined, CheckCircleOutlined, FileTextOutlined,
} from '@ant-design/icons';
import { requirementApi, testPointApi, testCaseApi } from '../api/client';
import dayjs from 'dayjs';

const statusLabelMap: Record<string, string> = {
  draft: '草稿',
  parsed: '已解析',
  test_points_generated: '已生成测试点',
  cases_generated: '已生成用例',
  reviewed: '已审核',
};

const RequirementDetail: React.FC = () => {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [req, setReq] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [parsing, setParsing] = useState(false);

  const load = async () => {
    if (!id) return;
    setLoading(true);
    try {
      const res = await requirementApi.get(id);
      setReq(res.data);
    } catch (e) {
      // handled
    }
    setLoading(false);
  };

  useEffect(() => { load(); }, [id]);

  const handleParse = async () => {
    if (!id) return;
    setParsing(true);
    try {
      await requirementApi.parse(id);
      message.success('Stage 1 完成：需求解析成功');
      await load();
    } catch (e) {
      // handled
    }
    setParsing(false);
  };

  const handleGenerateTestPoints = async () => {
    if (!id) return;
    try {
      await testPointApi.generate(id);
      message.success('Stage 2 完成：测试点生成成功');
      await load();
    } catch (e) {
      // handled
    }
  };

  const handleGenerateCases = async () => {
    if (!id) return;
    try {
      await testCaseApi.generate(id, [], true);
      message.success('Stage 3 完成：用例生成成功');
      await load();
    } catch (e) {
      // handled
    }
  };

  if (loading) return <Spin size="large" style={{ display: 'block', margin: '100px auto' }} />;
  if (!req) return <Empty description="需求不存在" />;

  const fpList = Array.isArray(req.functional_points) ? req.functional_points : [];
  const entities = req.extracted_entities || {};

  return (
    <div>
      {/* 面包屑 + 标题 */}
      <Space style={{ marginBottom: 8 }}>
        <a onClick={() => navigate('/requirements')}>需求管理</a>
        <span>/</span>
        <Typography.Text strong>{req.title}</Typography.Text>
      </Space>

      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
        <Space>
          <Typography.Title level={3} style={{ margin: 0 }}>{req.title}</Typography.Title>
          <Tag>v{req.version}</Tag>
          <Tag color="blue">{statusLabelMap[req.status] || req.status}</Tag>
        </Space>
      </div>

      {/* 阶段进度 */}
      <Card size="small" style={{ marginBottom: 16 }}>
        <Steps
          current={req.status === 'draft' ? 0 : req.status === 'parsed' ? 1 :
                   req.status === 'test_points_generated' ? 2 : 3}
          size="small"
          items={[
            { title: 'Stage 1', description: '需求解析', icon: <FileTextOutlined /> },
            { title: 'Stage 2', description: '测试点生成', icon: <ExperimentOutlined /> },
            { title: 'Stage 3', description: '用例转换', icon: <BugOutlined /> },
            { title: '完成', description: 'QA 审核', icon: <CheckCircleOutlined /> },
          ]}
        />
      </Card>

      {/* 操作按钮 */}
      <Card size="small" style={{ marginBottom: 16 }}>
        <Space size="middle">
          <Button type="primary" icon={<PlayCircleOutlined />}
            onClick={handleParse} loading={parsing}
            disabled={!req.raw_text}>
            Stage 1: 解析需求
          </Button>
          <Button icon={<ExperimentOutlined />}
            onClick={handleGenerateTestPoints}
            disabled={req.status === 'draft'}>
            Stage 2: 生成测试点
          </Button>
          <Button icon={<BugOutlined />}
            onClick={handleGenerateCases}
            disabled={!['test_points_generated', 'cases_generated'].includes(req.status)}>
            Stage 3: 生成用例
          </Button>
        </Space>
      </Card>

      {/* 需求详情 */}
      <Card title="需求信息" style={{ marginBottom: 16 }}>
        <Descriptions column={2} size="small">
          <Descriptions.Item label="模块">{req.module}</Descriptions.Item>
          <Descriptions.Item label="来源">{req.source}</Descriptions.Item>
          <Descriptions.Item label="Feature ID">
            {req.feature_id ? <Typography.Text code>{req.feature_id}</Typography.Text> : '-'}
          </Descriptions.Item>
          <Descriptions.Item label="版本">v{req.version}</Descriptions.Item>
          <Descriptions.Item label="创建时间">
            {req.created_at ? dayjs(req.created_at).format('YYYY-MM-DD HH:mm') : '-'}
          </Descriptions.Item>
          <Descriptions.Item label="状态">
            <Tag color="blue">{statusLabelMap[req.status] || req.status}</Tag>
          </Descriptions.Item>
        </Descriptions>
        {req.summary_text && (
          <Alert message="结构化摘要" description={req.summary_text} type="info" style={{ marginTop: 12 }} />
        )}
      </Card>

      {/* 功能点 */}
      {fpList.length > 0 && (
        <Card title={`功能点 (${fpList.length})`} style={{ marginBottom: 16 }}>
          <Table
            dataSource={fpList}
            rowKey="feature_id"
            size="small"
            pagination={false}
            columns={[
              { title: 'Feature ID', dataIndex: 'feature_id', width: 250, render: (v: string) => <Typography.Text code>{v}</Typography.Text> },
              { title: '名称', dataIndex: 'name', width: 200 },
              { title: '描述', dataIndex: 'description' },
            ]}
          />
        </Card>
      )}

      {/* 抽取的实体 */}
      {(entities.pages?.length || entities.apis?.length || entities.roles?.length) && (
        <Card title="抽取实体（供定位使用）" style={{ marginBottom: 16 }}>
          {entities.pages?.length > 0 && (
            <div style={{ marginBottom: 8 }}>
              <Typography.Text strong>页面：</Typography.Text>
              {entities.pages.map((p: string, i: number) => <Tag key={i} color="blue">{p}</Tag>)}
            </div>
          )}
          {entities.apis?.length > 0 && (
            <div style={{ marginBottom: 8 }}>
              <Typography.Text strong>接口：</Typography.Text>
              {entities.apis.map((a: string, i: number) => <Tag key={i} color="green">{a}</Tag>)}
            </div>
          )}
          {entities.roles?.length > 0 && (
            <div style={{ marginBottom: 8 }}>
              <Typography.Text strong>角色：</Typography.Text>
              {entities.roles.map((r: string, i: number) => <Tag key={i} color="purple">{r}</Tag>)}
            </div>
          )}
        </Card>
      )}

      {/* 快捷导航 */}
      <Card size="small">
        <Space>
          <Button type="link" onClick={() => navigate(`/requirements/${id}/test-points`)}
            disabled={req.status === 'draft'}>
            查看测试点 <ArrowRightOutlined />
          </Button>
          <Button type="link" onClick={() => navigate(`/requirements/${id}/cases`)}
            disabled={!['test_points_generated', 'cases_generated', 'reviewed'].includes(req.status)}>
            查看用例 <ArrowRightOutlined />
          </Button>
        </Space>
      </Card>
    </div>
  );
};

export default RequirementDetail;
