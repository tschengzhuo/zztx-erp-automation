import React, { useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import {
  Card, Table, Button, Tag, Typography, Space, Spin, Tabs,
  Modal, Descriptions, message, Select, Empty, Badge, Tooltip,
} from 'antd';
import {
  ArrowLeftOutlined, DownloadOutlined, LockOutlined,
  UnlockOutlined, CheckOutlined, EditOutlined, RobotOutlined,
} from '@ant-design/icons';
import { testCaseApi, requirementApi } from '../api/client';

const priorityColorMap: Record<string, string> = {
  P0: 'red', P1: 'orange', P2: 'blue', P3: 'default',
};

const CaseView: React.FC = () => {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [cases, setCases] = useState<any[]>([]);
  const [req, setReq] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState<'all' | 'UI' | 'API'>('all');
  const [detailOpen, setDetailOpen] = useState(false);
  const [selectedCase, setSelectedCase] = useState<any>(null);

  const load = async () => {
    if (!id) return;
    setLoading(true);
    try {
      const [cRes, rRes] = await Promise.all([
        testCaseApi.listByRequirement(id),
        requirementApi.get(id),
      ]);
      setCases(cRes.data || []);
      setReq(rRes.data);
    } catch (e) {
      // handled
    }
    setLoading(false);
  };

  useEffect(() => { load(); }, [id]);

  const handleExport = async (format: string) => {
    if (!id) return;
    try {
      const res = await testCaseApi.export(id, format);
      // 创建下载链接
      const url = window.URL.createObjectURL(new Blob([res.data]));
      const link = document.createElement('a');
      link.href = url;
      link.download = `test-cases-${id.slice(0, 8)}.${format === 'markdown' ? 'md' : format}`;
      link.click();
      window.URL.revokeObjectURL(url);
      message.success(`导出 ${format.toUpperCase()} 成功`);
    } catch (e) {
      // handled
    }
  };

  const handleConfirm = async (caseId: string) => {
    await testCaseApi.confirm(caseId);
    message.success('用例已确认');
    await load();
  };

  const filtered = cases.filter(c =>
    activeTab === 'all' ? true : c.case_type === activeTab
  );

  const uiCount = cases.filter(c => c.case_type === 'UI').length;
  const apiCount = cases.filter(c => c.case_type === 'API').length;
  const confirmedCount = cases.filter(c => c.is_confirmed).length;

  const columns = [
    {
      title: '用例ID',
      dataIndex: 'case_id',
      key: 'case_id',
      width: 140,
      render: (v: string) => <Typography.Text code>{v}</Typography.Text>,
    },
    {
      title: '标题',
      dataIndex: 'title',
      key: 'title',
      width: 320,
      render: (text: string, record: any) => (
        <Space>
          {record.is_confirmed && <CheckOutlined style={{ color: '#52c41a' }} />}
          <a onClick={() => { setSelectedCase(record); setDetailOpen(true); }}>{text}</a>
        </Space>
      ),
    },
    {
      title: '类型',
      dataIndex: 'case_type',
      key: 'case_type',
      width: 70,
      render: (t: string) => <Tag color={t === 'UI' ? 'blue' : 'green'}>{t}</Tag>,
    },
    {
      title: '优先级',
      dataIndex: 'priority',
      key: 'priority',
      width: 70,
      render: (p: string) => <Tag color={priorityColorMap[p]}>{p}</Tag>,
    },
    {
      title: '步骤数',
      key: 'step_count',
      width: 80,
      render: (_: any, record: any) => (record.steps || []).length,
    },
    {
      title: '生成者',
      dataIndex: 'created_by',
      key: 'created_by',
      width: 80,
      render: (v: string) => (
        <Tag icon={v === 'AI' ? <RobotOutlined /> : undefined} color={v === 'AI' ? 'purple' : 'default'}>
          {v}
        </Tag>
      ),
    },
    {
      title: '标签',
      dataIndex: 'tags',
      key: 'tags',
      width: 200,
      render: (tags: string[]) => tags?.map(t => <Tag key={t}>{t}</Tag>),
    },
    {
      title: '操作',
      key: 'actions',
      width: 120,
      render: (_: any, record: any) => (
        <Space>
          <Button size="small" type="link"
            onClick={() => { setSelectedCase(record); setDetailOpen(true); }}>
            查看
          </Button>
          {!record.is_confirmed && (
            <Button size="small" type="link" onClick={() => handleConfirm(record.id)}>
              确认
            </Button>
          )}
        </Space>
      ),
    },
  ];

  if (loading) return <Spin size="large" style={{ display: 'block', margin: '100px auto' }} />;

  if (cases.length === 0) {
    return (
      <Empty description="暂无用例，请先生成测试点后执行 Stage 3">
        <Button type="primary" onClick={() => navigate(`/requirements/${id}`)}>返回需求</Button>
      </Empty>
    );
  }

  return (
    <div>
      {/* 标题栏 */}
      <Space style={{ marginBottom: 16 }}>
        <Button icon={<ArrowLeftOutlined />} onClick={() => navigate(`/requirements/${id}`)}>返回需求</Button>
        <Typography.Title level={3} style={{ margin: 0 }}>用例列表</Typography.Title>
        <Tag color="blue">{req?.title}</Tag>
        <Badge count={confirmedCount} style={{ backgroundColor: '#52c41a' }}>
          <Typography.Text type="secondary">已确认</Typography.Text>
        </Badge>
      </Space>

      {/* 操作栏 */}
      <Card size="small" style={{ marginBottom: 16 }}>
        <Space size="middle">
          <Button icon={<DownloadOutlined />} onClick={() => handleExport('xmind')}>导出 XMind</Button>
        </Space>
      </Card>

      {/* 用例表格 */}
      <Card
        tabProps={{ size: 'small' }}
        tabList={[
          { key: 'all', label: `全部 (${cases.length})` },
          { key: 'UI', label: `UI (${uiCount})` },
          { key: 'API', label: `API (${apiCount})` },
        ]}
        activeTabKey={activeTab}
        onTabChange={(k) => setActiveTab(k as any)}
      >
        <Table
          columns={columns}
          dataSource={filtered}
          rowKey="id"
          size="middle"
          pagination={{ pageSize: 20 }}
        />
      </Card>

      {/* 用例详情弹窗 */}
      <Modal
        title={selectedCase?.title}
        open={detailOpen}
        onCancel={() => setDetailOpen(false)}
        footer={null}
        width={800}
      >
        {selectedCase && (
          <>
            <Descriptions column={2} size="small" style={{ marginBottom: 16 }}>
              <Descriptions.Item label="用例ID">{selectedCase.case_id}</Descriptions.Item>
              <Descriptions.Item label="类型">
                <Tag color={selectedCase.case_type === 'UI' ? 'blue' : 'green'}>{selectedCase.case_type}</Tag>
              </Descriptions.Item>
              <Descriptions.Item label="优先级">
                <Tag color={priorityColorMap[selectedCase.priority]}>{selectedCase.priority}</Tag>
              </Descriptions.Item>
              <Descriptions.Item label="标签">
                {(selectedCase.tags || []).map((t: string) => <Tag key={t}>{t}</Tag>)}
              </Descriptions.Item>
            </Descriptions>

            {selectedCase.precondition && (
              <Card size="small" title="前置条件" style={{ marginBottom: 12 }}>
                <Typography.Text>{selectedCase.precondition}</Typography.Text>
              </Card>
            )}

            <Card size="small" title={`步骤 (${(selectedCase.steps || []).length})`} style={{ marginBottom: 12 }}>
              {(selectedCase.steps || []).map((step: any, i: number) => (
                <div key={i} className={`step-row${step.locked ? ' step-locked' : ''}`}>
                  <span className="step-index">{i + 1}</span>
                  <Tag color="blue">{step.action}</Tag>
                  <Typography.Text style={{ flex: 1 }}>{step.target}</Typography.Text>
                  {step.value && <Tag>{step.value}</Tag>}
                  {step.locked && (
                    <Tooltip title="已锁定（人工修改保护）">
                      <LockOutlined style={{ color: '#faad14' }} />
                    </Tooltip>
                  )}
                  <Tag color={step.last_modified_by === 'AI' ? 'purple' : 'default'}>
                    {step.last_modified_by === 'AI' ? 'AI' : '人工'}
                  </Tag>
                </div>
              ))}
            </Card>

            {selectedCase.expected_result && (
              <Card size="small" title="预期结果">
                <Typography.Text>{selectedCase.expected_result}</Typography.Text>
              </Card>
            )}
          </>
        )}
      </Modal>
    </div>
  );
};

export default CaseView;
