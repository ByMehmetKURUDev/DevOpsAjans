import { useCallback, useEffect, useState } from 'react';
import { ChevronLeft, ChevronRight, Loader2, RefreshCw, X } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';

import { Button } from '@/components/ui/button';
import SiteRaporGorunumu from '@/components/SiteRaporGorunumu';
import { fetchSettingRows, saveSiteSetting } from '@/lib/siteSettings';
import {
  PAZARLAMA_AYARI,
  puanRengi,
  yonetimListesi,
  yonetimRaporu,
  type AnalizSatiri,
  type TamRapor,
} from '@/lib/siteAnalizi';

/**
 * Yönetici paneli › Site analizleri.
 *
 * Herkese açık "Ücretsiz site analizi" sayfasında yapılan her analiz
 * burada. E-posta bırakanlar aynı zamanda Talepler'e `site_analizi`
 * kaynağıyla aday olarak düşüyor; satırdaki "Talep #" o kayda işaret ediyor.
 * Satıra tıklayınca tam rapor, müşterinin gördüğü görünümle açılıyor.
 *
 * Faz 4G: "Pazarlama izni sor" anahtarı (site ayarı `site_analizi_pazarlama_izni`)
 * açıkken herkese açık tam rapor formunda isteğe bağlı, işaretsiz bir
 * "kampanya ve duyurular" kutusu çıkar; işaretlenirse izin kaydedilir ve
 * raporun ayrıntısında görünür.
 */

const ADET = 20;

