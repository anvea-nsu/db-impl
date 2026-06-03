import { useState, useEffect } from 'react'
import { Table, Input, Select, Checkbox, Button, Tag, Space, Tabs, Typography, Tooltip, Col, Card, Spin, Row } from 'antd'
import { SearchOutlined, TrophyOutlined, ReadOutlined } from '@ant-design/icons'
import { journalsApi } from '../api/client'
import type { Journal, JournalDBEntry } from '../types'

const { Text } = Typography
const PAGE_SIZE = 50

// Short display name for a DB in badges (inside table cells)
function dbBadgeLabel(dbName: string): string {
  if (/web of science/i.test(dbName)) return 'WoS'
  if (dbName === 'Scopus') return 'Scopus'
  if (dbName === 'ВАК') return 'ВАК'
  if (/rsci/i.test(dbName) || /russian science citation/i.test(dbName)) return 'RSCI'
  // Белый список YYYY → БС YYYY
  const wlMatch = dbName.match(/(?:белый список|white\s*list)\s*(\d{4})/i)
  if (wlMatch) return `БС ${wlMatch[1]}`
  return dbName.length > 14 ? dbName.slice(0, 14) + '…' : dbName
}

function DBBadges({ dbs }: { dbs: JournalDBEntry[] }) {
  const inc = dbs.filter(d => d.is_included)
  if (!inc.length) return <Text type="secondary">—</Text>

  // Deduplicate: for non-whitelist DBs keep latest year; whitelists keep each
  const byName = new Map<string, JournalDBEntry>()
  inc.forEach(d => {
    if (/белый список/i.test(d.db_name)) {
      byName.set(d.db_name, d) // unique by full name
    } else {
      const ex = byName.get(d.db_name)
      if (!ex || d.year > ex.year) byName.set(d.db_name, d)
    }
  })

  const order = (name: string) =>
    name === 'WoS' || /web of science/i.test(name) ? 0 : name === 'Scopus' ? 1 : /rsci/i.test(name) ? 2
    : name === 'ВАК' ? 3 : /белый список/i.test(name) ? 4 : 5

  const badges = [...byName.values()].sort((a, b) => order(a.db_name) - order(b.db_name) || a.db_name.localeCompare(b.db_name))

  return (
    <Space size={2} wrap>
      {badges.map((d, i) => {
        const cls = d.quartile === 1 ? 'tag-q1' : d.quartile === 2 ? 'tag-q2'
          : d.quartile === 3 ? 'tag-q3' : d.quartile === 4 ? 'tag-q4' : 'tag-db'
        const label = dbBadgeLabel(d.db_name)
        return (
          <Tooltip key={i} title={`${d.db_name}${d.year ? ` · ${d.year}` : ''}${d.quartile ? ` · Q${d.quartile}` : ''}`}>
            <span className={cls}>{label}{d.quartile ? ` Q${d.quartile}` : ''}</span>
          </Tooltip>
        )
      })}
    </Space>
  )
}

// Checkbox label — full readable name, used in filter panel
function dbCheckboxLabel(dbName: string): string {
  if (/web of science/i.test(dbName) || dbName === 'WoS') return 'WoS'
  if (dbName === 'Scopus') return 'Scopus'
  if (dbName === 'ВАК') return 'ВАК'
  if (/rsci/i.test(dbName) || /russian science citation/i.test(dbName)) return 'RSCI'
  // "Белый список YYYY" or "White List YYYY"
  const wlMatch = dbName.match(/(?:белый список|white\s*list)\s*(\d{4})/i)
  if (wlMatch) return `Белый список ${wlMatch[1]}`
  return dbName
}

