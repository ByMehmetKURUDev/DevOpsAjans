import { useCallback, useEffect, useState, type ReactElement } from 'react';
import { Link, useParams } from 'react-router-dom';
import { AlertCircle, Ban, CheckCircle2, Clock, Home, Loader2, ShieldCheck, XCircle } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import IslemKarari from '@/components/IslemKarari';
import { Button } from '@/components/ui/button';
import {
  IslemHatasi,
  islemGetir,
  islemKarari,
  olumluMu,
  tarihSaatBicimle,
  yerelBaslik,
  type AcikIslem,
  type IslemSonucu,
} from '@/lib/imzaliIslem';

/**
 * İmzalı işlem sayfası: `/islem/<jeton>`.
 *
 * Müşteriye e-postayla (ya da yöneticinin elle ilettiği) giden bağlantı.
 * Oturum istemiyor — jetonun kendisi yetki. Bu yüzden:
 *  * prerender listesinde yok ve çalışma anında noindex veriliyor
 *    (ödeme ve rapor sayfalarıyla aynı desen);
 *  * sunucu alıcı e-postasını maskeli döndürüyor.
 *
 * Durumlar: bekliyor → kart + karar; kullanıldı / süresi doldu / iptal →
 * ayrı durum ekranı; karar verildikten hemen sonra → sonuç ekranı.
 * Mobil öncelikli: düğmeler tam genişlik, onay penceresi alttan açılıyor.
 */
export default function IslemSayfasi() {
  const { jeton } = useParams<{ jeton: string }>();
  const { t, i18n } = useTranslation();
  const [islem, setIslem] = useState<AcikIslem | null>(null);
  const [yukleniyor, setYukleniyor] = useState(true);
  const [hata, setHata] = useState<IslemHatasi | null>(null);
  const [yeniSonuc, setYeniSonuc] = useState<IslemSonucu | null>(null);

  useEffect(() => {
    const etiket = document.createElement('meta');
    etiket.name = 'robots';
    etiket.content = 'noindex, nofollow';
    document.head.appendChild(etiket);
    // Jeton, dışarı giden bağlantılarda Referer ile sızmasın.
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
      setIslem(await islemGetir(jeton));
    } catch (h) {
      setHata(h instanceof IslemHatasi ? h : new IslemHatasi(0, 'genel'));
    } finally {
      setYukleniyor(false);
    }
  }, [jeton]);

  useEffect(() => {
    void yukle();
  }, [yukle]);

  const kararVer = async (sonuc: IslemSonucu, not?: string) => {
    if (!jeton) return;
    try {
      await islemKarari(jeton, sonuc, not);
      setYeniSonuc(sonuc);
    } catch (h) {
      // Bu arada başka biri kullandıysa / süresi dolduysa durum ekranına geç.
      if (h instanceof IslemHatasi && (h.durum === 409 || h.durum === 410)) {
        await yukle();
        return;
      }
      throw h;
    }
  };

  const dil = i18n.language;

  const durumEkrani = (ikon: ReactElement, baslik: string, metin: string, testId: string, ek?: ReactElement) => (
    <div
      className="cam-kart mx-auto max-w-xl rounded-3xl border border-white/10 bg-white/[0.03] p-6 text-center sm:p-8"
      data-testid={testId}
    >
      <div className="mx-auto mb-3 flex justify-center">{ikon}</div>
      <h1 className="text-xl font-semibold">{baslik}</h1>
      <p className="mt-2 text-sm text-muted-foreground">{metin}</p>
      {ek}
      <Button asChild variant="outline" className="mt-6 !bg-transparent">
        <Link to="/">
          <Home className="mr-2 h-4 w-4" aria-hidden="true" />
          {t('islem.anaSayfa')}
        </Link>
      </Button>
    </div>
  );

  let icerik: ReactElement | null = null;
  if (yukleniyor) {
    icerik = (
      <div className="flex min-h-[40vh] items-center justify-center text-muted-foreground">
        <Loader2 className="h-6 w-6 animate-spin" aria-hidden="true" />
      </div>
    );
  } else if (hata) {
    icerik = durumEkrani(
      <AlertCircle className="h-10 w-10 text-red-300" aria-hidden="true" />,
      hata.durum === 404 ? t('islem.durum.bulunamadi.baslik') : t('islem.hata.baslik'),
      hata.durum === 404
        ? t('islem.durum.bulunamadi.metin')
        : t(`islem.hata.${hata.kod}`, { defaultValue: t('islem.hata.genel') }),
      'islem-hata',
    );
  } else if (yeniSonuc && islem) {
    const olumlu = olumluMu(yeniSonuc);
    icerik = durumEkrani(
      olumlu ? (
        <CheckCircle2 className="h-12 w-12 text-emerald-300" aria-hidden="true" />
      ) : (
        <XCircle className="h-12 w-12 text-amber-300" aria-hidden="true" />
      ),
      t(`islem.sonucEkrani.${yeniSonuc}.baslik`),
      t(`islem.sonucEkrani.${yeniSonuc}.metin`),
      'islem-sonuc',
      <p className="mt-4 break-words text-sm font-medium">{yerelBaslik(islem, t, dil)}</p>,
    );
  } else if (islem && islem.durum === 'kullanildi') {
    icerik = durumEkrani(
      <ShieldCheck className="h-10 w-10 text-emerald-300" aria-hidden="true" />,
      t('islem.durum.kullanildi.baslik'),
      islem.sonuc
        ? t('islem.durum.kullanildi.metin', {
            sonuc: t(`islem.sonuc.${islem.sonuc}`),
            tarih: tarihSaatBicimle(islem.kullanildi_at, dil),
          })
        : t('islem.durum.kullanildi.metinSonucsuz'),
      'islem-durum-kullanildi',
      <p className="mt-4 break-words text-sm font-medium">{yerelBaslik(islem, t, dil)}</p>,
    );
  } else if (islem && islem.durum === 'suresi_doldu') {
    icerik = durumEkrani(
      <Clock className="h-10 w-10 text-amber-300" aria-hidden="true" />,
      t('islem.durum.suresi_doldu.baslik'),
      t('islem.durum.suresi_doldu.metin'),
      'islem-durum-suresi_doldu',
    );
  } else if (islem && islem.durum === 'iptal') {
    icerik = durumEkrani(
      <Ban className="h-10 w-10 text-muted-foreground" aria-hidden="true" />,
      t('islem.durum.iptal.baslik'),
      t('islem.durum.iptal.metin'),
      'islem-durum-iptal',
    );
  } else if (islem) {
    icerik = (
      <div className="mx-auto max-w-xl">
        <p className="mb-3 text-center text-xs text-muted-foreground">
          {t('islem.alici', { eposta: islem.alici })}
        </p>
        <IslemKarari islem={islem} onKarar={kararVer} />
        <p className="mt-4 flex items-center justify-center gap-2 text-center text-xs text-muted-foreground">
          <ShieldCheck className="h-4 w-4 shrink-0" aria-hidden="true" />
          {t('islem.guvenlikNotu')}
        </p>
      </div>
    );
  }

  return (
    <div className="pt-28 pb-20 sm:pt-32" data-testid="islem-sayfasi">
      <div className="mx-auto max-w-5xl px-4 sm:px-6 lg:px-8">{icerik}</div>
    </div>
  );
}
