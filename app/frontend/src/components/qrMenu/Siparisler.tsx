import { useCallback, useState } from 'react';
import { createPortal } from 'react-dom';
import { useTranslation } from 'react-i18next';
import { Loader2, Printer, RefreshCw, ShieldCheck, X } from 'lucide-react';
import { toast } from 'sonner';

import { Button } from '@/components/ui/button';
import { useYoklama } from '@/hooks/useYoklama';
import { DIS_DUGME, KART, Rozet, SECIM, tarihYaz } from '@/components/qrMenu/ortak';
import { SIPARIS_DURUMLARI, hataMetni, type Magaza, type MenuApi, type Siparis, type SiparisDurumu } from '@/lib/qrMenu';
import { paraYaz } from '@/lib/qrMenuOrtak';

/**
 * Faz 4M — siparişler: liste (yeni/hazırlanıyor/teslim edildi/iptal), yeni
 * sipariş sayacı (30 sn yoklama) ve 58/80 mm fiş yazdırma.
 *
 * Fiş `document.body`ye portal olarak çiziliyor; yazdırma CSS'i yalnız fişi
 * gösteriyor (`@page { size: 80mm auto }`), panelin geri kalanı kâğıda çıkmıyor.
 */

const YOKLAMA_MS = 20000;
const DURUM_RENGI: Record<SiparisDurumu, string> = {
  yeni: 'border-emerald-400/40 bg-emerald-500/15 text-emerald-200',
  hazirlaniyor: 'border-sky-400/40 bg-sky-500/15 text-sky-200',
  teslim_edildi: 'border-white/15 bg-white/[0.05] text-muted-foreground',
  iptal: 'border-red-400/40 bg-red-500/10 text-red-200',
};

function Fis({ siparis, magaza, genislik, onGenislik, onKapat }: { siparis: Siparis; magaza: Magaza; genislik: 58 | 80; onGenislik: (g: 58 | 80) => void; onKapat: () => void }) {
  const { t, i18n } = useTranslation();
  const dil = i18n.language || 'tr';
  const para = (n: number) => paraYaz(n, siparis.para_birimi, dil);
  const kagit = genislik === 58 ? 48 : 72; // yazdırılabilir alan (mm)
  const stil = `
.mk-fis-kok{position:fixed;inset:0;z-index:70;display:flex;flex-direction:column;align-items:center;gap:12px;overflow:auto;padding:24px 12px;background:rgba(0,0,0,.75)}
.mk-fis{width:${kagit}mm;background:#fff;color:#000;font:${genislik === 58 ? 11 : 12}px/1.35 ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;padding:4mm 3mm;box-shadow:0 10px 30px rgba(0,0,0,.4)}
.mk-fis h1{font-size:1.25em;margin:0 0 2px;text-align:center}
.mk-fis .orta{text-align:center}
.mk-fis hr{border:0;border-top:1px dashed #000;margin:6px 0}
.mk-fis .satir{display:flex;justify-content:space-between;gap:6px}
.mk-fis .satir span:last-child{white-space:nowrap}
.mk-fis .alt{padding-inline-start:10px;font-size:.92em}
.mk-fis .buyuk{font-weight:700;font-size:1.15em}
@media print{
  @page{size:${genislik}mm auto;margin:0}
  html,body{background:#fff!important}
  body>*:not(.mk-fis-kok){display:none!important}
  .mk-fis-kok{position:static;display:block;padding:0;background:#fff;overflow:visible}
  .mk-fis-kontrol{display:none!important}
  .mk-fis{box-shadow:none;margin:0;width:${kagit}mm}
}`;
  return createPortal(
    <div className="mk-fis-kok" role="dialog" aria-modal="true" aria-label={t('qrMenu.siparis.fis')} data-testid="menu-fis" data-genislik={genislik}>
      <style>{stil}</style>
      <div className="mk-fis-kontrol flex flex-wrap items-center gap-2 rounded-xl border border-white/10 bg-[#120b1f] p-2 text-sm text-white">
        <label className="flex items-center gap-1.5">
          {t('qrMenu.siparis.kagit')}
          <select className={`${SECIM} h-8 w-24`} value={genislik} onChange={(e) => onGenislik(Number(e.target.value) as 58 | 80)} data-testid="menu-fis-genislik">
            <option value={80}>80 mm</option>
            <option value={58}>58 mm</option>
          </select>
        </label>
        <Button size="sm" className="gap-1.5" onClick={() => window.print()} data-testid="menu-fis-yazdir">
          <Printer className="h-4 w-4" aria-hidden="true" />
          {t('qrMenu.siparis.yazdir')}
        </Button>
        <Button size="sm" variant="ghost" className="gap-1" onClick={onKapat} data-testid="menu-fis-kapat">
          <X className="h-4 w-4" aria-hidden="true" />
          {t('qrMenu.kapat')}
        </Button>
      </div>
      <div className="mk-fis" data-testid="menu-fis-kagit">
        <h1>{magaza.ad}</h1>
        {magaza.adres && <div className="orta">{magaza.adres}</div>}
        {magaza.telefon && <div className="orta">{magaza.telefon}</div>}
        <hr />
        <div className="satir buyuk">
          <span>#{siparis.siparis_no}</span>
          <span>{t(`qrMenuSayfa.teslimat.${siparis.teslimat}`)}</span>
        </div>
        <div>{tarihYaz(siparis.created_at, dil)}</div>
        {siparis.masa && <div className="buyuk">{t('qrMenuSayfa.masa', { masa: siparis.masa })}</div>}
        {siparis.musteri_ad && <div>{siparis.musteri_ad}</div>}
        {siparis.adres && <div>{siparis.adres}</div>}
        <hr />
        {siparis.kalemler.map((k, i) => (
          <div key={i}>
            <div className="satir">
              <span>
                {k.adet} × {k.ad}
              </span>
              <span>{para(k.tutar)}</span>
            </div>
            {k.secenekler.map((s, j) => (
              <div key={j} className="alt">
                + {s.ad}
              </div>
            ))}
          </div>
        ))}
        <hr />
        <div className="satir">
          <span>{t('qrMenuSayfa.araToplam')}</span>
          <span>{para(siparis.ara_toplam)}</span>
        </div>
        {siparis.indirim > 0 && (
          <div className="satir">
            <span>
              {t('qrMenuSayfa.indirim')}
              {siparis.kupon_kodu ? ` (${siparis.kupon_kodu})` : ''}
            </span>
            <span>−{para(siparis.indirim)}</span>
          </div>
        )}
        {siparis.paket_ucreti > 0 && (
          <div className="satir">
            <span>{t('qrMenuSayfa.paketUcreti')}</span>
            <span>{para(siparis.paket_ucreti)}</span>
          </div>
        )}
        <div className="satir buyuk">
          <span>{t('qrMenuSayfa.toplam')}</span>
          <span>{para(siparis.toplam)}</span>
        </div>
        {siparis.siparis_notu && (
          <>
            <hr />
            <div>
              {t('qrMenuSayfa.not')}: {siparis.siparis_notu}
            </div>
          </>
        )}
        <hr />
        <div className="orta">{t('qrMenu.siparis.tesekkur')}</div>
      </div>
    </div>,
    document.body
  );
}

