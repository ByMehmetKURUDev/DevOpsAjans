import { client } from '@/lib/sdkClient';

/**
 * İçerik takvimi — veri katmanı.
 *
 * Plan tutuyor, yayın yapmıyor. Nedeni models/content_posts.py içinde
 * yazılı: platformlar program üzerinden gönderi için onaylı uygulama
 * istiyor ve ücretsiz arka uç uykuya geçtiği için zamanlanmış bir iş
 * saatinde çalışmıyor. Bu yüzden akış "hazırla → onayla → zamanı gelince
 * tek tuşla kopyala ve paylaş".
 */

export type Kanal = 'instagram' | 'facebook' | 'linkedin' | 'x' | 'blog' | 'email';
export type Durum = 'draft' | 'approved' | 'published';

export interface Gonderi {
  id: number;
  title: string;
  channel?: string;
  body?: string;
  hashtags?: string;
  image_url?: string;
  link_url?: string;
  scheduled_at?: string;
  status?: string;
  campaign?: string;
  notes?: string;
  published_at?: string;
}

export const KANALLAR: Kanal[] = ['instagram', 'facebook', 'linkedin', 'x', 'blog', 'email'];

/**
 * Kanalın yazma ekranı.
 *
 * Metni adrese gömmüyoruz: Instagram ve LinkedIn gövdeyi bağlantıdan
 * almıyor, X alıyor ama uzun metinde kesiyor. Her kanalda aynı davranış
 * olsun diye metin panoya kopyalanıyor, bağlantı yalnızca doğru ekranı
 * açıyor. "Bazı kanallarda dolu geliyor, bazılarında gelmiyor" hâli
 * kullanıcının kafasını karıştırmaktan başka işe yaramıyor.
 */
export const KANAL_ADRESI: Record<Kanal, string> = {
  instagram: 'https://www.instagram.com/',
  facebook: 'https://www.facebook.com/',
  linkedin: 'https://www.linkedin.com/feed/?shareActive=true',
  x: 'https://x.com/compose/post',
  blog: '/admin',
  email: 'https://mail.google.com/mail/u/0/#inbox?compose=new',
};

/** Kanalın karakter sınırı; aşılırsa panelde uyarı çıkıyor. */
export const KANAL_SINIRI: Partial<Record<Kanal, number>> = {
  instagram: 2200,
  x: 280,
  linkedin: 3000,
  facebook: 63206,
};

export function gonderiMetni(g: Gonderi): string {
  const parcalar = [g.body?.trim(), g.link_url?.trim(), g.hashtags?.trim()].filter(Boolean);
  return parcalar.join('\n\n');
}

function govdeyiCoz(yanit: unknown): { items?: Gonderi[] } {
  const kok = (yanit ?? {}) as Record<string, unknown>;
  return ('data' in kok ? kok.data : kok) as { items?: Gonderi[] };
}

export async function gonderileriGetir(): Promise<Gonderi[]> {
  const yanit = await client.entities.content_posts.query({ sort: 'scheduled_at', limit: 300 });
  return govdeyiCoz(yanit)?.items ?? [];
}

export async function gonderiOlustur(veri: Partial<Gonderi>): Promise<void> {
  await client.entities.content_posts.create({ data: veri });
}

export async function gonderiGuncelle(id: number, veri: Partial<Gonderi>): Promise<void> {
  await client.entities.content_posts.update({ id: String(id), data: veri });
}

export async function gonderiSil(id: number): Promise<void> {
  await client.entities.content_posts.delete({ id: String(id) });
}

/**
 * Zamanı geçmiş ama hâlâ paylaşılmamış gönderiler.
 *
 * Hatırlatma e-postası SÖZ VERMİYORUZ: sunucudaki e-posta sağlayıcısı
 * yapılandırılmamış durumda ve gitmeyen bir hatırlatma, hiç olmayandan
 * daha kötü. Onun yerine panel açıldığında gecikenler en üstte duruyor.
 */
export function gecikenler(liste: Gonderi[], simdi = new Date()): Gonderi[] {
  return liste.filter((g) => {
    if (g.status === 'published' || !g.scheduled_at) return false;
    const t = new Date(g.scheduled_at);
    return !Number.isNaN(t.getTime()) && t <= simdi;
  });
}

/** `datetime-local` girdisi ile ISO metin arasında çeviri. */
export function girdiyeCevir(iso?: string): string {
  if (!iso) return '';
  const t = new Date(iso);
  if (Number.isNaN(t.getTime())) return '';
  const p = (n: number) => String(n).padStart(2, '0');
  return `${t.getFullYear()}-${p(t.getMonth() + 1)}-${p(t.getDate())}T${p(t.getHours())}:${p(t.getMinutes())}`;
}

export function isoyaCevir(girdi: string): string | null {
  if (!girdi) return null;
  const t = new Date(girdi);
  return Number.isNaN(t.getTime()) ? null : t.toISOString();
}
