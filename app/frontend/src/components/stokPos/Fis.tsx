import { useState, type ReactNode } from 'react';
import { createPortal } from 'react-dom';
import { useTranslation } from 'react-i18next';
import { Download, Printer, X } from 'lucide-react';

import { Button } from '@/components/ui/button';
import { miktarYaz, para, tarihSaat, type Ozet, type Oturum, type Satis } from '@/lib/stokPos';

/**
 * Faz 6P — 80/58 mm termal yazıcıya uygun yazdırma görünümü (fiş ve Z-benzeri gün sonu).
 *
 * Kâğıt `document.body`ye portal olarak çiziliyor; yazdırma CSS'i yalnız kâğıdı gösteriyor
 * (`@page { size: 80mm auto }`), panelin geri kalanı kâğıda çıkmıyor (Faz 4M sipariş fişi deseni).
 * Her fişte "mali fiş değildir" ibaresi var: ÖKC fişi / e-Arşiv belge yerine geçmez.
 */
export function Kagit({ baslik, children, onKapat, onPdf, testid }: { baslik: string; children: ReactNode; onKapat: () => void; onPdf?: () => void; testid?: string }) {
  const { t } = useTranslation();
  const [genislik, setGenislik] = useState<58 | 80>(80);
  const kagit = genislik === 58 ? 48 : 72;
  const stil = `
.mk-pos-kok{position:fixed;inset:0;z-index:70;display:flex;flex-direction:column;align-items:center;gap:12px;overflow:auto;padding:16px 8px;background:rgba(0,0,0,.78)}
.mk-pos-fis{width:${kagit}mm;max-width:100%;background:#fff;color:#000;font:${genislik === 58 ? 11 : 12}px/1.35 ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;padding:4mm 3mm;box-shadow:0 10px 30px rgba(0,0,0,.4)}
.mk-pos-fis h1{font-size:1.2em;margin:0 0 2px;text-align:center}
.mk-pos-fis .orta{text-align:center}
.mk-pos-fis hr{border:0;border-top:1px dashed #000;margin:6px 0}
.mk-pos-fis .satir{display:flex;justify-content:space-between;gap:6px}
.mk-pos-fis .satir span:last-child{white-space:nowrap}
.mk-pos-fis .alt{padding-inline-start:10px;font-size:.92em}
.mk-pos-fis .buyuk{font-weight:700;font-size:1.15em}
.mk-pos-fis .kucuk{font-size:.85em}
@media print{
  @page{size:${genislik}mm auto;margin:0}
  html,body{background:#fff!important}
  body>*:not(.mk-pos-kok){display:none!important}
  .mk-pos-kok{position:static;display:block;padding:0;background:#fff;overflow:visible}
  .mk-pos-kontrol{display:none!important}
  .mk-pos-fis{box-shadow:none;margin:0;width:${kagit}mm}
}`;
  return createPortal(
    <div className="mk-pos-kok" role="dialog" aria-modal="true" aria-label={baslik} data-testid={testid} data-genislik={genislik}>
      <style>{stil}</style>
      <div className="mk-pos-kontrol flex flex-wrap items-center justify-center gap-2 rounded-xl border border-white/10 bg-[#120b1f] p-2 text-sm text-white">
        <label className="flex items-center gap-1.5">
          {t('stokPos.fis.kagit')}
          <select
            className="h-8 w-24 rounded-md border border-white/10 bg-black/40 px-2 text-sm"
            value={genislik}
            onChange={(e) => setGenislik(Number(e.target.value) as 58 | 80)}
            data-testid="pos-fis-genislik"
          >
            <option value={80}>80 mm</option>
            <option value={58}>58 mm</option>
          </select>
        </label>
        <Button size="sm" className="gap-1.5" onClick={() => window.print()} data-testid="pos-fis-yazdir">
          <Printer className="h-4 w-4" aria-hidden="true" />
          {t('stokPos.fis.yazdir')}
        </Button>
        {onPdf && (
          <Button size="sm" variant="outline" className="gap-1.5 !bg-transparent border-white/20" onClick={onPdf} data-testid="pos-fis-pdf">
            <Download className="h-4 w-4" aria-hidden="true" />
            PDF
          </Button>
        )}
        <Button size="sm" variant="ghost" className="gap-1" onClick={onKapat} data-testid="pos-fis-kapat">
          <X className="h-4 w-4" aria-hidden="true" />
          {t('stokPos.kapat')}
        </Button>
      </div>
      <div className="mk-pos-fis" dir="auto" data-testid="pos-fis-kagit">
        {children}
      </div>
    </div>,
    document.body
  );
}

