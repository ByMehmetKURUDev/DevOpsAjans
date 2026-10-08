import { useCallback, useEffect, useMemo, useState, type FormEvent } from 'react';
import {
  ArrowLeft,
  Banknote,
  BookOpen,
  Check,
  FileDown,
  Info,
  Landmark,
  Loader2,
  Paperclip,
  Plus,
  RefreshCw,
  RotateCcw,
  Search,
  SlidersHorizontal,
  Undo2,
  Wallet,
  X,
} from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';

import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { BelgeHatasi, bugunIso, paraBicimle, pdfDili, pdfIndir, tarihBicimle } from '@/lib/belge';
import {
  CUZDAN_PARA_BIRIMLERI,
  YUKLEME_YONTEMLERI,
  bakiyeDuzelt,
  bakiyeIadeEt,
  bankaAyarlari,
  bankaAyarlariniYaz,
  elleYukle,
  hareketDekontu,
  hesapAyrintisi,
  talebiOnayla,
  talebiReddet,
  talepDekontu,
  tersKayit,
  yoneticiEkstresi,
  yoneticiListesi,
  type HesapAyrintisi,
  type YoneticiListesi,
  type YuklemeTalebi,
} from '@/lib/cuzdan';
import { adresiIndir } from '@/lib/dosyalar';
import HareketSatiri from '@/components/cuzdan/HareketSatiri';

/**
 * Faz 5C — Yönetici › Finans › Ödemeler › "Müşteri bakiyeleri" (alt gezinme; yeni üst sekme yok).
 * Onay bekleyen yükleme bildirimleri (onay / neden yazarak ret), hesap listesi (bakiye, son hareket), hesap defteri
 * (ekstre PDF/CSV, ters kayıt), elle yükleme, iade (müşteriye ödeme), düzeltme (gerekçe zorunlu) ve müşteriye
 * gösterilen ödeme bilgisi. Defter satırları silinmez. Metinler `cuzdan` ek paketinde.
 */
type Panel = 'yukle' | 'iade' | 'duzeltme' | 'banka' | null;

const KART = 'cam-kart rounded-2xl border border-white/10 bg-white/[0.03] p-4 sm:p-6';
const SECIM = 'h-10 w-full rounded-md border border-white/10 bg-white/5 px-2 text-sm';

function talepParam(): number | null {
  try {
    const t = Number(new URLSearchParams(window.location.search).get('talep'));
    return Number.isFinite(t) && t > 0 ? t : null;
  } catch {
    return null;
  }
}