export default function Journals() {
  const [data, setData]         = useState<Journal[]>([])
  const [total, setTotal]       = useState(0)
  const [loading, setLoading]   = useState(false)
  const [top10, setTop10]       = useState<any[]>([])
  const [top10Loading, setT10L] = useState(false)
  const [search, setSearch]     = useState('')
  const [selDbs, setSelDbs]     = useState<string[]>([])
  const [quartile, setQuartile] = useState<number | undefined>()
  const [page, setPage]         = useState(1)
  const [yearFrom, setYearFrom] = useState('')
  const [yearTo, setYearTo]     = useState('')

  // Split available DBs into regular and whitelists for separate rendering
  const [regularDbs, setRegularDbs] = useState<string[]>([])
  const [whitelistDbs, setWlDbs]    = useState<string[]>([])
  const [dbsLoaded, setDbsLoaded]   = useState(false)

  useEffect(() => {
    journalsApi.availableDbs()
      .then(r => {
        const all: string[] = (r.data as { db_id: number; name: string }[]).map(d => d.name)
        // Show only main DBs in checkboxes; whitelists shown separately
        const MAIN_DBS = ['crossref', 'rsci', 'scopus', 'wos', 'web of science', 'zbmath', 'вак']
        setRegularDbs(
          all.filter(n => {
            const lower = n.toLowerCase()
            return MAIN_DBS.some(m => lower === m || lower.includes(m)) &&
                   !/белый список/i.test(n) && !/white\s*list/i.test(n)
          }).sort()
        )
        setWlDbs(all.filter(n => /белый список/i.test(n) || /white\s*list/i.test(n)).sort())
      })
      .catch(() => {})
      .finally(() => setDbsLoaded(true))
    fetchJournals('', [], undefined, 1)
    fetchTop10()
  }, [])

  const fetchJournals = async (s: string, dbs: string[], q: number | undefined, p: number) => {
    setLoading(true)
    try {
      const params: Record<string, unknown> = { skip: (p - 1) * PAGE_SIZE, limit: PAGE_SIZE }
      if (s) params.search = s
      if (dbs.length) params.dbs = dbs
      if (q) params.quartile = q
      const res = await journalsApi.list(params)
      setData(res.data.items); setTotal(res.data.total)
    } catch {/**/ } finally { setLoading(false) }
  }

  const fetchTop10 = async () => {
    setT10L(true)
    try {
      const p: Record<string, unknown> = {}
      if (yearFrom) p.year_from = parseInt(yearFrom)
      if (yearTo) p.year_to = parseInt(yearTo)
      const res = await journalsApi.top10(p)
      setTop10(res.data)
    } catch {/**/ } finally { setT10L(false) }
  }

  const apply = () => { setPage(1); fetchJournals(search, selDbs, quartile, 1) }

  const columns = [
    {
      title: 'Название', dataIndex: 'title', ellipsis: true,
      render: (t: string, r: Journal) => (
        <div>
          <div style={{ fontWeight: 500 }}>{t}</div>
          {r.titles.filter(x => x.title_text !== t).slice(0, 1).map(x => (
            <div key={x.title_id} style={{ fontSize: 12, color: 'var(--text-muted)' }}>[{x.lang}] {x.title_text}</div>
          ))}
        </div>
      )
    },
    {
      title: 'ISSN', dataIndex: 'issn', width: 110,
      render: (v: string) => <Text style={{ fontFamily: 'var(--mono)', fontSize: 12 }}>{v || '—'}</Text>
    },
    {
      title: 'eISSN', dataIndex: 'eissn', width: 110,
      render: (v: string) => <Text style={{ fontFamily: 'var(--mono)', fontSize: 12 }}>{v || '—'}</Text>
    },
    {
      title: 'Базы данных', dataIndex: 'databases', width: 340,
      render: (dbs: JournalDBEntry[]) => <DBBadges dbs={dbs} />
    },
  ]

  return (
    <div>
      <div className="page-header">
        <div>
          <div className="page-title"><ReadOutlined style={{ marginRight: 8, color: 'var(--amber-dim)' }} />Журналы</div>
          <div className="page-subtitle">Поиск и фильтрация по базам данных и квартилям</div>
        </div>
      </div>

      <Tabs defaultActiveKey="search" items={[
        {
          key: 'search', label: 'Поиск и фильтры', children: (
            <>
              {/* Search row */}
              <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', alignItems: 'flex-end', marginBottom: 12 }}>
                <Input.Search
                  placeholder="Название, ISSN или eISSN…"
                  allowClear
                  enterButton={<SearchOutlined />}
                  style={{ width: 360 }}
                  value={search}
                  onChange={e => setSearch(e.target.value)}
                  onSearch={v => { setSearch(v); fetchJournals(v, selDbs, quartile, 1) }}
                />
                <div>
                  <div style={{ fontSize: 11, color: 'var(--text-muted)', marginBottom: 4 }}>
                    Уровень (только при выбранном Белом списке)
                  </div>
                  <Select
                    placeholder={selDbs.some(d => /белый список|white\s*list/i.test(d)) ? "Любой" : "Сначала выберите БС"}
                    disabled={!selDbs.some(d => /белый список|white\s*list/i.test(d))}
                    allowClear
                    style={{ width: 240 }}
                    options={[1, 2, 3, 4].map(q => ({ value: q, label: `Уровень ${q}` }))}
                    value={quartile}
                    onChange={v => {
                      setQuartile(v)
                      if (v && !selDbs.some(d => /белый список|white\s*list/i.test(d))) setQuartile(undefined)
                    }}
                  />
                </div>
                <Button type="primary" onClick={apply} style={{ background: 'var(--navy)' }}>
                  Применить
                </Button>
                {total > 0 && (
                  <Text type="secondary" style={{ fontFamily: 'var(--mono)', fontSize: 12, alignSelf: 'center' }}>
                    Найдено: {total}
                  </Text>
                )}
              </div>

              {/* DB filter block */}
              <div style={{
                background: '#f8fafd', border: '1px solid var(--border)', borderRadius: 8,
                padding: '12px 16px', marginBottom: 16
              }}>
                {!dbsLoaded ? <Spin size="small" /> : (
                  <Row gutter={[24, 0]}>
                    {/* Regular DBs */}
                    <Col>
                      <div style={{ fontSize: 11, color: 'var(--text-muted)', marginBottom: 6, fontWeight: 600, textTransform: 'uppercase', letterSpacing: 0.5 }}>
                        Базы данных (пересечение — И)
                      </div>
                      <div style={{ display: 'flex', flexWrap: 'wrap', gap: '4px 0' }}>
                        {regularDbs.map(name => (
                          <Checkbox
                            key={name}
                            checked={selDbs.includes(name)}
                            onChange={e => setSelDbs(e.target.checked
                              ? [...selDbs, name]
                              : selDbs.filter(d => d !== name)
                            )}
                            style={{ marginInlineStart: 0, marginRight: 16, whiteSpace: 'nowrap' }}
                          >
                            {dbCheckboxLabel(name)}
                          </Checkbox>
                        ))}
                      </div>
                    </Col>

                    {/* Whitelist DBs — separate column so they're visually grouped */}
                    {whitelistDbs.length > 0 && (
                      <Col>
                        <div style={{ fontSize: 11, color: 'var(--text-muted)', marginBottom: 6, fontWeight: 600, textTransform: 'uppercase', letterSpacing: 0.5 }}>
                          Белые списки
                        </div>
                        <div style={{ display: 'flex', flexWrap: 'wrap', gap: '4px 0' }}>
                          {whitelistDbs.map(name => (
                            <Checkbox
                              key={name}
                              checked={selDbs.includes(name)}
                              onChange={e => {
                                const next = e.target.checked
                                  ? [...selDbs, name]
                                  : selDbs.filter(d => d !== name)
                                setSelDbs(next)
                                // clear quartile if no whitelist remains
                                if (!next.some(d => /белый список|white\s*list/i.test(d))) setQuartile(undefined)
                              }}
                              style={{ marginInlineStart: 0, marginRight: 16, whiteSpace: 'nowrap' }}
                            >
                              {dbCheckboxLabel(name)}
                            </Checkbox>
                          ))}
                        </div>
                      </Col>
                    )}
                  </Row>
                )}
              </div>

              <Table
                dataSource={data} columns={columns} rowKey="journal_id"
                loading={loading} size="middle"
                pagination={{
                  current: page, pageSize: PAGE_SIZE, total,
                  showTotal: t => `Всего: ${t}`,
                  onChange: p => { setPage(p); fetchJournals(search, selDbs, quartile, p) }
                }}
                scroll={{ x: 900 }}
                style={{ background: '#fff', borderRadius: 8 }}
              />
            </>
          )
        },
        {
          key: 'top10', label: <><TrophyOutlined /> Топ-10</>, children: (
            <div>
              <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', alignItems: 'flex-end', marginBottom: 16 }}>
                <div>
                  <div style={{ fontSize: 11, color: 'var(--text-muted)', marginBottom: 4 }}>Год от</div>
                  <Input style={{ width: 100 }} value={yearFrom} onChange={e => setYearFrom(e.target.value)} placeholder="напр. 2020" />
                </div>
                <div>
                  <div style={{ fontSize: 11, color: 'var(--text-muted)', marginBottom: 4 }}>Год до</div>
                  <Input style={{ width: 100 }} value={yearTo} onChange={e => setYearTo(e.target.value)} placeholder="напр. 2024" />
                </div>
                <Button onClick={fetchTop10} loading={top10Loading}
                  style={{ background: 'var(--navy)', color: '#fff', border: 'none' }}>
                  Обновить
                </Button>
              </div>
              <Row gutter={[12, 10]}>
                {top10.map((j, i) => (
                  <Col key={j.journal_id} span={24}>
                    <Card size="small" style={{ border: '1px solid var(--border)' }}
                      styles={{ body: { padding: '10px 16px', display: 'flex', alignItems: 'center', gap: 16 } }}>
                      <div style={{
                        fontFamily: 'var(--mono)', fontSize: 22, fontWeight: 700, width: 36,
                        color: i < 3 ? 'var(--amber)' : 'var(--slate)'
                      }}>{i + 1}</div>
                      <div style={{ flex: 1 }}>
                        <div style={{ fontWeight: 500 }}>{j.title}</div>
                        <div style={{ fontFamily: 'var(--mono)', fontSize: 11, color: 'var(--text-muted)' }}>
                          {j.issn || '—'} / {j.eissn || '—'}
                        </div>
                      </div>
                      <div style={{ fontFamily: 'var(--mono)', fontSize: 24, fontWeight: 700, color: 'var(--navy)', textAlign: 'right' }}>
                        {j.article_count}
                        <div style={{ fontSize: 10, color: 'var(--text-muted)', fontWeight: 400 }}>публикаций</div>
                      </div>
                    </Card>
                  </Col>
                ))}
              </Row>
            </div>
          )
        },
      ]} />
    </div>
  )
}
