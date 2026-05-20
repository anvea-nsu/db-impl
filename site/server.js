const express = require('express');
const { Pool } = require('pg');
const multer = require('multer');
const cors = require('cors');
const { spawn } = require('child_process');
const path = require('path');
const fs = require('fs');

const app = express();
const PORT = 3000;

// ── PostgreSQL connection ──────────────────────────────────────────────────
const pool = new Pool({
  host:     process.env.DB_HOST     || 'localhost',
  port:     parseInt(process.env.DB_PORT || '5432'),
  database: process.env.DB_NAME     || 'publication_db',
  user:     process.env.DB_USER     || 'anvea',
  password: process.env.DB_PASSWORD || '',
});

// ── Middleware ─────────────────────────────────────────────────────────────
app.use(cors());
app.use(express.json());
app.use(express.static(path.join(__dirname, 'public')));

// Uploads directory for imported files
const UPLOADS_DIR = path.join(__dirname, 'uploads');
if (!fs.existsSync(UPLOADS_DIR)) fs.mkdirSync(UPLOADS_DIR);
const upload = multer({ dest: UPLOADS_DIR });

// Scripts directory
const SCRIPTS_DIR = path.join(__dirname, 'scripts');

// ── Helper: run query safely ───────────────────────────────────────────────
async function query(sql, params = []) {
  const client = await pool.connect();
  try {
    const res = await client.query(sql, params);
    return res;
  } finally {
    client.release();
  }
}

// ══════════════════════════════════════════════════════════════════════════
// API: Connection test
// ══════════════════════════════════════════════════════════════════════════
app.get('/api/ping', async (req, res) => {
  try {
    await query('SELECT 1');
    res.json({ ok: true });
  } catch (e) {
    res.status(500).json({ ok: false, error: e.message });
  }
});

// DB config endpoint (for UI display)
app.get('/api/config', (req, res) => {
  res.json({
    host: pool.options.host,
    port: pool.options.port,
    database: pool.options.database,
    user: pool.options.user,
  });
});

// ══════════════════════════════════════════════════════════════════════════
// API: Generic table operations
// ══════════════════════════════════════════════════════════════════════════

// List all available tables
app.get('/api/tables', async (req, res) => {
  try {
    const r = await query(`
      SELECT table_name
      FROM information_schema.tables
      WHERE table_schema = 'public' AND table_type = 'BASE TABLE'
      ORDER BY table_name
    `);
    res.json(r.rows.map(r => r.table_name));
  } catch (e) {
    res.status(500).json({ error: e.message });
  }
});

// Get table columns
app.get('/api/tables/:table/columns', async (req, res) => {
  const { table } = req.params;
  try {
    const r = await query(`
      SELECT column_name, data_type, is_nullable, column_default,
             character_maximum_length
      FROM information_schema.columns
      WHERE table_schema = 'public' AND table_name = $1
      ORDER BY ordinal_position
    `, [table]);
    res.json(r.rows);
  } catch (e) {
    res.status(500).json({ error: e.message });
  }
});

// Get rows with pagination, search, sort
app.get('/api/tables/:table/rows', async (req, res) => {
  const { table } = req.params;
  const page    = Math.max(1, parseInt(req.query.page  || '1'));
  const limit   = Math.min(200, Math.max(1, parseInt(req.query.limit || '50')));
  const offset  = (page - 1) * limit;
  const search  = req.query.search || '';
  const sortCol = req.query.sort   || '';
  const sortDir = req.query.dir === 'desc' ? 'DESC' : 'ASC';

  // Validate table name (prevent injection)
  const validTables = (await query(`
    SELECT table_name FROM information_schema.tables
    WHERE table_schema = 'public' AND table_type = 'BASE TABLE'
  `)).rows.map(r => r.table_name);

  if (!validTables.includes(table)) {
    return res.status(400).json({ error: 'Unknown table' });
  }

  // Get columns for search
  const colsRes = await query(`
    SELECT column_name, data_type FROM information_schema.columns
    WHERE table_schema = 'public' AND table_name = $1
    ORDER BY ordinal_position
  `, [table]);
  const cols = colsRes.rows;

  // Build WHERE clause for search
  let whereClause = '';
  const params = [];
  if (search) {
    const textCols = cols.filter(c =>
      ['character varying', 'text', 'character', 'varchar'].includes(c.data_type)
    );
    if (textCols.length > 0) {
      const conditions = textCols.map((c, i) => {
        params.push(`%${search}%`);
        return `"${c.column_name}"::text ILIKE $${i + 1}`;
      });
      whereClause = `WHERE ${conditions.join(' OR ')}`;
    }
  }

  // Build ORDER BY
  let orderClause = '';
  const validCols = cols.map(c => c.column_name);
  if (sortCol && validCols.includes(sortCol)) {
    orderClause = `ORDER BY "${sortCol}" ${sortDir}`;
  } else if (validCols.length > 0) {
    orderClause = `ORDER BY "${validCols[0]}" ${sortDir}`;
  }

  try {
    const countRes = await query(
      `SELECT COUNT(*) FROM "${table}" ${whereClause}`, params
    );
    const total = parseInt(countRes.rows[0].count);

    const rowsRes = await query(
      `SELECT * FROM "${table}" ${whereClause} ${orderClause} LIMIT ${limit} OFFSET ${offset}`,
      params
    );

    res.json({
      rows: rowsRes.rows,
      total,
      page,
      limit,
      pages: Math.ceil(total / limit),
    });
  } catch (e) {
    res.status(500).json({ error: e.message });
  }
});