export default function MusteriBakiyeleri() {
  const { t, i18n } = useTranslation();
  const dil = i18n.language;
  const [liste, setListe] = useState<YoneticiListesi | null>(null);
  const [q, setQ] = useState('');
  const [secili, setSecili] = useState<string | null>(null);
  const [ayrinti, setAyrinti] = useState<HesapAyrintisi | null>(null);
  const [pbSuzgec, setPbSuzgec] = useState('');
  const [panel, setPanel] = useState<Panel>(null);
  const [mesgul, setMesgul] = useState(false);
  const [vurgu] = useState<number | null>(talepParam);

  const hata = useCallback(
    (h: unknown) => {
      const kod = h instanceof BelgeHatasi ? h.kod : 'genel';
      toast.error(t(`cuzdan.hata.${kod}`, { defaultValue: t('cuzdan.hata.genel') }));
    },
    [t],
  );

  const yukle = useCallback(async () => {
    try {
      setListe(await yoneticiListesi(q.trim()));
    } catch (h) {
      hata(h);
    }
  }, [q, hata]);

  const ayrintiYukle = useCallback(async (eposta: string, pb = '') => {
    try {
      setAyrinti(await hesapAyrintisi(eposta, pb || undefined));
    } catch (h) {
      hata(h);
    }
  }, [hata]);

  useEffect(() => {
    void yukle();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (secili) void ayrintiYukle(secili, pbSuzgec);
  }, [secili, pbSuzgec, ayrintiYukle]);

  const tazele = async () => {
    await yukle();
    if (secili) await ayrintiYukle(secili, pbSuzgec);
  };

  const calistir = async (fn: () => Promise<unknown>, mesaj: string) => {
    setMesgul(true);
    try {
      await fn();
      toast.success(mesaj);
      await tazele();
      return true;
    } catch (h) {
      hata(h);
      return false;
    } finally {
      setMesgul(false);
    }
  };

  const para = (d: number, pb: string) => paraBicimle(d, pb, dil);

  return (
    <div className="min-w-0 space-y-6" data-testid="musteri-bakiyeleri">
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <h2 className="flex items-center gap-2 text-xl font-semibold" id="bakiyeler-baslik">
            <Wallet className="h-5 w-5 text-purple-300" aria-hidden="true" />
            {t('cuzdan.yonetim.baslik')}
          </h2>
          <p className="mt-1 max-w-3xl text-sm text-muted-foreground">{t('cuzdan.yonetim.aciklama')}</p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button size="sm" className="gap-1" onClick={() => setPanel(panel === 'yukle' ? null : 'yukle')} data-panel-ac="yukle">
            <Plus className="h-4 w-4" aria-hidden="true" />{t('cuzdan.yonetim.elleYukle')}
          </Button>
          <Button size="sm" variant="outline" className="gap-1 !bg-transparent" onClick={() => setPanel(panel === 'banka' ? null : 'banka')}
            data-panel-ac="banka">
            <Landmark className="h-4 w-4" aria-hidden="true" />{t('cuzdan.yonetim.bankaBaslik')}
          </Button>
          <Button size="sm" variant="ghost" className="gap-1" onClick={() => void tazele()} aria-label={t('cuzdan.yenile')}>
            <RefreshCw className="h-4 w-4" aria-hidden="true" />
          </Button>
        </div>
      </header>

      <div className="flex items-start gap-2 rounded-xl border border-sky-500/25 bg-sky-500/[0.06] p-3 text-xs text-muted-foreground">
        <Info className="mt-0.5 h-4 w-4 flex-none text-sky-300" aria-hidden="true" />
        <p className="min-w-0">
          {t('cuzdan.yonetim.muhasebeNotu')} <span className="block mt-1">{t('cuzdan.hukuki.metin')} {t('cuzdan.hukuki.not')}</span>
        </p>
      </div>

      {panel === 'yukle' && (
        <YuklemeFormu
          varsayilanEposta={secili || ''}
          mesgul={mesgul}
          onIptal={() => setPanel(null)}
          onGonder={async (veri) => {
            if (await calistir(() => elleYukle(veri), t('cuzdan.yonetim.yuklendi'))) setPanel(null);
          }}
        />
      )}
      {panel === 'banka' && <BankaFormu onKapat={() => setPanel(null)} hata={hata} />}

      {liste && liste.toplamlar.length > 0 && (
        <div className="flex flex-wrap gap-3" data-testid="bakiye-toplamlar">
          {liste.toplamlar.map((x) => (
            <div key={x.para_birimi} className="cam-kart rounded-xl border border-white/10 bg-white/[0.03] px-4 py-2 text-sm">
              <span className="text-muted-foreground">{t('cuzdan.yonetim.toplam', { pb: x.para_birimi })}: </span>
              <span className="font-bold tabular-nums">{para(x.bakiye, x.para_birimi)}</span>
            </div>
          ))}
        </div>
      )}

      <section className={KART} data-testid="bekleyen-talepler">
        <h3 className="mb-3 text-base font-semibold">{t('cuzdan.yonetim.bekleyen')}</h3>
        {!liste ? (
          <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" aria-hidden="true" />
        ) : liste.bekleyen_talepler.length === 0 ? (
          <p className="text-sm text-muted-foreground">{t('cuzdan.yonetim.bekleyenYok')}</p>
        ) : (
          <ul className="space-y-3">
            {liste.bekleyen_talepler.map((tl) => (
              <TalepSatiri key={tl.id} talep={tl} vurgu={vurgu === tl.id} mesgul={mesgul}
                onOnayla={(tutar) => calistir(() => talebiOnayla(tl.id, tutar ? { tutar } : {}), t('cuzdan.yonetim.onaylandi'))}
                onReddet={(neden) => calistir(() => talebiReddet(tl.id, neden), t('cuzdan.yonetim.reddedildi'))}
                hata={hata} />
            ))}
          </ul>
        )}
      </section>

      {secili && ayrinti ? (
        <HesapDefteri
          ayrinti={ayrinti}
          pbSuzgec={pbSuzgec}
          setPbSuzgec={setPbSuzgec}
          panel={panel}
          setPanel={setPanel}
          mesgul={mesgul}
          calistir={calistir}
          hata={hata}
          onGeri={() => {
            setSecili(null);
            setAyrinti(null);
            setPbSuzgec('');
            if (panel === 'iade' || panel === 'duzeltme') setPanel(null);
          }}
        />
      ) : (
        <section className={KART} data-testid="bakiye-hesaplari">
          <form
            className="mb-4 flex gap-2"
            onSubmit={(e) => {
              e.preventDefault();
              void yukle();
            }}
          >
            <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder={t('cuzdan.yonetim.ara')} aria-label={t('cuzdan.yonetim.ara')}
              className="max-w-xs" />
            <Button type="submit" size="sm" variant="ghost" aria-label={t('cuzdan.yonetim.ara')}>
              <Search className="h-4 w-4" aria-hidden="true" />
            </Button>
          </form>
          {!liste ? (
            <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" aria-hidden="true" />
          ) : liste.hesaplar.length === 0 ? (
            <p className="text-sm text-muted-foreground">{t('cuzdan.yonetim.hesapYok')}</p>
          ) : (
            <ul className="divide-y divide-white/5">
              {liste.hesaplar.map((h) => (
                <li key={h.id} className="flex flex-wrap items-center gap-3 py-3" data-bakiye-hesap={h.hesap_email}>
                  <div className="min-w-0 flex-1">
                    <p className="truncate font-medium">{h.ad || h.hesap_email}</p>
                    <p className="break-all text-xs text-muted-foreground">
                      {h.ad ? `${h.hesap_email} · ` : ''}
                      {t('cuzdan.yonetim.sonHareket')}: {tarihBicimle(h.son_hareket_at, dil, true)}
                    </p>
                  </div>
                  <span className={`text-lg font-bold tabular-nums ${h.dusuk_uyari ? 'text-amber-300' : ''}`}>
                    {para(h.bakiye, h.para_birimi)}
                  </span>
                  <Button size="sm" variant="outline" className="gap-1 !bg-transparent" data-defter={h.hesap_email}
                    onClick={() => {
                      setSecili(h.hesap_email);
                      setPbSuzgec('');
                    }}>
                    <BookOpen className="h-4 w-4" aria-hidden="true" />{t('cuzdan.yonetim.defter')}
                  </Button>
                </li>
              ))}
            </ul>
          )}
        </section>
      )}
    </div>
  );
}

