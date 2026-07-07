import React from 'react';
import { Outlet, useNavigate, useLocation } from 'react-router-dom';
import { Layout, Menu, Typography } from 'antd';
import {
  DashboardOutlined,
  FileTextOutlined,
  ExperimentOutlined,
  BugOutlined,
  SettingOutlined,
} from '@ant-design/icons';

const { Header, Sider, Content } = Layout;

const menuItems = [
  { key: '/', icon: <DashboardOutlined />, label: '仪表盘' },
  { key: '/requirements', icon: <FileTextOutlined />, label: '需求管理' },
];

const MainLayout: React.FC = () => {
  const navigate = useNavigate();
  const location = useLocation();

  const selectedKey = '/' + location.pathname.split('/')[1];

  return (
    <Layout style={{ minHeight: '100vh' }}>
      <Sider
        width={220}
        style={{
          background: '#fff',
          borderRight: '1px solid #f0f0f0',
        }}
      >
        <div style={{
          height: 64,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          borderBottom: '1px solid #f0f0f0',
        }}>
          <Typography.Title level={4} style={{ margin: 0, color: '#185FA5' }}>
            <BugOutlined /> AI 测试平台
          </Typography.Title>
        </div>
        <Menu
          mode="inline"
          selectedKeys={[selectedKey]}
          items={menuItems}
          onClick={({ key }) => navigate(key)}
          style={{ borderRight: 0, marginTop: 8 }}
        />
      </Sider>
      <Layout>
        <Header style={{
          background: '#fff',
          padding: '0 24px',
          borderBottom: '1px solid #f0f0f0',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
        }}>
          <Typography.Text strong style={{ fontSize: 16 }}>
            Phase 1 MVP · 需求→用例自动化生成
          </Typography.Text>
          <Typography.Text type="secondary" style={{ fontSize: 13 }}>
            v0.1.0 · LLM: OpenAI/Claude/Qwen
          </Typography.Text>
        </Header>
        <Content style={{ margin: 16, padding: 24, background: '#fff', borderRadius: 8, minHeight: 360 }}>
          <Outlet />
        </Content>
      </Layout>
    </Layout>
  );
};

export default MainLayout;
