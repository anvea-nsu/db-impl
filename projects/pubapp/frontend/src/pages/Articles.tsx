import { useState, useEffect, useCallback, useRef } from 'react'
import { Table, Input, Select, Button, Tabs, Tag, Drawer, InputNumber, Checkbox,
         Typography, Spin, Divider, Tooltip, Row, Col } from 'antd'
import { SearchOutlined, FileTextOutlined, PercentageOutlined } from '@ant-design/icons'
import { articlesApi, statsApi, journalsApi, authorsApi } from '../api/client'

const { Text } = Typography
const PAGE_SIZE = 50
const MAIN_DBS = ['crossref', 'rsci', 'scopus', 'wos', 'web of science', 'zbmath', 'вак']

function normName(n: string): string {
  if (/web of science/i.test(n)) return 'WoS'
  if (/белый список/i.test(n) || /white\s*list/i.test(n))
    return n.replace(/white\s*list/gi, 'Белый список')
  return n
}

function VSTag({ v }: { v?: boolean | null }) {
  if (v === true)  return <Tag color="success" style={{ fontFamily: 'var(--mono)', fontSize: 11 }}>✓ Подтверждена</Tag>
  if (v === false) return <Tag color="error"   style={{ fontFamily: 'var(--mono)', fontSize: 11 }}>✗ Не подтверждена</Tag>
  return <span style={{ color: 'var(--text-muted)' }}>—</span>
}

// Generic autocomplete hook
function useAutocomplete(fetchFn: (q: string) => Promise<any>) {
  const [query, setQuery]     = useState('')
  const [options, setOptions] = useState<any[]>([])
  const [busy, setBusy]       = useState(false)
  const [selId, setSelId]     = useState<number | undefined>()
  const timer = useRef<ReturnType<typeof setTimeout>>()

  const onSearch = (q: string) => {
    setQuery(q)
    if (!q) { setSelId(undefined); setOptions([]); return }
    clearTimeout(timer.current)
    timer.current = setTimeout(async () => {
      setBusy(true)
      try { const r = await fetchFn(q); setOptions(r.data?.items ?? r.data ?? []) }
      catch {/**/ } finally { setBusy(false) }
    }, 300)
  }
  const onSelect = (id: number, label: string) => { setSelId(id); setQuery(label); setOptions([]) }
  const clear = () => { setSelId(undefined); setQuery(''); setOptions([]) }
  return { query, options, busy, selId, onSearch, onSelect, clear }
}

