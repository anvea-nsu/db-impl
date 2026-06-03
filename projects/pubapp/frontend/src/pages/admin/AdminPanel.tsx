import { useState, useEffect, useCallback } from 'react'
import { Layout, Menu, Table, Button, Modal, Form, Input, InputNumber, Select,
  Space, Popconfirm, message, Typography, Tag, Tooltip, Badge, Spin, Alert } from 'antd'
import { PlusOutlined, EditOutlined, DeleteOutlined, ReloadOutlined,
  DatabaseOutlined, SearchOutlined } from '@ant-design/icons'
import api from '../../api/client'

const { Sider, Content } = Layout
const { Text } = Typography

// ── Types ─────────────────────────────────────────────────────────────────────
interface TableInfo { table: string; pk: string; count: number }
interface ColDef { name: string; type: string; nullable: boolean; serial: boolean; pk: boolean }
interface RawData { total: number; columns: string[]; rows: Record<string,any>[] }

// ── API helpers ───────────────────────────────────────────────────────────────
const adminRaw = {
  tables:  ()                         => api.get<TableInfo[]>('/admin/tables'),
  schema:  (t:string)                 => api.get<ColDef[]>(`/admin/schema/${t}`),
  list:    (t:string, p:Record<string,unknown>) => api.get<RawData>(`/admin/raw/${t}`, {params:p}),
  insert:  (t:string, d:Record<string,unknown>) => api.post(`/admin/raw/${t}`, d),
  update:  (t:string, pk:string|number, d:Record<string,unknown>) => api.put(`/admin/raw/${t}/${pk}`, d),
  remove:  (t:string, pk:string|number) => api.delete(`/admin/raw/${t}/${pk}`),
}

const PAGE_SIZE = 100

// Map PostgreSQL types → Ant Design input type
function inputType(pgType: string): 'text'|'number'|'bool'|'date' {
  if (['integer','smallint','bigint','serial','numeric','real','double precision','float'].some(t=>pgType.includes(t))) return 'number'
  if (pgType==='boolean') return 'bool'
  if (pgType.includes('date') || pgType.includes('timestamp')) return 'date'
  return 'text'
}

// Render a cell value nicely
function CellVal({ val, pgType }: { val:any; pgType:string }) {
  if (val===null||val===undefined) return <Text type="secondary" style={{fontSize:11}}>null</Text>
  if (typeof val==='boolean'||pgType==='boolean')
    return <Tag color={val?'success':'error'} style={{fontFamily:'var(--mono)',fontSize:11}}>{String(val)}</Tag>
  const s = String(val)
  if (s.length > 80) return <Tooltip title={s}><span style={{fontSize:12}}>{s.slice(0,77)}…</span></Tooltip>
  if (pgType.includes('int')||pgType.includes('float')||pgType.includes('numeric'))
    return <Text style={{fontFamily:'var(--mono)',fontSize:12}}>{s}</Text>
  return <span style={{fontSize:12}}>{s}</span>
}

// ── Row form (add / edit) ─────────────────────────────────────────────────────
function RowForm({ cols, initialValues, onOk, onCancel }:
  { cols:ColDef[]; initialValues?:Record<string,any>; onOk:(v:Record<string,any>)=>Promise<void>; onCancel:()=>void }) {
  const [form] = Form.useForm()
  const [saving, setSaving] = useState(false)
  const isEdit = !!initialValues

  useEffect(() => { form.setFieldsValue(initialValues||{}) }, [initialValues, form])

  const submit = async () => {
    setSaving(true)
    try {
      const vals = await form.validateFields()
      await onOk(vals)
    } catch (e:any) {
      if (e?.errorFields) return // antd validation
      message.error(e?.response?.data?.detail || String(e?.message || e))
    } finally { setSaving(false) }
  }

  // Filter editable cols
  const editableCols = cols.filter(c => isEdit ? !c.pk : !c.serial)

  return (
    <Modal
      open title={isEdit ? 'Редактировать запись' : 'Добавить запись'}
      onOk={submit} onCancel={onCancel} okText={isEdit?'Сохранить':'Добавить'}
      confirmLoading={saving} width={560} destroyOnClose>
      <Form form={form} layout="vertical" style={{marginTop:12}}>
        {editableCols.map(col=>{
          const t = inputType(col.type)
          const label = (
            <span>
              {col.name}
              <Text type="secondary" style={{fontFamily:'var(--mono)',fontSize:10,marginLeft:6}}>{col.type}</Text>
              {col.nullable && <Text type="secondary" style={{fontSize:10,marginLeft:4}}>nullable</Text>}
            </span>
          )
          return (
            <Form.Item key={col.name} name={col.name} label={label}
              rules={col.nullable ? [] : [{required:true, message:`${col.name} обязательно`}]}>
              {t==='bool'
                ? <Select options={[{value:true,label:'true'},{value:false,label:'false'},{value:null,label:'null'}]} allowClear />
                : t==='number'
                  ? <InputNumber style={{width:'100%'}} />
                  : <Input />}
            </Form.Item>
          )
        })}
      </Form>
    </Modal>
  )
}