function Satir({ sol, sag, sinif }: { sol: ReactNode; sag: ReactNode; sinif?: string }) {
  return (
    <div className={`satir ${sinif ?? ''}`}>
      <span>{sol}</span>
      <span>{sag}</span>
    </div>
  );
}

export function Fis({ satis, onKapat, onPdf }: { satis: Satis; onKapat: () => void; onPdf?: () => void }) {
  const { t, i18n } = useTranslation();
  const dil = i18n.language || 'tr';
  const p = (n: number) => para(n, satis.para_birimi, dil);
  const f = satis.firma;
  const vergi = [f.vergi_dairesi, f.vergi_no].filter(Boolean).join(' / ');
  return (
    <Kagit baslik={t('stokPos.fis.baslik')} onKapat={onKapat} onPdf={onPdf} testid="pos-fis">
      {f.ad && <h1>{f.ad}</h1>}
      {f.adres && <div className="orta">{f.adres}</div>}
      {f.telefon && <div className="orta">{f.telefon}</div>}
      {vergi && <div className="orta">{vergi}</div>}
      <hr />
      <div className="orta buyuk">{t('stokPos.fis.baslik')}</div>
      <Satir sol={`${t('stokPos.fis.no')}: ${satis.no}`} sag={tarihSaat(satis.zaman, dil)} />
      {satis.musteri_ad && <div className="kucuk">{t('stokPos.fis.musteri')}: {satis.musteri_ad}</div>}
      <hr />
      {satis.kalemler.map((k) => (
        <div key={k.id}>
          <div>{k.ad}</div>
          <Satir
            sinif="kucuk"
            sol={`${miktarYaz(k.adet, dil)}${k.birim === 'adet' ? '' : ` ${t(`stokPos.birim.${k.birim}`)}`} × ${p(k.birim_fiyat)}  %${k.kdv_orani}`}
            sag={p(k.brut)}
          />
          {k.satir_indirim > 0 && <Satir sinif="alt" sol={t('stokPos.fis.indirim')} sag={`−${p(k.satir_indirim)}`} />}
        </div>
      ))}
      <hr />
      {satis.toplam_indirim > 0 && (
        <>
          <Satir sol={t('stokPos.fis.araToplam')} sag={p(satis.ara_toplam - satis.satir_indirim)} />
          <Satir sol={t('stokPos.fis.indirim')} sag={`−${p(satis.toplam_indirim)}`} />
        </>
      )}
      <Satir sinif="buyuk" sol={t('stokPos.fis.toplam')} sag={<span data-testid="pos-fis-toplam">{p(satis.toplam)}</span>} />
      {satis.kdv_dokumu
        .filter((d) => d.kdv > 0)
        .map((d) => (
          <Satir key={d.oran} sinif="kucuk" sol={t('stokPos.fis.kdv', { oran: d.oran })} sag={p(d.kdv)} />
        ))}
      <Satir sinif="kucuk" sol={t('stokPos.fis.kdvToplam')} sag={p(satis.kdv_toplam)} />
      <hr />
      {(['nakit', 'kart', 'havale'] as const)
        .filter((tur) => satis[tur] > 0)
        .map((tur) => (
          <Satir key={tur} sol={t(`stokPos.odeme.${tur}`)} sag={p(satis[tur])} />
        ))}
      {satis.nakit > 0 && satis.para_ustu > 0 && (
        <>
          <Satir sol={t('stokPos.fis.alinan')} sag={p(satis.nakit_alinan)} />
          <Satir sinif="buyuk" sol={t('stokPos.fis.paraUstu')} sag={<span data-testid="pos-fis-para-ustu">{p(satis.para_ustu)}</span>} />
        </>
      )}
      {satis.iade_toplam > 0 && <Satir sol={t('stokPos.fis.iade')} sag={`−${p(satis.iade_toplam)}`} />}
      {satis.durum === 'iptal' && <div className="orta buyuk">{t('stokPos.durum.iptal')}</div>}
      <hr />
      {f.fis_notu && <div className="orta">{f.fis_notu}</div>}
      {satis.kart > 0 && <div className="orta kucuk">{t('stokPos.fis.kartNotu')}</div>}
      <div className="orta kucuk" style={{ fontWeight: 700 }} data-testid="pos-fis-mali-degil">
        {t('stokPos.fis.maliDegil')}
      </div>
    </Kagit>
  );
}

