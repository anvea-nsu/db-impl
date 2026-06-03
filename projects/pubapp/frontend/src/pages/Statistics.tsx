import { useState, useEffect, useRef } from 'react'
import { Row, Col, Card, Button, Select, Spin, Input, InputNumber, Collapse, Tag } from 'antd'
import { BarChartOutlined, FilterOutlined, SearchOutlined } from '@ant-design/icons'
import { statsApi } from '../api/client'

// Normalise DB names for display
function normName(n: string): string {
  if (/web of science/i.test(n)) return 'WoS'
  if (/white\s*list/i.test(n)) return n.replace(/white\s*list/gi, 'Белый список')
  return n
}

interface StatCardProps { label: string; value: number; color?: string; sub?: React.ReactNode }
function StatCard({ label, value, color, sub }: StatCardProps) {
  return (
    <div style={{
      background: '#fff', border: '1px solid var(--border)', borderRadius: 8,
      padding: '14px 16px', borderTop: color ? `3px solid ${color}` : undefined,
    }}>
      <div style={{ fontSize: 11, color: 'var(--text-muted)', marginBottom: 4, fontWeight: 600, textTransform: 'uppercase', letterSpacing: 0.5 }}>{label}</div>
      <div style={{ fontSize: 32, fontWeight: 700, color: color || 'var(--navy)', fontFamily: 'var(--mono)' }}>{value}</div>
      {sub && <div style={{ marginTop: 6 }}>{sub}</div>}
    </div>
  )
}

function QuartileBadges({ q }: { q: { q1: number; q2: number; q3: number; q4: number } }) {
  return (
    <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginTop: 4 }}>
      {([1, 2, 3, 4] as const).map(n => (
        q[`q${n}`] > 0 &&
        <span key={n} className={`tag-q${n}`} style={{ fontSize: 11, padding: '1px 6px' }}>
          Q{n}: {q[`q${n}`]}
        </span>
      ))}
    </div>
  )
}