function AutocompleteInput({ placeholder, options, busy, query, onSearch, onSelect, renderOption, getLabel, getId }:
  { placeholder: string; options: any[]; busy: boolean; query: string;
    onSearch: (q: string) => void; onSelect: (id: number, label: string) => void;
    renderOption: (o: any) => string; getLabel: (o: any) => string; getId: (o: any) => number }) {
  return (
    <div style={{ position: 'relative' }}>
      <Input placeholder={placeholder} value={query}
        onChange={e => onSearch(e.target.value)}
        suffix={busy ? <Spin size="small" /> : <SearchOutlined style={{ color: 'var(--text-muted)' }} />} />
      {options.length > 0 && (
        <div style={{
          position: 'absolute', top: '100%', left: 0, right: 0, zIndex: 300,
          background: '#fff', border: '1px solid var(--border)', borderRadius: 6,
          boxShadow: '0 4px 16px rgba(0,0,0,0.12)', maxHeight: 200, overflowY: 'auto'
        }}>
          {options.map((o, i) => (
            <div key={i} style={{ padding: '7px 12px', cursor: 'pointer', fontSize: 12, borderBottom: '1px solid var(--border)' }}
              onMouseDown={() => onSelect(getId(o), getLabel(o))}>
              {renderOption(o)}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

function ContribDrawer({ articleId, onClose, wlDbs }:
  { articleId: number | null; onClose: () => void; wlDbs: string[] }) {
  const [data, setData]   = useState<any>(null)
  const [loading, setL]   = useState(false)
  const [wlName, setWlN]  = useState<string>('')
  const [orgQuery, setOQ] = useState('')
  const [orgOpts, setOO]  = useState<any[]>([])
  const [orgBusy, setOB]  = useState(false)
  const orgTimer = useRef<ReturnType<typeof setTimeout>>()

  useEffect(() => {
    if (wlDbs.length && !wlName) setWlN(wlDbs[wlDbs.length - 1])
  }, [wlDbs])

  const searchOrg = (q: string) => {
    setOQ(q); clearTimeout(orgTimer.current)
    if (q.length < 2) { setOO([]); return }
    orgTimer.current = setTimeout(async () => {
      setOB(true)
      try { const r = await statsApi.orgSearch(q); setOO(r.data) }
      catch {/**/ } finally { setOB(false) }
    }, 300)
  }

  const load = useCallback(async (id: number, wl: string, orgQ: string) => {
    if (!wl) return
    setL(true); setData(null)
    try {
      const params: Record<string, unknown> = { whitelist_name: wl }
      if (orgQ.length >= 2) params.org_search = orgQ
      const r = await articlesApi.contribution(id, params)
      setData(r.data)
    } catch {/**/ } finally { setL(false) }
  }, [])

  useEffect(() => { if (articleId && wlName) load(articleId, wlName, orgQuery) }, [articleId, wlName])

  return (
    <Drawer title={<span><PercentageOutlined /> Вклад организации</span>}
      open={!!articleId} onClose={onClose} width={520} destroyOnClose>

      <div style={{ display: 'flex', flexDirection: 'column', gap: 10, marginBottom: 16 }}>
        <div>
          <div style={{ fontSize: 11, color: 'var(--text-muted)', marginBottom: 3 }}>Белый список для КБПР</div>
          <Select value={wlName} onChange={v => setWlN(v)} style={{ width: '100%' }}
            options={wlDbs.map(n => ({ value: n, label: normName(n) }))} />
        </div>
        <div>
          <div style={{ fontSize: 11, color: 'var(--text-muted)', marginBottom: 3 }}>
            Организация (по умолчанию: ФИЦ ИВТ)
          </div>
          <div style={{ position: 'relative' }}>
            <Input placeholder="Введите название…" value={orgQuery}
              onChange={e => searchOrg(e.target.value)}
              suffix={orgBusy ? <Spin size="small" /> : <SearchOutlined style={{ color: 'var(--text-muted)' }} />} />
            {orgOpts.length > 0 && (
              <div style={{
                position: 'absolute', top: '100%', left: 0, right: 0, zIndex: 300,
                background: '#fff', border: '1px solid var(--border)', borderRadius: 6,
                boxShadow: '0 4px 16px rgba(0,0,0,0.12)', maxHeight: 200, overflowY: 'auto'
              }}>
                {orgOpts.map((o: any) => (
                  <div key={o.org_id} style={{ padding: '7px 12px', cursor: 'pointer', fontSize: 12, borderBottom: '1px solid var(--border)' }}
                    onMouseDown={() => { setOQ(o.orgname); setOO([]) }}>
                    {o.orgname}
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
        <Button type="primary" style={{ background: 'var(--navy)', alignSelf: 'flex-start' }}
          onClick={() => { if (articleId && wlName) load(articleId, wlName, orgQuery) }}>
          Рассчитать
        </Button>
      </div>

      {loading ? <div style={{ textAlign: 'center', padding: 40 }}><Spin /></div>
        : data && (
        <div>
          <div style={{ display: 'flex', gap: 24, marginBottom: 20 }}>
            <div style={{ textAlign: 'center' }}>
              <div style={{ fontSize: 11, color: 'var(--text-muted)', textTransform: 'uppercase', fontFamily: 'var(--mono)', letterSpacing: 1 }}>Вклад</div>
              <div style={{ fontSize: 36, fontWeight: 700, color: 'var(--navy)', fontFamily: 'var(--mono)' }}>{data.contribution_pct}%</div>
            </div>
            <div style={{ textAlign: 'center' }}>
              <div style={{ fontSize: 11, color: 'var(--text-muted)', textTransform: 'uppercase', fontFamily: 'var(--mono)', letterSpacing: 1 }}>КБПР</div>
              <div className="kbpr-value" style={{ fontSize: 36 }}>{data.kbpr}</div>
            </div>
            {data.quartile > 0 && (
              <div style={{ textAlign: 'center' }}>
                <div style={{ fontSize: 11, color: 'var(--text-muted)', textTransform: 'uppercase', fontFamily: 'var(--mono)', letterSpacing: 1 }}>Уровень</div>
                <div className={`tag-q${data.quartile}`} style={{ fontSize: 20, padding: '4px 10px', display: 'inline-block', marginTop: 4 }}>
                  {data.quartile}
                </div>
              </div>
            )}
          </div>
          {data.org_name && (
            <div style={{ fontSize: 12, color: 'var(--text-muted)', marginBottom: 12 }}>
              Организация: <b>{data.org_name}</b> · {normName(data.whitelist_name || '')}
            </div>
          )}
          <Divider orientation="left" style={{ fontSize: 12 }}>Авторы и аффилиации</Divider>
          {data.authors?.map((a: any) => (
            <div key={a.author_id} style={{ padding: '8px 0', borderBottom: '1px solid var(--border)' }}>
              <div style={{ fontWeight: 500, fontSize: 13 }}>{a.num}. {a.lastname} {a.initials}</div>
              <div style={{ fontSize: 11, color: 'var(--text-muted)' }}>Аффилиаций: {a.affiliations_count}</div>
              <div style={{ marginTop: 2 }}>
                {a.affiliations?.map((org: string, i: number) => (
                  <Tag key={i} style={{ fontSize: 10, margin: '2px', whiteSpace: 'normal', height: 'auto', lineHeight: 1.4 }}>
                    {org || `org#${i}`}
                  </Tag>
                ))}
              </div>
            </div>
          ))}
        </div>
      )}
    </Drawer>
  )
}

function ArticleTable({ data, total, loading, page, onPage, onContrib }:
  { data: any[]; total: number; loading: boolean; page: number;
    onPage: (p: number) => void; onContrib: (id: number) => void }) {
  const cols = [
    { title: 'Публикация', render: (_: any, r: any) => (
        <div>
          <div style={{ fontWeight: 500, lineHeight: 1.4 }}>{r.title}</div>
          <div style={{ fontSize: 12, color: 'var(--text-muted)', marginTop: 2 }}>
            {r.journal_title && <span style={{ marginRight: 8 }}>{r.journal_title}</span>}
            {r.year && <span style={{ fontFamily: 'var(--mono)' }}>{r.year}</span>}
          </div>
        </div>) },
    { title: 'DOI', dataIndex: 'doi', width: 150,
      render: (v: string) => v ? <Text style={{ fontFamily: 'var(--mono)', fontSize: 11 }}>{v}</Text> : '—' },
    { title: 'Поддержка', dataIndex: 'valid_support', width: 140,
      render: (v: boolean) => <VSTag v={v} /> },
    { title: '', width: 46,
      render: (_: any, r: any) => (
        <Tooltip title="Вклад и КБПР">
          <Button size="small" icon={<PercentageOutlined />} onClick={() => onContrib(r.article_id)} />
        </Tooltip>) },
  ]
  return (
    <Table dataSource={data} columns={cols} rowKey="article_id" loading={loading} size="small"
      pagination={{ current: page, pageSize: PAGE_SIZE, total, showTotal: t => `Всего: ${t}`, onChange: onPage }}
      scroll={{ x: 720 }} style={{ background: '#fff', borderRadius: 8 }} />
  )
}

function dbCheckLabel(name: string): string {
  if (/web of science/i.test(name)) return 'WoS'
  if (name === 'Scopus') return 'Scopus'
  if (name === 'ВАК') return 'ВАК'
  if (/rsci/i.test(name)) return 'RSCI'
  if (/zbmath/i.test(name)) return 'zbMATH'
  if (/crossref/i.test(name)) return 'Crossref'
  const wlM = name.match(/(?:белый список|white\s*list)\s*(\d{4})/i)
  if (wlM) return `Белый список ${wlM[1]}`
  return name
}

export default function Articles() {
  const [data, setData]           = useState<any[]>([])
  const [total, setTotal]         = useState(0)
  const [loading, setLoading]     = useState(false)
  const [page, setPage]           = useState(1)

  // Text search
  const [search, setSearch]       = useState('')
  const [doi, setDoi]             = useState('')
  const [yearFrom, setYearFrom]   = useState<number | undefined>()
  const [yearTo, setYearTo]       = useState<number | undefined>()
  const [validSupport, setVS]     = useState<string | undefined>()
  const [quartile, setQuartile]   = useState<number | undefined>()
  const [dbs, setDbs]             = useState<string[]>([])

  // Autocompletes
  const author = useAutocomplete(q => authorsApi.list({ search: q, limit: 10 }))
  const journal = useAutocomplete(q => journalsApi.list({ search: q, limit: 10 }))
  const orgAC = useAutocomplete(q => statsApi.orgSearch(q))

  // DB lists
  const [regularDbs, setRegularDbs] = useState<string[]>([])
  const [wlDbs, setWlDbs]           = useState<string[]>([])
  const [dbsLoaded, setDbsLoaded]   = useState(false)

  // Contrib drawer
  const [contribId, setContribId] = useState<number | null>(null)

  // VAK-only tab
  const [vakData, setVakData]       = useState<any[]>([])
  const [vakTotal, setVakTotal]     = useState(0)
  const [vakPage, setVakPage]       = useState(1)
  const [vakLoading, setVakL]       = useState(false)
  const [vakAuthor2, setVakA2]      = useState('')
  const [vakAuthorId2, setVakAId2]  = useState<number | undefined>()
  const [vakYf, setVakYf]           = useState<number | undefined>()
  const [vakYt, setVakYt]           = useState<number | undefined>()

  // Not-indexed tab
  const [niData, setNiData]   = useState<any[]>([])
  const [niTotal, setNiTotal] = useState(0)
  const [niPage, setNiPage]   = useState(1)
  const [niLoading, setNiL]   = useState(false)

  useEffect(() => {
    statsApi.availableDbs()
      .then(r => {
        const names: string[] = r.data as string[]
        setRegularDbs(
          names.filter(n => {
            const lower = n.toLowerCase()
            return MAIN_DBS.some(m => lower === m || lower.includes(m)) &&
                   !/белый список/i.test(n) && !/white\s*list/i.test(n)
          }).sort()
        )
        setWlDbs(names.filter(n => /белый список/i.test(n) || /white\s*list/i.test(n)).sort())
      })
      .catch(() => {})
      .finally(() => setDbsLoaded(true))
    fetchMain(1)
  }, [])

  const fetchMain = useCallback(async (p: number) => {
    setLoading(true)
    try {
      const params: Record<string, unknown> = { skip: (p - 1) * PAGE_SIZE, limit: PAGE_SIZE }
      if (search) params.search = search
      if (doi) params.doi = doi
      if (author.selId) params.author_id = author.selId
      if (journal.selId) params.journal_id = journal.selId
      if (yearFrom) params.year_from = yearFrom
      if (yearTo) params.year_to = yearTo
      if (orgAC.selId) params.org_id = orgAC.selId
      if (validSupport) params.valid_support = validSupport
      if (dbs.length) params.dbs = dbs
      if (quartile) params.quartile = quartile
      const r = await articlesApi.list(params)
      setData(r.data.items); setTotal(r.data.total)
    } catch {/**/ } finally { setLoading(false) }
  }, [search, doi, author.selId, journal.selId, yearFrom, yearTo, orgAC.selId, validSupport, dbs, quartile])

  const fetchVak = async (p: number) => {
    setVakL(true)
    const params: Record<string, unknown> = { skip: (p - 1) * PAGE_SIZE, limit: PAGE_SIZE }
    if (vakAuthorId2) params.author_id = vakAuthorId2
    if (vakYf) params.year_from = vakYf; if (vakYt) params.year_to = vakYt
    try { const r = await articlesApi.vakOnly(params); setVakData(r.data.items); setVakTotal(r.data.total) }
    catch {/**/ } finally { setVakL(false) }
  }
  const fetchNi = async (p: number) => {
    setNiL(true)
    const params: Record<string, unknown> = { skip: (p - 1) * PAGE_SIZE, limit: PAGE_SIZE }
    if (vakAuthorId2) params.author_id = vakAuthorId2
    if (vakYf) params.year_from = vakYf; if (vakYt) params.year_to = vakYt
    try { const r = await articlesApi.notIndexed(params); setNiData(r.data.items); setNiTotal(r.data.total) }
    catch {/**/ } finally { setNiL(false) }
  }

  const simpleCols = [
    { title: 'Название', dataIndex: 'title', ellipsis: true,
      render: (t: string) => <span style={{ fontWeight: 500 }}>{t}</span> },
    { title: 'Журнал', dataIndex: 'journal_title', ellipsis: true, width: 200 },
    { title: 'Год', dataIndex: 'year', width: 70,
      render: (v: number) => <Text style={{ fontFamily: 'var(--mono)' }}>{v || '—'}</Text> },
    { title: 'DOI', dataIndex: 'doi', width: 140,
      render: (v: string) => v ? <Text style={{ fontFamily: 'var(--mono)', fontSize: 11 }}>{v}</Text> : '—' },
    { title: 'Поддержка', dataIndex: 'valid_support', width: 140,
      render: (v: boolean) => <VSTag v={v} /> },
  ]

  const [vakAuthorOpts, setVakAOpts] = useState<any[]>([])
  const vakTimer = useRef<ReturnType<typeof setTimeout>>()
  const searchVakAuthor = (q: string) => {
    setVakA2(q); setVakAId2(undefined); clearTimeout(vakTimer.current)
    if (!q) { setVakAOpts([]); return }
    vakTimer.current = setTimeout(async () => {
      try { const r = await authorsApi.list({ search: q, limit: 10 }); setVakAOpts(r.data.items) }
      catch {/**/ }
    }, 300)
  }

  const secondaryFilter = (
    <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', alignItems: 'flex-end', marginBottom: 12 }}>
      <div>
        <div style={{ fontSize: 11, color: 'var(--text-muted)', marginBottom: 3 }}>Автор</div>
        <div style={{ position: 'relative', width: 240 }}>
          <Input placeholder="Фамилия…" value={vakAuthor2} onChange={e => searchVakAuthor(e.target.value)} />
          {vakAuthorOpts.length > 0 && (
            <div style={{ position: 'absolute', top: '100%', left: 0, right: 0, zIndex: 200,
                background: '#fff', border: '1px solid var(--border)', borderRadius: 6,
                boxShadow: '0 4px 12px rgba(0,0,0,0.1)', maxHeight: 180, overflowY: 'auto' }}>
              {vakAuthorOpts.map((a: any) => (
                <div key={a.author_id} style={{ padding: '6px 12px', cursor: 'pointer', fontSize: 12, borderBottom: '1px solid var(--border)' }}
                  onMouseDown={() => { setVakA2([a.lastname, a.firstname].filter(Boolean).join(' ')); setVakAId2(a.author_id); setVakAOpts([]) }}>
                  {[a.lastname, a.firstname, a.middlename].filter(Boolean).join(' ')}
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
      <div>
        <div style={{ fontSize: 11, color: 'var(--text-muted)', marginBottom: 3 }}>Год от</div>
        <InputNumber style={{ width: 100 }} value={vakYf} onChange={v => setVakYf(v || undefined)} />
      </div>
      <div>
        <div style={{ fontSize: 11, color: 'var(--text-muted)', marginBottom: 3 }}>Год до</div>
        <InputNumber style={{ width: 100 }} value={vakYt} onChange={v => setVakYt(v || undefined)} />
      </div>
    </div>
  )

  return (
    <div>
      <div className="page-header">
        <div>
          <div className="page-title"><FileTextOutlined style={{ marginRight: 8, color: 'var(--amber-dim)' }} />Публикации</div>
          <div className="page-subtitle">Поиск, фильтрация, спецвыборки и расчёт вклада</div>
        </div>
      </div>

      <Tabs defaultActiveKey="search" items={[
        { key: 'search', label: 'Поиск и фильтры', children: (<>
            {/* Main filter grid */}
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(200px, 1fr))', gap: 10, marginBottom: 12 }}>
              <div>
                <div style={{ fontSize: 11, color: 'var(--text-muted)', marginBottom: 3 }}>Название</div>
                <Input value={search} onChange={e => setSearch(e.target.value)} prefix={<SearchOutlined />} />
              </div>
              <div>
                <div style={{ fontSize: 11, color: 'var(--text-muted)', marginBottom: 3 }}>DOI</div>
                <Input value={doi} onChange={e => setDoi(e.target.value)} style={{ fontFamily: 'var(--mono)' }} />
              </div>
              <div>
                <div style={{ fontSize: 11, color: 'var(--text-muted)', marginBottom: 3 }}>Автор</div>
                <AutocompleteInput placeholder="Фамилия…" {...author}
                  renderOption={o => [o.lastname, o.firstname, o.middlename].filter(Boolean).join(' ')}
                  getLabel={o => [o.lastname, o.firstname].filter(Boolean).join(' ')}
                  getId={o => o.author_id} />
              </div>
              <div>
                <div style={{ fontSize: 11, color: 'var(--text-muted)', marginBottom: 3 }}>Журнал</div>
                <AutocompleteInput placeholder="Название или ISSN…" {...journal}
                  renderOption={o => o.title} getLabel={o => o.title} getId={o => o.journal_id} />
              </div>
              <div>
                <div style={{ fontSize: 11, color: 'var(--text-muted)', marginBottom: 3 }}>Год от</div>
                <InputNumber style={{ width: '100%' }} value={yearFrom} onChange={v => setYearFrom(v || undefined)} />
              </div>
              <div>
                <div style={{ fontSize: 11, color: 'var(--text-muted)', marginBottom: 3 }}>Год до</div>
                <InputNumber style={{ width: '100%' }} value={yearTo} onChange={v => setYearTo(v || undefined)} />
              </div>
              <div>
                <div style={{ fontSize: 11, color: 'var(--text-muted)', marginBottom: 3 }}>Организация</div>
                <AutocompleteInput placeholder="Название…" {...orgAC}
                  renderOption={o => o.orgname} getLabel={o => o.orgname} getId={o => o.org_id} />
              </div>
              <div>
                <div style={{ fontSize: 11, color: 'var(--text-muted)', marginBottom: 3 }}>Подтверждение поддержки</div>
                <Select allowClear style={{ width: '100%' }} value={validSupport} onChange={setVS}
                  options={[
                    { value: 'true',  label: '✓ Подтверждена' },
                    { value: 'false', label: '✗ Не подтверждена' },
                    { value: 'null',  label: '— Не указано' },
                  ]} />
              </div>
              <div>
                <div style={{ fontSize: 11, color: 'var(--text-muted)', marginBottom: 3 }}>
                  Уровень (только при выбранном Белом списке)
                </div>
                <Select
                  allowClear
                  style={{ width: '100%' }}
                  disabled={!dbs.some((d: string) => /белый список|white\s*list/i.test(d))}
                  placeholder={dbs.some((d: string) => /белый список|white\s*list/i.test(d)) ? 'Любой' : 'Сначала выберите БС'}
                  value={quartile}
                  onChange={setQuartile}
                  options={[1, 2, 3, 4].map(q => ({ value: q, label: `Уровень ${q}` }))}
                />
              </div>
            </div>

            {/* DB checkboxes */}
            <div style={{ background: '#f8fafd', border: '1px solid var(--border)', borderRadius: 8,
                          padding: '12px 16px', marginBottom: 12 }}>
              {!dbsLoaded ? <Spin size="small" /> : (
                <Row gutter={[32, 0]}>
                  <Col>
                    <div style={{ fontSize: 11, color: 'var(--text-muted)', marginBottom: 6, fontWeight: 600, textTransform: 'uppercase', letterSpacing: 0.5 }}>
                      Базы данных (пересечение — И)
                    </div>
                    <div style={{ display: 'flex', flexWrap: 'wrap', gap: '4px 0' }}>
                      {regularDbs.map(name => (
                        <Checkbox key={name} checked={dbs.includes(name)}
                          onChange={e => setDbs(e.target.checked ? [...dbs, name] : dbs.filter(d => d !== name))}
                          style={{ marginInlineStart: 0, marginRight: 16, whiteSpace: 'nowrap' }}>
                          {dbCheckLabel(name)}
                        </Checkbox>
                      ))}
                    </div>
                  </Col>
                  {wlDbs.length > 0 && (
                    <Col>
                      <div style={{ fontSize: 11, color: 'var(--text-muted)', marginBottom: 6, fontWeight: 600, textTransform: 'uppercase', letterSpacing: 0.5 }}>
                        Белые списки
                      </div>
                      <div style={{ display: 'flex', flexWrap: 'wrap', gap: '4px 0' }}>
                        {wlDbs.map(name => (
                          <Checkbox key={name} checked={dbs.includes(name)}
                            onChange={e => setDbs(e.target.checked ? [...dbs, name] : dbs.filter(d => d !== name))}
                            style={{ marginInlineStart: 0, marginRight: 16, whiteSpace: 'nowrap' }}>
                            {dbCheckLabel(name)}
                          </Checkbox>
                        ))}
                      </div>
                    </Col>
                  )}
                </Row>
              )}
            </div>

            <div style={{ display: 'flex', gap: 12, alignItems: 'center', marginBottom: 12 }}>
              <Button type="primary" style={{ background: 'var(--navy)' }}
                onClick={() => { setPage(1); fetchMain(1) }}>Поиск</Button>
              {total > 0 && <Text type="secondary" style={{ fontFamily: 'var(--mono)', fontSize: 12 }}>Найдено: {total}</Text>}
            </div>

            <ArticleTable data={data} total={total} loading={loading} page={page}
              onPage={p => { setPage(p); fetchMain(p) }} onContrib={setContribId} />
          </>)
        },
        { key: 'vak', label: 'ВАК (не в Scopus/WoS/БС)', children: (<>
            {secondaryFilter}
            <div style={{ display: 'flex', gap: 12, alignItems: 'center', marginBottom: 12 }}>
              <Button type="primary" style={{ background: 'var(--navy)' }}
                onClick={() => { setVakPage(1); fetchVak(1) }}>Применить</Button>
              {vakTotal > 0 && <Text type="secondary" style={{ fontFamily: 'var(--mono)', fontSize: 12 }}>Найдено: {vakTotal}</Text>}
            </div>
            <Table dataSource={vakData} columns={simpleCols} rowKey="article_id" loading={vakLoading} size="small"
              pagination={{ current: vakPage, pageSize: PAGE_SIZE, total: vakTotal,
                showTotal: t => `Всего: ${t}`, onChange: p => { setVakPage(p); fetchVak(p) } }}
              style={{ background: '#fff', borderRadius: 8 }} />
          </>)
        },
        { key: 'ni', label: 'Вне всех баз', children: (<>
            {secondaryFilter}
            <div style={{ display: 'flex', gap: 12, alignItems: 'center', marginBottom: 12 }}>
              <Button type="primary" style={{ background: 'var(--navy)' }}
                onClick={() => { setNiPage(1); fetchNi(1) }}>Применить</Button>
              {niTotal > 0 && <Text type="secondary" style={{ fontFamily: 'var(--mono)', fontSize: 12 }}>Найдено: {niTotal}</Text>}
            </div>
            <Table dataSource={niData} columns={simpleCols} rowKey="article_id" loading={niLoading} size="small"
              pagination={{ current: niPage, pageSize: PAGE_SIZE, total: niTotal,
                showTotal: t => `Всего: ${t}`, onChange: p => { setNiPage(p); fetchNi(p) } }}
              style={{ background: '#fff', borderRadius: 8 }} />
          </>)
        },
      ]} />

      <ContribDrawer articleId={contribId} onClose={() => setContribId(null)} wlDbs={wlDbs} />
    </div>
  )
}
