import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Copy, FileDown, History, Info, Landmark, Loader2, Plus, Settings2, Wallet, XCircle } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';

import HareketSatiri from '@/components/cuzdan/HareketSatiri';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { BelgeHatasi, bugunIso, paraBicimle, pdfDili, pdfIndir, tarihBicimle } from '@/lib/belge';
import {
  CUZDAN_PARA_BIRIMLERI,
  YUKLEME_YONTEMLERI,
  ayarlarimiYaz,
  ekstrem,
  hareketlerim,
  talebiIptalEt,
  yuklemeTalebiGonder,
  type CuzdanHareketi,
  type MusteriCuzdani,
} from '@/lib/cuzdan';

/**
 * Faz 5C — Müşteri paneli › Faturalar › "Bakiyem": bakiye kartı (para birimi başına), "Bakiye yükle" (ajansın
 * havale bilgisi + hesaba özgü açıklama kodu + tutar/dekont bildirimi → yönetici onayı), bildirimler, hareketler,
 * ekstre PDF/CSV, otomatik ödeme (açarken onay metni) ve düşük bakiye eşiği. Hukuki çerçeve notu her zaman görünür.
 * Metinler `cuzdan` ek paketinde (Faturalar sekmesiyle birlikte yükleniyor).
 */
type Panel = 'yukle' | 'hareketler' | 'ayarlar' | null;
const SECIM = 'h-10 w-full rounded-md border border-white/10 bg-white/5 px-2 text-sm';