// Insert a row
app.post('/api/tables/:table/rows', async (req, res) => {
  const { table } = req.params;
  const data = req.body;

  const validTables = (await query(`
    SELECT table_name FROM information_schema.tables
    WHERE table_schema = 'public' AND table_type = 'BASE TABLE'
  `)).rows.map(r => r.table_name);
  if (!validTables.includes(table)) {
    return res.status(400).json({ error: 'Unknown table' });
  }

  const keys = Object.keys(data).filter(k => data[k] !== '' && data[k] !== null);
  if (keys.length === 0) return res.status(400).json({ error: 'No data provided' });

  const cols  = keys.map(k => `"${k}"`).join(', ');
  const vals  = keys.map((_, i) => `$${i + 1}`).join(', ');
  const values = keys.map(k => data[k] === '' ? null : data[k]);

  try {
    const r = await query(
      `INSERT INTO "${table}" (${cols}) VALUES (${vals}) RETURNING *`,
      values
    );
    res.json(r.rows[0]);
  } catch (e) {
    res.status(500).json({ error: e.message });
  }
});

// Update a row by primary key
app.put('/api/tables/:table/rows/:pk', async (req, res) => {
  const { table, pk } = req.params;
  const data = req.body;

  const validTables = (await query(`
    SELECT table_name FROM information_schema.tables
    WHERE table_schema = 'public' AND table_type = 'BASE TABLE'
  `)).rows.map(r => r.table_name);
  if (!validTables.includes(table)) {
    return res.status(400).json({ error: 'Unknown table' });
  }

  // Find PK column
  const pkRes = await query(`
    SELECT kcu.column_name
    FROM information_schema.table_constraints tc
    JOIN information_schema.key_column_usage kcu
      ON tc.constraint_name = kcu.constraint_name
    WHERE tc.table_schema = 'public'
      AND tc.table_name = $1
      AND tc.constraint_type = 'PRIMARY KEY'
    LIMIT 1
  `, [table]);

  if (!pkRes.rows.length) return res.status(400).json({ error: 'No primary key found' });
  const pkCol = pkRes.rows[0].column_name;

  const keys = Object.keys(data).filter(k => k !== pkCol);
  if (keys.length === 0) return res.status(400).json({ error: 'No fields to update' });

  const sets = keys.map((k, i) => `"${k}" = $${i + 1}`).join(', ');
  const values = keys.map(k => data[k] === '' ? null : data[k]);
  values.push(pk);

  try {
    const r = await query(
      `UPDATE "${table}" SET ${sets} WHERE "${pkCol}" = $${values.length} RETURNING *`,
      values
    );
    if (!r.rows.length) return res.status(404).json({ error: 'Row not found' });
    res.json(r.rows[0]);
  } catch (e) {
    res.status(500).json({ error: e.message });
  }
});

// Delete a row by primary key
app.delete('/api/tables/:table/rows/:pk', async (req, res) => {
  const { table, pk } = req.params;

  const validTables = (await query(`
    SELECT table_name FROM information_schema.tables
    WHERE table_schema = 'public' AND table_type = 'BASE TABLE'
  `)).rows.map(r => r.table_name);
  if (!validTables.includes(table)) {
    return res.status(400).json({ error: 'Unknown table' });
  }

  const pkRes = await query(`
    SELECT kcu.column_name
    FROM information_schema.table_constraints tc
    JOIN information_schema.key_column_usage kcu
      ON tc.constraint_name = kcu.constraint_name
    WHERE tc.table_schema = 'public'
      AND tc.table_name = $1
      AND tc.constraint_type = 'PRIMARY KEY'
    LIMIT 1
  `, [table]);

  if (!pkRes.rows.length) return res.status(400).json({ error: 'No primary key found' });
  const pkCol = pkRes.rows[0].column_name;

  try {
    await query(`DELETE FROM "${table}" WHERE "${pkCol}" = $1`, [pk]);
    res.json({ ok: true });
  } catch (e) {
    res.status(500).json({ error: e.message });
  }
});

