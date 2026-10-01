import { useCallback, useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';
import { ArrowDown, ArrowUp, Languages, Loader2, Plus, Save, Trash2 } from 'lucide-react';

import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import {
  asamaAdi,
  asamaEkle,
  asamaGuncelle,
  asamaListesi,
  asamaSil,
  asamaSirala,
  hataMetni,
  renk,
  RENK_SINIFI,
  type Asama,
  type AsamaTuru,
} from '@/lib/crm';
import { Bekle, SECIM } from './ortak';

const DILLER = ['en', 'de', 'ru', 'zh', 'hi', 'ar'] as const;
const TURLER: AsamaTuru[] = ['acik', 'kazanildi', 'kaybedildi'];

/**
 * Aşama yönetimi: ekle, yeniden adlandır (7 dil), renk/tür/olasılık, sırala
 * (yukarı/aşağı — klavyeyle de), sil. İçinde aday olan aşama silinirken
 * adayların taşınacağı aşamayı seçmek zorunlu (sunucu da 409 veriyor).
 */
export default function CrmAsamalari({ onDegisti }: { onDegisti: () => void }) {
  const { t } = useTranslation();
  const [liste, setListe] = useState<Asama[] | null>(null);
  const [mesgul, setMesgul] = useState(false);
  const [yeni, setYeni] = useState({ ad: '', renk: 'slate', tur: 'acik' as AsamaTuru });

  const yukle = useCallback(async () => {
    try {
      setListe((await asamaListesi()).asamalar);
    } catch (e) {
      toast.error(hataMetni(t, e));
    }
  }, [t]);

  useEffect(() => {
    void yukle();
  }, [yukle]);

  const islem = async (is: () => Promise<unknown>, basari?: string) => {
    setMesgul(true);
    try {
      await is();
      if (basari) toast.success(basari);
      await yukle();
      onDegisti();
    } catch (e) {
      toast.error(hataMetni(t, e));
    } finally {
      setMesgul(false);
    }
  };

  const kaydir = (i: number, yon: -1 | 1) => {
    if (!liste) return;
    const j = i + yon;
    if (j < 0 || j >= liste.length) return;
    const sira = liste.map((a) => a.anahtar);
    [sira[i], sira[j]] = [sira[j], sira[i]];
    void islem(() => asamaSirala(sira));
  };

  if (!liste) return <Bekle />;

  return (
    <div className="space-y-4" data-testid="crm-asamalar">
      <p className="text-sm text-muted-foreground">{t('crm.asamaYonetimi.aciklama')}</p>
      <ul className="space-y-2">
        {liste.map((a, i) => (
          <AsamaSatiri
            key={a.anahtar}
            a={a}
            liste={liste}
            ilk={i === 0}
            son={i === liste.length - 1}
            mesgul={mesgul}
            onYukari={() => kaydir(i, -1)}
            onAsagi={() => kaydir(i, 1)}
            onKaydet={(veri) => islem(() => asamaGuncelle(a.anahtar, veri), t('crm.kaydedildi'))}
            onSil={(hedef) => islem(() => asamaSil(a.anahtar, hedef), t('crm.asamaYonetimi.silindi'))}
          />
        ))}
      </ul>

      <form
        className="cam-kart grid gap-2 rounded-2xl border border-white/10 bg-white/[0.03] p-3 sm:grid-cols-[1fr_9rem_9rem_auto] sm:items-center"
        onSubmit={(e) => {
          e.preventDefault();
          if (!yeni.ad.trim()) return;
          void islem(async () => {
            await asamaEkle(yeni);
            setYeni({ ad: '', renk: 'slate', tur: 'acik' });
          }, t('crm.asamaYonetimi.eklendi'));
        }}
      >
        <Input
          value={yeni.ad}
          onChange={(e) => setYeni((y) => ({ ...y, ad: e.target.value }))}
          placeholder={t('crm.asamaYonetimi.yeniAd')}
          aria-label={t('crm.asamaYonetimi.yeniAd')}
          maxLength={60}
          data-testid="crm-asama-yeni"
        />
        <select aria-label={t('crm.asamaYonetimi.renk')} className={SECIM} value={yeni.renk} onChange={(e) => setYeni((y) => ({ ...y, renk: e.target.value }))}>
          {Object.keys(RENK_SINIFI).map((r) => (
            <option key={r} value={r}>
              {t(`crm.renk.${r}`)}
            </option>
          ))}
        </select>
        <select
          aria-label={t('crm.asamaYonetimi.tur')}
          className={SECIM}
          value={yeni.tur}
          onChange={(e) => setYeni((y) => ({ ...y, tur: e.target.value as AsamaTuru }))}
        >
          {TURLER.map((x) => (
            <option key={x} value={x}>
              {t(`crm.asamaTuru.${x}`)}
            </option>
          ))}
        </select>
        <Button type="submit" size="sm" disabled={mesgul || !yeni.ad.trim()} className="gap-1">
          {mesgul ? <Loader2 className="h-4 w-4 animate-spin" /> : <Plus className="h-4 w-4" />}
          {t('crm.asamaYonetimi.ekle')}
        </Button>
      </form>
      <p className="text-xs text-muted-foreground">{t('crm.asamaYonetimi.kural')}</p>
    </div>
  );
}

function AsamaSatiri({
  a,
  liste,
  ilk,
  son,
  mesgul,
  onYukari,
  onAsagi,
  onKaydet,
  onSil,
}: {
  a: Asama;
  liste: Asama[];
  ilk: boolean;
  son: boolean;
  mesgul: boolean;
  onYukari: () => void;
  onAsagi: () => void;
  onKaydet: (veri: Record<string, unknown>) => void;
  onSil: (hedef?: string) => void;
}) {
  const { t, i18n } = useTranslation();
  const dil = i18n.language;
  const [ad, setAd] = useState(a.ad);
  const [renkAdi, setRenkAdi] = useState(a.renk);
  const [tur, setTur] = useState<AsamaTuru>(a.tur);
  const [olasilik, setOlasilik] = useState(a.olasilik === null ? '' : String(a.olasilik));
  const [ceviriAcik, setCeviriAcik] = useState(false);
  const [ceviriler, setCeviriler] = useState<Record<string, string>>(
    Object.fromEntries(DILLER.map((d) => [d, a.ceviriler?.[d]?.ad || ''])),
  );
  const [silHedefi, setSilHedefi] = useState('');
  const [silAcik, setSilAcik] = useState(false);
  const sayi = a.aday_sayisi ?? 0;

  return (
    <li className={`cam-kart rounded-2xl border bg-white/[0.03] p-3 ${renk(a.renk).kenar}`} data-crm-asama={a.anahtar}>
      <div className="flex flex-wrap items-center gap-2">
        <div className="flex flex-col">
          <button
            type="button"
            className="rounded p-0.5 hover:bg-white/5 disabled:opacity-30"
            onClick={onYukari}
            disabled={ilk || mesgul}
            aria-label={t('crm.asamaYonetimi.yukari', { ad: asamaAdi(a, dil) })}
          >
            <ArrowUp className="h-3.5 w-3.5" />
          </button>
          <button
            type="button"
            className="rounded p-0.5 hover:bg-white/5 disabled:opacity-30"
            onClick={onAsagi}
            disabled={son || mesgul}
            aria-label={t('crm.asamaYonetimi.asagi', { ad: asamaAdi(a, dil) })}
          >
            <ArrowDown className="h-3.5 w-3.5" />
          </button>
        </div>
        <span className={`h-2.5 w-2.5 rounded-full ${renk(renkAdi).nokta}`} aria-hidden="true" />
        <Input
          className="h-9 min-w-[10rem] flex-1"
          value={ad}
          onChange={(e) => setAd(e.target.value)}
          maxLength={60}
          aria-label={t('crm.asamaYonetimi.ad')}
        />
        <select aria-label={t('crm.asamaYonetimi.renk')} className={SECIM + ' w-28'} value={renkAdi} onChange={(e) => setRenkAdi(e.target.value)}>
          {Object.keys(RENK_SINIFI).map((r) => (
            <option key={r} value={r}>
              {t(`crm.renk.${r}`)}
            </option>
          ))}
        </select>
        <select
          aria-label={t('crm.asamaYonetimi.tur')}
          className={SECIM + ' w-32'}
          value={tur}
          onChange={(e) => setTur(e.target.value as AsamaTuru)}
        >
          {TURLER.map((x) => (
            <option key={x} value={x}>
              {t(`crm.asamaTuru.${x}`)}
            </option>
          ))}
        </select>
        <Input
          className="h-9 w-20"
          type="number"
          min={0}
          max={100}
          value={olasilik}
          onChange={(e) => setOlasilik(e.target.value)}
          aria-label={t('crm.alan.olasilik')}
          placeholder="%"
        />
        <span className="text-xs text-muted-foreground">{t('crm.asamaYonetimi.adaySayisi', { sayi })}</span>
        <div className="ms-auto flex items-center gap-1">
          <Button size="sm" variant="ghost" onClick={() => setCeviriAcik((x) => !x)} aria-expanded={ceviriAcik} aria-label={t('crm.asamaYonetimi.ceviriler')}>
            <Languages className="h-4 w-4" />
          </Button>
          <Button
            size="sm"
            variant="outline"
            disabled={mesgul || !ad.trim()}
            onClick={() =>
              onKaydet({
                ad,
                renk: renkAdi,
                tur,
                olasilik: olasilik === '' ? null : Number(olasilik),
                ceviriler: Object.fromEntries(Object.entries(ceviriler).map(([d, v]) => [d, { ad: v }])),
              })
            }
            aria-label={t('crm.kaydet')}
          >
            <Save className="h-4 w-4" />
          </Button>
          <Button size="sm" variant="ghost" className="text-destructive" disabled={mesgul} onClick={() => setSilAcik((x) => !x)} aria-label={t('crm.sil')}>
            <Trash2 className="h-4 w-4" />
          </Button>
        </div>
      </div>
      {ceviriAcik && (
        <div className="mt-3 grid gap-2 sm:grid-cols-3">
          {DILLER.map((d) => (
            <label key={d} className="block text-xs">
              <span className="uppercase text-muted-foreground">{d}</span>
              <Input
                className="mt-0.5 h-8"
                value={ceviriler[d]}
                placeholder={a.ad}
                dir={d === 'ar' ? 'rtl' : undefined}
                onChange={(e) => setCeviriler((c) => ({ ...c, [d]: e.target.value }))}
                maxLength={60}
              />
            </label>
          ))}
        </div>
      )}
      {silAcik && (
        <div className="mt-3 flex flex-wrap items-center gap-2 rounded-xl border border-rose-400/30 bg-rose-500/[0.06] p-2 text-xs">
          {sayi > 0 ? (
            <>
              <span>{t('crm.asamaYonetimi.tasimaGerekli', { sayi })}</span>
              <select aria-label={t('crm.asamaYonetimi.hedef')} className={SECIM + ' h-8 w-48 text-xs'} value={silHedefi} onChange={(e) => setSilHedefi(e.target.value)}>
                <option value="">{t('crm.asamaYonetimi.hedefSec')}</option>
                {liste
                  .filter((x) => x.anahtar !== a.anahtar)
                  .map((x) => (
                    <option key={x.anahtar} value={x.anahtar}>
                      {asamaAdi(x, dil)}
                    </option>
                  ))}
              </select>
            </>
          ) : (
            <span>{t('crm.asamaYonetimi.silOnay', { ad: asamaAdi(a, dil) })}</span>
          )}
          <Button size="sm" variant="destructive" disabled={mesgul || (sayi > 0 && !silHedefi)} onClick={() => onSil(silHedefi || undefined)}>
            {t('crm.sil')}
          </Button>
        </div>
      )}
    </li>
  );
}