export default function Bakiyem({ ozet, onDegisti }: { ozet: MusteriCuzdani; onDegisti: () => void }) {
  const { t, i18n } = useTranslation();
  const dil = i18n.language;
  const [panel, setPanel] = useState<Panel>(null);
  const kok = useRef<HTMLElement | null>(null);

  useEffect(() => {
    // `?sekme=invoices&bolum=bakiye` (bildirim bağlantıları) → bölüme kaydır.
    try {
      if (new URLSearchParams(window.location.search).get('bolum') === 'bakiye') kok.current?.scrollIntoView({ block: 'start' });
    } catch {
      /* tarayıcı dışı */
    }
  }, []);

  const hata = useCallback(
    (h: unknown) => {
      const kod = h instanceof BelgeHatasi ? h.kod : 'genel';
      toast.error(t(`cuzdan.hata.${kod}`, { defaultValue: t('cuzdan.hata.genel') }));
    },
    [t],
  );

  const bekleyenler = ozet.talepler.filter((x) => x.durum === 'beklemede' || x.durum === 'reddedildi').slice(0, 6);
  const sekme = (p: Panel) => setPanel(panel === p ? null : p);

  return (
    <section ref={kok} id="bakiyem" className="cam-kart scroll-mt-24 rounded-2xl border border-white/10 bg-white/[0.03] p-5" data-testid="bakiyem">
      <div className="flex flex-wrap items-start gap-3">
        <div className="min-w-0 flex-1">
          <h3 className="flex items-center gap-2 text-lg font-semibold">
            <Wallet className="h-5 w-5 text-purple-300" aria-hidden="true" />{t('cuzdan.baslik')}
          </h3>
          <p className="mt-1 text-sm text-muted-foreground">{t('cuzdan.aciklama')}</p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button size="sm" className="gap-1" onClick={() => sekme('yukle')} aria-expanded={panel === 'yukle'} data-bakiyem-ac="yukle">
            <Plus className="h-4 w-4" aria-hidden="true" />{t('cuzdan.yukle.dugme')}
          </Button>
          <Button size="sm" variant="ghost" className="gap-1" onClick={() => sekme('hareketler')} aria-expanded={panel === 'hareketler'}
            data-bakiyem-ac="hareketler">
            <History className="h-4 w-4" aria-hidden="true" />{t('cuzdan.hareketler.baslik')}
          </Button>
          <Button size="sm" variant="ghost" className="gap-1" onClick={() => sekme('ayarlar')} aria-expanded={panel === 'ayarlar'}
            data-bakiyem-ac="ayarlar">
            <Settings2 className="h-4 w-4" aria-hidden="true" />{t('cuzdan.ayarlar.baslik')}
          </Button>
        </div>
      </div>

      <div className="mt-4 flex flex-wrap gap-3" data-testid="bakiyem-bakiyeler">
        {ozet.bakiyeler.length === 0 ? (
          <p className="text-sm text-muted-foreground">{t('cuzdan.bakiyeYok')}</p>
        ) : (
          ozet.bakiyeler.map((b) => (
            <div key={b.para_birimi} className="rounded-xl border border-white/10 bg-white/[0.03] px-4 py-2" data-bakiye-pb={b.para_birimi}>
              <p className="text-xs text-muted-foreground">{t('cuzdan.bakiye')} · {b.para_birimi}</p>
              <p className="text-2xl font-bold tabular-nums gradient-text" data-bakiye-tutar={b.bakiye}>{paraBicimle(b.bakiye, b.para_birimi, dil)}</p>
              {b.dusuk_uyari && <p className="text-[11px] text-amber-300">{t('cuzdan.dusuk')}</p>}
            </div>
          ))
        )}
      </div>

      {bekleyenler.length > 0 && (
        <div className="mt-4">
          <p className="mb-2 text-sm font-semibold">{t('cuzdan.yukle.bekleyen')}</p>
          <ul className="space-y-2">
            {bekleyenler.map((x) => (
              <li key={x.id} className="flex flex-wrap items-center gap-2 rounded-lg border border-white/10 px-3 py-2 text-sm" data-bakiye-talep={x.id}
                data-talep-durum={x.durum}>
                <span className="font-semibold tabular-nums">{paraBicimle(x.tutar, x.para_birimi, dil)}</span>
                <span className="text-xs text-muted-foreground">{tarihBicimle(x.odeme_tarihi || x.created_at, dil)}</span>
                <span className={`rounded-full px-2 py-0.5 text-[11px] ${x.durum === 'beklemede' ? 'bg-amber-500/15 text-amber-200' : 'bg-red-500/15 text-red-200'}`}>
                  {t(`cuzdan.durum.${x.durum}`)}
                </span>
                {x.ret_nedeni && <span className="min-w-0 break-words text-xs text-muted-foreground">{t('cuzdan.yukle.retNedeni', { neden: x.ret_nedeni })}</span>}
                {x.durum === 'beklemede' && (
                  <Button size="sm" variant="ghost" className="ms-auto h-7 gap-1 px-2 text-xs"
                    onClick={() => void talebiIptalEt(x.id).then(() => {
                      toast.success(t('cuzdan.yukle.iptalEdildi'));
                      onDegisti();
                    }).catch(hata)}>
                    <XCircle className="h-3.5 w-3.5" aria-hidden="true" />{t('cuzdan.yukle.iptal')}
                  </Button>
                )}
              </li>
            ))}
          </ul>
        </div>
      )}

      {panel === 'yukle' && <YuklemePaneli ozet={ozet} hata={hata} onGonderildi={() => {
        setPanel(null);
        onDegisti();
      }} />}
      {panel === 'hareketler' && <HareketPaneli ozet={ozet} hata={hata} />}
      {panel === 'ayarlar' && <AyarPaneli ozet={ozet} hata={hata} onKaydedildi={onDegisti} />}

      <p className="mt-4 flex items-start gap-2 text-xs text-muted-foreground" data-testid="bakiyem-hukuki">
        <Info className="mt-0.5 h-3.5 w-3.5 flex-none" aria-hidden="true" />
        <span className="min-w-0">
          <span className="font-semibold">{t('cuzdan.hukuki.baslik')}: </span>{t('cuzdan.hukuki.metin')} <em>{t('cuzdan.hukuki.not')}</em>
        </span>
      </p>
    </section>
  );
}

function Kopyala({ metin }: { metin: string }) {
  const { t } = useTranslation();
  const [oldu, setOldu] = useState(false);
  return (
    <Button size="sm" variant="ghost" className="h-7 gap-1 px-2 text-xs" type="button"
      onClick={() => void navigator.clipboard?.writeText(metin).then(() => {
        setOldu(true);
        window.setTimeout(() => setOldu(false), 1500);
      }).catch(() => undefined)}>
      <Copy className="h-3.5 w-3.5" aria-hidden="true" />{oldu ? t('cuzdan.kopyalandi') : t('cuzdan.kopyala')}
    </Button>
  );
}