function TalepSatiri({
  talep,
  vurgu,
  mesgul,
  onOnayla,
  onReddet,
  hata,
}: {
  talep: YuklemeTalebi;
  vurgu: boolean;
  mesgul: boolean;
  onOnayla: (tutar: string) => Promise<boolean>;
  onReddet: (neden: string) => Promise<boolean>;
  hata: (h: unknown) => void;
}) {
  const { t, i18n } = useTranslation();
  const dil = i18n.language;
  const [mod, setMod] = useState<'onay' | 'ret' | null>(vurgu ? 'ret' : null);
  const [tutar, setTutar] = useState(String(talep.tutar));
  const [neden, setNeden] = useState('');
  return (
    <li className={`rounded-xl border p-3 ${vurgu ? 'border-purple-400/60 bg-purple-500/[0.06]' : 'border-white/10'}`} data-talep={talep.id}>
      <div className="flex flex-wrap items-center gap-3">
        <div className="min-w-0 flex-1">
          <p className="font-medium">
            <span className="tabular-nums">{paraBicimle(talep.tutar, talep.para_birimi, dil)}</span>
            <span className="ms-2 text-xs text-muted-foreground">{t(`cuzdan.yontem.${talep.yontem}`, { defaultValue: talep.yontem })}</span>
          </p>
          <p className="break-all text-xs text-muted-foreground">
            {talep.ad ? `${talep.ad} · ` : ''}{talep.hesap_email} · {tarihBicimle(talep.odeme_tarihi || talep.created_at, dil)}
            {talep.referans ? ` · ${t('cuzdan.yonetim.referans', { kod: talep.referans })}` : ''}
          </p>
          {talep.notu && <p className="mt-1 whitespace-pre-line text-xs">{talep.notu}</p>}
        </div>
        <div className="flex flex-wrap gap-2">
          {talep.dekont_var && (
            <Button size="sm" variant="ghost" className="gap-1" onClick={() => void talepDekontu(talep.id).then((d) => adresiIndir(d.adres)).catch(hata)}>
              <Paperclip className="h-4 w-4" aria-hidden="true" />{t('cuzdan.yonetim.dekont')}
            </Button>
          )}
          <Button size="sm" className="gap-1" disabled={mesgul} onClick={() => setMod(mod === 'onay' ? null : 'onay')} data-talep-onayla>
            <Check className="h-4 w-4" aria-hidden="true" />{t('cuzdan.yonetim.onayla')}
          </Button>
          <Button size="sm" variant="ghost" className="gap-1" disabled={mesgul} onClick={() => setMod(mod === 'ret' ? null : 'ret')} data-talep-reddet>
            <X className="h-4 w-4" aria-hidden="true" />{t('cuzdan.yonetim.reddet')}
          </Button>
        </div>
      </div>
      {mod === 'onay' && (
        <form className="mt-3 flex flex-wrap items-end gap-2" onSubmit={(e) => {
          e.preventDefault();
          void onOnayla(tutar === String(talep.tutar) ? '' : tutar).then((ok) => ok && setMod(null));
        }}>
          <label className="grid gap-1 text-xs">{t('cuzdan.yonetim.onayTutari')} ({talep.para_birimi})
            <Input type="number" min={0.01} step="0.01" required value={tutar} onChange={(e) => setTutar(e.target.value)} className="w-40" data-onay-tutar />
          </label>
          <Button type="submit" size="sm" disabled={mesgul} data-onay-gonder>{t('cuzdan.yonetim.onayla')}</Button>
        </form>
      )}
      {mod === 'ret' && (
        <form className="mt-3 flex flex-wrap items-end gap-2" onSubmit={(e) => {
          e.preventDefault();
          void onReddet(neden).then((ok) => ok && setMod(null));
        }}>
          <label className="grid min-w-0 flex-1 gap-1 text-xs">{t('cuzdan.yonetim.retNedeni')}
            <Input required maxLength={500} value={neden} onChange={(e) => setNeden(e.target.value)} data-ret-neden />
          </label>
          <Button type="submit" size="sm" variant="outline" className="!bg-transparent" disabled={mesgul || !neden.trim()} data-ret-gonder>
            {t('cuzdan.yonetim.reddet')}
          </Button>
        </form>
      )}
    </li>
  );
}

