import axios from 'axios';

// FastAPI expects repeated query params for arrays: dbs=a&dbs=b
// Axios default sends dbs[]=a&dbs[]=b which FastAPI doesn't parse correctly
function serializeParams(params: Record<string, unknown>): string {
  const parts: string[] = [];
  for (const [key, val] of Object.entries(params)) {
    if (val === null || val === undefined) continue;
    if (Array.isArray(val)) {
      for (const item of val) {
        parts.push(`${encodeURIComponent(key)}=${encodeURIComponent(String(item))}`);
      }
    } else {
      parts.push(`${encodeURIComponent(key)}=${encodeURIComponent(String(val))}`);
    }
  }
  return parts.join('&');
}

const api = axios.create({
  baseURL: '/api',
  paramsSerializer: { serialize: serializeParams },
});

api.interceptors.request.use((config) => {
  const token = localStorage.getItem('token');
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

api.interceptors.response.use(
  (r) => r,
  (err) => {
    if (err.response?.status === 401) {
      // Only redirect if user was previously logged in (had a token)
      const hadToken = !!localStorage.getItem('token');
      localStorage.removeItem('token');
      localStorage.removeItem('user');
      if (hadToken) {
        window.location.href = '/login';
      }
    }
    return Promise.reject(err);
  }
);

export default api;

// ── Auth ─────────────────────────────────────────────────────────────────────
export const authApi = {
  login: (username: string, password: string) => {
    const form = new FormData();
    form.append('username', username);
    form.append('password', password);
    return api.post('/auth/token', form);
  },
  register: (data: { username?: string; email: string; password: string }) =>
    api.post('/auth/register', data),
  me: () => api.get('/auth/me'),
};

// ── Organizations ──────────────────────────────────────────────────────────
export const orgsApi = {
  list: (params?: Record<string, unknown>) => api.get('/organizations', { params }),
  get: (id: number) => api.get(`/organizations/${id}`),
};

// ── Journals ───────────────────────────────────────────────────────────────
export const journalsApi = {
  list: (params?: Record<string, unknown>) => api.get('/journals', { params }),
  get: (id: number) => api.get(`/journals/${id}`),
  top10: (params?: Record<string, unknown>) => api.get('/journals/top10', { params }),
  availableDbs: () => api.get('/journals/available-dbs'),
};

// ── Authors ────────────────────────────────────────────────────────────────
export const authorsApi = {
  list: (params?: Record<string, unknown>) => api.get('/authors', { params }),
  get: (id: number) => api.get(`/authors/${id}`),
  activity: (id: number, params?: Record<string, unknown>) =>
    api.get(`/authors/${id}/activity`, { params }),
  invalidSupportCount: (id: number, params?: Record<string, unknown>) =>
    api.get(`/authors/${id}/invalid-support-count`, { params }),
  kbpr: (id: number, params?: Record<string, unknown>) =>
    api.get(`/authors/${id}/kbpr`, { params }),
};

// ── Articles ───────────────────────────────────────────────────────────────
export const articlesApi = {
  list: (params?: Record<string, unknown>) => api.get('/articles', { params }),
  vakOnly: (params?: Record<string, unknown>) => api.get('/articles/vak-only', { params }),
  notIndexed: (params?: Record<string, unknown>) => api.get('/articles/not-indexed', { params }),
  contribution: (id: number, params?: Record<string, unknown>) =>
    api.get(`/articles/${id}/contribution`, { params }),
};

// ── Statistics ─────────────────────────────────────────────────────────────
export const statsApi = {
  overview: (params?: Record<string, unknown>) => api.get('/statistics/overview', { params }),
  availableDbs: () => api.get('/statistics/available-dbs'),
  orgSearch: (q: string) => api.get('/statistics/org-search', { params: { q } }),
};

// ── Authors extra ──────────────────────────────────────────────────────────
export const authorsOrgSearch = (q: string) =>
  api.get('/authors/org-search', { params: { q } });

// ── Import ─────────────────────────────────────────────────────────────────
export const importApi = {
  xml: (file: File) => {
    const fd = new FormData();
    fd.append('file', file);
    return api.post('/import/xml', fd, { timeout: 600_000 });
  },
  json: (file: File) => {
    const fd = new FormData();
    fd.append('file', file);
    return api.post('/import/json', fd, { timeout: 600_000 });
  },
};

// ── Admin ──────────────────────────────────────────────────────────────────
export const adminApi = {
  users: (p?: Record<string, unknown>) => api.get('/admin/users', { params: p }),
  setRole: (id: number, role: string) => api.patch(`/admin/users/${id}/role`, null, { params: { role } }),
  deleteUser: (id: number) => api.delete(`/admin/users/${id}`),
  list: (table: string, p?: Record<string, unknown>) => api.get(`/admin/${table}`, { params: p }),
  create: (table: string, data: unknown) => api.post(`/admin/${table}`, data),
  update: (table: string, id: number | string, data: unknown) => api.put(`/admin/${table}/${id}`, data),
  remove: (table: string, id: number | string) => api.delete(`/admin/${table}/${id}`),
};