function YuklemePaneli({ ozet, hata, onGonderildi }: { ozet: MusteriCuzdani; hata: (h: unknown) => void; onGonderildi: () => void }) {
  const { t } = useTranslation();
  const b = ozet.banka;
  const ref = ozet.ayarlar.referans || '';
  const [v, setV] = useState({ tutar: '', para_birimi: ozet.bakiyeler[0]?.para_birimi || 'TRY', yontem: 'havale', odeme_tarihi: bugunIso(), notu: '' });
  const [dekont, setDekont] = useState<File | null>(null);
  const [mesgul, setMesgul] = useState(false);
  return (
    <div className="mt-4 grid gap-4 lg:grid-cols-2" data-testid="bakiye-yukle">
      <div className="rounded-xl border border-white/10 p-4 text-sm">
        <p className="mb-2 flex items-center gap-2 font-semibold"><Landmark className="h-4 w-4 text-purple-300" aria-hidden="true" />{t('cuzdan.yukle.banka')}</p>
        <p className="mb-3 text-xs text-muted-foreground">{t('cuzdan.yukle.adimlar')}</p>
        {b.var ? (
          <dl className="grid gap-2" data-testid="bakiye-banka">
            {b.hesap_sahibi && <div><dt className="text-xs text-muted-foreground">{t('cuzdan.yukle.hesapSahibi')}</dt><dd className="break-words">{b.hesap_sahibi}</dd></div>}
            {b.banka_adi && <div><dt className="text-xs text-muted-foreground">{t('cuzdan.yukle.bankaAdi')}</dt><dd className="break-words">{b.banka_adi}</dd></div>}
            <div>
              <dt className="text-xs text-muted-foreground">{t('cuzdan.yukle.iban')}</dt>
              <dd className="flex flex-wrap items-center gap-2"><span className="break-all font-mono" dir="ltr">{b.iban}</span><Kopyala metin={b.iban} /></dd>
            </div>
            {b.aciklama && <p className="text-xs text-muted-foreground">{b.aciklama}</p>}
          </dl>
        ) : (
          <p className="rounded-lg border border-amber-500/30 bg-amber-500/[0.07] p-3 text-xs text-amber-100" data-testid="bakiye-banka-yok">
            {t('cuzdan.yukle.bankaYok')}
          </p>
        )}
        {ref && (
          <div className="mt-3 rounded-lg border border-purple-400/30 bg-purple-500/[0.06] p-3">
            <p className="text-xs text-muted-foreground">{t('cuzdan.yukle.referans')}</p>
            <p className="flex flex-wrap items-center gap-2"><span className="font-mono text-base font-bold" dir="ltr" data-testid="bakiye-referans">{ref}</span><Kopyala metin={ref} /></p>
            <p className="mt-1 text-[11px] text-muted-foreground">{t('cuzdan.yukle.referansIpucu')}</p>
          </div>
        )}
      </div>
      <form className="grid gap-2 rounded-xl border border-white/10 p-4 sm:grid-cols-2" onSubmit={(e) => {
        e.preventDefault();
        setMesgul(true);
        yuklemeTalebiGonder({ ...v, dekont })
          .then(() => {
            toast.success(t('cuzdan.yukle.gonderildi'));
            onGonderildi();
          })
          .catch(hata)
          .finally(() => setMesgul(false));
      }}>
        <p className="text-sm font-semibold sm:col-span-2">{t('cuzdan.yukle.baslik')}</p>
        <label className="grid gap-1 text-xs">{t('cuzdan.yukle.tutar')}
          <Input type="number" min={0.01} step="0.01" required value={v.tutar} onChange={(e) => setV({ ...v, tutar: e.target.value })} data-yukle-alan="tutar" />
        </label>
        <label className="grid gap-1 text-xs">{t('cuzdan.yukle.paraBirimi')}
          <select className={SECIM} value={v.para_birimi} onChange={(e) => setV({ ...v, para_birimi: e.target.value })} data-yukle-alan="para_birimi">
            {CUZDAN_PARA_BIRIMLERI.map((p) => <option key={p} value={p} className="bg-[#150a2b]">{p}</option>)}
          </select>
        </label>
        <label className="grid gap-1 text-xs">{t('cuzdan.yukle.yontem')}
          <select className={SECIM} value={v.yontem} onChange={(e) => setV({ ...v, yontem: e.target.value })}>
            {YUKLEME_YONTEMLERI.map((y) => <option key={y} value={y} className="bg-[#150a2b]">{t(`cuzdan.yontem.${y}`)}</option>)}
          </select>
        </label>
        <label className="grid gap-1 text-xs">{t('cuzdan.yukle.tarih')}
          <Input type="date" max={bugunIso()} value={v.odeme_tarihi} onChange={(e) => setV({ ...v, odeme_tarihi: e.target.value })} />
        </label>
        <label className="grid gap-1 text-xs sm:col-span-2">{t('cuzdan.yukle.dekont')}
          <Input type="file" accept=".pdf,.png,.jpg,.jpeg,.webp" className="text-xs" onChange={(e) => setDekont(e.target.files?.[0] || null)} data-yukle-alan="dekont" />
          <span className="text-[11px] text-muted-foreground">{t('cuzdan.yukle.dekontIpucu')}</span>
        </label>
        <label className="grid gap-1 text-xs sm:col-span-2">{t('cuzdan.yukle.not')}
          <Input maxLength={1000} value={v.notu} onChange={(e) => setV({ ...v, notu: e.target.value })} />
        </label>
        <div className="sm:col-span-2">
          <Button type="submit" size="sm" disabled={mesgul} className="gap-1" data-yukle-gonder>
            {mesgul && <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />}{t('cuzdan.yukle.gonder')}
          </Button>
        </div>
      </form>
    </div>
  );
}