function HesapDefteri({
  ayrinti,
  pbSuzgec,
  setPbSuzgec,
  panel,
  setPanel,
  mesgul,
  calistir,
  hata,
  onGeri,
}: {
  ayrinti: HesapAyrintisi;
  pbSuzgec: string;
  setPbSuzgec: (pb: string) => void;
  panel: Panel;
  setPanel: (p: Panel) => void;
  mesgul: boolean;
  calistir: (fn: () => Promise<unknown>, mesaj: string) => Promise<boolean>;
  hata: (h: unknown) => void;
  onGeri: () => void;
}) {
  const { t, i18n } = useTranslation();
  const dil = i18n.language;
  const eposta = ayrinti.hesap_email;
  const pbler = useMemo(() => ayrinti.bakiyeler.map((b) => b.para_birimi), [ayrinti.bakiyeler]);
  const ekstrePb = pbSuzgec || pbler[0] || 'TRY';
  const [iade, setIade] = useState({ tutar: '', para_birimi: ekstrePb, yontem: 'havale', tarih: bugunIso(), notu: '' });
  const [duz, setDuz] = useState({ tutar: '', para_birimi: ekstrePb, gerekce: '' });
  const [tersAcik, setTersAcik] = useState<number | null>(null);
  const [tersNeden, setTersNeden] = useState('');

  return (
    <section className={`${KART} space-y-4`} data-testid="bakiye-defteri" data-hesap={eposta}>
      <div className="flex flex-wrap items-center gap-2">
        <Button size="sm" variant="ghost" className="gap-1" onClick={onGeri}>
          <ArrowLeft className="h-4 w-4 rtl:rotate-180" aria-hidden="true" />{t('cuzdan.yonetim.geri')}
        </Button>
        <h3 className="min-w-0 flex-1 break-all text-base font-semibold">{ayrinti.ad || eposta}</h3>
      </div>
      <div className="flex flex-wrap gap-3">
        {ayrinti.bakiyeler.map((b) => (
          <div key={b.para_birimi} className="rounded-xl border border-white/10 px-4 py-2" data-defter-bakiye={b.para_birimi}>
            <p className="text-xs text-muted-foreground">{t('cuzdan.bakiye')} · {b.para_birimi}</p>
            <p className="text-xl font-bold tabular-nums">{paraBicimle(b.bakiye, b.para_birimi, dil)}</p>
          </div>
        ))}
        {ayrinti.ayarlar.otomatik_odeme && (
          <p className="self-center text-xs text-emerald-300">{t('cuzdan.ayarlar.acik', { tarih: tarihBicimle(ayrinti.ayarlar.otomatik_baslangic, dil) })}</p>
        )}
      </div>
      <div className="flex flex-wrap items-center gap-2">
        <Button size="sm" variant="outline" className="gap-1 !bg-transparent" onClick={() => setPanel(panel === 'iade' ? null : 'iade')} data-panel-ac="iade">
          <Undo2 className="h-4 w-4" aria-hidden="true" />{t('cuzdan.yonetim.iade')}
        </Button>
        <Button size="sm" variant="outline" className="gap-1 !bg-transparent" onClick={() => setPanel(panel === 'duzeltme' ? null : 'duzeltme')}
          data-panel-ac="duzeltme">
          <SlidersHorizontal className="h-4 w-4" aria-hidden="true" />{t('cuzdan.yonetim.duzeltme')}
        </Button>
        <select value={pbSuzgec} onChange={(e) => setPbSuzgec(e.target.value)} className="h-9 rounded-md border border-white/10 bg-white/5 px-2 text-sm"
          aria-label={t('cuzdan.yukle.paraBirimi')}>
          <option value="" className="bg-[#150a2b]">{t('cuzdan.hareketler.tumu')}</option>
          {pbler.map((pb) => <option key={pb} value={pb} className="bg-[#150a2b]">{pb}</option>)}
        </select>
        <Button size="sm" variant="ghost" className="gap-1"
          onClick={() => void pdfIndir(yoneticiEkstresi(eposta, ekstrePb, 'pdf', pdfDili(dil)), `bakiye-${ekstrePb}.pdf`).catch(hata)}>
          <FileDown className="h-4 w-4" aria-hidden="true" />{t('cuzdan.ekstre.pdf')}
        </Button>
        <Button size="sm" variant="ghost" className="gap-1"
          onClick={() => void pdfIndir(yoneticiEkstresi(eposta, ekstrePb, 'csv', pdfDili(dil)), `bakiye-${ekstrePb}.csv`).catch(hata)}>
          <FileDown className="h-4 w-4" aria-hidden="true" />{t('cuzdan.ekstre.csv')}
        </Button>
      </div>

      {panel === 'iade' && (
        <form className="grid gap-2 rounded-xl border border-white/10 p-3 sm:grid-cols-2 lg:grid-cols-3" data-testid="iade-formu" onSubmit={(e: FormEvent) => {
          e.preventDefault();
          void calistir(() => bakiyeIadeEt({ hesap_email: eposta, ...iade }), t('cuzdan.yonetim.iadeYapildi')).then((ok) => ok && setPanel(null));
        }}>
          <p className="text-sm font-semibold sm:col-span-2 lg:col-span-3">{t('cuzdan.yonetim.iade')}</p>
          <TutarPb tutar={iade.tutar} pb={iade.para_birimi} onTutar={(v) => setIade({ ...iade, tutar: v })} onPb={(v) => setIade({ ...iade, para_birimi: v })} />
          <label className="grid gap-1 text-xs">{t('cuzdan.yukle.yontem')}
            <select className={SECIM} value={iade.yontem} onChange={(e) => setIade({ ...iade, yontem: e.target.value })}>
              {YUKLEME_YONTEMLERI.map((y) => <option key={y} value={y} className="bg-[#150a2b]">{t(`cuzdan.yontem.${y}`)}</option>)}
            </select>
          </label>
          <label className="grid gap-1 text-xs">{t('cuzdan.yukle.tarih')}
            <Input type="date" max={bugunIso()} value={iade.tarih} onChange={(e) => setIade({ ...iade, tarih: e.target.value })} />
          </label>
          <label className="grid gap-1 text-xs sm:col-span-2">{t('cuzdan.yukle.not')}
            <Input maxLength={1000} value={iade.notu} onChange={(e) => setIade({ ...iade, notu: e.target.value })} />
          </label>
          <div className="sm:col-span-2 lg:col-span-3"><Button type="submit" size="sm" disabled={mesgul}>{t('cuzdan.kaydet')}</Button></div>
        </form>
      )}
      {panel === 'duzeltme' && (
        <form className="grid gap-2 rounded-xl border border-white/10 p-3 sm:grid-cols-2 lg:grid-cols-3" data-testid="duzeltme-formu" onSubmit={(e: FormEvent) => {
          e.preventDefault();
          void calistir(() => bakiyeDuzelt({ hesap_email: eposta, ...duz }), t('cuzdan.yonetim.duzeltildi')).then((ok) => ok && setPanel(null));
        }}>
          <p className="text-sm font-semibold sm:col-span-2 lg:col-span-3">{t('cuzdan.yonetim.duzeltme')}</p>
          <p className="text-xs text-muted-foreground sm:col-span-2 lg:col-span-3">{t('cuzdan.yonetim.duzeltmeIpucu')}</p>
          <TutarPb tutar={duz.tutar} pb={duz.para_birimi} isaretli onTutar={(v) => setDuz({ ...duz, tutar: v })} onPb={(v) => setDuz({ ...duz, para_birimi: v })} />
          <label className="grid gap-1 text-xs sm:col-span-2 lg:col-span-3">{t('cuzdan.yonetim.gerekce')}
            <Input required maxLength={500} value={duz.gerekce} onChange={(e) => setDuz({ ...duz, gerekce: e.target.value })} />
          </label>
          <div className="sm:col-span-2 lg:col-span-3"><Button type="submit" size="sm" disabled={mesgul || !duz.gerekce.trim()}>{t('cuzdan.kaydet')}</Button></div>
        </form>
      )}

      <div>
        <h4 className="mb-2 text-sm font-semibold">{t('cuzdan.hareketler.baslik')}</h4>
        {ayrinti.hareketler.items.length === 0 ? (
          <p className="text-sm text-muted-foreground">{t('cuzdan.hareketler.bos')}</p>
        ) : (
          <ul className="divide-y divide-white/5 text-sm" data-testid="defter-satirlari">
            {ayrinti.hareketler.items.map((h) => (
              <li key={h.id} className="py-2" data-hareket={h.id} data-hareket-tur={h.tur}>
                <HareketSatiri h={h} yonetici />
                <div className="mt-1 flex flex-wrap gap-2">
                  {h.dekont_var && (
                    <Button size="sm" variant="ghost" className="h-7 gap-1 px-2 text-xs"
                      onClick={() => void hareketDekontu(h.id).then((d) => adresiIndir(d.adres)).catch(hata)}>
                      <Paperclip className="h-3.5 w-3.5" aria-hidden="true" />{t('cuzdan.yonetim.dekont')}
                    </Button>
                  )}
                  {h.ters_edilebilir && (
                    <Button size="sm" variant="ghost" className="h-7 gap-1 px-2 text-xs" onClick={() => setTersAcik(tersAcik === h.id ? null : h.id)}>
                      <RotateCcw className="h-3.5 w-3.5" aria-hidden="true" />{t('cuzdan.yonetim.ters')}
                    </Button>
                  )}
                </div>
                {tersAcik === h.id && (
                  <form className="mt-2 flex flex-wrap items-end gap-2" onSubmit={(e) => {
                    e.preventDefault();
                    void calistir(() => tersKayit(h.id, tersNeden), t('cuzdan.yonetim.tersYapildi')).then((ok) => {
                      if (ok) {
                        setTersAcik(null);
                        setTersNeden('');
                      }
                    });
                  }}>
                    <label className="grid min-w-0 flex-1 gap-1 text-xs">{t('cuzdan.yonetim.tersGerekce')}
                      <Input required maxLength={500} value={tersNeden} onChange={(e) => setTersNeden(e.target.value)} />
                    </label>
                    <Button type="submit" size="sm" variant="outline" className="!bg-transparent" disabled={mesgul || !tersNeden.trim()}>
                      {t('cuzdan.yonetim.ters')}
                    </Button>
                  </form>
                )}
              </li>
            ))}
          </ul>
        )}
      </div>
    </section>
  );
}

