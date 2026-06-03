import { useState, useEffect, useCallback, useRef } from 'react'
import { Table, Input, Button, Checkbox, Drawer, Divider, Spin, Tag, Typography, InputNumber } from 'antd'
import { SearchOutlined, TeamOutlined, BarChartOutlined } from '@ant-design/icons'
import { authorsApi, authorsOrgSearch, statsApi } from '../api/client'
import type { Author } from '../types'

const { Text } = Typography
const PAGE_SIZE = 50

function StatRow({ label, value, hl }: { label: string; value: number; hl?: boolean }) {
  return (
    <div style={{ display: 'flex', justifyContent: 'space-between', padding: '5px 0', borderBottom: '1px solid var(--border)' }}>
      <span style={{ color: 'var(--text-muted)', fontSize: 13 }}>{label}</span>
      <span style={{ fontFamily: 'var(--mono)', fontWeight: hl ? 700 : 400, fontSize: 14, color: hl ? 'var(--navy)' : undefined }}>{value}</span>
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

function normName(n: string): string {
  if (/web of science/i.test(n)) return 'WoS'
  if (/white\s*list/i.test(n)) return n.replace(/white\s*list/gi, 'Белый список')
  return n
}

export default function Authors() {
  const [authors, setAuthors]   = useState<Author[]>([])
  const [total, setTotal]       = useState(0)
  const [loading, setLoading]   = useState(false)
  const [search, setSearch]     = useState('')
  const [page, setPage]         = useState(1)

  // Whitelist DBs for КБПР selector
  const [wlDbs, setWlDbs]         = useState<string[]>([])
  const [wlDbsLoaded, setWlLoaded] = useState(false)

  // kbprWlYear: 0 = best across all; >0 = specific year
  const [kbprWlYear, setKbprWlYear] = useState(0)

  // Drawer state
  const [drawerOpen, setDrawerOpen]     = useState(false)
  const [selAuthor, setSelAuthor]       = useState<Author | null>(null)
  const [activity, setActivity]         = useState<any>(null)
  const [actFiltered, setActFiltered]   = useState<any>(null)
  const [invalidCount, setInvalidCount] = useState<number | null>(null)
  const [kbpr, setKbpr]                 = useState<any>(null)
  const [statsLoading, setStatsLoading] = useState(false)

  // Drawer-level filters (year range + org search)
  const [drawerYearFrom, setDYF]   = useState<number | undefined>()
  const [drawerYearTo, setDYT]     = useState<number | undefined>()
  const [orgQuery, setOrgQuery]     = useState('')
  const [orgOptions, setOrgOptions] = useState<{ org_id: number; orgname: string }[]>([])
  const [orgSearching, setOrgS]     = useState(false)
  const orgTimer = useRef<ReturnType<typeof setTimeout>>()

  useEffect(() => {
    statsApi.availableDbs()
      .then(r => {
        const wls: string[] = (r.data as string[]).filter((n: string) => /list/i.test(n) || /белый список/i.test(n)).sort()
        setWlDbs(wls)
      })
      .catch(() => {})
      .finally(() => setWlLoaded(true))
  }, [])

  const fetchAuthors = useCallback(async (s: string, p: number) => {
    setLoading(true)
    try {
      const res = await authorsApi.list({ search: s || undefined, skip: (p - 1) * PAGE_SIZE, limit: PAGE_SIZE })
      setAuthors(res.data.items); setTotal(res.data.total)
    } catch {/**/ } finally { setLoading(false) }
  }, [])

  useEffect(() => { fetchAuthors('', 1) }, [fetchAuthors])

  const searchOrg = (q: string) => {
    setOrgQuery(q)
    clearTimeout(orgTimer.current)
    if (q.length < 2) { setOrgOptions([]); return }
    orgTimer.current = setTimeout(async () => {
      setOrgS(true)
      try { const r = await authorsOrgSearch(q); setOrgOptions(r.data) }
      catch {/**/ } finally { setOrgS(false) }
    }, 300)
  }

  const loadStats = async (author: Author, yf?: number, yt?: number, orgQ?: string, wlYr?: number) => {
    setStatsLoading(true)
    setActivity(null); setActFiltered(null); setInvalidCount(null); setKbpr(null)
    const p: Record<string, unknown> = {}
    if (yf) p.year_from = yf
    if (yt) p.year_to = yt
    const kbprP: Record<string, unknown> = { ...p }
    if (orgQ && orgQ.length >= 2) kbprP.org_search = orgQ
    // Whitelist for КБПР
    const eff = wlYr ?? kbprWlYear
    if (eff > 0) {
      const found = wlDbs.find(n => n.match(/\d{4}/)?.[0] === String(eff))
      if (found) kbprP.whitelist_name = found
    }
    try {
      const [a, af, inv, k] = await Promise.all([
        authorsApi.activity(author.author_id, p),
        authorsApi.activity(author.author_id, { ...p, valid_support: 'true' }),
        authorsApi.invalidSupportCount(author.author_id, p),
        authorsApi.kbpr(author.author_id, kbprP),
      ])
      setActivity(a.data); setActFiltered(af.data)
      setInvalidCount(inv.data.count); setKbpr(k.data)
    } catch {/**/ } finally { setStatsLoading(false) }
  }

  const openDrawer = (author: Author) => {
    setSelAuthor(author); setDrawerOpen(true)
    setDYF(undefined); setDYT(undefined); setOrgQuery(''); setOrgOptions([])
    loadStats(author, undefined, undefined, '', 0)
  }

  const handleWlChange = async (selectedName: string) => {
    const isBest = selectedName === '__best__'
    const yr = isBest ? 0 : (parseInt(selectedName.replace(/\D/g, '')) || 0)
    setKbprWlYear(yr)
    if (!selAuthor) return
    const kbprP: Record<string, unknown> = {}
    if (drawerYearFrom) kbprP.year_from = drawerYearFrom
    if (drawerYearTo)   kbprP.year_to = drawerYearTo
    if (orgQuery.length >= 2) kbprP.org_search = orgQuery
    if (!isBest) kbprP.whitelist_name = selectedName
    try { const k = await authorsApi.kbpr(selAuthor.author_id, kbprP); setKbpr(k.data) }
    catch {/**/ }
  }

  const applyDrawerFilters = () => {
    if (selAuthor) loadStats(selAuthor, drawerYearFrom, drawerYearTo, orgQuery, kbprWlYear)
  }

  const fullName = (a: Author) => [a.lastname, a.firstname, a.middlename].filter(Boolean).join(' ')
  const wlYearLabel = (name: string) => {
    const m = name.match(/\d{4}/)
    if (!m) return name
    return /white/i.test(name) ? `Белый список ${m[0]}` : `Белый список ${m[0]}`
  }

  const columns = [
    { title: 'ФИО', render: (_: any, r: Author) => (
        <div>
          <div style={{ fontWeight: 500 }}>{fullName(r)}</div>
          {r.names.filter(n => n.lang === 'en').slice(0, 1).map(n => (
            <div key={n.id} style={{ fontSize: 12, color: 'var(--text-muted)' }}>
              {[n.lastname, n.firstname].filter(Boolean).join(' ')}
            </div>
          ))}
        </div>)},
    { title: 'Инициалы', dataIndex: 'initials', width: 90,
      render: (v: string) => <Text style={{ fontFamily: 'var(--mono)' }}>{v || '—'}</Text> },
    { title: 'Email', dataIndex: 'email', ellipsis: true,
      render: (v: string) => v ? <a href={`mailto:${v}`} style={{ fontFamily: 'var(--mono)', fontSize: 12 }}>{v}</a> : '—' },
    { title: '', width: 90,
      render: (_: any, r: Author) => (
        <Button size="small" icon={<BarChartOutlined />} onClick={() => openDrawer(r)} style={{ fontSize: 11 }}>
          Анализ
        </Button>) },
  ]

  return (
    <div>
      <div className="page-header">
        <div>
          <div className="page-title"><TeamOutlined style={{ marginRight: 8, color: 'var(--amber-dim)' }} />Авторы</div>
          <div className="page-subtitle">Поиск по ФИО, инициалам или email</div>
        </div>
      </div>

      <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', alignItems: 'flex-end', marginBottom: 12 }}>
        <div>
          <div style={{ fontSize: 11, color: 'var(--text-muted)', marginBottom: 4 }}>Поиск</div>
          <Input.Search placeholder="Фамилия, имя, инициалы или email…" allowClear
            enterButton={<SearchOutlined />} style={{ width: 380 }}
            onSearch={v => { setSearch(v); setPage(1); fetchAuthors(v, 1) }}
            onChange={e => !e.target.value && fetchAuthors('', 1)} />
        </div>
        {total > 0 && <Text type="secondary" style={{ fontFamily: 'var(--mono)', fontSize: 12, alignSelf: 'flex-end' }}>Найдено: {total}</Text>}
      </div>

      <Table dataSource={authors} columns={columns} rowKey="author_id" loading={loading} size="middle"
        pagination={{ current: page, pageSize: PAGE_SIZE, total, showTotal: t => `Всего: ${t}`,
          onChange: p => { setPage(p); fetchAuthors(search, p) } }}
        locale={{ emptyText: 'Введите запрос для поиска' }}
        style={{ background: '#fff', borderRadius: 8 }} />

      <Drawer title={selAuthor ? <span><TeamOutlined /> {fullName(selAuthor)}</span> : ''}
        open={drawerOpen} onClose={() => setDrawerOpen(false)} width={520} destroyOnClose>



        {statsLoading
          ? <div style={{ textAlign: 'center', padding: 60 }}><Spin size="large" /></div>
          : activity && (<div>

            {/* All activity */}
            <div style={{ marginBottom: 16 }}>
              <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--navy)', marginBottom: 8 }}>Публикационная активность (все публикации)</div>
              <StatRow label="Всего" value={activity.total} hl />
              <StatRow label="WoS" value={activity.wos} />
              {activity.wos_quartiles && <QuartileBadges q={activity.wos_quartiles} />}
              <StatRow label="Scopus" value={activity.scopus} />
              {activity.scp_quartiles && <QuartileBadges q={activity.scp_quartiles} />}
              <StatRow label="ВАК" value={activity.vak} />
              <StatRow label="РИНЦ" value={activity.risc} />
              {Object.entries((activity.whitelists || {}) as Record<string, number>).map(([name, val]) => (
                <div key={name}>
                  <StatRow label={normName(name)} value={val as number} />
                  {activity.whitelist_quartiles?.[name] && <QuartileBadges q={activity.whitelist_quartiles[name]} />}
                </div>
              ))}
            </div>

            <Divider />

            {/* Confirmed only */}
            {actFiltered && (
              <div style={{ marginBottom: 16 }}>
                <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--navy)', marginBottom: 8 }}>Только с подтверждённой поддержкой</div>
                <StatRow label="Всего" value={actFiltered.total} hl />
                <StatRow label="WoS"    value={actFiltered.wos} />
                <StatRow label="Scopus" value={actFiltered.scopus} />
                <StatRow label="ВАК"    value={actFiltered.vak} />
                <StatRow label="РИНЦ"   value={actFiltered.risc} />
                {Object.entries((actFiltered.whitelists || {}) as Record<string, number>).map(([name, val]) => (
                  <StatRow key={name} label={normName(name)} value={val as number} />
                ))}
              </div>
            )}

            <Divider />

            {/* No confirmed support */}
            <div style={{ marginBottom: 16 }}>
              <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--navy)', marginBottom: 8 }}>Без подтверждённой поддержки</div>
              <div style={{ fontFamily: 'var(--mono)', fontSize: 32, color: '#c62828', fontWeight: 700 }}>{invalidCount ?? '—'}</div>
              <div style={{ fontSize: 12, color: 'var(--text-muted)' }}>публикаций</div>
            </div>

            <Divider />

            {/* Параметры анализа — год и организация */}
            <div style={{ background: '#f8fafd', border: '1px solid var(--border)', borderRadius: 8, padding: '12px 14px', marginBottom: 16 }}>
              <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--navy)', marginBottom: 10 }}>Параметры анализа</div>
              <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap', alignItems: 'flex-end' }}>
                <div>
                  <div style={{ fontSize: 11, color: 'var(--text-muted)', marginBottom: 3 }}>Год от</div>
                  <InputNumber style={{ width: 100 }} min={1990} max={2100} value={drawerYearFrom} onChange={v => setDYF(v || undefined)} />
                </div>
                <div>
                  <div style={{ fontSize: 11, color: 'var(--text-muted)', marginBottom: 3 }}>Год до</div>
                  <InputNumber style={{ width: 100 }} min={1990} max={2100} value={drawerYearTo} onChange={v => setDYT(v || undefined)} />
                </div>
                <div style={{ flex: 1, minWidth: 200, position: 'relative' }}>
                  <div style={{ fontSize: 11, color: 'var(--text-muted)', marginBottom: 3 }}>Организация (для КБПР)</div>
                  <Input placeholder="ФИЦ ИВТ по умолчанию…" value={orgQuery}
                    onChange={e => searchOrg(e.target.value)}
                    suffix={orgSearching ? <Spin size="small" /> : <SearchOutlined style={{ color: 'var(--text-muted)' }} />} />
                  {orgOptions.length > 0 && (
                    <div style={{
                      position: 'absolute', top: '100%', left: 0, right: 0, zIndex: 200,
                      background: '#fff', border: '1px solid var(--border)', borderRadius: 6,
                      boxShadow: '0 4px 16px rgba(0,0,0,0.12)', maxHeight: 200, overflowY: 'auto',
                    }}>
                      {orgOptions.map(o => (
                        <div key={o.org_id}
                          style={{ padding: '7px 12px', cursor: 'pointer', fontSize: 12, borderBottom: '1px solid var(--border)' }}
                          onMouseDown={() => { setOrgQuery(o.orgname); setOrgOptions([]) }}>
                          {o.orgname}
                        </div>
                      ))}
                    </div>
                  )}
                </div>
                <Button type="primary" onClick={applyDrawerFilters} style={{ background: 'var(--navy)' }}>
                  Применить
                </Button>
              </div>
            </div>

            {/* КБПР */}
            {kbpr && (
              <div>
                <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--navy)', marginBottom: 4 }}>
                  КБПР · {kbpr.org_name || `Организация #${kbpr.org_id}`}
                </div>
                <div style={{ fontSize: 11, color: 'var(--text-muted)', marginBottom: 10 }}>
                  Формула: вклад = (1/N)·Σ(1/mᵢ), где N — авторов, mᵢ — аффилиаций i-го автора с данной org.
                  K: уровень 1 → 20, уровень 2 → 10, уровень 3 → 5, уровень 4 → 2,5; ВАК (не в БС) → 0,12
                </div>
                {wlDbsLoaded && wlDbs.length > 0 && (
                  <div style={{ marginBottom: 10 }}>
                    <div style={{ fontSize: 11, color: 'var(--text-muted)', marginBottom: 4 }}>Белый список для K:</div>
                    <div style={{ display: 'flex', flexWrap: 'wrap', gap: '4px 0' }}>
                      <Checkbox checked={kbprWlYear === 0} onChange={() => handleWlChange('__best__')}
                        style={{ marginInlineStart: 0, marginRight: 16, whiteSpace: 'nowrap', fontWeight: kbprWlYear === 0 ? 600 : 400 }}>
                        ★ Лучший квартиль
                      </Checkbox>
                      {wlDbs.map(name => {
                        const yr = parseInt(name.replace(/\D/g, ''))
                        return (
                          <Checkbox key={name} checked={kbprWlYear === yr}
                            onChange={() => handleWlChange(name)}
                            style={{ marginInlineStart: 0, marginRight: 16, whiteSpace: 'nowrap' }}>
                            {wlYearLabel(name)}
                          </Checkbox>
                        )
                      })}
                    </div>
                  </div>
                )}
                <div className="kbpr-value" style={{ fontSize: 36 }}>{kbpr.kbpr?.toFixed(4) ?? '—'}</div>
                <div style={{ fontSize: 12, color: 'var(--text-muted)', marginTop: 4 }}>
                  по {kbpr.article_count} публикациям ·{' '}
                  {kbpr.kbpr_mode === 'best_across_all' ? '★ лучший квартиль' : normName(kbpr.whitelist_name || '')}
                </div>
              </div>
            )}
          </div>)}
      </Drawer>
    </div>
  )
}
