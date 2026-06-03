import { useState, useEffect, useCallback } from 'react'
import { Table, Input, Tag, Space, Typography } from 'antd'
import { SearchOutlined, BankOutlined } from '@ant-design/icons'
import { orgsApi } from '../api/client'
import type { Organization } from '../types'

const { Text } = Typography
const PAGE_SIZE = 50

export default function Organizations() {
  const [data, setData]       = useState<Organization[]>([])
  const [total, setTotal]     = useState(0)
  const [loading, setLoading] = useState(false)
  const [search, setSearch]   = useState('')
  const [page, setPage]       = useState(1)

  const fetch = useCallback(async (s: string, p: number) => {
    setLoading(true)
    try {
      const res = await orgsApi.list({ search: s || undefined, skip: (p-1)*PAGE_SIZE, limit: PAGE_SIZE })
      setData(res.data.items); setTotal(res.data.total)
    } catch {/**/} finally { setLoading(false) }
  }, [])

  // Auto-load on mount
  useEffect(() => { fetch('', 1) }, [fetch])

  const onSearch = (v: string) => { setSearch(v); setPage(1); fetch(v, 1) }

  const columns = [
    { title:'ID', dataIndex:'org_id', width:70,
      render:(v:number) => <Text type="secondary" style={{ fontFamily:'var(--mono)', fontSize:12 }}>{v}</Text> },
    { title:'Каноническое название', dataIndex:'orgname', ellipsis:true,
      render:(v:string) => v || <Text type="secondary" italic>не указано</Text> },
    { title:'Названия', dataIndex:'names',
      render:(names:Organization['names']) => (
        <Space size={4} wrap>
          {names.slice(0,4).map(n => (
            <Tag key={n.id} color="blue" style={{ fontFamily:'var(--mono)', fontSize:11, margin:1 }}>
              [{n.lang}] {n.name.length > 55 ? n.name.slice(0,52)+'…' : n.name}
            </Tag>
          ))}
          {names.length > 4 && <Tag color="default">+{names.length-4}</Tag>}
        </Space>
      ) },
    { title:'Страна', dataIndex:'country_id', width:90, render:(v:string) => v || '—' },
  ]

  return (
    <div>
      <div className="page-header">
        <div>
          <div className="page-title"><BankOutlined style={{ marginRight:8, color:'var(--amber-dim)' }}/>Организации</div>
          <div className="page-subtitle">Поиск по каноническому или локализованному названию</div>
        </div>
      </div>
      <div className="filter-bar">
        <Input.Search placeholder="Поиск по названию…" allowClear enterButton={<SearchOutlined />}
          style={{ width:400 }} onSearch={onSearch}
          onChange={e => !e.target.value && onSearch('')} />
        {total > 0 && <Text type="secondary" style={{ fontFamily:'var(--mono)', fontSize:12 }}>Найдено: {total}</Text>}
      </div>
      <Table dataSource={data} columns={columns} rowKey="org_id" loading={loading} size="middle"
        pagination={{ current:page, pageSize:PAGE_SIZE, total, showTotal:t=>`Всего: ${t}`,
          onChange:p => { setPage(p); fetch(search, p) } }}
        scroll={{ x:800 }}
        style={{ background:'#fff', borderRadius:8 }} />
    </div>
  )
}