function TutarPb({ tutar, pb, isaretli = false, onTutar, onPb }: {
  tutar: string; pb: string; isaretli?: boolean; onTutar: (v: string) => void; onPb: (v: string) => void;
}) {
  const { t } = useTranslation();
  return (
    <>
      <label className="grid gap-1 text-xs">{t('cuzdan.yukle.tutar')}
        <Input type="number" step="0.01" min={isaretli ? undefined : 0.01} required value={tutar} onChange={(e) => onTutar(e.target.value)} data-alan="tutar" />
      </label>
      <label className="grid gap-1 text-xs">{t('cuzdan.yukle.paraBirimi')}
        <select className={SECIM} value={pb} onChange={(e) => onPb(e.target.value)}>
          {CUZDAN_PARA_BIRIMLERI.map((p) => <option key={p} value={p} className="bg-[#150a2b]">{p}</option>)}
        </select>
      </label>
    </>
  );
}

function YuklemeFormu({ varsayilanEposta, mesgul, onIptal, onGonder }: {
  varsayilanEposta: string;
  mesgul: boolean;
  onIptal: () => void;
  onGonder: (veri: Parameters<typeof elleYukle>[0]) => Promise<void>;
}) {
  const { t } = useTranslation();
  const [v, setV] = useState({ hesap_email: varsayilanEposta, tutar: '', para_birimi: 'TRY', yontem: 'havale', tarih: bugunIso(), notu: '' });
  const [dekont, setDekont] = useState<File | null>(null);
  return (
    <form className={`${KART} grid gap-2 sm:grid-cols-2 lg:grid-cols-3`} data-testid="elle-yukleme-formu" onSubmit={(e) => {
      e.preventDefault();
      void onGonder({ ...v, dekont });
    }}>
      <p className="flex items-center gap-2 text-sm font-semibold sm:col-span-2 lg:col-span-3">
        <Banknote className="h-4 w-4 text-purple-300" aria-hidden="true" />{t('cuzdan.yonetim.elleYukle')}
      </p>
      <label className="grid gap-1 text-xs sm:col-span-2 lg:col-span-1">{t('cuzdan.yonetim.hesapEposta')}
        <Input type="email" required value={v.hesap_email} onChange={(e) => setV({ ...v, hesap_email: e.target.value })} data-alan="hesap_email" />
      </label>
      <TutarPb tutar={v.tutar} pb={v.para_birimi} onTutar={(x) => setV({ ...v, tutar: x })} onPb={(x) => setV({ ...v, para_birimi: x })} />
      <label className="grid gap-1 text-xs">{t('cuzdan.yukle.yontem')}
        <select className={SECIM} value={v.yontem} onChange={(e) => setV({ ...v, yontem: e.target.value })}>
          {YUKLEME_YONTEMLERI.map((y) => <option key={y} value={y} className="bg-[#150a2b]">{t(`cuzdan.yontem.${y}`)}</option>)}
        </select>
      </label>
      <label className="grid gap-1 text-xs">{t('cuzdan.yukle.tarih')}
        <Input type="date" max={bugunIso()} value={v.tarih} onChange={(e) => setV({ ...v, tarih: e.target.value })} />
      </label>
      <label className="grid gap-1 text-xs">{t('cuzdan.yukle.dekont')}
        <Input type="file" accept=".pdf,.png,.jpg,.jpeg,.webp" className="text-xs" onChange={(e) => setDekont(e.target.files?.[0] || null)} />
      </label>
      <label className="grid gap-1 text-xs sm:col-span-2 lg:col-span-3">{t('cuzdan.yukle.not')}
        <Input maxLength={1000} value={v.notu} onChange={(e) => setV({ ...v, notu: e.target.value })} />
      </label>
      <div className="flex gap-2 sm:col-span-2 lg:col-span-3">
        <Button type="submit" size="sm" disabled={mesgul} data-yukle-gonder>
          {mesgul && <Loader2 className="me-1 h-4 w-4 animate-spin" aria-hidden="true" />}{t('cuzdan.kaydet')}
        </Button>
        <Button type="button" size="sm" variant="ghost" onClick={onIptal}>{t('cuzdan.vazgec')}</Button>
      </div>
    </form>
  );
}

