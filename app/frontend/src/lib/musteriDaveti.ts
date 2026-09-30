import { client } from '@/lib/sdkClient';

/**
 * Müşteriyi panele davet eder.
 *
 * Proje bir müşteri e-postasına bağlandığında o kişinin panele kaydolması
 * gerekiyor; panel bütün kayıtları `client_email` üzerinden eşleştiriyor.
 *
 * E-postayı arka uç gönderiyor, tarayıcı değil: gönderim anahtarı
 * (RESEND_API_KEY / SMTP_*) sunucuda duruyor ve uç yalnızca yöneticiye
 * açık — aksi hâlde herkes site üzerinden istediği adrese posta
 * attırabilirdi.
 *
 * Arka uç e-postanın GERÇEKTEN gidip gitmediğini söylüyor. Söylemesi
 * gerekiyordu: e-posta sağlayıcısı yapılandırılmamışsa gönderim sessizce
 * atlanıyor, uç yine de "ok" dönüyordu ve panelde "davet gönderildi"
 * yazması yanlış oluyordu. Çağıran taraf `epostaGitti` yanlışsa daveti
 * elden gönderebilsin diye metnin kendisi de dönüyor.
 */

export interface DavetSonucu {
  /** Arka uç davet kaydını oluşturdu mu (panel içi bildirim her hâlükârda yazılıyor). */
  ok: boolean;
  /** E-posta kanalı ne yaptı: sent | skipped | failed | off | unknown */
  epostaDurumu: string;
  /** Gitmediyse sebebi — panelde gösterilebilir. */
  epostaAyrinti: string;
  /** Kısayol: yalnızca "sent" ise gerçekten gitti. */
  epostaGitti: boolean;
  /** Davet başlığı (mailto konusu için). */
  baslik: string;
  /** Davet metni; e-posta gitmediyse kopyalanıp WhatsApp'tan yollanabilir. */
  metin: string;
}

interface DavetYaniti {
  ok?: boolean;
  link?: string;
  email_status?: string;
  email_detail?: string;
  subject?: string;
  message?: string;
}

export async function musteriyiDavetEt(
  email: string,
  name?: string,
  projectTitle?: string,
): Promise<DavetSonucu> {
  const yanit = (await client.apiCall.invoke({
    method: 'POST',
    url: '/api/v1/client-invite',
    data: { email, name: name || '', project_title: projectTitle || '' },
  })) as unknown;

  // SDK bazı uçlarda gövdeyi `data` altında sarmalıyor; ikisini de karşılıyoruz.
  const kok = (yanit ?? {}) as Record<string, unknown>;
  const govde: DavetYaniti =
    ('data' in kok ? ((kok.data as DavetYaniti) ?? {}) : (kok as DavetYaniti)) || {};

  const durum = govde.email_status || 'unknown';

  return {
    ok: govde.ok !== false,
    epostaDurumu: durum,
    epostaAyrinti: govde.email_detail || '',
    epostaGitti: durum === 'sent',
    baslik: govde.subject || '',
    metin: govde.message || '',
  };
}
