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
 */
export async function musteriyiDavetEt(
  email: string,
  name?: string,
  projectTitle?: string,
): Promise<void> {
  await client.apiCall.invoke({
    method: 'POST',
    url: '/api/v1/client-invite',
    data: { email, name: name || '', project_title: projectTitle || '' },
  });
}
