import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Table, Button, Modal, Form, Input, Select, Upload, Tree, TreeSelect,
  Tag, Space, Typography, message, Spin, Card, Tabs, Row, Col, Popconfirm,
} from 'antd';
import {
  PlusOutlined, UploadOutlined, FileTextOutlined, EditOutlined,
  DeleteOutlined, SearchOutlined, FolderOutlined,
} from '@ant-design/icons';
import { requirementApi, categoryApi } from '../api/client';
import type { DataNode } from 'antd/es/tree';
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

// 分类树节点类型
interface CatTreeNode {
  id: string;
  name: string;
  parent_id: string | null;
  sort_order: number;
  description?: string;
  path?: string;
  requirement_count?: number;
  children?: CatTreeNode[];
}

const RequirementList: React.FC = () => {
  const navigate = useNavigate();
  const [items, setItems] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [createOpen, setCreateOpen] = useState(false);
  const [createForm] = Form.useForm();
  const [editOpen, setEditOpen] = useState(false);
  const [editForm] = Form.useForm();
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editLoading, setEditLoading] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [activeTab, setActiveTab] = useState('manual');

  // 搜索 & 排序
  const [searchTitle, setSearchTitle] = useState('');
  const [searchStatus, setSearchStatus] = useState<string | undefined>(undefined);
  const [sortBy, setSortBy] = useState('created_at');
  const [sortOrder, setSortOrder] = useState('descend');

  // 分类树
  const [categoryTree, setCategoryTree] = useState<CatTreeNode[]>([]);
  const [selectedCategoryId, setSelectedCategoryId] = useState<string | null>(null);
  const [catManageOpen, setCatManageOpen] = useState(false);
  const [catForm] = Form.useForm();
  const [catEditingId, setCatEditingId] = useState<string | null>(null);
  const [treeExpandedKeys, setTreeExpandedKeys] = useState<string[]>([]);

  // ==================== 数据加载 ====================

  const loadCategoryTree = async () => {
    try {
      const res = await categoryApi.getTree();
      setCategoryTree(res.data || []);
      // 展开所有节点
      const allKeys: string[] = [];
      const collectKeys = (nodes: CatTreeNode[]) => {
        nodes.forEach(n => {
          allKeys.push(n.id);
          if (n.children?.length) collectKeys(n.children);
        });
      };
      collectKeys(res.data || []);
      setTreeExpandedKeys(allKeys);
    } catch (e) { /* handled by interceptor */ }
  };

  const loadList = async () => {
    setLoading(true);
    try {
      const res = await requirementApi.list({
        page_size: 100,
        title: searchTitle || undefined,
        category_id: selectedCategoryId || undefined,
        status: searchStatus,
        sort_by: sortBy,
        sort_order: sortOrder === 'ascend' ? 'asc' : 'desc',
      });
      setItems(res.data.items || []);
    } catch (e) { /* handled by interceptor */ }
    setLoading(false);
  };

  useEffect(() => { loadCategoryTree(); }, []);
  useEffect(() => { loadList(); }, [searchTitle, selectedCategoryId, searchStatus, sortBy, sortOrder]);

  // ==================== 需求 CRUD ====================

  const handleCreate = async () => {
    try {
      await createForm.validateFields();
      const values = createForm.getFieldsValue();
      const res = await requirementApi.create({
        title: values.title,
        module: '', // 留空由系统自动分类
        raw_text: values.raw_text,
      });
      const autoClassified = res?.data?.auto_classified;
      const moduleName = res?.data?.module || '';
      message.success(
        autoClassified
          ? `需求创建成功，已自动归入"${moduleName}"`
          : '需求创建成功，请点击"解析"执行 Stage 1'
      );
      setCreateOpen(false);
      createForm.resetFields();
      loadList();
      loadCategoryTree(); // 自动分类可能新增了分类节点
    } catch (e) { /* validation error */ }
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
    return false;
  };

  const handleEdit = async (record: any) => {
    setEditLoading(true);
    setEditingId(record.id);
    try {
      const res = await requirementApi.get(record.id);
      const detail = res.data;
      editForm.setFieldsValue({
        title: detail.title,
        module: detail.module,
        raw_text: detail.raw_text || '',
      });
      setEditOpen(true);
    } finally {
      setEditLoading(false);
    }
  };

  const handleEditSubmit = async () => {
    try {
      await editForm.validateFields();
      const values = editForm.getFieldsValue();
      await requirementApi.update(editingId!, {
        title: values.title,
        module: values.module,
        raw_text: values.raw_text,
      });
      message.success('需求已更新');
      setEditOpen(false);
      editForm.resetFields();
      setEditingId(null);
      loadList();
    } catch (e) { /* validation error */ }
  };

  const handleDelete = async (id: string) => {
    await requirementApi.delete(id);
    message.success('已删除');
    loadList();
  };

  // ==================== 分类树管理 ====================

  const getTreeSelectNodes = (): DataNode[] => {
    // 用于 TreeSelect 和 Tree 渲染
    const toTreeData = (nodes: CatTreeNode[]): DataNode[] =>
      nodes.map(n => ({
        title: n.name,
        value: n.id,
        key: n.id,
        children: n.children?.length ? toTreeData(n.children) : undefined,
      }));
    return toTreeData(categoryTree);
  };

  const getFlatCategoryOptions = (): { value: string; label: string }[] => {
    const options: { value: string; label: string }[] = [];
    const walk = (nodes: CatTreeNode[], depth: number) => {
      nodes.forEach(n => {
        const prefix = '\u00A0\u00A0'.repeat(depth);
        options.push({ value: n.name, label: prefix + n.name });
        if (n.children?.length) walk(n.children, depth + 1);
      });
    };
    walk(categoryTree, 0);
    return options;
  };

  const findCatNode = (nodes: CatTreeNode[], id: string): CatTreeNode | null => {
    for (const n of nodes) {
      if (n.id === id) return n;
      if (n.children?.length) {
        const found = findCatNode(n.children, id);
        if (found) return found;
      }
    }
    return null;
  };

  const handleCatSelect = (selectedKeys: React.Key[]) => {
    if (selectedKeys.length === 0) {
      setSelectedCategoryId(null);
    } else {
      setSelectedCategoryId(selectedKeys[0] as string);
    }
  };

  const handleCatAdd = (parentId: string | null = null) => {
    setCatEditingId(null);
    catForm.resetFields();
    catForm.setFieldsValue({ parent_id: parentId || undefined });
    setCatManageOpen(true);
  };

  const handleCatEdit = (nodeId: string) => {
    const node = findCatNode(categoryTree, nodeId);
    if (node) {
      setCatEditingId(node.id);
      catForm.setFieldsValue({
        name: node.name,
        parent_id: node.parent_id || undefined,
        sort_order: node.sort_order,
        description: node.description || '',
      });
      setCatManageOpen(true);
    }
  };

  const handleCatSubmit = async () => {
    try {
      await catForm.validateFields();
      const vals = catForm.getFieldsValue();
      if (catEditingId) {
        await categoryApi.update(catEditingId, {
          name: vals.name,
          parent_id: vals.parent_id || null,
          sort_order: vals.sort_order,
          description: vals.description,
        });
        message.success('分类已更新');
      } else {
        await categoryApi.create({
          name: vals.name,
          parent_id: vals.parent_id || undefined,
          sort_order: vals.sort_order || 0,
          description: vals.description,
        });
        message.success('分类已创建');
      }
      setCatManageOpen(false);
      catForm.resetFields();
      setCatEditingId(null);
      loadCategoryTree();
    } catch (e) { /* validation error */ }
  };

  const handleCatDelete = async (nodeId: string) => {
    await categoryApi.delete(nodeId);
    message.success('分类已删除');
    if (selectedCategoryId === nodeId) setSelectedCategoryId(null);
    loadCategoryTree();
  };

  // ==================== 表格列 ====================

  const columns = [
    {
      title: '需求标题',
      dataIndex: 'title',
      key: 'title',
      width: 260,
      sorter: true,
      sortOrder: sortBy === 'title' ? (sortOrder as 'ascend' | 'descend') : undefined,
      render: (text: string, record: any) => (
        <a onClick={() => navigate(`/requirements/${record.id}`)} style={{ fontWeight: 500 }}>
          {text}
        </a>
      ),
    },
    {
      title: '模块分类',
      dataIndex: 'module',
      key: 'module',
      width: 200,
      sorter: true,
      ellipsis: true,
      sortOrder: sortBy === 'module' ? (sortOrder as 'ascend' | 'descend') : undefined,
      render: (m: string) => {
        // 将路径按 " > " 分割，每段一个 Tag
        if (!m || m === '未分类') return <Tag color="default">{m || '未分类'}</Tag>;
        const parts = m.split(' > ');
        if (parts.length <= 1) return <Tag>{m}</Tag>;
        return (
          <span style={{ fontSize: 12 }}>
            {parts.map((part, i) => (
              <span key={i}>
                {i > 0 && <span style={{ color: '#bbb', margin: '0 2px' }}>›</span>}
                <Tag style={{ margin: 0, fontSize: 11 }}>{part}</Tag>
              </span>
            ))}
          </span>
        );
      },
    },
    {
      title: '版本',
      dataIndex: 'version',
      key: 'version',
      width: 55,
      render: (v: number) => <span style={{ color: '#999' }}>v{v}</span>,
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      width: 160,
      sorter: true,
      sortOrder: sortBy === 'status' ? (sortOrder as 'ascend' | 'descend') : undefined,
      render: (s: string) => (
        <Tag color={statusColorMap[s] || 'default'}>{statusLabelMap[s] || s}</Tag>
      ),
    },
    {
      title: 'Feature ID',
      dataIndex: 'feature_id',
      key: 'feature_id',
      width: 200,
      ellipsis: true,
      render: (v: string) => v ? <Typography.Text code style={{ fontSize: 12 }}>{v}</Typography.Text> : '-',
    },
    {
      title: '创建时间',
      dataIndex: 'created_at',
      key: 'created_at',
      width: 160,
      render: (v: string) => v ? dayjs(v).format('YYYY-MM-DD HH:mm') : '-',
    },
    {
      title: '操作',
      key: 'actions',
      width: 240,
      fixed: 'right' as const,
      render: (_: any, record: any) => (
        <Space size="small">
          <Button size="small" type="link" onClick={() => navigate(`/requirements/${record.id}`)}>
            详情
          </Button>
          <Button size="small" type="link" onClick={() => handleEdit(record)}>
            编辑
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
          <Popconfirm title="确认删除？" onConfirm={() => handleDelete(record.id)}>
            <Button size="small" type="link" danger>删除</Button>
          </Popconfirm>
        </Space>
      ),
    },
  ];

  // ==================== 渲染 ====================

  return (
    <div style={{ display: 'flex', gap: 16, height: 'calc(100vh - 80px)' }}>
      {/* ====== 左侧分类树 ====== */}
      <Card
        size="small"
        title={<><FolderOutlined style={{ marginRight: 8 }} />需求分类</>}
        style={{ width: 240, flexShrink: 0, display: 'flex', flexDirection: 'column' }}
        bodyStyle={{ flex: 1, overflow: 'auto', padding: '8px 12px' }}
        extra={
          <Button size="small" type="link" onClick={() => handleCatAdd(null)}>
            新增
          </Button>
        }
      >
        {categoryTree.length === 0 ? (
          <div style={{ textAlign: 'center', padding: 20, color: '#999' }}>
            <Button type="dashed" icon={<PlusOutlined />} onClick={() => handleCatAdd(null)} block>
              创建根分类
            </Button>
          </div>
        ) : (
          <Tree
            showLine={{ showLeafIcon: false }}
            defaultExpandAll
            expandedKeys={treeExpandedKeys}
            onExpand={(keys) => setTreeExpandedKeys(keys as string[])}
            selectedKeys={selectedCategoryId ? [selectedCategoryId] : []}
            onSelect={handleCatSelect}
            treeData={getTreeSelectNodes()}
            titleRender={(node: any) => {
              const catNode = findCatNode(categoryTree, node.key as string);
              const count = catNode?.requirement_count;
              return (
                <div
                  style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', width: '100%' }}
                  onDoubleClick={() => {
                    if (selectedCategoryId === node.key) {
                      setSelectedCategoryId(null);
                    }
                  }}
                >
                  <span
                    style={{
                      overflow: 'hidden',
                      textOverflow: 'ellipsis',
                      whiteSpace: 'nowrap',
                      flex: 1,
                      cursor: 'pointer',
                    }}
                    title={String(node.title)}
                  >
                    {node.title}
                    {count !== undefined && count > 0 && (
                      <span style={{ color: '#185FA5', marginLeft: 4, fontSize: 11 }}>
                        ({count})
                      </span>
                    )}
                  </span>
                  <span style={{ flexShrink: 0, marginLeft: 4 }}>
                    <Button
                      size="small" type="link"
                      icon={<EditOutlined />}
                      onClick={(e) => { e.stopPropagation(); handleCatEdit(node.key as string); }}
                      style={{ padding: '0 2px', height: 20, fontSize: 11 }}
                    />
                    <Popconfirm
                      title="删除分类及其子分类？"
                      onConfirm={(e) => { e?.stopPropagation(); handleCatDelete(node.key as string); }}
                      onCancel={(e) => e?.stopPropagation()}
                    >
                      <Button
                        size="small" type="link" danger
                        icon={<DeleteOutlined />}
                        onClick={(e) => e.stopPropagation()}
                        style={{ padding: '0 2px', height: 20, fontSize: 11 }}
                      />
                    </Popconfirm>
                  </span>
                </div>
              );
            }}
          />
        )}
      </Card>

      {/* ====== 右侧内容区 ====== */}
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', minWidth: 0 }}>
        {/* 顶部标题栏 */}
        <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 16, alignItems: 'center' }}>
          <Space>
            <Typography.Title level={3} style={{ margin: 0 }}>需求管理</Typography.Title>
            {selectedCategoryId && (
              <Tag closable color="blue" onClose={() => setSelectedCategoryId(null)}>
                已按分类筛选
              </Tag>
            )}
          </Space>
          <Button type="primary" icon={<PlusOutlined />} onClick={() => setCreateOpen(true)}>
            新建需求
          </Button>
        </div>

        {/* 搜索栏 */}
        <Card size="small" style={{ marginBottom: 16 }}>
          <Row gutter={[16, 12]} align="middle">
            <Col flex="260px">
              <Input
                placeholder="搜索需求标题..."
                prefix={<SearchOutlined />}
                allowClear
                value={searchTitle}
                onChange={(e) => setSearchTitle(e.target.value)}
              />
            </Col>
            <Col flex="180px">
              <Select
                placeholder="筛选状态"
                allowClear
                style={{ width: '100%' }}
                value={searchStatus}
                onChange={(v) => setSearchStatus(v)}
                options={Object.entries(statusLabelMap).map(([value, label]) => ({ value, label }))}
              />
            </Col>
          </Row>
        </Card>

        {/* 需求表格 */}
        <Table
          columns={columns}
          dataSource={items}
          rowKey="id"
          loading={loading}
          size="small"
          pagination={{ pageSize: 20, showTotal: (total) => `共 ${total} 条` }}
          scroll={{ x: 1300 }}
          onChange={(pagination, filters, sorter: any) => {
            if (sorter.field) {
              setSortBy(sorter.field as string);
              setSortOrder(sorter.order || 'descend');
            }
          }}
        />
      </div>

      {/* ====== 新建需求弹窗 ====== */}
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
                  <Form.Item name="raw_text" label="需求文档" rules={[{ required: true, message: '请输入需求文档内容' }]}>
                    <Input.TextArea rows={12} placeholder="粘贴需求文档原文，系统将自动分析内容并归入分类树..." />
                  </Form.Item>
                  <div style={{ color: '#888', fontSize: 12, marginTop: -8, marginBottom: 8 }}>
                    <FileTextOutlined style={{ marginRight: 4 }} />
                    系统将根据需求内容自动分析业务领域并归入分类树，无需手动选择模块
                  </div>
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

      {/* ====== 编辑需求弹窗 ====== */}
      <Modal
        title="编辑需求"
        open={editOpen}
        onOk={handleEditSubmit}
        onCancel={() => { setEditOpen(false); editForm.resetFields(); setEditingId(null); }}
        width={700}
        confirmLoading={editLoading}
      >
        <Form form={editForm} layout="vertical">
          <Form.Item name="title" label="需求标题" rules={[{ required: true }]}>
            <Input placeholder="需求标题" />
          </Form.Item>
          <Form.Item name="module" label="所属模块" rules={[{ required: true }]}>
            <Select
              placeholder="选择或输入模块分类"
              showSearch
              allowClear
              options={getFlatCategoryOptions()}
              filterOption={(input, option) =>
                (option?.label ?? '').toLowerCase().includes(input.toLowerCase())
              }
            />
          </Form.Item>
          <Form.Item name="raw_text" label="需求文档内容">
            <Input.TextArea rows={12} placeholder="编辑需求文档内容..." />
          </Form.Item>
        </Form>
      </Modal>

      {/* ====== 分类管理弹窗 ====== */}
      <Modal
        title={catEditingId ? '编辑分类' : '新建分类'}
        open={catManageOpen}
        onOk={handleCatSubmit}
        onCancel={() => { setCatManageOpen(false); catForm.resetFields(); setCatEditingId(null); }}
        width={500}
      >
        <Form form={catForm} layout="vertical">
          <Form.Item name="name" label="分类名称" rules={[{ required: true, message: '请输入分类名称' }]}>
            <Input placeholder="如：订单管理" />
          </Form.Item>
          <Form.Item name="parent_id" label="父分类">
            <TreeSelect
              placeholder="留空为根分类"
              allowClear
              treeDefaultExpandAll
              treeData={getTreeSelectNodes()}
            />
          </Form.Item>
          <Form.Item name="sort_order" label="排序序号">
            <Input type="number" placeholder="数字越小越靠前，默认 0" />
          </Form.Item>
          <Form.Item name="description" label="描述">
            <Input.TextArea rows={2} placeholder="分类说明（可选）" />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
};

export default RequirementList;
