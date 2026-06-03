import { useState } from 'react'
import { Form, Input, Button, Card, Divider, Alert } from 'antd'
import { MailOutlined, LockOutlined } from '@ant-design/icons'
import { useNavigate, Link } from 'react-router-dom'
import { authApi } from '../api/client'
import { useAuthStore } from '../store/authStore'

export default function Login() {
  const [loading, setLoading] = useState(false)
  const [errorMsg, setErrorMsg] = useState<string | null>(null)
  const navigate = useNavigate()
  const { login } = useAuthStore()

  const handleLogin = async (values: { email: string; password: string }) => {
    setLoading(true)
    setErrorMsg(null)
    try {
      const res = await authApi.login(values.email, values.password)
      const { access_token } = res.data
      localStorage.setItem('token', access_token)
      const meRes = await authApi.me()
      login(access_token, meRes.data)
      navigate('/')
    } catch (e: any) {
      const detail = e.response?.data?.detail
      const msg = typeof detail === 'string'
        ? detail
        : `Ошибка ${e.response?.status ?? ''}: ${e.message}`
      setErrorMsg(msg)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div style={{
      minHeight: '100vh', background: 'var(--navy)', display: 'flex',
      alignItems: 'center', justifyContent: 'center', flexDirection: 'column', gap: 24
    }}>
      <div style={{ textAlign: 'center' }}>
        <div style={{ fontSize: 32, fontWeight: 700, color: '#fff', letterSpacing: -0.5 }}>
          Публикации<span style={{ color: 'var(--amber)' }}>НИИ</span>
        </div>
        <div style={{ color: 'rgba(255,255,255,0.55)', fontFamily: 'var(--mono)', fontSize: 11, letterSpacing: 3, marginTop: 4 }}>
          ФИЦ ИВТ · УПРАВЛЕНИЕ ПУБЛИКАЦИЯМИ
        </div>
      </div>

      <Card
        style={{ width: 400, border: '1px solid rgba(255,255,255,0.15)', background: 'rgba(255,255,255,0.06)', borderRadius: 10 }}
        styles={{ body: { padding: '32px 28px' } }}
      >
        <div style={{ color: '#fff', fontSize: 18, fontWeight: 600, marginBottom: 24 }}>Вход в систему</div>

        {errorMsg && (
          <Alert
            type="error"
            message={errorMsg}
            showIcon
            style={{ marginBottom: 16 }}
            closable
            onClose={() => setErrorMsg(null)}
          />
        )}

        <Form layout="vertical" onFinish={handleLogin} size="large">
          <Form.Item
            name="email"
            label={<span style={{ color: 'rgba(255,255,255,0.85)', fontSize: 13 }}>Email</span>}
            rules={[{ required: true, type: 'email', message: 'Введите корректный email' }]}
          >
            <Input
              prefix={<MailOutlined style={{ color: 'rgba(255,255,255,0.4)' }} />}
              placeholder="your@email.com"
              style={{ background: 'rgba(255,255,255,0.08)', border: '1px solid rgba(255,255,255,0.2)', color: '#fff' }}
            />
          </Form.Item>
          <Form.Item
            name="password"
            label={<span style={{ color: 'rgba(255,255,255,0.85)', fontSize: 13 }}>Пароль</span>}
            rules={[{ required: true, message: 'Введите пароль' }]}
          >
            <Input.Password
              prefix={<LockOutlined style={{ color: 'rgba(255,255,255,0.4)' }} />}
              placeholder="Пароль"
              style={{ background: 'rgba(255,255,255,0.08)', border: '1px solid rgba(255,255,255,0.2)', color: '#fff' }}
            />
          </Form.Item>
          <Button
            type="primary" htmlType="submit" block loading={loading}
            style={{ background: 'var(--amber)', border: 'none', color: '#000', fontWeight: 600, height: 44, marginTop: 4 }}
          >
            Войти
          </Button>
        </Form>

        <Divider style={{ borderColor: 'rgba(255,255,255,0.1)', margin: '20px 0' }} />
        <div style={{ textAlign: 'center', color: 'rgba(255,255,255,0.5)', fontSize: 13 }}>
          Нет аккаунта?{' '}
          <Link to="/register" style={{ color: 'var(--amber)' }}>Зарегистрироваться</Link>
        </div>
      </Card>
    </div>
  )
}
