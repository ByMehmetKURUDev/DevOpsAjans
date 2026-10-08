import { useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { ExternalLink, Loader2 } from 'lucide-react';

import { KART, KodKutusu, ROZET } from '@/components/apiErisimi/ortak';
import { anahtarAdi, hataMetni, openapiGetir, type ApiMeta, type OpenApiBelgesi } from '@/lib/apiErisimi';

/**
 * Faz 4A — API belgeleri: `/api/public/v1/openapi.json`'dan kendi bileşenimizle
 * (dış Swagger/Redoc CDN'i yok — CSP). Uç açıklamaları ve kavramlar ek paketten
 * yedi dilde; webhook imza doğrulaması için Python ve Node örnekleri (testte
 * sunucunun algoritmasıyla birebir karşılaştırılıyor).
 */

const YONTEM_RENGI: Record<string, string> = {
  get: 'border-sky-400/40 bg-sky-500/10 text-sky-200',
  post: 'border-emerald-400/40 bg-emerald-500/10 text-emerald-200',
  patch: 'border-amber-400/40 bg-amber-500/10 text-amber-200',
  put: 'border-amber-400/40 bg-amber-500/10 text-amber-200',
  delete: 'border-red-400/40 bg-red-500/10 text-red-200',
};

const ORNEK_PYTHON = `import hashlib
import hmac
import time


def verify(secret: str, timestamp: str, body: bytes, signature_header: str, tolerance: int = 300) -> bool:
    # MK-Webhook-Imza: v1=hex(HMAC-SHA256(secret, timestamp + "." + body))
    if abs(time.time() - int(timestamp)) > tolerance:
        return False
    expected = hmac.new(secret.encode(), f"{timestamp}.".encode() + body, hashlib.sha256).hexdigest()
    return any(
        hmac.compare_digest(part.split("=", 1)[1], expected)
        for part in signature_header.split()
        if part.startswith("v1=")
    )


# Flask:
# ok = verify(SECRET, request.headers["MK-Webhook-Zaman"], request.get_data(), request.headers["MK-Webhook-Imza"])
`;

const ORNEK_NODE = `import crypto from 'node:crypto';

export function verify(secret, timestamp, body, signatureHeader, tolerance = 300) {
  // MK-Webhook-Imza: v1=hex(HMAC-SHA256(secret, timestamp + "." + body))
  if (Math.abs(Date.now() / 1000 - Number(timestamp)) > tolerance) return false;
  const expected = crypto.createHmac('sha256', secret).update(\`\${timestamp}.\`).update(body).digest();
  return signatureHeader.split(' ').some((part) => {
    if (!part.startsWith('v1=')) return false;
    const given = Buffer.from(part.slice(3), 'hex');
    return given.length === expected.length && crypto.timingSafeEqual(given, expected);
  });
}

// Express (body = RAW bytes):
// app.post('/webhook', express.raw({ type: 'application/json' }), (req, res) => {
//   if (!verify(SECRET, req.get('MK-Webhook-Zaman'), req.body, req.get('MK-Webhook-Imza'))) return res.sendStatus(400);
//   res.sendStatus(200);
// });
`;

const ORNEK_BASLIKLAR = `MK-Webhook-Id: evt_3f2a9c0d1e7b4a6f8c2d5e10
MK-Webhook-Zaman: 1790871975
MK-Webhook-Imza: v1=9c1b7f0e4d…
Content-Type: application/json; charset=utf-8`;

const ORNEK_GOVDE = `{
  "id": "evt_3f2a9c0d1e7b4a6f8c2d5e10",
  "tur": "fatura.odendi",
  "olusturma": "2026-10-01T12:00:00Z",
  "hesap": "musteri@ornek.com",
  "veri": { "fatura_id": 42, "no": "F-2026-0042", "tutar": 1500.0, "para_birimi": "TRY", "durum": "paid" }
}`;

const OLAYLAR = [
  'aday.olusturuldu', 'teklif.kabul_edildi', 'teklif.reddedildi', 'sozlesme.imzalandi', 'fatura.olusturuldu',
  'fatura.odendi', 'destek.olusturuldu', 'destek.yanitlandi', 'gorev.olusturuldu', 'gorev.tamamlandi',
  'proje.asama_degisti', 'menu.siparis', 'kart.mesaj', 'qr.tarama', 'asistan.devredildi',
  'is_emri.olusturuldu', 'is_emri.tamamlandi', 'etkinlik.kayit', 'etkinlik.bilet_satildi', 'etkinlik.giris',
  'etkinlik.iptal', 'pos.satis', 'stok.kritik', 'egitim.kayit', 'egitim.tamamlandi', 'egitim.devamsizlik', 'ik.izin_talebi', 'ik.izin_karari', 'muhasebe.butce_asildi', 'muhasebe.alacak_gecikti',
  'ortaklik.basvuru', 'ortaklik.komisyon', 'ortaklik.odeme_talebi', 'ping',
];

/** "GET /api/public/v1/projeler/{proje_id}" → "get_projeler_proje_id" (ek paketteki açıklama anahtarı). */
function ucAnahtari(yontem: string, yol: string): string {
  return `${yontem}_${yol.replace('/api/public/v1/', '').replace(/[^a-z0-9]+/gi, '_').replace(/^_|_$/g, '')}`;
}

export default function Belgeler({ meta }: { meta: ApiMeta | null }) {
  const { t } = useTranslation();
  const [belge, setBelge] = useState<OpenApiBelgesi | null>(null);
  const [hata, setHata] = useState<string | null>(null);
  const ajans = meta?.sahip_tur === 'ajans';
  const taban = meta?.api_taban || '/api/public/v1';

  useEffect(() => {
    let iptal = false;
    openapiGetir()
      .then((b) => !iptal && setBelge(b))
      .catch((e) => !iptal && setHata(hataMetni(t, e)));
    return () => {
      iptal = true;
    };
  }, [t]);

  const uclar = useMemo(() => {
    if (!belge) return [];
    const liste: { yontem: string; yol: string; kapsam: string | null; params: string[]; govde: string | null; ozet?: string }[] = [];
    for (const [yol, islemler] of Object.entries(belge.paths)) {
      for (const [yontem, islem] of Object.entries(islemler)) {
        const kapsam = islem['x-kapsam'] ?? null;
        if (!ajans && kapsam?.startsWith('crm:')) continue;
        const ref = islem.requestBody?.content?.['application/json']?.schema?.$ref;
        liste.push({
          yontem,
          yol,
          kapsam,
          params: (islem.parameters || [])
            .filter((p) => p.in !== 'header' || p.name === 'Idempotency-Key')
            .map((p) => `${p.name}${p.required ? '*' : ''}`),
          govde: ref ? ref.split('/').pop() || null : null,
          ozet: islem.summary,
        });
      }
    }
    return liste;
  }, [belge, ajans]);

  const curlListe = `curl -s "${taban}/projeler?limit=10" \\
  -H "Authorization: Bearer $MK_API_KEY"`;
  const curlYazma = `curl -s -X POST "${taban}/gorevler" \\
  -H "Authorization: Bearer $MK_API_KEY" \\
  -H "Content-Type: application/json" \\
  -H "Idempotency-Key: $(uuidgen)" \\
  -d '{"proje_id": 12, "baslik": "Ana sayfa metnini güncelle"}'`;
  const curlSuzgec = `curl -s "${taban}/destek?updated_since=2026-10-01T00:00:00Z&cursor=$CURSOR" \\
  -H "X-API-Key: $MK_API_KEY"`;
  const hataOrnegi = `HTTP/1.1 403 Forbidden
{"hata": {"kod": "kapsam_yetersiz", "mesaj": "…", "gereken": "faturalar:oku"}}`;

  return (
    <div className="space-y-6" data-testid="api-belgeler">
      <div className={`${KART} space-y-3 p-5`}>
        <h3 className="text-lg font-semibold">{t('apiErisimi.belgeler.baslik')}</h3>
        <p className="text-sm text-muted-foreground">{t('apiErisimi.belgeler.giris')}</p>
        <dl className="grid grid-cols-1 gap-3 text-sm md:grid-cols-2">
          {(['taban', 'kimlik', 'sayfalama', 'hatalar', 'idempotency', 'hiz'] as const).map((k) => (
            <div key={k} className="min-w-0 rounded-xl border border-white/10 p-3">
              <dt className="font-medium text-white">{t(`apiErisimi.belgeler.${k}`)}</dt>
              <dd className="mt-1 text-xs text-muted-foreground">
                {k === 'taban' ? (
                  <code className="break-all font-mono text-purple-200" dir="ltr" data-testid="api-taban">
                    {taban}
                  </code>
                ) : (
                  t(`apiErisimi.belgeler.${k}Aciklama`)
                )}
              </dd>
            </div>
          ))}
        </dl>
        {meta && (
          <a
            href={meta.openapi_url}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-1 text-sm text-purple-200 hover:underline"
          >
            <ExternalLink className="h-4 w-4" aria-hidden="true" />
            {t('apiErisimi.belgeler.openapi')}
          </a>
        )}
      </div>

      <div className="space-y-3">
        <h3 className="text-lg font-semibold">{t('apiErisimi.belgeler.ornekler')}</h3>
        <KodKutusu baslik={t('apiErisimi.belgeler.ornekListe')} kod={curlListe} testId="api-curl-liste" />
        <KodKutusu baslik={t('apiErisimi.belgeler.ornekYazma')} kod={curlYazma} />
        <KodKutusu baslik={t('apiErisimi.belgeler.ornekSuzgec')} kod={curlSuzgec} />
        <KodKutusu baslik={t('apiErisimi.belgeler.hatalar')} kod={hataOrnegi} />
      </div>

      <div className="space-y-3">
        <h3 className="text-lg font-semibold">{t('apiErisimi.belgeler.uclar')}</h3>
        {hata && <p className="text-sm text-red-200">{hata}</p>}
        {!belge && !hata && <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" aria-hidden="true" />}
        <ul className="space-y-2" data-testid="api-uc-listesi">
          {uclar.map((u) => (
            <li key={`${u.yontem} ${u.yol}`} className={`${KART} p-3`} data-uc={`${u.yontem.toUpperCase()} ${u.yol}`}>
              <div className="flex flex-wrap items-center gap-2">
                <span className={`${ROZET} font-mono uppercase ${YONTEM_RENGI[u.yontem] || ''}`}>{u.yontem}</span>
                <code className="min-w-0 break-all font-mono text-sm text-white" dir="ltr">
                  {u.yol}
                </code>
                {u.kapsam && (
                  <span className={`${ROZET} border-purple-400/30 bg-purple-500/10 text-purple-100`} dir="ltr">
                    {u.kapsam}
                  </span>
                )}
              </div>
              <p className="mt-1 text-xs text-muted-foreground">
                {t(`apiErisimi.uc.${ucAnahtari(u.yontem, u.yol)}`, { defaultValue: u.ozet || '' })}
              </p>
              {(u.params.length > 0 || u.govde) && (
                <p className="mt-1 break-words font-mono text-[11px] text-slate-400" dir="ltr">
                  {u.params.join(' · ')}
                  {u.govde ? `${u.params.length ? ' · ' : ''}body: ${u.govde}` : ''}
                </p>
              )}
            </li>
          ))}
        </ul>
      </div>

      <div className={`${KART} space-y-3 p-5`} data-testid="api-webhook-belgesi">
        <h3 className="text-lg font-semibold">{t('apiErisimi.belgeler.webhookBaslik')}</h3>
        <p className="text-sm text-muted-foreground">{t('apiErisimi.belgeler.webhookAciklama')}</p>
        <KodKutusu baslik={t('apiErisimi.belgeler.basliklar')} kod={ORNEK_BASLIKLAR} />
        <KodKutusu baslik={t('apiErisimi.belgeler.govdeBicimi')} kod={ORNEK_GOVDE} />
        <KodKutusu baslik="Python" kod={ORNEK_PYTHON} testId="api-ornek-python" />
        <KodKutusu baslik="Node.js" kod={ORNEK_NODE} testId="api-ornek-node" />
        <h4 className="pt-2 text-sm font-semibold">{t('apiErisimi.belgeler.olaylarBaslik')}</h4>
        <ul className="grid grid-cols-1 gap-1 text-xs sm:grid-cols-2">
          {OLAYLAR.filter((o) => ajans || o !== 'aday.olusturuldu').map((o) => (
            <li key={o} className="flex min-w-0 flex-wrap gap-2">
              <code className="font-mono text-purple-200" dir="ltr">
                {o}
              </code>
              <span className="text-muted-foreground">{t(`apiErisimi.olay.${anahtarAdi(o)}`)}</span>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}