function tarih(deger: string | null | undefined, dil: string): string {
  if (!deger) return '—';
  const an = new Date(deger);
  if (Number.isNaN(an.getTime())) return '—';
  return an.toLocaleString(dil, { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' });
}

export default function SiteAnalizleri() {
  const { t, i18n } = useTranslation();
  const [satirlar, setSatirlar] = useState<AnalizSatiri[]>([]);
  const [toplam, setToplam] = useState(0);
  const [sayfa, setSayfa] = useState(1);
  const [yalnizEposta, setYalnizEposta] = useState(false);
  const [yukleniyor, setYukleniyor] = useState(true);
  const [secili, setSecili] = useState<TamRapor | null>(null);
  const [aciliyor, setAciliyor] = useState<number | null>(null);
  const [pazarlamaSor, setPazarlamaSor] = useState<boolean | null>(null);
  const [ayarKaydediliyor, setAyarKaydediliyor] = useState(false);

  useEffect(() => {
    fetchSettingRows()
      .then((satir) => setPazarlamaSor(satir.find((r) => r.setting_key === PAZARLAMA_AYARI)?.setting_value === '1'))
      .catch(() => setPazarlamaSor(false));
  }, []);

  const pazarlamaDegistir = async (acik: boolean) => {
    // İyimser: kutu hemen değişir, kayıt düşerse geri alınır.
    setPazarlamaSor(acik);
    setAyarKaydediliyor(true);
    try {
      await saveSiteSetting(await fetchSettingRows(), PAZARLAMA_AYARI, acik ? '1' : '0', 'kvkk', PAZARLAMA_AYARI);
      toast.success(t('siteAnalizi.yonetim.pazarlamaKaydedildi'));
    } catch {
      setPazarlamaSor(!acik);
      toast.error(t('siteAnalizi.yonetim.hata'));
    } finally {
      setAyarKaydediliyor(false);
    }
  };

  const yukle = useCallback(async () => {
    setYukleniyor(true);
    try {
      const liste = await yonetimListesi({ sayfa, adet: ADET, eposta_var: yalnizEposta });
      setSatirlar(liste.items);
      setToplam(liste.toplam);
    } catch {
      toast.error(t('siteAnalizi.yonetim.hata'));
    } finally {
      setYukleniyor(false);
    }
  }, [sayfa, yalnizEposta, t]);

  useEffect(() => {
    void yukle();
  }, [yukle]);

  const ac = async (id: number) => {
    setAciliyor(id);
    try {
      setSecili(await yonetimRaporu(id));
    } catch {
      toast.error(t('siteAnalizi.yonetim.hata'));
    } finally {
      setAciliyor(null);
    }
  };

  const sayfaSayisi = Math.max(1, Math.ceil(toplam / ADET));

  if (secili) {
    return (
      <div className="space-y-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="text-sm text-muted-foreground">
            {secili.eposta ? (
              <span>
                {secili.ad ? `${secili.ad} · ` : ''}
                <a href={`mailto:${secili.eposta}`} className="text-foreground hover:underline">
                  {secili.eposta}
                </a>
                {secili.inquiry_id ? ` · ${t('siteAnalizi.yonetim.adayNo', { sayi: secili.inquiry_id })}` : ''}
                {' · '}
                <span data-testid="site-analizi-pazarlama-durumu">
                  {secili.pazarlama_izni
                    ? t('siteAnalizi.yonetim.pazarlamaVar', { tarih: tarih(secili.pazarlama_izni_at, i18n.language), surum: secili.pazarlama_metin_surumu || '—' })
                    : t('siteAnalizi.yonetim.pazarlamaYok')}
                </span>
              </span>
            ) : (
              <span>{t('siteAnalizi.yonetim.epostaYok')}</span>
            )}
          </div>
          <Button variant="outline" onClick={() => setSecili(null)} className="gap-2">
            <X className="h-4 w-4" aria-hidden="true" />
            {t('siteAnalizi.yonetim.kapat')}
          </Button>
        </div>
        {secili.durum === 'tamam' ? (
          <SiteRaporGorunumu rapor={secili} yazdirilabilir />
        ) : (
          <p className="rounded-xl border border-white/10 p-6 text-sm text-muted-foreground">
            {t(`siteAnalizi.hata.${secili.hata_kodu || 'genel'}`, { defaultValue: t('siteAnalizi.hata.genel') })}
          </p>
        )}
      </div>
    );
  }

  return (
    <div className="cam-kart rounded-2xl border border-white/10 bg-white/[0.03] p-6">
      <div className="mb-5 flex flex-wrap items-start justify-between gap-4">
        <div>
          <h3 className="text-lg font-semibold">{t('siteAnalizi.yonetim.baslik')}</h3>
          <p className="mt-1 text-xs text-muted-foreground">{t('siteAnalizi.yonetim.aciklama', { sayi: toplam })}</p>
          <label className="mt-3 flex max-w-xl cursor-pointer items-start gap-2 text-sm">
            <input
              type="checkbox"
              checked={Boolean(pazarlamaSor)}
              disabled={pazarlamaSor === null || ayarKaydediliyor}
              onChange={(o) => void pazarlamaDegistir(o.target.checked)}
              className="mt-0.5 h-4 w-4 flex-none accent-purple-500"
              data-testid="site-analizi-pazarlama-sor"
            />
            <span>
              {t('siteAnalizi.yonetim.pazarlamaSor')}
              <span className="block text-[11px] text-muted-foreground">{t('siteAnalizi.yonetim.pazarlamaSorIpucu')}</span>
            </span>
          </label>
        </div>
        <div className="flex items-center gap-3">
          <label className="flex cursor-pointer items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={yalnizEposta}
              onChange={(o) => {
                setSayfa(1);
                setYalnizEposta(o.target.checked);
              }}
              className="h-4 w-4 accent-purple-500"
            />
            {t('siteAnalizi.yonetim.yalnizEposta')}
          </label>
          <Button variant="outline" size="icon" onClick={() => void yukle()} aria-label={t('siteAnalizi.yonetim.yenile')}>
            <RefreshCw className={`h-4 w-4 ${yukleniyor ? 'animate-spin' : ''}`} aria-hidden="true" />
          </Button>
        </div>
      </div>

      {yukleniyor && satirlar.length === 0 ? (
        <div className="flex justify-center py-10 text-muted-foreground">
          <Loader2 className="h-5 w-5 animate-spin" aria-hidden="true" />
        </div>
      ) : satirlar.length === 0 ? (
        <p className="py-8 text-center text-sm text-muted-foreground">{t('siteAnalizi.yonetim.bos')}</p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead className="text-xs text-muted-foreground">
              <tr className="border-b border-white/10">
                <th className="py-2 pr-4 font-medium">{t('siteAnalizi.yonetim.tarih')}</th>
                <th className="py-2 pr-4 font-medium">{t('siteAnalizi.yonetim.alan')}</th>
                <th className="py-2 pr-4 font-medium">{t('siteAnalizi.yonetim.puan')}</th>
                <th className="py-2 pr-4 font-medium">{t('siteAnalizi.yonetim.eposta')}</th>
                <th className="py-2 font-medium">{t('siteAnalizi.yonetim.aday')}</th>
              </tr>
            </thead>
            <tbody>
              {satirlar.map((s) => (
                <tr
                  key={s.id}
                  onClick={() => void ac(s.id)}
                  className="cursor-pointer border-b border-white/5 hover:bg-white/[0.04]"
                >
                  <td className="whitespace-nowrap py-2.5 pr-4 text-xs text-muted-foreground">
                    {tarih(s.created_at, i18n.language)}
                  </td>
                  <td className="py-2.5 pr-4">
                    <button type="button" className="break-all text-left font-medium hover:text-purple-300">
                      {aciliyor === s.id ? <Loader2 className="mr-1 inline h-3 w-3 animate-spin" aria-hidden="true" /> : null}
                      {s.alan_adi}
                    </button>
                    <span className="block text-[11px] text-muted-foreground">
                      {t(`siteAnalizi.yonetim.kaynak.${s.kaynak || 'acik'}`, { defaultValue: s.kaynak || '' })}
                    </span>
                  </td>
                  <td className={`py-2.5 pr-4 font-semibold ${puanRengi(s.puan)}`}>
                    {s.durum === 'tamam' ? (s.puan ?? '—') : (
                      <span className="text-xs font-normal text-red-300">
                        {t(`siteAnalizi.hata.${s.hata_kodu || 'genel'}`, { defaultValue: s.durum })}
                      </span>
                    )}
                  </td>
                  <td className="break-all py-2.5 pr-4 text-xs">{s.eposta || '—'}</td>
                  <td className="py-2.5 text-xs">
                    {s.inquiry_id ? t('siteAnalizi.yonetim.adayNo', { sayi: s.inquiry_id }) : '—'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {sayfaSayisi > 1 && (
        <div className="mt-4 flex items-center justify-end gap-2 text-xs text-muted-foreground">
          <Button
            variant="outline"
            size="icon"
            disabled={sayfa <= 1}
            onClick={() => setSayfa((s) => Math.max(1, s - 1))}
            aria-label={t('siteAnalizi.yonetim.onceki')}
          >
            <ChevronLeft className="h-4 w-4" aria-hidden="true" />
          </Button>
          <span>{t('siteAnalizi.yonetim.sayfa', { sayi: sayfa, toplam: sayfaSayisi })}</span>
          <Button
            variant="outline"
            size="icon"
            disabled={sayfa >= sayfaSayisi}
            onClick={() => setSayfa((s) => s + 1)}
            aria-label={t('siteAnalizi.yonetim.sonraki')}
          >
            <ChevronRight className="h-4 w-4" aria-hidden="true" />
          </Button>
        </div>
      )}
    </div>
  );
}
