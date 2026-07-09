import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { Form, Input, Button, Card, Typography, message, Space } from 'antd';
import { UserOutlined, LockOutlined, BugOutlined } from '@ant-design/icons';
import { useAuth } from '../contexts/AuthContext';

const { Title, Text } = Typography;

const Login: React.FC = () => {
  const { login, register, token } = useAuth();
  const navigate = useNavigate();
  const [loading, setLoading] = useState(false);
  const [isLogin, setIsLogin] = useState(true);
  const [loginForm] = Form.useForm();
  const [registerForm] = Form.useForm();

  // Token 更新后再跳转，避免状态未同步导致 ProtectedRoute 拦截
  useEffect(() => {
    if (token) {
      navigate('/', { replace: true });
    }
  }, [token, navigate]);

  const handleLogin = async () => {
    try {
      const values = await loginForm.validateFields();
      setLoading(true);
      await login(values.username, values.password);
      message.success('登录成功');
    } catch (e: any) {
      if (e.errorFields) return; // 表单验证错误
      message.error(e.response?.data?.detail || '登录失败，请检查用户名和密码');
    } finally {
      setLoading(false);
    }
  };

  const handleRegister = async () => {
    try {
      const values = await registerForm.validateFields();
      if (values.password !== values.confirmPassword) {
        message.error('两次密码不一致');
        return;
      }
      setLoading(true);
      await register(values.username, values.password, values.username);
      message.success('注册成功，已自动登录');
    } catch (e: any) {
      if (e.errorFields) return; // 表单验证错误
      message.error(e.response?.data?.detail || '注册失败');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div
      style={{
        minHeight: '100vh',
        display: 'flex',
        justifyContent: 'center',
        alignItems: 'center',
        background: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)',
      }}
    >
      <Card
        style={{
          width: 420,
          borderRadius: 12,
          boxShadow: '0 20px 60px rgba(0,0,0,0.3)',
        }}
      >
        <div style={{ textAlign: 'center', marginBottom: 24 }}>
          <BugOutlined style={{ fontSize: 48, color: '#185FA5' }} />
          <Title level={3} style={{ marginTop: 12, marginBottom: 4, color: '#185FA5' }}>
            AI 测试平台
          </Title>
          <Text type="secondary">需求 → 用例自动化生成系统</Text>
        </div>

        {/* 切换按钮 */}
        <div style={{ textAlign: 'center', marginBottom: 20 }}>
          <Space size="large">
            <Button
              type={isLogin ? 'primary' : 'default'}
              onClick={() => { setIsLogin(true); loginForm.resetFields(); }}
            >
              登录
            </Button>
            <Button
              type={!isLogin ? 'primary' : 'default'}
              onClick={() => { setIsLogin(false); registerForm.resetFields(); }}
            >
              注册
            </Button>
          </Space>
        </div>

        {/* 登录表单 */}
        {isLogin && (
          <Form form={loginForm} size="large" autoComplete="off" layout="vertical">
            <Form.Item
              name="username"
              rules={[{ required: true, message: '请输入用户名' }]}
            >
              <Input prefix={<UserOutlined />} placeholder="用户名" />
            </Form.Item>
            <Form.Item
              name="password"
              rules={[{ required: true, message: '请输入密码' }]}
            >
              <Input.Password prefix={<LockOutlined />} placeholder="密码" />
            </Form.Item>
            <Form.Item>
              <Button type="primary" block loading={loading} onClick={handleLogin}>
                登 录
              </Button>
            </Form.Item>
          </Form>
        )}

        {/* 注册表单 */}
        {!isLogin && (
          <Form form={registerForm} size="large" autoComplete="off" layout="vertical">
            <Form.Item
              name="username"
              rules={[{ required: true, message: '请输入用户名' }]}
            >
              <Input prefix={<UserOutlined />} placeholder="用户名" />
            </Form.Item>
            <Form.Item
              name="password"
              rules={[
                { required: true, message: '请输入密码' },
                { min: 6, message: '密码至少6个字符' },
              ]}
            >
              <Input.Password prefix={<LockOutlined />} placeholder="密码" />
            </Form.Item>
            <Form.Item
              name="confirmPassword"
              rules={[
                { required: true, message: '请确认密码' },
                ({ getFieldValue }) => ({
                  validator(_, value) {
                    if (!value || getFieldValue('password') === value) {
                      return Promise.resolve();
                    }
                    return Promise.reject(new Error('两次密码不一致'));
                  },
                }),
              ]}
            >
              <Input.Password prefix={<LockOutlined />} placeholder="确认密码" />
            </Form.Item>
            <Form.Item>
              <Button type="primary" block loading={loading} onClick={handleRegister}>
                注 册
              </Button>
            </Form.Item>
          </Form>
        )}
      </Card>
    </div>
  );
};

export default Login;
