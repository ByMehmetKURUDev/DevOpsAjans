import { useCallback, useEffect, useState, type ReactElement } from 'react';
import { Link, useParams } from 'react-router-dom';
import { AlertCircle, Ban, CheckCircle2, Clock, Home, Loader2, MessageSquareWarning, PenTool, ShieldCheck } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';

import { IcerikKarari, IcerikOnizleme } from '@/components/IcerikOnizleme';
import { Button } from '@/components/ui/button';
import { OnayHatasi, acikOnayGetir, acikOnayKarari, onayHataMetni, type AcikOnay, type OnaySonucu } from '@/lib/icerikOnay';

/**
 * Faz 5I — Girişsiz içerik onayı: `/icerik-onay/<jeton>`.
 *
 * Ajansın müşteriye gönderdiği imzalı bağlantı (Faz 1E deseni): jeton yetki, tek kullanımlık,
 * süreli. Prerender yok, çalışma anında noindex + no-referrer (jeton dışarı sızmasın).
 * Durumlar: bekliyor → önizleme + karar; kullanıldı / süresi doldu / iptal → durum ekranı.
 */
export default function IcerikOnaySayfasi() {
  const { jeton } = useParams<{ jeton: string }>();
  const { t, i18n } = useTranslation();
  const [veri, setVeri] = useState<AcikOnay | null>(null);
  const [yukleniyor, setYukleniyor] = useState(true);
  const [hata, setHata] = useState<OnayHatasi | null>(null);
  const [yeni, setYeni] = useState<OnaySonucu | null>(null);

  useEffect(() => {
    const robots = document.createElement('meta');
    robots.name = 'robots';
    robots.content = 'noindex, nofollow';
    const ref = document.createElement('meta');
    ref.name = 'referrer';
    ref.content = 'no-referrer';
    document.head.append(robots, ref);
    return () => {
      robots.remove();
      ref.remove();
    };
  }, []);

  const yukle = useCallback(async () => {
    if (!jeton) return;
    setYukleniyor(true);
    setHata(null);
    try {
      setVeri(await acikOnayGetir(jeton));
    } catch (h) {
      setHata(h instanceof OnayHatasi ? h : new OnayHatasi(0, 'genel'));
    } finally {
      setYukleniyor(false);
    }
  }, [jeton]);

  useEffect(() => {
    void yukle();
  }, [yukle]);

  const karar = async (sonuc: OnaySonucu, not?: string) => {
    if (!jeton) return;
    try {
      await acikOnayKarari(jeton, sonuc, not);
      setYeni(sonuc);
    } catch (h) {
      if (h instanceof OnayHatasi && (h.durum === 409 || h.durum === 410)) {
        await yukle();
        return;
      }
      toast.error(onayHataMetni(t, h));
    }
  };

  const ekran = (ikon: ReactElement, baslik: string, metin: string, testId: string) => (
    <div className="cam-kart mx-auto max-w-xl rounded-3xl border border-white/10 bg-white/[0.03] p-6 text-center sm:p-8" data-testid={testId}>
      <div className="mx-auto mb-3 flex justify-center">{ikon}</div>
      <h1 className="text-xl font-semibold">{baslik}</h1>
      <p className="mt-2 text-sm text-muted-foreground">{metin}</p>
      <Button asChild variant="outline" className="mt-6 !bg-transparent">
        <Link to="/">
          <Home className="me-2 h-4 w-4" aria-hidden="true" />
          {t('icerikOnay.anaSayfa')}
        </Link>
      </Button>
    </div>
  );

  let icerik: ReactElement;
  if (yukleniyor) {
    icerik = (
      <div className="flex min-h-[40vh] items-center justify-center text-muted-foreground">
        <Loader2 className="h-6 w-6 animate-spin" aria-hidden="true" />
      </div>
    );
  } else if (hata) {
    icerik = ekran(
      <AlertCircle className="h-10 w-10 text-red-300" aria-hidden="true" />,
      t(hata.durum === 404 ? 'icerikOnay.sayfa.bulunamadi.baslik' : 'icerikOnay.sayfa.hata'),
      hata.durum === 404 ? t('icerikOnay.sayfa.bulunamadi.metin') : onayHataMetni(t, hata),
      'icerik-onay-hata',
    );
  } else if (yeni) {
    icerik = yeni === 'onay'
      ? ekran(<CheckCircle2 className="h-10 w-10 text-emerald-300" aria-hidden="true" />, t('icerikOnay.sayfa.sonuc.onay.baslik'),
          t('icerikOnay.sayfa.sonuc.onay.metin'), 'icerik-onay-sonuc')
      : ekran(<MessageSquareWarning className="h-10 w-10 text-amber-300" aria-hidden="true" />, t('icerikOnay.sayfa.sonuc.revizyon.baslik'),
          t('icerikOnay.sayfa.sonuc.revizyon.metin'), 'icerik-onay-sonuc');
  } else if (veri && veri.durum !== 'bekliyor') {
    const durum = ['kullanildi', 'suresi_doldu', 'iptal'].includes(veri.durum) ? veri.durum : 'kullanildi';
    const ikon = durum === 'kullanildi' ? <CheckCircle2 className="h-10 w-10 text-emerald-300" aria-hidden="true" />
      : durum === 'iptal' ? <Ban className="h-10 w-10 text-rose-300" aria-hidden="true" /> : <Clock className="h-10 w-10 text-amber-300" aria-hidden="true" />;
    icerik = ekran(ikon, t(`icerikOnay.sayfa.${durum}.baslik`),
      durum === 'kullanildi' && veri.sonuc ? t(`icerikOnay.sayfa.kullanildi.${veri.sonuc}`) : t(`icerikOnay.sayfa.${durum}.metin`),
      `icerik-onay-${durum}`);
  } else if (veri?.gonderi) {
    const g = veri.gonderi;
    icerik = (
      <div className="cam-kart mx-auto max-w-2xl rounded-3xl border border-white/10 bg-white/[0.03] p-5 sm:p-7" data-testid="icerik-onay-kart">
        <p className="mb-1 flex items-center gap-1.5 text-xs uppercase tracking-wider text-fuchsia-200">
          <PenTool className="h-3.5 w-3.5" aria-hidden="true" />
          {t('icerikOnay.sayfa.baslik')}
        </p>
        <h1 className="break-words text-xl font-semibold sm:text-2xl">{g.baslik}</h1>
        <p className="mt-1 text-sm text-muted-foreground">{t('icerikOnay.sayfa.aciklama')}</p>
        <div className="mt-5">
          <IcerikOnizleme g={g} testId="icerik-onay-onizleme" />
        </div>
        <IcerikKarari onKarar={karar} testId="icerik-onay-karar" />
        <p className="mt-5 flex items-start gap-1.5 text-[11px] text-muted-foreground">
          <ShieldCheck className="mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden="true" />
          <span>
            {t('icerikOnay.alici', { alici: veri.alici })}
            {veri.son_kullanma ? ` · ${t('icerikOnay.sonKullanma', { tarih: new Date(veri.son_kullanma).toLocaleDateString(i18n.language) })}` : ''}
          </span>
        </p>
      </div>
    );
  } else {
    icerik = ekran(<AlertCircle className="h-10 w-10 text-red-300" aria-hidden="true" />, t('icerikOnay.sayfa.bulunamadi.baslik'),
      t('icerikOnay.sayfa.bulunamadi.metin'), 'icerik-onay-hata');
  }

  return (
    <div className="pt-10 pb-20 sm:pt-14" data-testid="icerik-onay-sayfasi">
      <div className="mx-auto max-w-5xl px-4 sm:px-6 lg:px-8">{icerik}</div>
    </div>
  );
}
