import axios, { type AxiosRequestConfig } from 'axios';

export const ACCESS_KEY = 'billing_access';
export const REFRESH_KEY = 'billing_refresh';
export const PORTAL_KEY = 'billing_portal';

const client = axios.create({ baseURL: '/api/v1', headers: { 'Content-Type': 'application/json' } });

client.interceptors.request.use((config) => {
  const isPortal = (config.url || '').startsWith('/portal/');
  const token = isPortal
    ? localStorage.getItem(PORTAL_KEY) || localStorage.getItem(ACCESS_KEY)
    : localStorage.getItem(ACCESS_KEY) || localStorage.getItem(PORTAL_KEY);
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

export type Envelope<T> = { data: T; meta?: Record<string, unknown> };

export async function apiGet<T>(path: string, params?: Record<string, unknown>): Promise<Envelope<T>> {
  const res = await client.get<Envelope<T>>(path, { params });
  return res.data;
}

export async function apiSend<T>(method: 'post' | 'patch' | 'delete', path: string, body?: unknown, config?: AxiosRequestConfig): Promise<Envelope<T>> {
  const res = await client.request<Envelope<T>>({ method, url: path, data: body, ...config });
  return res.data;
}

export function apiErrorMessage(error: unknown): string {
  const e = error as { response?: { data?: { error?: { message?: string } } }; message?: string };
  return e?.response?.data?.error?.message || e?.message || 'Something went wrong';
}

/** Fetch a raw (non-envelope) authenticated response body as text, e.g. SVG QR. */
export async function apiText(path: string): Promise<string> {
  const token = localStorage.getItem(ACCESS_KEY) || localStorage.getItem(PORTAL_KEY);
  const res = await fetch(`/api/v1${path}`, { headers: token ? { Authorization: `Bearer ${token}` } : {} });
  if (!res.ok) throw new Error(`Request failed (${res.status})`);
  return res.text();
}

export function setTokens(access: string, refresh?: string) {
  localStorage.setItem(ACCESS_KEY, access);
  if (refresh) localStorage.setItem(REFRESH_KEY, refresh);
  localStorage.removeItem(PORTAL_KEY);
}

export function clearTokens() {
  [ACCESS_KEY, REFRESH_KEY, PORTAL_KEY].forEach((key) => localStorage.removeItem(key));
}

/** Fetch an HTML document with the bearer token and print it in a new window. */
export async function printAuthenticatedHtml(url: string): Promise<void> {
  const token = localStorage.getItem(ACCESS_KEY) || localStorage.getItem(PORTAL_KEY);
  const res = await fetch(url, { headers: token ? { Authorization: `Bearer ${token}` } : {} });
  if (!res.ok) {
    throw new Error(`Print failed (${res.status})`);
  }
  const html = await res.text();
  const win = window.open('', '_blank');
  if (!win) throw new Error('Popup blocked. Enable popups to print.');
  win.document.open();
  win.document.write(html);
  win.document.close();
  // Give the browser a tick to render before printing.
  setTimeout(() => { try { win.focus(); win.print(); } catch { } }, 250);
}
