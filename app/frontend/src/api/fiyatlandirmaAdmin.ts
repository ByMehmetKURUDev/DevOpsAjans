import { getAPIBaseURL } from '../lib/config';

/**
 * Fiyatlandırma v5 — admin panelinin 6 fiyat tablosunu (pricing_scales,
 * pricing_profiles, pricing_services, pricing_addons, ai_pm_tiers,
 * pricing_inquiries) düzenlemesi için CRUD istemcisi.
 *
 * `@metagptx/web-sdk` yerine düz `fetch` kullanılıyor: bu altı tablo bu
 * oturumda eklendi, üretilmiş SDK büyük olasılıkla henüz onları tanımıyor
 * (SDK ayrı bir şemadan regenerate ediliyor, bu depoda elle
 * düzenlenemiyor — bkz. proje notları). `dependencies/entity_guard.py`
 * yazma işlemlerinde `Authorization: Bearer <token>` bekliyor (çerez değil);
 * jeton `sdkClient.ts`'nin belgelediği gibi `localStorage['token']`'da.
 */

const apiBase = () => `${getAPIBaseURL()}/api/v1/entities`;

function yetkiBasligi(): Record<string, string> {
  try {
    const token = localStorage.getItem('token');
    return token ? { Authorization: `Bearer ${token}` } : {};
  } catch {
    return {};
  }
}

async function ayikla(response: Response): Promise<never> {
  let detail: string | undefined;
  try {
    const body = await response.json();
    detail = body?.detail;
  } catch {
    /* JSON degil */
  }
  throw new Error(detail || `İstek başarısız (${response.status})`);
}

export interface FiyatV5Satir {
  id: number;
  [key: string]: unknown;
}

export const fiyatlandirmaAdminApi = {
  async list(table: string): Promise<FiyatV5Satir[]> {
    const response = await fetch(`${apiBase()}/${table}/all`, { headers: { ...yetkiBasligi() } });
    if (!response.ok) return ayikla(response);
    const data = await response.json();
    return data.items ?? [];
  },

  async create(table: string, data: Record<string, unknown>): Promise<FiyatV5Satir> {
    const response = await fetch(`${apiBase()}/${table}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...yetkiBasligi() },
      body: JSON.stringify(data),
    });
    if (!response.ok) return ayikla(response);
    return response.json();
  },

  async update(table: string, id: number, data: Record<string, unknown>): Promise<FiyatV5Satir> {
    const response = await fetch(`${apiBase()}/${table}/${id}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json', ...yetkiBasligi() },
      body: JSON.stringify(data),
    });
    if (!response.ok) return ayikla(response);
    return response.json();
  },

  async remove(table: string, id: number): Promise<void> {
    const response = await fetch(`${apiBase()}/${table}/${id}`, {
      method: 'DELETE',
      headers: { ...yetkiBasligi() },
    });
    if (!response.ok) return ayikla(response);
  },
};