// ══════════════════════════════════════════════════════════════════════════
// API: Statistics
// ══════════════════════════════════════════════════════════════════════════
app.get('/api/stats', async (req, res) => {
  try {
    const tables = ['articles', 'journals', 'authors', 'organizations', 'databases', 'issues'];
    const counts = {};
    for (const t of tables) {
      try {
        const r = await query(`SELECT COUNT(*) FROM "${t}"`);
        counts[t] = parseInt(r.rows[0].count);
      } catch {
        counts[t] = 0;
      }
    }
    res.json(counts);
  } catch (e) {
    res.status(500).json({ error: e.message });
  }
});

// ══════════════════════════════════════════════════════════════════════════
// API: Run Python import scripts
// ══════════════════════════════════════════════════════════════════════════

function runScript(scriptName, args, res) {
  const scriptPath = path.join(SCRIPTS_DIR, scriptName);
  if (!fs.existsSync(scriptPath)) {
    return res.status(404).json({ error: `Script not found: ${scriptName}` });
  }

  res.setHeader('Content-Type', 'text/event-stream');
  res.setHeader('Cache-Control', 'no-cache');
  res.setHeader('Connection', 'keep-alive');

  const proc = spawn('python3', [scriptPath, ...args]);

  proc.stdout.on('data', (data) => {
    const lines = data.toString().split('\n');
    lines.forEach(line => {
      if (line.trim()) res.write(`data: ${JSON.stringify({ type: 'stdout', text: line })}\n\n`);
    });
  });

  proc.stderr.on('data', (data) => {
    const lines = data.toString().split('\n');
    lines.forEach(line => {
      if (line.trim()) res.write(`data: ${JSON.stringify({ type: 'stderr', text: line })}\n\n`);
    });
  });

  proc.on('close', (code) => {
    res.write(`data: ${JSON.stringify({ type: 'exit', code })}\n\n`);
    res.end();
  });

  proc.on('error', (err) => {
    res.write(`data: ${JSON.stringify({ type: 'error', text: err.message })}\n\n`);
    res.end();
  });
}

// Import from XML (eLibrary articles)
app.post('/api/import/xml', upload.single('file'), (req, res) => {
  if (!req.file) return res.status(400).json({ error: 'No file uploaded' });
  const xmlPath = req.file.path;
  // Rename with original extension
  const finalPath = xmlPath + '.xml';
  fs.renameSync(xmlPath, finalPath);
  runScript('import_from_xml.py', [finalPath], res);
});

// Import from JSON (journals)
app.post('/api/import/json', upload.single('file'), (req, res) => {
  if (!req.file) return res.status(400).json({ error: 'No file uploaded' });
  // The JSON script reads DATA_FILE = Path("journals.json") relative to CWD
  // So we copy the file to scripts/ as journals.json
  const dest = path.join(SCRIPTS_DIR, 'journals.json');
  fs.copyFileSync(req.file.path, dest);
  fs.unlinkSync(req.file.path);

  res.setHeader('Content-Type', 'text/event-stream');
  res.setHeader('Cache-Control', 'no-cache');
  res.setHeader('Connection', 'keep-alive');

  const proc = spawn('python3', [path.join(SCRIPTS_DIR, 'import_from_json.py')], {
    cwd: SCRIPTS_DIR,
  });

  proc.stdout.on('data', (data) => {
    data.toString().split('\n').forEach(line => {
      if (line.trim()) res.write(`data: ${JSON.stringify({ type: 'stdout', text: line })}\n\n`);
    });
  });
  proc.stderr.on('data', (data) => {
    data.toString().split('\n').forEach(line => {
      if (line.trim()) res.write(`data: ${JSON.stringify({ type: 'stderr', text: line })}\n\n`);
    });
  });
  proc.on('close', (code) => {
    res.write(`data: ${JSON.stringify({ type: 'exit', code })}\n\n`);
    res.end();
  });
  proc.on('error', (err) => {
    res.write(`data: ${JSON.stringify({ type: 'error', text: err.message })}\n\n`);
    res.end();
  });
});

// ── Start ──────────────────────────────────────────────────────────────────
app.listen(PORT, () => {
  console.log(`\n╔═══════════════════════════════════════╗`);
  console.log(`║  PubDB Admin running on               ║`);
  console.log(`║  http://localhost:${PORT}               ║`);
  console.log(`╚═══════════════════════════════════════╝\n`);
});
