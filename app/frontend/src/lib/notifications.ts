import { useCallback, useEffect, useState } from 'react';
import { client } from '@/lib/sdkClient';

/**
 * Bildirimler.
 *
 * SDK'nın `entities` yardımcıları üretilmiş CRUD uçlarına bakıyor; bizim
 * uçlarımız kendi sorgu parametrelerini alıyor, o yüzden doğrudan
 * `apiCall` kullanılıyor. Adres yine aynı origin'e göreli.
 */
export interface AppNotification {
  id: number;
  recipient_email: string;
  recipient_role?: string;
  event_type: string;
  title: string;
  body?: string;
  link?: string;
  channel: string;
  delivery_status?: string;
  delivery_detail?: string;
  ref_type?: string;
  ref_id?: number;
  read_at?: string | null;
  created_at?: string;
}

interface ListResponse {
  items: AppNotification[];
  total: number;
  unread: number;
}

const BASE = '/api/v1/entities/notifications';

export async function fetchNotifications(
  email: string,
  options: { channel?: string; unreadOnly?: boolean; limit?: number } = {},
): Promise<ListResponse> {
  const params = new URLSearchParams({
    recipient_email: email,
    channel: options.channel ?? 'inapp',
    unread_only: String(Boolean(options.unreadOnly)),
    limit: String(options.limit ?? 30),
  });
  const res = (await client.apiCall.invoke({
    method: 'GET',
    url: `${BASE}?${params}`,
  })) as { data?: ListResponse };
  return res?.data ?? { items: [], total: 0, unread: 0 };
}

export async function markNotificationsRead(email: string, ids?: number[]): Promise<void> {
  const params = new URLSearchParams({ recipient_email: email });
  await client.apiCall.invoke({
    method: 'POST',
    url: `${BASE}/mark-read?${params}`,
    data: { ids: ids ?? null },
  });
}

/**
 * Çan için veri.
 *
 * Yoklama aralığı 60 saniye: bildirim anlık olmak zorunda değil, ama
 * sayfayı yenilemeden görünmeli. Sekme arkaplandayken yoklama durur —
 * açık bırakılan bir sekme boşuna istek atmasın.
 */
export function useNotifications(email: string | undefined) {
  const [items, setItems] = useState<AppNotification[]>([]);
  const [unread, setUnread] = useState(0);
  const [loading, setLoading] = useState(false);

  const reload = useCallback(async () => {
    if (!email) return;
    setLoading(true);
    try {
      const data = await fetchNotifications(email);
      setItems(data.items);
      setUnread(data.unread);
    } catch {
      // Bildirim listesi alınamazsa panel çalışmaya devam etmeli.
    } finally {
      setLoading(false);
    }
  }, [email]);

  useEffect(() => {
    if (!email) return;
    void reload();

    const tik = () => {
      if (document.visibilityState === 'visible') void reload();
    };
    const zamanlayici = window.setInterval(tik, 60_000);
    document.addEventListener('visibilitychange', tik);
    return () => {
      window.clearInterval(zamanlayici);
      document.removeEventListener('visibilitychange', tik);
    };
  }, [email, reload]);

  const markAllRead = useCallback(async () => {
    if (!email || unread === 0) return;
    // İyimser güncelleme: rozet hemen sıfırlanıyor, istek arkada gidiyor.
    setUnread(0);
    setItems((liste) => liste.map((i) => ({ ...i, read_at: i.read_at ?? new Date().toISOString() })));
    try {
      await markNotificationsRead(email);
    } catch {
      void reload();
    }
  }, [email, unread, reload]);

  return { items, unread, loading, reload, markAllRead };
}
