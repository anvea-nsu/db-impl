import { useState, useRef, useCallback } from 'react'
import { Layout, Menu, Button, Avatar, Dropdown, Upload, Modal, Tag, Alert, Typography } from 'antd'
import {
  BankOutlined, ReadOutlined, TeamOutlined, FileTextOutlined, BarChartOutlined,
  SettingOutlined, LogoutOutlined, UserOutlined, UploadOutlined, ImportOutlined,
  MenuFoldOutlined, MenuUnfoldOutlined, CheckCircleOutlined, CloseCircleOutlined,
  LoadingOutlined, LoginOutlined,
} from '@ant-design/icons'
import { useNavigate, useLocation, Outlet } from 'react-router-dom'
import { useAuthStore } from '../store/authStore'

const { Sider, Header, Content } = Layout

const menuItems = [
  { key: '/statistics',    icon: <BarChartOutlined />,  label: 'Статистика'  },
  { key: '/organizations', icon: <BankOutlined />,      label: 'Организации' },
  { key: '/journals',      icon: <ReadOutlined />,      label: 'Журналы'     },
  { key: '/authors',       icon: <TeamOutlined />,      label: 'Авторы'      },
  { key: '/articles',      icon: <FileTextOutlined />,  label: 'Публикации'  },
]

interface ImportState {
  running: boolean; done: boolean; success: boolean; exitCode: number | null; lines: string[]
}
const initImport = (): ImportState => ({ running: false, done: false, success: false, exitCode: null, lines: [] })