function HareketPaneli({ ozet, hata }: { ozet: MusteriCuzdani; hata: (h: unknown) => void }) {
  const { t, i18n } = useTranslation();
  const dil = i18n.language;
  const pbler = ozet.bakiyeler.map((b) => b.para_birimi);
  const [pb, setPb] = useState('');
  const [satirlar, setSatirlar] = useState<CuzdanHareketi[] | null>(null);
  const [sayfa, setSayfa] = useState(1);
  const [toplam, setToplam] = useState(0);
  useEffect(() => {
    let iptal = false;
    hareketlerim(pb || undefined, 1)
      .then((s) => {
        if (iptal) return;
        setSatirlar(s.items);
        setToplam(s.toplam);
        setSayfa(1);
      })
      .catch(hata);
    return () => {
      iptal = true;
    };
  }, [pb, hata]);
  const ekstrePb = pb || pbler[0] || 'TRY';
  return (
    <div className="mt-4 rounded-xl border border-white/10 p-4" data-testid="bakiyem-hareketler">
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <select value={pb} onChange={(e) => setPb(e.target.value)} className="h-9 rounded-md border border-white/10 bg-white/5 px-2 text-sm"
          aria-label={t('cuzdan.yukle.paraBirimi')}>
          <option value="" className="bg-[#150a2b]">{t('cuzdan.hareketler.tumu')}</option>
          {pbler.map((p) => <option key={p} value={p} className="bg-[#150a2b]">{p}</option>)}
        </select>
        <Button size="sm" variant="ghost" className="gap-1" onClick={() => void pdfIndir(ekstrem(ekstrePb, 'pdf', pdfDili(dil)), `bakiye-${ekstrePb}.pdf`).catch(hata)}>
          <FileDown className="h-4 w-4" aria-hidden="true" />{t('cuzdan.ekstre.pdf')}
        </Button>
        <Button size="sm" variant="ghost" className="gap-1" onClick={() => void pdfIndir(ekstrem(ekstrePb, 'csv', pdfDili(dil)), `bakiye-${ekstrePb}.csv`).catch(hata)}>
          <FileDown className="h-4 w-4" aria-hidden="true" />{t('cuzdan.ekstre.csv')}
        </Button>
      </div>
      {!satirlar ? (
        <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" aria-hidden="true" />
      ) : satirlar.length === 0 ? (
        <p className="text-sm text-muted-foreground">{t('cuzdan.hareketler.bos')}</p>
      ) : (
        <>
          <ul className="divide-y divide-white/5 text-sm">
            {satirlar.map((h) => <li key={h.id} className="py-2" data-hareket-tur={h.tur}><HareketSatiri h={h} /></li>)}
          </ul>
          {satirlar.length < toplam && (
            <Button size="sm" variant="ghost" className="mt-2" onClick={() => void hareketlerim(pb || undefined, sayfa + 1).then((s) => {
              setSatirlar([...satirlar, ...s.items]);
              setSayfa(sayfa + 1);
            }).catch(hata)}>
              {t('cuzdan.hareketler.dahaFazla')}
            </Button>
          )}
        </>
      )}
    </div>
  );
}

