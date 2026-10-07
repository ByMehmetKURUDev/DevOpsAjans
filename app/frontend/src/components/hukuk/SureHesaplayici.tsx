import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Calculator, CalendarPlus, Loader2 } from 'lucide-react';
import { toast } from 'sonner';

import { Button } from '@/components/ui/button';
import { Alan, Anahtar, GIRDI, KART, Not, SECIM } from '@/components/hukuk/ortak';
import { gunYaz, hataMetni, type Dosya, type HukukApi, type Meta, type SureAdimi, type SureBirimi, type SureSonucu } from '@/lib/hukuk';

/**
 * Faz 6H — süre hesaplayıcı (HMK m.92 başlangıç günü sayılmaz / karşılık gelen gün, m.93 tatil kaydırması,
 * m.104 adli tatil uzatması). Sunucu hesaplar; burada girdi, sonuç, uygulanan kurallar ve AÇIK uyarılar.
 * "Hesaplama yardımcıdır; kesin süreyi avukat doğrular."
 */
export default function SureHesaplayici({ api, meta }: { api: HukukApi; meta: Meta }) {
  const { t, i18n } = useTranslation();
  const dil = i18n.language || 'tr';
  const [baslangic, setBaslangic] = useState(meta.bugun);
  const [miktar, setMiktar] = useState('14');
  const [birim, setBirim] = useState<SureBirimi>('gun');
  const [adli, setAdli] = useState(true);
  const [sonuc, setSonuc] = useState<SureSonucu | null>(null);
  const [hesaplaniyor, setHesaplaniyor] = useState(false);
  const [dosyalar, setDosyalar] = useState<Dosya[]>([]);
  const [dosyaId, setDosyaId] = useState('');
  const [baslik, setBaslik] = useState('');

  useEffect(() => {
    api
      .ayarlar()
      .then((a) => setAdli(a.adli_tatil_varsayilan))
      .catch(() => undefined);
    api
      .dosyalar({ durum: 'acik' })
      .then((r) => setDosyalar(r.items))
      .catch(() => setDosyalar([]));
  }, [api]);

  const girdi = () => ({ baslangic, miktar: Number(miktar) || 0, birim, adli_tatil: adli });

  const hesapla = async () => {
    setHesaplaniyor(true);
    try {
      setSonuc(await api.sureHesapla(girdi()));
    } catch (e) {
      toast.error(hataMetni(t, e));
      setSonuc(null);
    } finally {
      setHesaplaniyor(false);
    }
  };

  const takvimeEkle = async () => {
    try {
      await api.olayEkle({ tur: 'kesin_sure', dosya_id: dosyaId ? Number(dosyaId) : null, baslik, hesap: girdi() });
      toast.success(t('hukuk.sure.olayEklendi'));
      setBaslik('');
    } catch (e) {
      toast.error(hataMetni(t, e));
    }
  };

  const adimMetni = (a: SureAdimi) => {
    if (a.kural === 'hmk92') return t('hukuk.sure.kural.hmk92', { tarih: gunYaz(a.tarih, dil) });
    if (a.kural === 'hmk104') return t('hukuk.sure.kural.hmk104', { tarih: gunYaz(a.tarih, dil), bitis: gunYaz(a.adli_tatil_bitis, dil), gun: a.uzatma_gun ?? 7 });
    return t('hukuk.sure.kural.hmk93', { tarih: gunYaz(a.tarih, dil) });
  };

  return (
    <div className="space-y-4" data-testid="hukuk-sure">
      <Not tur="uyari" testid="hukuk-sure-not">
        {t('hukuk.sure.not')}
      </Not>
      <div className={`${KART} space-y-3 p-4 sm:p-6`}>
        <h3 className="flex items-center gap-2 text-base font-semibold">
          <Calculator className="h-4 w-4" aria-hidden="true" />
          {t('hukuk.sure.baslik')}
        </h3>
        <div className="grid gap-3 sm:grid-cols-[180px_100px_140px] sm:items-end">
          <Alan etiket={t('hukuk.sure.baslangic')}>
            <input className={GIRDI} type="date" value={baslangic} onChange={(e) => setBaslangic(e.target.value)} data-testid="hukuk-sure-baslangic" />
          </Alan>
          <Alan etiket={t('hukuk.sure.miktar')}>
            <input className={GIRDI} type="number" min={1} max={3650} value={miktar} onChange={(e) => setMiktar(e.target.value)} data-testid="hukuk-sure-miktar" />
          </Alan>
          <Alan etiket={t('hukuk.sure.birimEtiket')}>
            <select className={SECIM} value={birim} onChange={(e) => setBirim(e.target.value as SureBirimi)} data-testid="hukuk-sure-birim">
              {meta.sure_birimleri.map((b) => (
                <option key={b} value={b}>
                  {t(`hukuk.sure.birim.${b}`)}
                </option>
              ))}
            </select>
          </Alan>
        </div>
        <div>
          <Anahtar acik={adli} onDegis={setAdli} etiket={t('hukuk.sure.adliTatil')} testid="hukuk-sure-adli" />
          <p className="ms-6 text-xs text-muted-foreground">{t('hukuk.sure.adliTatilIpucu')}</p>
        </div>
        <Button onClick={() => void hesapla()} disabled={hesaplaniyor || !baslangic} className="gap-1.5" data-testid="hukuk-sure-hesapla">
          {hesaplaniyor && <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />}
          {t('hukuk.sure.hesapla')}
        </Button>
        <p className="text-xs text-muted-foreground">{t('hukuk.sure.tatilNotu')}</p>
      </div>

      {sonuc && (
        <div className={`${KART} space-y-3 p-4 sm:p-6`} data-testid="hukuk-sure-sonuc" data-son-gun={sonuc.son_gun}>
          <p className="text-xs uppercase tracking-wide text-muted-foreground">{t('hukuk.sure.sonuc')}</p>
          <p className="text-2xl font-bold text-white">{gunYaz(sonuc.son_gun, dil, { dateStyle: 'full' })}</p>
          <p className="text-sm text-muted-foreground">{t('hukuk.sure.sonucMetni')}</p>
          <div>
            <p className="mb-1 text-sm font-medium">{t('hukuk.sure.adimlar')}</p>
            <ol className="list-decimal space-y-1 ps-5 text-sm" data-testid="hukuk-sure-adimlar">
              {sonuc.adimlar.map((a, i) => (
                <li key={i} data-kural={a.kural}>
                  {adimMetni(a)}
                  {a.atlanan && a.atlanan.length > 0 && (
                    <span className="block text-xs text-muted-foreground">
                      {a.atlanan.map((x) => t(`hukuk.sure.atlanan.${x.neden}`, { tarih: gunYaz(x.tarih, dil), ad: x.ad || '' })).join(' · ')}
                    </span>
                  )}
                </li>
              ))}
            </ol>
          </div>
          {sonuc.uyarilar.map((u) => (
            <Not key={u} tur="uyari">
              {t(`hukuk.sure.uyari.${u}`)}
            </Not>
          ))}
          <div className="grid gap-2 border-t border-white/10 pt-3 sm:grid-cols-[minmax(0,1fr)_minmax(0,1fr)_auto] sm:items-end">
            <Alan etiket={t('hukuk.olay.alan.dosya')}>
              <select className={SECIM} value={dosyaId} onChange={(e) => setDosyaId(e.target.value)} data-testid="hukuk-sure-dosya">
                <option value="">{t('hukuk.olay.alan.dosyaYok')}</option>
                {dosyalar.map((d) => (
                  <option key={d.id} value={d.id}>
                    {d.baslik} · {d.muvekkil_ad}
                  </option>
                ))}
              </select>
            </Alan>
            <Alan etiket={t('hukuk.olay.alan.baslik')}>
              <input className={GIRDI} value={baslik} maxLength={200} onChange={(e) => setBaslik(e.target.value)} />
            </Alan>
            <Button variant="outline" className="gap-1 !bg-transparent" onClick={() => void takvimeEkle()} data-testid="hukuk-sure-takvime">
              <CalendarPlus className="h-4 w-4" aria-hidden="true" />
              {t('hukuk.sure.olayEkle')}
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}
