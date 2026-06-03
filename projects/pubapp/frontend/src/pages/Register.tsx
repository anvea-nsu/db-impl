import { useState } from 'react'
import { Form, Input, Button, Card, message, Divider, Alert } from 'antd'
import { UserOutlined, LockOutlined, MailOutlined } from '@ant-design/icons'
import { useNavigate, Link } from 'react-router-dom'
import { authApi } from '../api/client'

export default function Register() {
  const [loading, setLoading] = useState(false)
  const [errorMsg, setErrorMsg] = useState<string | null>(null)
  const navigate = useNavigate()

  const onFinish = async (values: { username?: string; email: string; password: string }) => {
    setLoading(true)
    setErrorMsg(null)
    try {
      await authApi.register(values)
      message.success('Аккаунт создан! Войдите в систему.')
      navigate('/login')
    } catch (e: any) {
      const detail = e.response?.data?.detail
      const msg = typeof detail === 'string'
        ? detail
        : Array.isArray(detail)
          ? detail.map((d: any) => d.msg || JSON.stringify(d)).join('; ')
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
        style={{ width: 420, border: '1px solid rgba(255,255,255,0.15)', background: 'rgba(255,255,255,0.06)', borderRadius: 10 }}
        styles={{ body: { padding: '32px 28px' } }}
      >
        <div style={{ color: '#fff', fontSize: 18, fontWeight: 600, marginBottom: 6 }}>Регистрация</div>
        <div style={{ color: 'rgba(255,255,255,0.45)', fontSize: 12, fontFamily: 'var(--mono)', marginBottom: 24 }}>
          Первый зарегистрированный пользователь получает роль admin
        </div>

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

        <Form layout="vertical" onFinish={onFinish} size="large">
          <Form.Item
            name="email"
            label={<span style={{ color: 'rgba(255,255,255,0.85)', fontSize: 13 }}>Email <span style={{ color: 'rgba(255,255,255,0.45)', fontSize:11 }}>(используется для входа)</span></span>}
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
            rules={[{ required: true, min: 6, message: 'Минимум 6 символов' }]}
          >
            <Input.Password
              prefix={<LockOutlined style={{ color: 'rgba(255,255,255,0.4)' }} />}
              placeholder="Минимум 6 символов"
              style={{ background: 'rgba(255,255,255,0.08)', border: '1px solid rgba(255,255,255,0.2)', color: '#fff' }}
            />
          </Form.Item>

          <Form.Item
            name="username"
            label={<span style={{ color: 'rgba(255,255,255,0.85)', fontSize: 13 }}>Имя пользователя <span style={{ color: 'rgba(255,255,255,0.45)', fontSize:11 }}>(необязательно)</span></span>}
            rules={[{ max: 100, message: 'Максимум 100 символов' }]}
          >
            <Input
              prefix={<UserOutlined style={{ color: 'rgba(255,255,255,0.4)' }} />}
              placeholder="Отображаемое имя (любая строка)"
              style={{ background: 'rgba(255,255,255,0.08)', border: '1px solid rgba(255,255,255,0.2)', color: '#fff' }}
            />
          </Form.Item>

          <Button
            type="primary" htmlType="submit" block loading={loading}
            style={{ background: 'var(--amber)', border: 'none', color: '#000', fontWeight: 600, height: 44, marginTop: 4 }}
          >
            Создать аккаунт
          </Button>
        </Form>

        <Divider style={{ borderColor: 'rgba(255,255,255,0.1)', margin: '20px 0' }} />
        <div style={{ textAlign: 'center', color: 'rgba(255,255,255,0.5)', fontSize: 13 }}>
          Уже есть аккаунт?{' '}
          <Link to="/login" style={{ color: 'var(--amber)' }}>Войти</Link>
        </div>
      </Card>
    </div>
  )
}