export default function AppLayout() {
  const navigate  = useNavigate()
  const location  = useLocation()
  const { user, isAdmin, logout } = useAuthStore()
  const [collapsed, setCollapsed]   = useState(false)
  const [modal, setModal]           = useState<'xml' | 'json' | null>(null)
  const [imp, setImp]               = useState<ImportState>(initImport())
  const [netErr, setNetErr]         = useState<string | null>(null)
  const logRef = useRef<HTMLDivElement>(null)

  const isLoggedIn = !!user

  const selectedKey = '/' + location.pathname.split('/')[1]
  const navItems = [
    ...menuItems,
    ...(isAdmin() ? [{ key: '/admin', icon: <SettingOutlined />, label: 'Админка' }] : []),
  ]

  const openModal = (type: 'xml' | 'json') => { setModal(type); setImp(initImport()); setNetErr(null) }

  const scrollBottom = useCallback(() => {
    if (logRef.current) logRef.current.scrollTop = logRef.current.scrollHeight
  }, [])

  const handleImport = async (file: File, type: 'xml' | 'json') => {
    setImp({ running: true, done: false, success: false, exitCode: null, lines: [] })
    setNetErr(null)
    const fd = new FormData()
    fd.append('file', file)
    const token = localStorage.getItem('token') || ''
    let response: Response
    try {
      response = await fetch(`/api/import/${type}/stream`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${token}` },
        body: fd,
      })
    } catch (e: any) {
      setNetErr(`Ошибка сети: ${e.message}`)
      setImp(s => ({ ...s, running: false }))
      return
    }
    if (!response.ok) {
      let msg = `HTTP ${response.status}`
      try { const j = await response.json(); msg = j.detail || msg } catch {}
      setNetErr(msg)
      setImp(s => ({ ...s, running: false }))
      return
    }
    const reader = response.body!.getReader()
    const dec = new TextDecoder()
    let buf = ''
    const flush = (chunk: string) => {
      buf += chunk
      const parts = buf.split('\n')
      buf = parts.pop()!
      for (const raw of parts) {
        if (!raw.startsWith('data: ')) continue
        try {
          const obj = JSON.parse(raw.slice(6))
          if (obj.line !== undefined) {
            setImp(s => ({ ...s, lines: [...s.lines, obj.line] }))
            setTimeout(scrollBottom, 10)
          }
          if (obj.done) {
            setImp(s => ({ ...s, running: false, done: true, success: obj.code === 0, exitCode: obj.code }))
          }
        } catch {}
      }
    }
    try {
      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        flush(dec.decode(value, { stream: true }))
      }
      flush(dec.decode())
    } catch (e: any) {
      setNetErr(`Ошибка чтения потока: ${e.message}`)
      setImp(s => ({ ...s, running: false }))
    }
    return false
  }

  const userMenu = { items: [{ key: 'out', icon: <LogoutOutlined />, label: 'Выйти',
    onClick: () => { logout(); navigate('/login') } }] }

  return (
    <Layout style={{ minHeight: '100vh' }}>
      <Sider collapsible collapsed={collapsed} onCollapse={setCollapsed} trigger={null}
        width={220} style={{ background:'var(--navy)', position:'fixed', height:'100vh', left:0, top:0, zIndex:100 }}>

        <div style={{ height:64, display:'flex', alignItems:'center',
          justifyContent: collapsed ? 'center' : 'flex-start',
          padding: collapsed ? 0 : '0 20px',
          borderBottom:'1px solid rgba(255,255,255,0.08)' }}>
          {collapsed
            ? <span style={{ color:'var(--amber)', fontFamily:'var(--mono)', fontWeight:700, fontSize:16 }}>Π</span>
            : <div>
                <div style={{ color:'#fff', fontWeight:700, fontSize:15 }}>ПубликацииНИИ</div>
                <div style={{ color:'var(--slate)', fontSize:10, fontFamily:'var(--mono)', letterSpacing:1 }}>ФИЦ ИВТ</div>
              </div>}
        </div>

        <Menu theme="dark" mode="inline" selectedKeys={[selectedKey]}
          onClick={({ key }) => navigate(key)}
          style={{ background:'transparent', border:'none', marginTop:8 }}
          items={navItems} />

        {isAdmin() && !collapsed && (
          <div style={{ position:'absolute', bottom:80, left:0, right:0, padding:'0 12px' }}>
            <div style={{ borderTop:'1px solid rgba(255,255,255,0.08)', paddingTop:12, display:'flex', flexDirection:'column', gap:6 }}>
              {(['xml','json'] as const).map(t => (
                <Button key={t} size="small" block icon={<ImportOutlined />}
                  style={{ background:'rgba(232,168,56,0.1)', border:'1px solid rgba(232,168,56,0.3)', color:'var(--amber)', fontSize:12 }}
                  onClick={() => openModal(t)}>
                  Импорт {t.toUpperCase()}
                </Button>
              ))}
            </div>
          </div>
        )}

        <div style={{ position:'absolute', bottom:0, left:0, right:0, height:48,
          display:'flex', alignItems:'center', justifyContent:'center',
          borderTop:'1px solid rgba(255,255,255,0.08)', cursor:'pointer', color:'var(--slate)', fontSize:16 }}
          onClick={() => setCollapsed(!collapsed)}>
          {collapsed ? <MenuUnfoldOutlined /> : <MenuFoldOutlined />}
        </div>
      </Sider>

      <Layout style={{ marginLeft: collapsed ? 80 : 220, transition:'margin 0.2s' }}>
        <Header style={{ background:'#fff', padding:'0 24px', borderBottom:'1px solid var(--border)',
          display:'flex', alignItems:'center', justifyContent:'flex-end', gap:16, height:56 }}>
          {isLoggedIn ? (
            <>
              {isAdmin() && <Tag color="gold" style={{ fontFamily:'var(--mono)', fontSize:11 }}>ADMIN</Tag>}
              <Dropdown menu={userMenu}>
                <div style={{ cursor:'pointer', display:'flex', alignItems:'center', gap:8 }}>
                  <Avatar size={30} icon={<UserOutlined />} style={{ background:'var(--navy)' }} />
                  <span style={{ fontSize:13, color:'var(--text-muted)' }}>{user?.username || user?.email}</span>
                </div>
              </Dropdown>
            </>
          ) : (
            <Button
              icon={<LoginOutlined />}
              onClick={() => navigate('/login')}
              style={{ background:'var(--navy)', color:'#fff', border:'none', fontWeight:500 }}>
              Войти
            </Button>
          )}
        </Header>
        <Content style={{ padding:'24px', minHeight:'calc(100vh - 56px)' }}><Outlet /></Content>
      </Layout>

      <Modal
        title={<span><ImportOutlined style={{ marginRight:8 }} />
          {modal === 'xml' ? 'Импорт публикаций из XML (eLibrary)' : 'Импорт журналов из JSON'}
        </span>}
        open={!!modal} width={760} footer={null} destroyOnClose
        onCancel={() => { if (!imp.running) { setModal(null); setImp(initImport()) } }}>

        {!imp.running && !imp.done && !netErr && (
          <Upload.Dragger accept={modal === 'xml' ? '.xml' : '.json'}
            beforeUpload={f => { handleImport(f, modal!); return false }}
            showUploadList={false} style={{ marginBottom:16 }}>
            <p style={{ fontSize:28, color:'var(--amber)', marginBottom:8 }}><UploadOutlined /></p>
            <p style={{ fontWeight:600 }}>Перетащите файл или нажмите для выбора</p>
            <p style={{ color:'var(--text-muted)', fontSize:12, marginTop:4 }}>
              {modal === 'xml' ? 'XML из eLibrary' : 'JSON с journalrank.rcsi.science'} · без ограничения размера
            </p>
          </Upload.Dragger>
        )}

        {netErr && (
          <div>
            <Alert type="error" showIcon icon={<CloseCircleOutlined />}
              message="Ошибка соединения" description={netErr} style={{ marginBottom:12 }} />
            <Button onClick={() => { setNetErr(null); setImp(initImport()) }}>← Попробовать снова</Button>
          </div>
        )}

        {(imp.running || imp.done) && (
          <div>
            <div style={{ display:'flex', alignItems:'center', gap:10, marginBottom:10 }}>
              {imp.running
                ? <><LoadingOutlined style={{ color:'var(--amber)' }} />
                    <span style={{ fontFamily:'var(--mono)', fontSize:12, color:'var(--text-muted)' }}>
                      Выполняется… получено строк: {imp.lines.length}
                    </span></>
                : imp.success
                  ? <><CheckCircleOutlined style={{ color:'#52c41a', fontSize:16 }} />
                      <span style={{ fontFamily:'var(--mono)', fontSize:13, color:'#52c41a', fontWeight:600 }}>
                        Импорт завершён успешно
                      </span></>
                  : <><CloseCircleOutlined style={{ color:'#ff4d4f', fontSize:16 }} />
                      <span style={{ fontFamily:'var(--mono)', fontSize:13, color:'#ff4d4f', fontWeight:600 }}>
                        Ошибка (код {imp.exitCode})
                      </span></>
              }
            </div>
            <div ref={logRef} className="log-output"
              style={{ height:380, overflowY:'auto', fontSize:11, lineHeight:1.6 }}>
              {imp.lines.map((l, i) => (
                <div key={i} style={{
                  color: l.includes('[ERROR]') || l.includes('Error') || l.includes('Traceback') ? '#ff8080'
                       : l.includes('[WARNING]') ? '#ffd080'
                       : l.includes('+') ? '#80ff9f'
                       : '#a8d8a0'
                }}>{l}</div>
              ))}
              {imp.running && (
                <div style={{ color:'rgba(168,216,160,0.4)', animation:'pulse 1s infinite' }}>▌</div>
              )}
            </div>
            {imp.done && (
              <div style={{ marginTop:10 }}>
                <Button onClick={() => { setImp(initImport()) }}>← Импортировать ещё</Button>
              </div>
            )}
          </div>
        )}
      </Modal>
    </Layout>
  )
}