export default function Statistics() {
  const [stats, setStats]               = useState<any>(null)
  const [loading, setLoading]           = useState(false)
  const [validSupport, setValidSupport] = useState<string | undefined>()
  const [projectNumber, setProjectNumber] = useState<number | undefined>()
  const [yearFrom, setYearFrom]         = useState<number | undefined>()
  const [yearTo, setYearTo]             = useState<number | undefined>()
  const [wlName, setWlName]             = useState<string | undefined>()
  const [wlOptions, setWlOptions]       = useState<{ value: string; label: string }[]>([])
  const [wlLoaded, setWlLoaded]         = useState(false)

  // Org autocomplete
  const [orgQuery, setOrgQuery]         = useState('')
  const [orgOptions, setOrgOptions]     = useState<{ org_id: number; orgname: string }[]>([])
  const [orgSearching, setOrgSearching] = useState(false)
  const orgTimer = useRef<ReturnType<typeof setTimeout>>()

  useEffect(() => {
    statsApi.availableDbs()
      .then(r => {
        const wls: string[] = (r.data as string[]).filter((n: string) => /list/i.test(n) || /белый список/i.test(n)).sort()
        setWlOptions(wls.map(n => ({ value: n, label: normName(n) })))
      })
      .catch(() => {})
      .finally(() => setWlLoaded(true))
  }, [])

  const searchOrg = (q: string) => {
    setOrgQuery(q)
    clearTimeout(orgTimer.current)
    if (q.length < 2) { setOrgOptions([]); return }
    orgTimer.current = setTimeout(async () => {
      setOrgSearching(true)
      try {
        const r = await statsApi.orgSearch(q)
        setOrgOptions(r.data)
      } catch {/**/ } finally { setOrgSearching(false) }
    }, 300)
  }

  const fetchStats = async () => {
    setLoading(true)
    try {
      const params: Record<string, unknown> = {}
      if (wlName) params.whitelist_name = wlName
      if (orgQuery.length >= 2) params.org_search = orgQuery
      if (validSupport) params.valid_support = validSupport
      if (projectNumber) params.project_number = projectNumber
      if (yearFrom) params.year_from = yearFrom
      if (yearTo) params.year_to = yearTo
      const res = await statsApi.overview(params)
      setStats(res.data)
    } catch {/**/ } finally { setLoading(false) }
  }

  const whitelists: Record<string, number> = stats?.whitelists || {}
  const wlQuartiles: Record<string, { q1: number; q2: number; q3: number; q4: number }> = stats?.whitelist_quartiles || {}

  return (
    <div>
      <div className="page-header">
        <div>
          <div className="page-title"><BarChartOutlined style={{ marginRight: 8, color: 'var(--amber-dim)' }} />Общая статистика</div>
          <div className="page-subtitle">Агрегированные показатели публикационной активности</div>
        </div>
      </div>

      <Card size="small" style={{ marginBottom: 24, border: '1px solid var(--border)' }}
        title={<span style={{ fontSize: 13, color: 'var(--text-muted)' }}><FilterOutlined /> Фильтры</span>}>
        <Row gutter={[12, 12]} align="bottom">
          <Col>
            <div style={{ fontSize: 11, color: 'var(--text-muted)', marginBottom: 4 }}>Год от</div>
            <InputNumber placeholder="напр. 2020" style={{ width: 120 }} value={yearFrom} onChange={v => setYearFrom(v || undefined)} />
          </Col>
          <Col>
            <div style={{ fontSize: 11, color: 'var(--text-muted)', marginBottom: 4 }}>Год до</div>
            <InputNumber placeholder="напр. 2024" style={{ width: 120 }} value={yearTo} onChange={v => setYearTo(v || undefined)} />
          </Col>
          <Col>
            <div style={{ fontSize: 11, color: 'var(--text-muted)', marginBottom: 4 }}>Подтверждение поддержки</div>
            <Select allowClear placeholder="Любое" value={validSupport} onChange={setValidSupport} style={{ width: 190 }}
              options={[
                { value: 'true',  label: '✓ Подтверждена' },
                { value: 'false', label: '✗ Не подтверждена' },
                { value: 'null',  label: '— Не указано' },
              ]} />
          </Col>
          <Col>
            <div style={{ fontSize: 11, color: 'var(--text-muted)', marginBottom: 4 }}>Номер темы</div>
            <InputNumber placeholder="1–100" style={{ width: 110 }} min={1} max={100} value={projectNumber} onChange={v => setProjectNumber(v || undefined)} />
          </Col>
          <Col>
            <div style={{ fontSize: 11, color: 'var(--text-muted)', marginBottom: 4 }}>Организация (для КБПР)</div>
            <div style={{ position: 'relative' }}>
              <Input
                placeholder="Введите название…"
                value={orgQuery}
                onChange={e => searchOrg(e.target.value)}
                suffix={orgSearching ? <Spin size="small" /> : <SearchOutlined style={{ color: 'var(--text-muted)' }} />}
                style={{ width: 280 }}
              />
              {orgOptions.length > 0 && (
                <div style={{
                  position: 'absolute', top: '100%', left: 0, right: 0, zIndex: 100,
                  background: '#fff', border: '1px solid var(--border)', borderRadius: 6,
                  boxShadow: '0 4px 16px rgba(0,0,0,0.12)', maxHeight: 220, overflowY: 'auto',
                }}>
                  {orgOptions.map(o => (
                    <div key={o.org_id}
                      style={{ padding: '8px 12px', cursor: 'pointer', fontSize: 13, borderBottom: '1px solid var(--border)' }}
                      onMouseDown={() => { setOrgQuery(o.orgname); setOrgOptions([]) }}
                    >
                      {o.orgname}
                    </div>
                  ))}
                </div>
              )}
            </div>
          </Col>
          <Col>
            <div style={{ fontSize: 11, color: 'var(--text-muted)', marginBottom: 4 }}>Белый список (для КБПР)</div>
            {!wlLoaded
              ? <Select disabled placeholder="Загрузка…" style={{ width: 240 }} />
              : <Select
                  value={wlName ?? '__best__'}
                  onChange={v => setWlName(v === '__best__' ? undefined : v)}
                  style={{ width: 240 }}
                  options={[
                    { value: '__best__', label: '★ Лучший квартиль (все списки)' },
                    ...wlOptions,
                  ]}
                />
            }
          </Col>
          <Col>
            <div style={{ fontSize: 11, color: 'var(--text-muted)', marginBottom: 4 }}>&nbsp;</div>
            <Button type="primary" loading={loading} onClick={fetchStats}
              style={{ background: 'var(--navy)', fontWeight: 600 }}>
              Рассчитать
            </Button>
          </Col>
        </Row>
      </Card>

      {loading && <div style={{ textAlign: 'center', padding: 60 }}><Spin size="large" /></div>}

      {stats && !loading && (<>
        {/* КБПР hero card */}
        <Card style={{ marginBottom: 24, background: 'var(--navy)', border: 'none', borderRadius: 10 }}>
          <Row gutter={24} align="middle">
            <Col flex="1">
              <div style={{ color: 'rgba(255,255,255,0.5)', fontSize: 11, fontFamily: 'var(--mono)', letterSpacing: 2, textTransform: 'uppercase' }}>
                Суммарный КБПР
              </div>
              <div style={{ color: 'rgba(255,255,255,0.65)', fontSize: 12, margin: '3px 0 6px' }}>
                {stats.kbpr_mode === 'best_across_all'
                  ? '★ Лучший квартиль по всем Белым спискам'
                  : normName(stats.kbpr_whitelist || '')}
                {stats.org_name && <span style={{ marginLeft: 8, opacity: 0.7 }}>· {stats.org_name}</span>}
              </div>
              <div style={{ fontSize: 52, fontWeight: 700, color: 'var(--amber)', fontFamily: 'var(--mono)', lineHeight: 1 }}>
                {(stats.total_kbpr || 0).toFixed(4)}
              </div>
            </Col>
            <Col>
              <div style={{ textAlign: 'center', padding: '0 24px' }}>
                <div style={{ color: 'rgba(255,255,255,0.5)', fontSize: 11, fontFamily: 'var(--mono)', letterSpacing: 1 }}>ИТОГО</div>
                <div style={{ fontSize: 56, fontWeight: 700, color: '#fff', fontFamily: 'var(--mono)', lineHeight: 1 }}>{stats.total}</div>
                <div style={{ color: 'rgba(255,255,255,0.4)', fontSize: 12 }}>публикаций</div>
              </div>
            </Col>
          </Row>
        </Card>

        {/* Per-DB counts with quartiles */}
        <div style={{ marginBottom: 8, fontWeight: 600, color: 'var(--text-muted)', fontSize: 12, textTransform: 'uppercase', letterSpacing: 1, fontFamily: 'var(--mono)' }}>
          По базам данных
        </div>
        <Row gutter={[12, 12]} style={{ marginBottom: 24 }}>
          <Col xs={12} sm={8} md={6}>
            <StatCard label="WoS" value={stats.wos} color="#1565c0"
              sub={stats.wos_quartiles && <QuartileBadges q={stats.wos_quartiles} />} />
          </Col>
          <Col xs={12} sm={8} md={6}>
            <StatCard label="Scopus" value={stats.scopus} color="#2e7d32"
              sub={stats.scp_quartiles && <QuartileBadges q={stats.scp_quartiles} />} />
          </Col>
          <Col xs={12} sm={8} md={6}>
            <StatCard label="ВАК" value={stats.vak} color="#6a1b9a" />
          </Col>
          <Col xs={12} sm={8} md={6}>
            <StatCard label="РИНЦ" value={stats.risc} color="#37474f" />
          </Col>
          {Object.entries(whitelists).map(([name, val]) => (
            <Col key={name} xs={12} sm={8} md={6}>
              <StatCard label={normName(name)} value={val as number} color="#b71c1c"
                sub={wlQuartiles[name] && <QuartileBadges q={wlQuartiles[name]} />} />
            </Col>
          ))}
        </Row>
      </>)}

      {!stats && !loading && (
        <div style={{ textAlign: 'center', padding: 80, color: 'var(--text-muted)' }}>
          <BarChartOutlined style={{ fontSize: 48, opacity: 0.2, display: 'block', marginBottom: 16 }} />
          <div>Настройте фильтры и нажмите «Рассчитать»</div>
        </div>
      )}
    </div>
  )
}
