import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Table, Button, Modal, Form, Input, Select, Upload,
  Tag, Space, Typography, message, Spin, Card, Tabs,
} from 'antd';
import { PlusOutlined, UploadOutlined, FileTextOutlined, EditOutlined, DeleteOutlined } from '@ant-design/icons';
import { requirementApi } from '../api/client';
import dayjs from 'dayjs';

const statusColorMap: Record<string, string> = {
  draft: 'default',
  parsed: 'blue',
  test_points_generated: 'green',
  cases_generated: 'purple',
  reviewed: 'cyan',
  archived: 'default',
};

const statusLabelMap: Record<string, string> = {
  draft: '草稿',
  parsed: '已解析(Stage 1)',
  test_points_generated: '已生成测试点(Stage 2)',
  cases_generated: '已生成用例(Stage 3)',
  reviewed: '已审核',
  archived: '已归档',
};

const RequirementList: React.FC = () => {
  const navigate = useNavigate();
  const [items, setItems] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [createOpen, setCreateOpen] = useState(false);
  const [createForm] = Form.useForm();
  const [uploading, setUploading] = useState(false);
  const [activeTab, setActiveTab] = useState('manual');

  const loadList = async () => {
    setLoading(true);
    try {
      const res = await requirementApi.list({ page_size: 100 });
      setItems(res.data.items || []);
    } catch (e) {
      // handled by interceptor
    }
    setLoading(false);
  };

  useEffect(() => { loadList(); }, []);

  const handleCreate = async () => {
    try {
      await createForm.validateFields();
      const values = createForm.getFieldsValue();
      await requirementApi.create({
        title: values.title,
        module: values.module,
        raw_text: values.raw_text,
      });
      message.success('需求创建成功，请点击"解析"执行 Stage 1');
      setCreateOpen(false);
      createForm.resetFields();
      loadList();
    } catch (e) {
      // validation error
    }
  };

  const handleUpload = async (file: File) => {
    setUploading(true);
    try {
      await requirementApi.upload(file, '未分类');
      message.success('文件上传成功');
      loadList();
    } finally {
      setUploading(false);
    }
    return false; // prevent default upload
  };

  const handleDelete = async (id: string) => {
    Modal.confirm({
      title: '确认删除',
      content: '删除后需求及关联的测试点和用例都将软删除',
      onOk: async () => {
        await requirementApi.delete(id);
        message.success('已删除');
        loadList();
      },
    });
  };

  const columns = [
    {
      title: '需求标题',
      dataIndex: 'title',
      key: 'title',
      width: 280,
      render: (text: string, record: any) => (
        <a onClick={() => navigate(`/requirements/${record.id}`)}>{text}</a>
      ),
    },
    {
      title: '模块',
      dataIndex: 'module',
      key: 'module',
      width: 120,
    },
    {
      title: '版本',
      dataIndex: 'version',
      key: 'version',
      width: 60,
      render: (v: number) => `v${v}`,
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      width: 150,
      render: (s: string) => (
        <Tag color={statusColorMap[s] || 'default'}>{statusLabelMap[s] || s}</Tag>
      ),
    },
    {
      title: 'Feature ID',
      dataIndex: 'feature_id',
      key: 'feature_id',
      width: 200,
      render: (v: string) => v ? <Typography.Text code>{v}</Typography.Text> : '-',
    },
    {
      title: '创建时间',
      dataIndex: 'created_at',
      key: 'created_at',
      width: 170,
      render: (v: string) => v ? dayjs(v).format('YYYY-MM-DD HH:mm') : '-',
    },
    {
      title: '操作',
      key: 'actions',
      width: 200,
      render: (_: any, record: any) => (
        <Space>
          <Button size="small" type="link" onClick={() => navigate(`/requirements/${record.id}`)}>
            详情
          </Button>
          <Button size="small" type="link"
            onClick={() => navigate(`/requirements/${record.id}/test-points`)}
            disabled={record.status === 'draft'}>
            测试点
          </Button>
          <Button size="small" type="link"
            onClick={() => navigate(`/requirements/${record.id}/cases`)}
            disabled={record.status !== 'cases_generated' && record.status !== 'reviewed'}>
            用例
          </Button>
          <Button size="small" type="link" danger onClick={() => handleDelete(record.id)}>
            删除
          </Button>
        </Space>
      ),
    },
  ];

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 16 }}>
        <Typography.Title level={3} style={{ margin: 0 }}>需求管理</Typography.Title>
        <Button type="primary" icon={<PlusOutlined />} onClick={() => setCreateOpen(true)}>
          新建需求
        </Button>
      </div>

      <Table
        columns={columns}
        dataSource={items}
        rowKey="id"
        loading={loading}
        pagination={{ pageSize: 20 }}
      />

      {/* 新建需求弹窗 */}
      <Modal
        title="新建需求"
        open={createOpen}
        onOk={handleCreate}
        onCancel={() => { setCreateOpen(false); createForm.resetFields(); }}
        width={700}
      >
        <Tabs activeKey={activeTab} onChange={setActiveTab}
          items={[
            {
              key: 'manual',
              label: '手动输入',
              children: (
                <Form form={createForm} layout="vertical">
                  <Form.Item name="title" label="需求标题" rules={[{ required: true }]}>
                    <Input placeholder="如：订单优惠券叠加规则优化" />
                  </Form.Item>
                  <Form.Item name="module" label="所属模块" rules={[{ required: true }]}>
                    <Input placeholder="如：order.cart" />
                  </Form.Item>
                  <Form.Item name="raw_text" label="需求文档" rules={[{ required: true, message: '请输入需求文档内容' }]}>
                    <Input.TextArea rows={10} placeholder="粘贴需求文档原文..." />
                  </Form.Item>
                </Form>
              ),
            },
            {
              key: 'upload',
              label: '上传文件',
              children: (
                <div style={{ padding: '40px 0', textAlign: 'center' }}>
                  <Upload.Dragger
                    beforeUpload={handleUpload}
                    showUploadList={false}
                    accept=".txt,.md,.docx"
                  >
                    <UploadOutlined style={{ fontSize: 48, color: '#185FA5' }} />
                    <p>点击或拖拽上传需求文件</p>
                    <p style={{ color: '#999' }}>支持 .txt .md .docx 格式</p>
                  </Upload.Dragger>
                  {uploading && <Spin style={{ marginTop: 16 }} />}
                </div>
              ),
            },
          ]}
        />
      </Modal>
    </div>
  );
};

export default RequirementList;
