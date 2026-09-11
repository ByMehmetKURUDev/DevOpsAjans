import { client } from '@/lib/sdkClient';

const BASE = '/api/v1/entities/notifications';

export interface DeliveryLogItem {
  id: number;
  created_at?: string;
  event_type: string;
  title: string;
  recipient_email: string;
  channel: string;
  delivery_status?: string;
  delivery_detail?: string;
}

export interface DeliveryLog {
  items: DeliveryLogItem[];
  total: number;
  /** { email: { sent: 4, skipped: 2 }, sms: { … } } */
  summary: Record<string, Record<string, number>>;
}

export async function fetchDeliveryLog(status?: string): Promise<DeliveryLog> {
  const params = new URLSearchParams({ limit: '100' });
  if (status) params.set('status', status);
  const res = (await client.apiCall.invoke({
    method: 'GET',
    url: `${BASE}/log?${params}`,
  })) as { data?: DeliveryLog };
  return res?.data ?? { items: [], total: 0, summary: {} };
}

export interface TestResult {
  channel: string;
  status: string;
  detail: string;
}

export async function testChannel(channel: string, target: string): Promise<TestResult> {
  const res = (await client.apiCall.invoke({
    method: 'POST',
    url: `${BASE}/test`,
    data: { channel, target },
  })) as { data?: TestResult };
  return res?.data as TestResult;
}

/**
 * Bildirim şablonları.
 *
 * Her olayın başlığı ve gövdesi panelde düzenlenebiliyor; ayar anahtarı
 * `notify_tpl_<olay>_title` / `_body`. Boş bırakılan alanda sunucudaki
 * varsayılan kullanılıyor.
 *
 * Yer tutucular olay başına farklı: iletişim mesajında gönderenin adı,
 * projede aşama adı var. Aşağıdaki liste panelde ipucu olarak gösteriliyor.
 */
export const NOTIFY_EVENTS = [
  {
    key: 'inquiry',
    labelKey: 'notifyAdmin.evInquiry',
    tokens: ['ad', 'eposta', 'telefon', 'konu', 'mesaj'],
  },
  {
    key: 'ticket',
    labelKey: 'notifyAdmin.evTicket',
    tokens: ['musteri', 'eposta', 'konu', 'oncelik', 'mesaj'],
  },
  {
    key: 'project_stage',
    labelKey: 'notifyAdmin.evStage',
    tokens: ['proje', 'asama', 'oncekiAsama', 'not', 'musteri'],
  },
] as const;

export function templateKeys(event: string): { title: string; body: string } {
  return { title: `notify_tpl_${event}_title`, body: `notify_tpl_${event}_body` };
}
