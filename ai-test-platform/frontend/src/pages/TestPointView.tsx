import React, { useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import {
  Card, Table, Button, Tag, Typography, Space, Spin, message,
  Checkbox, Empty, Popconfirm, Badge,
} from 'antd';
import {
  CheckOutlined, DeleteOutlined, ArrowLeftOutlined, BugOutlined,
} from '@ant-design/icons';
import { testPointApi, requirementApi, testCaseApi } from '../api/client';

const dimensionColorMap: Record<string, string> = {
  '功能正常': 'blue',
  '边界值': 'orange',
  '异常输入': 'red',
  '权限控制': 'purple',
  '并发场景': 'volcano',
  '兼容性': 'cyan',
  '数据完整性': 'green',
};

const TestPointView: React.FC = () => {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [points, setPoints] = useState<any[]>([]);
  const [req, setReq] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [generating, setGenerating] = useState(false);

  const load = async () => {
    if (!id) return;
    setLoading(true);
    try {
      const [pRes, rRes] = await Promise.all([
        testPointApi.listByRequirement(id),
        requirementApi.get(id),
      ]);
      setPoints(pRes.data || []);
      setReq(rRes.data);
    } catch (e) {
      // handled
    }
    setLoading(false);
  };

  useEffect(() => { load(); }, [id]);

  const handleConfirm = async () => {
    if (selectedIds.length === 0) {
      message.warning('请至少选择一个测试点');
      return;
    }
    const unconfirmed = points.filter(p => p.is_confirmed);
    if (unconfirmed.length > 0 && !window.confirm(`有 ${unconfirmed.length} 条已确认的测试点可能被重置，继续？`)) {
      return;
    }
    await testPointApi.confirm(selectedIds);
    message.success(`已确认 ${selectedIds.length} 条测试点`);
    setSelectedIds([]);
    await load();
  };

  const handleGenerateCases = async () => {
    if (!id) return;
    const confirmedIds = points.filter(p => p.is_confirmed).map(p => p.id);
    if (confirmedIds.length === 0) {
      message.warning('请先确认测试点');
      return;
    }
    setGenerating(true);
    try {
      const res = await testCaseApi.generate(id, confirmedIds, true);
      const taskId = res.data?.task_id;
      if (!taskId) {
        message.error('未获取到生成任务 ID');
        return;
      }

      // 轮询后台任务状态
      const poll = async (): Promise<boolean> => {
        const statusRes = await testCaseApi.getGenerateStatus(taskId);
        const { status, message: taskMsg, error } = statusRes.data || {};
        if (status === 'completed') {
          const result = statusRes.data?.result || {};
          const total = (result.ui_count || 0) + (result.api_count || 0);
          if (total === 0) {
            message.warning('任务已完成，但未生成任何用例，请检查后台日志');
            return false;
          }
          message.success(taskMsg || `用例生成完成（共 ${total} 条）`);
          return true;
        }
        if (status === 'failed') {
          message.error(error || taskMsg || '用例生成失败');
          return false;
        }
        // pending / running 继续轮询
        return new Promise((resolve) => {
          setTimeout(() => resolve(poll()), 1500);
        });
      };

      const success = await poll();
      if (success) {
        await load();
        navigate(`/requirements/${id}/cases`);
      }
    } finally {
      setGenerating(false);
    }
  };

  const allIds = points.map(p => p.id);
  const allSelected = allIds.length > 0 && selectedIds.length === allIds.length;
  const someSelected = selectedIds.length > 0 && selectedIds.length < allIds.length;

  const handleSelectAll = (checked: boolean) => {
    setSelectedIds(checked ? allIds : []);
  };

  const columns = [
    {
      title: (
        <Checkbox
          checked={allSelected}
          indeterminate={someSelected}
          onChange={(e) => handleSelectAll(e.target.checked)}
        />
      ),
      dataIndex: 'id',
      width: 50,
      render: (tpId: string, record: any) => (
        <Checkbox
          checked={selectedIds.includes(tpId)}
          onChange={(e) => {
            if (e.target.checked) {
              setSelectedIds([...selectedIds, tpId]);
            } else {
              setSelectedIds(selectedIds.filter(i => i !== tpId));
            }
          }}
        />
      ),
    },
    {
      title: '测试点',
      dataIndex: 'title',
      key: 'title',
      width: 300,
      render: (text: string, record: any) => (
        <Space>
          {record.is_confirmed && <CheckOutlined style={{ color: '#52c41a' }} />}
          <span>{text}</span>
        </Space>
      ),
    },
    {
      title: '覆盖维度',
      dataIndex: 'dimension',
      key: 'dimension',
      width: 120,
      render: (d: string) => <Tag color={dimensionColorMap[d] || 'default'}>{d}</Tag>,
    },
    {
      title: '测试技法',
      dataIndex: 'technique',
      key: 'technique',
      width: 130,
    },
    {
      title: '优先级',
      dataIndex: 'priority',
      key: 'priority',
      width: 70,
      render: (p: string) => (
        <Tag color={p === 'P0' ? 'red' : p === 'P1' ? 'orange' : p === 'P2' ? 'blue' : 'default'}>{p}</Tag>
      ),
    },
    {
      title: '场景描述',
      dataIndex: 'scenario_desc',
      key: 'scenario_desc',
      ellipsis: true,
    },
    {
      title: 'Feature ID',
      dataIndex: 'feature_id',
      key: 'feature_id',
      width: 200,
      render: (v: string) => v ? <Typography.Text code>{v}</Typography.Text> : '-',
    },
  ];

  if (loading) return <Spin size="large" style={{ display: 'block', margin: '100px auto' }} />;

  const confirmedCount = points.filter(p => p.is_confirmed).length;

  return (
    <div>
      <Space style={{ marginBottom: 16 }}>
        <Button icon={<ArrowLeftOutlined />} onClick={() => navigate(`/requirements/${id}`)}>返回需求</Button>
        <Typography.Title level={3} style={{ margin: 0 }}>测试点清单</Typography.Title>
        <Tag color="blue">{req?.title}</Tag>
        <Badge count={confirmedCount} showZero style={{ backgroundColor: '#52c41a' }}>
          <Typography.Text type="secondary">已确认</Typography.Text>
        </Badge>
      </Space>

      {points.length === 0 ? (
        <Empty description="暂无测试点，请先执行 Stage 2">
          <Button type="primary" onClick={async () => {
            await testPointApi.generate(id!);
            location.reload();
          }}>生成测试点</Button>
        </Empty>
      ) : (
        <>
          {/* 操作栏 */}
          <Card size="small" style={{ marginBottom: 16 }}>
            <Space size="middle">
              <Button type="primary" icon={<CheckOutlined />} onClick={handleConfirm}>
                确认选中 ({selectedIds.length})
              </Button>
              <Button icon={<BugOutlined />} onClick={handleGenerateCases}
                loading={generating} disabled={confirmedCount === 0}>
                Stage 3: 生成用例 ({confirmedCount}条)
              </Button>
              <Popconfirm title="清空所有选择？" onConfirm={() => setSelectedIds([])}>
                <Button>清空选择</Button>
              </Popconfirm>
            </Space>
          </Card>

          {/* 测试点表格 */}
          <Table
            columns={columns}
            dataSource={points}
            rowKey="id"
            size="middle"
            pagination={{ pageSize: 30 }}
            rowClassName={(record) => record.is_confirmed ? 'ant-table-row-selected' : ''}
          />
        </>
      )}
    </div>
  );
};

export default TestPointView;