function AyarPaneli({ ozet, hata, onKaydedildi }: { ozet: MusteriCuzdani; hata: (h: unknown) => void; onKaydedildi: () => void }) {
  const { t, i18n } = useTranslation();
  const dil = i18n.language;
  const a = ozet.ayarlar;
  const pbler = useMemo(() => (ozet.bakiyeler.length ? ozet.bakiyeler.map((b) => b.para_birimi) : ['TRY']), [ozet.bakiyeler]);
  const [oto, setOto] = useState(a.otomatik_odeme);
  const [onay, setOnay] = useState(false);
  const [kismi, setKismi] = useState(a.otomatik_kismi);
  const [zaman, setZaman] = useState(a.otomatik_zaman);
  const [esikler, setEsikler] = useState<Record<string, string>>(() =>
    Object.fromEntries(pbler.map((pb) => {
      const b = ozet.bakiyeler.find((x) => x.para_birimi === pb);
      return [pb, b?.dusuk_esik != null ? String(b.dusuk_esik) : ''];
    })));
  const [mesgul, setMesgul] = useState(false);
  const acilacak = oto && !a.otomatik_odeme;
  return (
    <form className="mt-4 grid gap-3 rounded-xl border border-white/10 p-4 text-sm" data-testid="bakiyem-ayarlar" onSubmit={(e) => {
      e.preventDefault();
      setMesgul(true);
      ayarlarimiYaz({
        otomatik_odeme: oto, onay: acilacak ? onay : undefined, otomatik_kismi: kismi, otomatik_zaman: zaman,
        dusuk_esikler: Object.fromEntries(Object.entries(esikler).map(([pb, v]) => [pb, v.trim() ? v.trim() : null])),
      })
        .then(() => {
          toast.success(t('cuzdan.ayarlar.kaydedildi'));
          onKaydedildi();
        })
        .catch(hata)
        .finally(() => setMesgul(false));
    }}>
      <label className="flex items-start gap-2">
        <input type="checkbox" className="mt-0.5 h-4 w-4 accent-purple-500" checked={oto} onChange={(e) => setOto(e.target.checked)} data-ayar="otomatik" />
        <span className="font-medium">{t('cuzdan.ayarlar.otomatik')}</span>
      </label>
      {a.otomatik_odeme && a.otomatik_baslangic && (
        <p className="text-xs text-emerald-300">{t('cuzdan.ayarlar.acik', { tarih: tarihBicimle(a.otomatik_baslangic, dil) })}</p>
      )}
      {acilacak && (
        <div className="rounded-lg border border-purple-400/30 bg-purple-500/[0.06] p-3 text-xs">
          <p className="mb-2 text-muted-foreground">{t('cuzdan.ayarlar.onayMetni')}</p>
          <label className="flex items-center gap-2">
            <input type="checkbox" className="h-4 w-4 accent-purple-500" checked={onay} onChange={(e) => setOnay(e.target.checked)} data-ayar="onay" />
            {t('cuzdan.ayarlar.onayKutusu')}
          </label>
        </div>
      )}
      {oto && (
        <>
          <label className="flex items-start gap-2 text-xs">
            <input type="checkbox" className="mt-0.5 h-4 w-4 accent-purple-500" checked={kismi} onChange={(e) => setKismi(e.target.checked)} />
            {t('cuzdan.ayarlar.kismi')}
          </label>
          <label className="grid max-w-xs gap-1 text-xs">{t('cuzdan.ayarlar.zaman')}
            <select className={SECIM} value={zaman} onChange={(e) => setZaman(e.target.value as 'kesilince' | 'vadesinde')}>
              <option value="kesilince" className="bg-[#150a2b]">{t('cuzdan.ayarlar.kesilince')}</option>
              <option value="vadesinde" className="bg-[#150a2b]">{t('cuzdan.ayarlar.vadesinde')}</option>
            </select>
          </label>
        </>
      )}
      <div className="grid gap-2 sm:grid-cols-2">
        {pbler.map((pb) => (
          <label key={pb} className="grid gap-1 text-xs">{t('cuzdan.ayarlar.dusukEsik', { pb })}
            <Input type="number" min={0} step="0.01" value={esikler[pb] ?? ''} onChange={(e) => setEsikler({ ...esikler, [pb]: e.target.value })}
              data-esik={pb} />
          </label>
        ))}
      </div>
      <p className="text-[11px] text-muted-foreground">{t('cuzdan.ayarlar.esikIpucu')}</p>
      <div>
        <Button type="submit" size="sm" disabled={mesgul || (acilacak && !onay)} data-ayar-kaydet>{t('cuzdan.kaydet')}</Button>
      </div>
    </form>
  );
}