function BankaFormu({ onKapat, hata }: { onKapat: () => void; hata: (h: unknown) => void }) {
  const { t } = useTranslation();
  const [v, setV] = useState<{ banka_adi: string; hesap_sahibi: string; iban: string; aciklama: string } | null>(null);
  const [mesgul, setMesgul] = useState(false);
  useEffect(() => {
    bankaAyarlari().then((x) => setV(x.kayitli)).catch(hata);
  }, [hata]);
  if (!v) return <div className={KART}><Loader2 className="h-5 w-5 animate-spin text-muted-foreground" aria-hidden="true" /></div>;
  return (
    <form className={`${KART} grid gap-2 sm:grid-cols-2`} data-testid="banka-formu" onSubmit={(e) => {
      e.preventDefault();
      setMesgul(true);
      bankaAyarlariniYaz(v)
        .then((x) => {
          setV(x.kayitli);
          toast.success(t('cuzdan.yonetim.bankaKaydedildi'));
          onKapat();
        })
        .catch(hata)
        .finally(() => setMesgul(false));
    }}>
      <p className="text-sm font-semibold sm:col-span-2">{t('cuzdan.yonetim.bankaBaslik')}</p>
      <p className="text-xs text-muted-foreground sm:col-span-2">{t('cuzdan.yonetim.bankaIpucu')}</p>
      <label className="grid gap-1 text-xs">{t('cuzdan.yukle.hesapSahibi')}
        <Input maxLength={160} value={v.hesap_sahibi} onChange={(e) => setV({ ...v, hesap_sahibi: e.target.value })} />
      </label>
      <label className="grid gap-1 text-xs">{t('cuzdan.yukle.bankaAdi')}
        <Input maxLength={160} value={v.banka_adi} onChange={(e) => setV({ ...v, banka_adi: e.target.value })} />
      </label>
      <label className="grid gap-1 text-xs sm:col-span-2">{t('cuzdan.yukle.iban')}
        <Input maxLength={40} value={v.iban} onChange={(e) => setV({ ...v, iban: e.target.value })} dir="ltr" />
      </label>
      <label className="grid gap-1 text-xs sm:col-span-2">{t('cuzdan.yonetim.aciklamaAlani')}
        <Input maxLength={500} value={v.aciklama} onChange={(e) => setV({ ...v, aciklama: e.target.value })} />
      </label>
      <div className="flex gap-2 sm:col-span-2">
        <Button type="submit" size="sm" disabled={mesgul}>{t('cuzdan.kaydet')}</Button>
        <Button type="button" size="sm" variant="ghost" onClick={onKapat}>{t('cuzdan.kapat')}</Button>
      </div>
    </form>
  );
}
