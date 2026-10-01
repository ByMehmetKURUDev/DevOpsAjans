import { useCallback, useEffect, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { AlertCircle, CheckCircle2, Home, Loader2, LogIn, Users } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import { Button } from '@/components/ui/button';
import { EkipHatasi, davetBilgisi, davetKabul, type DavetBilgisi } from '@/lib/hesapEkibi';
import { hesapSec } from '@/lib/hesapSecimi';
import { client, oturumIziVarMi } from '@/lib/sdkClient';

/**
 * Faz 2E — hesap ekibi davet sayfası: `/hesap-davet/<jeton>`.
 *
 * Bilgi girişsiz gösteriliyor (hesap adı, maskeli e-posta, rol); KABUL için
 * giriş gerekli ve sunucu jetondaki e-postanın davet edilen e-postayla aynı
 * olmasını şart koşuyor. Prerender edilmiyor, çalışma anında noindex +
 * no-referrer (jeton dışarı giden bağlantılarda sızmasın).
 */
export default function HesapDavetSayfasi() {
  const { jeton } = useParams<{ jeton: string }>();
  const { t, i18n } = useTranslation();
  const [bilgi, setBilgi] = useState<DavetBilgisi | null>(null);
  const [yukleniyor, setYukleniyor] = useState(true);
  const [hata, setHata] = useState<EkipHatasi | null>(null);
  const [girisli, setGirisli] = useState<{ email: string } | null>(null);
  const [calisiyor, setCalisiyor] = useState(false);
  const [kabul, setKabul] = useState<{ hesap: string } | null>(null);

  useEffect(() => {
    const etiket = document.createElement('meta');
    etiket.name = 'robots';
    etiket.content = 'noindex, nofollow';
    document.head.appendChild(etiket);
    const referans = document.createElement('meta');
    referans.name = 'referrer';
    referans.content = 'no-referrer';
    document.head.appendChild(referans);
    return () => {
      etiket.remove();
      referans.remove();
    };
  }, []);

  const yukle = useCallback(async () => {
    if (!jeton) return;
    setYukleniyor(true);
    setHata(null);
    try {
      setBilgi(await davetBilgisi(jeton));
    } catch (h) {
      setHata(h instanceof EkipHatasi ? h : new EkipHatasi(0, 'genel'));
    } finally {
      setYukleniyor(false);
    }
  }, [jeton]);

  useEffect(() => {
    void yukle();
    if (!oturumIziVarMi()) return;
    client.auth
      .me()
      .then((r) => {
        const e = (r?.data as { email?: string } | undefined)?.email;
        if (e) setGirisli({ email: e.toLowerCase() });
      })
      .catch(() => {});
  }, [yukle]);

  const kabulEt = async () => {
    if (!jeton) return;
    setCalisiyor(true);
    try {
      const y = await davetKabul(jeton);
      if (girisli) hesapSec(girisli.email, y.hesap_email);
      setKabul({ hesap: y.hesap_adi || y.hesap_email });
    } catch (h) {
      setHata(h instanceof EkipHatasi ? h : new EkipHatasi(0, 'genel'));
    } finally {
      setCalisiyor(false);
    }
  };

  const tarih = (d?: string | null) => {
    if (!d) return '—';
    try {
      return new Date(d).toLocaleString(i18n.language || 'tr', { dateStyle: 'medium', timeStyle: 'short' });
    } catch {
      return d;
    }
  };

  const kart = 'cam-kart mx-auto max-w-lg rounded-2xl border border-white/10 bg-white/[0.03] p-6 sm:p-8';

  if (yukleniyor) {
    return (
      <div className="flex min-h-[60vh] items-center justify-center">
        <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
      </div>
    );
  }

  const hesapAdi = bilgi?.hesap_adi || bilgi?.hesap_eposta || t('hesapEkibi.davet.bilinmeyenHesap');

  return (
    <div className="px-4 py-16" data-hesap-davet>
      <div className={kart}>
        <h1 className="mb-4 flex items-center gap-2 text-2xl font-bold">
          <Users className="h-6 w-6 text-purple-300" aria-hidden="true" /> {t('hesapEkibi.davet.baslik')}
        </h1>

        {kabul ? (
          <div className="space-y-4" data-davet-kabul-edildi>
            <p className="flex items-start gap-2 text-emerald-200">
              <CheckCircle2 className="mt-0.5 h-5 w-5 shrink-0" aria-hidden="true" />
              {t('hesapEkibi.davet.kabulEdildi', { hesap: kabul.hesap })}
            </p>
            <Link to="/client">
              <Button className="w-full gap-2 bg-gradient-to-r from-purple-600 to-pink-600 text-white border-0">
                {t('hesapEkibi.davet.panelGit')}
              </Button>
            </Link>
          </div>
        ) : !bilgi || (hata && hata.durum === 404) ? (
          <div className="space-y-4">
            <p className="flex items-start gap-2 text-amber-200">
              <AlertCircle className="mt-0.5 h-5 w-5 shrink-0" aria-hidden="true" />
              {t(hata?.kod === 'cok_istek' ? 'hesapEkibi.hata.cok_istek' : 'hesapEkibi.davet.gecersiz')}
            </p>
            <Link to="/" className="inline-flex items-center gap-1.5 text-sm text-purple-300 hover:text-purple-200">
              <Home className="h-4 w-4" /> {t('hesapEkibi.davet.anaSayfa')}
            </Link>
          </div>
        ) : (
          <div className="space-y-4">
            <p>{t('hesapEkibi.davet.aciklama', { hesap: hesapAdi, rol: t(`hesapEkibi.rol.${bilgi.rol}`) })}</p>
            <p className="text-sm text-muted-foreground">{t('hesapEkibi.davet.davetEdilen', { eposta: bilgi.davet_eposta })}</p>
            <div>
              <p className="mb-2 text-xs uppercase tracking-widest text-muted-foreground">{t('hesapEkibi.davet.izinler')}</p>
              <div className="flex flex-wrap gap-1.5">
                {bilgi.izinler.map((i) => (
                  <span key={i} className="rounded-full border border-white/15 px-2.5 py-0.5 text-xs">
                    {t(`hesapEkibi.izin.${i}`)}
                  </span>
                ))}
              </div>
            </div>

            {bilgi.durum === 'suresi_doldu' || hata?.kod === 'davet_suresi_doldu' ? (
              <p className="flex items-start gap-2 text-amber-200" data-davet-suresi-doldu>
                <AlertCircle className="mt-0.5 h-5 w-5 shrink-0" aria-hidden="true" />
                {t('hesapEkibi.davet.suresiDoldu')}
              </p>
            ) : (
              <>
                <p className="text-xs text-muted-foreground">{t('hesapEkibi.davet.gecerlilik', { tarih: tarih(bilgi.davet_bitis) })}</p>
                {hata && (
                  <p className="rounded-lg border border-destructive/30 bg-destructive/10 px-3 py-2 text-sm text-destructive" data-davet-hata={hata.kod}>
                    {hata.kod === 'eposta_uyusmuyor'
                      ? t('hesapEkibi.davet.epostaUyusmuyor', { beklenen: String(hata.ek.beklenen ?? bilgi.davet_eposta) })
                      : t(`hesapEkibi.hata.${hata.kod}`, { defaultValue: t('hesapEkibi.hata.genel') })}
                  </p>
                )}
                {girisli ? (
                  <Button
                    onClick={() => void kabulEt()}
                    disabled={calisiyor}
                    data-testid="davet-kabul"
                    className="w-full gap-2 bg-gradient-to-r from-purple-600 to-pink-600 text-white border-0"
                  >
                    {calisiyor ? <Loader2 className="h-4 w-4 animate-spin" /> : <CheckCircle2 className="h-4 w-4" />}
                    {t('hesapEkibi.davet.kabulEt')}
                  </Button>
                ) : (
                  <>
                    <p className="text-sm text-muted-foreground">{t('hesapEkibi.davet.girisAciklama')}</p>
                    <Button
                      onClick={() => client.auth.toLogin()}
                      className="w-full gap-2 bg-gradient-to-r from-purple-600 to-pink-600 text-white border-0"
                    >
                      <LogIn className="h-4 w-4" /> {t('hesapEkibi.davet.girisYap')}
                    </Button>
                  </>
                )}
              </>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