export function ZRaporu({ ozet, oturum, konum, onKapat }: { ozet: Ozet; oturum?: Oturum; konum?: string; onKapat: () => void }) {
  const { t, i18n } = useTranslation();
  const dil = i18n.language || 'tr';
  const p = (n: number | null | undefined) => para(n ?? 0, ozet.para_birimi, dil);
  return (
    <Kagit baslik={t('stokPos.z.baslik')} onKapat={onKapat} testid="pos-z">
      <h1>{t('stokPos.z.baslik')}</h1>
      <div className="orta kucuk" style={{ fontWeight: 700 }}>
        {t('stokPos.z.maliDegil')}
      </div>
      <hr />
      {konum && <Satir sol={t('stokPos.konum')} sag={konum} />}
      {oturum && (
        <>
          <Satir sol={t('stokPos.z.acilis')} sag={tarihSaat(oturum.acilis_at, dil)} />
          {oturum.kapanis_at && <Satir sol={t('stokPos.z.kapanis')} sag={tarihSaat(oturum.kapanis_at, dil)} />}
        </>
      )}
      {ozet.tarih && <Satir sol={t('stokPos.z.tarih')} sag={ozet.tarih} />}
      <hr />
      <Satir sol={t('stokPos.z.satisSayisi')} sag={ozet.satis_sayisi} />
      <Satir sol={t('stokPos.z.brut')} sag={p(ozet.brut)} />
      <Satir sol={t('stokPos.z.indirim')} sag={`−${p(ozet.indirim)}`} />
      <Satir sol={t('stokPos.z.satisToplam')} sag={p(ozet.satis_toplam)} />
      <Satir sol={t('stokPos.z.iade', { sayi: ozet.iade_sayisi })} sag={`−${p(ozet.iade_toplam)}`} />
      {ozet.iptal_sayisi > 0 && <Satir sol={t('stokPos.z.iptal', { sayi: ozet.iptal_sayisi })} sag={p(ozet.iptal_toplam)} />}
      <Satir sinif="buyuk" sol={t('stokPos.z.net')} sag={<span data-testid="pos-z-net">{p(ozet.net)}</span>} />
      <hr />
      <div className="buyuk">{t('stokPos.z.odemeler')}</div>
      {(['nakit', 'kart', 'havale'] as const).map((tur) => (
        <Satir key={tur} sol={t(`stokPos.odeme.${tur}`)} sag={p(ozet.odemeler[tur])} />
      ))}
      <hr />
      <div className="buyuk">{t('stokPos.z.kdvDokumu')}</div>
      {ozet.kdv_dokumu.map((d) => (
        <Satir key={d.oran} sinif="kucuk" sol={t('stokPos.z.kdvSatiri', { oran: d.oran, matrah: p(d.matrah) })} sag={p(d.kdv)} />
      ))}
      {ozet.en_cok_satanlar.length > 0 && (
        <>
          <hr />
          <div className="buyuk">{t('stokPos.z.enCok')}</div>
          {ozet.en_cok_satanlar.slice(0, 5).map((u) => (
            <Satir key={u.urun_id} sinif="kucuk" sol={`${miktarYaz(u.adet, dil)} × ${u.ad}`} sag={p(u.tutar)} />
          ))}
        </>
      )}
      {ozet.nakit && (
        <>
          <hr />
          <div className="buyuk">{t('stokPos.z.nakitMutabakat')}</div>
          <Satir sol={t('stokPos.z.acilisNakit')} sag={p(ozet.nakit.acilis)} />
          <Satir sol={t('stokPos.z.nakitSatis')} sag={p(ozet.nakit.satis)} />
          <Satir sol={t('stokPos.z.nakitIade')} sag={`−${p(ozet.nakit.iade)}`} />
          <Satir sol={t('stokPos.z.beklenen')} sag={p(ozet.nakit.beklenen)} />
          {ozet.nakit.sayilan !== null && ozet.nakit.sayilan !== undefined && (
            <>
              <Satir sol={t('stokPos.z.sayilan')} sag={p(ozet.nakit.sayilan)} />
              <Satir sinif="buyuk" sol={t('stokPos.z.fark')} sag={<span data-testid="pos-z-fark">{p(ozet.nakit.fark)}</span>} />
            </>
          )}
        </>
      )}
    </Kagit>
  );
}