// ── Main component ────────────────────────────────────────────────────────────
export default function AdminPanel() {
  const [tables, setTables]       = useState<TableInfo[]>([])
  const [tablesLoading, setTL]    = useState(false)
  const [activeTable, setActive]  = useState<string>('')
  const [schema, setSchema]       = useState<ColDef[]>([])
  const [rawData, setRawData]     = useState<RawData|null>(null)
  const [dataLoading, setDL]      = useState(false)
  const [page, setPage]           = useState(1)
  const [search, setSearch]       = useState('')
  const [editing, setEditing]     = useState<Record<string,any>|null>(null)
  const [adding, setAdding]       = useState(false)
  const [error, setError]         = useState<string|null>(null)

  // Load table list
  const loadTables = useCallback(async () => {
    setTL(true)
    try { const r = await adminRaw.tables(); setTables(r.data) }
    catch (e:any) { setError(e?.response?.data?.detail||String(e)) }
    finally { setTL(false) }
  }, [])

  useEffect(() => { loadTables() }, [loadTables])

  // Load schema when table changes
  useEffect(() => {
    if (!activeTable) return
    adminRaw.schema(activeTable).then(r => setSchema(r.data)).catch(()=>{})
  }, [activeTable])

  // Load rows
  const loadData = useCallback(async (tbl:string, p:number, q:string) => {
    if (!tbl) return
    setDL(true); setError(null)
    try {
      const params:Record<string,unknown> = { skip:(p-1)*PAGE_SIZE, limit:PAGE_SIZE }
      if (q) params.search = q
      const r = await adminRaw.list(tbl, params)
      setRawData(r.data)
    } catch (e:any) { setError(e?.response?.data?.detail||String(e)); setRawData(null) }
    finally { setDL(false) }
  }, [])

  useEffect(() => {
    if (activeTable) { setPage(1); setSearch(''); loadData(activeTable,1,'') }
  }, [activeTable, loadData])

  // Build Ant Design Table columns dynamically
  const pkField = tables.find(t=>t.table===activeTable)?.pk || 'id'
  const schemaMap = Object.fromEntries(schema.map(c=>[c.name,c]))

  const tableCols = rawData
    ? [
        ...rawData.columns.map(col => ({
          title: (
            <span>
              {col}
              {schemaMap[col]?.pk && <Tag color="gold" style={{marginLeft:4,fontSize:9,padding:'0 3px'}}>PK</Tag>}
              <br/>
              <span style={{fontFamily:'var(--mono)',fontSize:9,color:'var(--text-muted)',fontWeight:400}}>
                {schemaMap[col]?.type||''}
              </span>
            </span>
          ),
          dataIndex: col,
          key: col,
          ellipsis: true,
          width: schemaMap[col]?.pk ? 90
               : schemaMap[col]?.type==='boolean' ? 80
               : schemaMap[col]?.type?.includes('int') ? 90
               : 180,
          render: (val:any) => <CellVal val={val} pgType={schemaMap[col]?.type||''} />,
        })),
        {
          title: '',
          key: '__actions__',
          fixed: 'right' as const,
          width: 80,
          render: (_:any, row:Record<string,any>) => (
            <Space size={4}>
              <Tooltip title="Редактировать">
                <Button size="small" icon={<EditOutlined />} onClick={()=>setEditing(row)} />
              </Tooltip>
              <Popconfirm
                title="Удалить эту запись?"
                description="Это действие необратимо"
                onConfirm={async () => {
                  try {
                    await adminRaw.remove(activeTable, row[pkField])
                    message.success('Запись удалена')
                    loadData(activeTable, page, search)
                    loadTables()
                  } catch (e:any) {
                    message.error(e?.response?.data?.detail||'Ошибка удаления')
                  }
                }}
                okText="Удалить" cancelText="Отмена" okButtonProps={{danger:true}}>
                <Button size="small" danger icon={<DeleteOutlined />} />
              </Popconfirm>
            </Space>
          ),
        },
      ]
    : []

  const handleAdd = async (vals: Record<string,any>) => {
    await adminRaw.insert(activeTable, vals)
    message.success('Запись добавлена')
    setAdding(false)
    loadData(activeTable, page, search)
    loadTables()
  }

  const handleEdit = async (vals: Record<string,any>) => {
    await adminRaw.update(activeTable, editing![pkField], vals)
    message.success('Запись обновлена')
    setEditing(null)
    loadData(activeTable, page, search)
  }

  // Menu items
  const menuItems = tables.map(t=>({
    key: t.table,
    icon: <DatabaseOutlined style={{fontSize:12,color:'#555'}} />,
    label: (
      <span style={{display:'flex',justifyContent:'space-between',alignItems:'center',gap:4,minWidth:0}}>
        <span style={{fontFamily:'var(--mono)',fontSize:11,color:'#1a1a2e',overflow:'hidden',textOverflow:'ellipsis',whiteSpace:'nowrap',flex:1}}
          title={t.table}>{t.table}</span>
        <Badge count={t.count} showZero
          style={{backgroundColor:t.count>0?'var(--navy)':'#bbb',fontSize:9,height:16,lineHeight:'16px',padding:'0 4px',flexShrink:0}} />
      </span>
    ),
  }))

  return (
    <div>
      <div className="page-header">
        <div>
          <div className="page-title"><DatabaseOutlined style={{marginRight:8,color:'var(--amber-dim)'}}/>
            База данных
          </div>
          <div className="page-subtitle">
            {tables.length} таблиц · {tables.reduce((s,t)=>s+t.count,0).toLocaleString()} записей
          </div>
        </div>
      </div>

      <Layout style={{background:'#fff', borderRadius:8, border:'1px solid var(--border)', overflow:'hidden', minHeight:600}}>
        {/* Left: table list */}
        <Sider width={230} className="admin-sider" style={{background:'#f8fafc', borderRight:'1px solid var(--border)'}}>
          <div style={{padding:'12px 12px 8px', borderBottom:'1px solid var(--border)'}}>
            <div style={{fontSize:11, color:'#666', fontFamily:'var(--mono)', textTransform:'uppercase', letterSpacing:1}}>
              Таблицы
            </div>
          </div>
          {tablesLoading
            ? <div style={{padding:20,textAlign:'center'}}><Spin size="small"/></div>
            : <Menu mode="inline" theme="light" selectedKeys={[activeTable]}
                onClick={({key})=>setActive(key)}
                style={{background:'transparent',border:'none',fontSize:12,color:'#1a1a2e',overflow:'hidden'}}
                items={menuItems} />
          }
        </Sider>

        {/* Right: table content */}
        <Content style={{padding:20, overflow:'auto'}}>
          {!activeTable && (
            <div style={{textAlign:'center',padding:80,color:'var(--text-muted)'}}>
              <DatabaseOutlined style={{fontSize:48,opacity:0.2,display:'block',marginBottom:12}}/>
              Выберите таблицу из списка слева
            </div>
          )}

          {activeTable && (
            <>
              {/* Toolbar */}
              <div style={{display:'flex',gap:10,marginBottom:14,alignItems:'center',flexWrap:'wrap'}}>
                <Text strong style={{fontFamily:'var(--mono)',fontSize:14,color:'var(--navy)'}}>{activeTable}</Text>
                <Input.Search
                  placeholder="Поиск по текстовым полям…"
                  style={{width:260}} size="small"
                  value={search}
                  onChange={e=>setSearch(e.target.value)}
                  onSearch={q=>{setPage(1);loadData(activeTable,1,q)}}
                  allowClear
                  enterButton={<SearchOutlined />}
                />
                <Button size="small" icon={<ReloadOutlined />}
                  onClick={()=>loadData(activeTable,page,search)}>
                  Обновить
                </Button>
                <Button size="small" type="primary" icon={<PlusOutlined />}
                  style={{background:'var(--navy)'}}
                  onClick={()=>setAdding(true)}>
                  Добавить запись
                </Button>
                {rawData && (
                  <Text type="secondary" style={{fontFamily:'var(--mono)',fontSize:12}}>
                    Всего: {rawData.total.toLocaleString()}
                  </Text>
                )}
              </div>

              {/* Schema bar */}
              {schema.length>0 && (
                <div style={{marginBottom:10,display:'flex',gap:4,flexWrap:'wrap'}}>
                  {schema.map(c=>(
                    <Tag key={c.name}
                      color={c.pk?'gold':c.serial?'cyan':c.nullable?undefined:'blue'}
                      style={{fontFamily:'var(--mono)',fontSize:10,margin:'1px'}}>
                      {c.name}
                      <span style={{opacity:0.6,marginLeft:3}}>{c.type}</span>
                    </Tag>
                  ))}
                </div>
              )}

              {error && <Alert type="error" message={error} style={{marginBottom:12}} closable onClose={()=>setError(null)} />}

              <Table
                dataSource={rawData?.rows || []}
                columns={tableCols}
                rowKey={pkField}
                loading={dataLoading}
                size="small"
                scroll={{ x: Math.max(800, (rawData?.columns.length||0)*120) }}
                pagination={{
                  current: page,
                  pageSize: PAGE_SIZE,
                  total: rawData?.total || 0,
                  showTotal: t=>`${t.toLocaleString()} записей`,
                  showSizeChanger: false,
                  onChange: p => { setPage(p); loadData(activeTable,p,search) },
                }}
                locale={{ emptyText: dataLoading ? 'Загрузка…' : 'Нет данных' }}
              />
            </>
          )}
        </Content>
      </Layout>

      {/* Add modal */}
      {adding && schema.length>0 && (
        <RowForm cols={schema} onOk={handleAdd} onCancel={()=>setAdding(false)} />
      )}

      {/* Edit modal */}
      {editing && schema.length>0 && (
        <RowForm cols={schema} initialValues={editing} onOk={handleEdit} onCancel={()=>setEditing(null)} />
      )}
    </div>
  )
}