export default function Siparisler({ api, magaza, onSayac }: { api: MenuApi; magaza: Magaza; onSayac: (n: number) => void }) {
  const { t, i18n } = useTranslation();
  const dil = i18n.language || 'tr';
  const [durum, setDurum] = useState('');
  const [veri, setVeri] = useState<{ items: Siparis[]; yeni_sayisi: number; saklama_gun: number } | null>(null);
  const [fis, setFis] = useState<Siparis | null>(null);
  const [genislik, setGenislik] = useState<58 | 80>(80);
  const [degisen, setDegisen] = useState<number | null>(null);

  const yukle = useCallback(async () => {
    const y = await api.siparisler(magaza.id, durum || undefined);
    setVeri(y);
    onSayac(y.yeni_sayisi);
  }, [api, magaza.id, durum, onSayac]);

  const { simdi } = useYoklama(
    async () => {
      try {
        await yukle();
      } catch (e) {
        toast.error(hataMetni(t, e));
        throw e;
      }
    },
    { aralik: YOKLAMA_MS, etkin: true, anahtar: `${magaza.id}|${durum}` }
  );

  const durumDegistir = async (s: Siparis, yeni: SiparisDurumu) => {
    setDegisen(s.id);
    try {
      await api.siparisDurumu(magaza.id, s.id, yeni);
      await yukle();
    } catch (e) {
      toast.error(hataMetni(t, e));
    } finally {
      setDegisen(null);
    }
  };

  const fisAc = async (s: Siparis) => {
    try {
      setFis(await api.siparis(magaza.id, s.id));
    } catch (e) {
      toast.error(hataMetni(t, e));
    }
  };

  return (
    <div className="space-y-4" data-testid="menu-siparisler">
      <div className={`${KART} flex flex-wrap items-center gap-3 p-4`}>
        <select className={`${SECIM} w-48`} value={durum} onChange={(e) => setDurum(e.target.value)} aria-label={t('qrMenu.siparis.durum')}>
          <option value="">{t('qrMenu.siparis.hepsi')}</option>
          {SIPARIS_DURUMLARI.map((d) => (
            <option key={d} value={d}>
              {t(`qrMenu.siparis.d.${d}`)}
            </option>
          ))}
        </select>
        <Button size="sm" variant="outline" className={DIS_DUGME} onClick={() => simdi()}>
          <RefreshCw className="h-4 w-4" aria-hidden="true" />
          {t('qrMenu.yenile')}
        </Button>
        {veri && (
          <span className="text-sm text-muted-foreground" data-testid="menu-siparis-yeni-sayisi">
            {t('qrMenu.siparis.yeniSayisi', { sayi: veri.yeni_sayisi })}
          </span>
        )}
        {veri && (
          <span className="ms-auto flex items-center gap-1 text-xs text-muted-foreground">
            <ShieldCheck className="h-3.5 w-3.5" aria-hidden="true" />
            {t('qrMenu.siparis.saklama', { gun: veri.saklama_gun })}
          </span>
        )}
      </div>

      {veri === null ? (
        <div className="flex justify-center py-10 text-muted-foreground">
          <Loader2 className="h-5 w-5 animate-spin" aria-hidden="true" />
        </div>
      ) : veri.items.length === 0 ? (
        <p className={`${KART} p-8 text-center text-sm text-muted-foreground`} data-testid="menu-siparis-bos">
          {t('qrMenu.siparis.bos')}
        </p>
      ) : (
        <ul className="grid gap-3 lg:grid-cols-2" data-testid="menu-siparis-listesi">
          {veri.items.map((s) => (
            <li key={s.id} className={`${KART} p-4`} data-siparis={s.siparis_no} data-durum={s.durum}>
              <div className="flex flex-wrap items-center gap-2">
                <span className="font-mono text-base font-semibold" dir="ltr">
                  #{s.siparis_no}
                </span>
                <Rozet renk={DURUM_RENGI[s.durum]}>{t(`qrMenu.siparis.d.${s.durum}`)}</Rozet>
                <Rozet>{t(`qrMenuSayfa.teslimat.${s.teslimat}`)}</Rozet>
                {s.masa && <Rozet renk="border-purple-400/40 bg-purple-500/15 text-purple-100">{t('qrMenuSayfa.masa', { masa: s.masa })}</Rozet>}
                <span className="ms-auto text-xs text-muted-foreground">{tarihYaz(s.created_at, dil)}</span>
              </div>
              {s.anonim ? (
                <p className="mt-2 text-xs text-muted-foreground">{t('qrMenu.siparis.anonim')}</p>
              ) : (
                <div className="mt-2 text-sm">
                  {s.musteri_ad && <div className="font-medium">{s.musteri_ad}</div>}
                  {s.adres && <div className="text-muted-foreground">{s.adres}</div>}
                  {s.siparis_notu && (
                    <div className="mt-1 rounded-lg bg-white/[0.04] px-2 py-1 text-xs">
                      {t('qrMenuSayfa.not')}: {s.siparis_notu}
                    </div>
                  )}
                </div>
              )}
              <ul className="mt-2 space-y-0.5 text-sm">
                {s.kalemler.map((k, i) => (
                  <li key={i} className="flex justify-between gap-2">
                    <span className="min-w-0">
                      {k.adet} × {k.ad}
                      {k.secenekler.length > 0 && <span className="text-xs text-muted-foreground"> ({k.secenekler.map((x) => x.ad).join(', ')})</span>}
                    </span>
                    <span className="whitespace-nowrap tabular-nums">{paraYaz(k.tutar, s.para_birimi, dil)}</span>
                  </li>
                ))}
              </ul>
              <div className="mt-2 flex justify-between border-t border-white/10 pt-2 text-sm font-semibold">
                <span>{t('qrMenuSayfa.toplam')}</span>
                <span className="tabular-nums" data-testid="menu-siparis-toplam">
                  {paraYaz(s.toplam, s.para_birimi, dil)}
                </span>
              </div>
              <div className="mt-3 flex flex-wrap items-center gap-2">
                <select
                  className={`${SECIM} h-9 w-44`}
                  value={s.durum}
                  disabled={degisen === s.id}
                  onChange={(e) => void durumDegistir(s, e.target.value as SiparisDurumu)}
                  aria-label={t('qrMenu.siparis.durum')}
                  data-testid="menu-siparis-durum"
                >
                  {SIPARIS_DURUMLARI.map((d) => (
                    <option key={d} value={d}>
                      {t(`qrMenu.siparis.d.${d}`)}
                    </option>
                  ))}
                </select>
                <Button size="sm" variant="outline" className={DIS_DUGME} onClick={() => void fisAc(s)} data-testid="menu-fis-ac">
                  <Printer className="h-4 w-4" aria-hidden="true" />
                  {t('qrMenu.siparis.fis')}
                </Button>
              </div>
            </li>
          ))}
        </ul>
      )}
      {fis && <Fis siparis={fis} magaza={magaza} genislik={genislik} onGenislik={setGenislik} onKapat={() => setFis(null)} />}
    </div>
  );
}
