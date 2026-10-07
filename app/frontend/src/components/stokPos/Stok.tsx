import { lazy, Suspense, useCallback, useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { ArrowLeftRight, Camera, ClipboardCheck, History, PackagePlus, Plus, Trash2, Truck } from 'lucide-react';

import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';
import { Alan, Anahtar, Bos, DIS_DUGME, GIRDI, KART, METIN_ALANI, Pencere, Rozet, SECIM, Yukleniyor } from '@/components/stokPos/ortak';
import {
  gunOnce,
  bugun,
  hataMetni,
  miktarYaz,
  para,
  sayiCevir,
  tarihSaat,
  type Hareket,
  type Meta,
  type Sayim,
  type StokApi,
  type Tedarikci,
  type Urun,
} from '@/lib/stokPos';

const Okutucu = lazy(() => import('@/components/stokPos/Okutucu'));

type Alt = 'hareket' | 'transfer' | 'sayim' | 'gecmis' | 'tedarikciler';
const ALTLAR: { anahtar: Alt; ikon: typeof History }[] = [
  { anahtar: 'hareket', ikon: PackagePlus },
  { anahtar: 'transfer', ikon: ArrowLeftRight },
  { anahtar: 'sayim', ikon: ClipboardCheck },
  { anahtar: 'gecmis', ikon: History },
  { anahtar: 'tedarikciler', ikon: Truck },
];

/** Faz 6P — stok: giriş/çıkış/fire/düzeltme, şubeler arası transfer, envanter sayımı, hareket geçmişi, tedarikçiler. */
export default function Stok({ api, meta, saltOkunur, onMeta }: { api: StokApi; meta: Meta; saltOkunur: boolean; onMeta: () => void }) {
  const { t } = useTranslation();
  const gorunen = saltOkunur ? (['gecmis'] as Alt[]) : ALTLAR.map((a) => a.anahtar).filter((a) => a !== 'transfer' || meta.konumlar.filter((k) => k.aktif).length > 1);
  const [alt, setAlt] = useState<Alt>(gorunen[0]);
  return (
    <div className="space-y-3" data-testid="stok-stok">
      {gorunen.length > 1 && (
        <div className="flex flex-wrap gap-1" role="tablist">
          {ALTLAR.filter((a) => gorunen.includes(a.anahtar)).map(({ anahtar, ikon: Ikon }) => (
            <button
              key={anahtar}
              type="button"
              role="tab"
              aria-selected={alt === anahtar}
              onClick={() => setAlt(anahtar)}
              className={`flex items-center gap-1.5 rounded-full border px-3 py-1.5 text-xs ${alt === anahtar ? 'border-purple-400/60 bg-purple-500/20 text-white' : 'border-white/10 text-muted-foreground hover:text-white'}`}
              data-stok-alt={anahtar}
            >
              <Ikon className="h-3.5 w-3.5" aria-hidden="true" />
              {t(`stokPos.stok.alt.${anahtar}`)}
            </button>
          ))}
        </div>
      )}
      {alt === 'hareket' ? (
        <HareketFormu api={api} meta={meta} onMeta={onMeta} />
      ) : alt === 'transfer' ? (
        <TransferFormu api={api} meta={meta} />
      ) : alt === 'sayim' ? (
        <Sayimlar api={api} meta={meta} onMeta={onMeta} />
      ) : alt === 'gecmis' ? (
        <Gecmis api={api} meta={meta} />
      ) : (
        <Tedarikciler api={api} />
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Ürün seçici (arama + okutma)
// ---------------------------------------------------------------------------
export function UrunSecici({ api, onSec, testid }: { api: StokApi; onSec: (u: Urun) => void; testid?: string }) {
  const { t } = useTranslation();
  const [ara, setAra] = useState('');
  const [liste, setListe] = useState<Urun[]>([]);
  const [hata, setHata] = useState<string | null>(null);
  useEffect(() => {
    const a = ara.trim();
    if (a.length < 2) return setListe([]);
    const z = window.setTimeout(() => {
      api
        .urunler({ ara: a, adet: 12 })
        .then((r) => setListe(r.items.filter((u) => u.stok_takibi)))
        .catch(() => undefined);
    }, 220);
    return () => window.clearTimeout(z);
  }, [api, ara]);
  const kodla = async () => {
    const a = ara.trim();
    if (!a) return;
    try {
      onSec(await api.urunKodla(a));
      setAra('');
      setHata(null);
    } catch (e) {
      if (liste.length === 1) {
        onSec(liste[0]);
        setAra('');
      } else setHata(hataMetni(t, e));
    }
  };
  return (
    <div className="relative">
      <input
        className={GIRDI}
        value={ara}
        onChange={(e) => setAra(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === 'Enter') {
            e.preventDefault();
            void kodla();
          }
        }}
        placeholder={t('stokPos.stok.urunAra')}
        data-testid={testid}
        autoComplete="off"
      />
      {hata && <p className="mt-1 text-xs text-red-300">{hata}</p>}
      {liste.length > 0 && (
        <ul className="absolute inset-x-0 top-11 z-10 max-h-56 overflow-y-auto rounded-lg border border-white/10 bg-[#1a1229] shadow-xl">
          {liste.map((u) => (
            <li key={u.id}>
              <button
                type="button"
                className="flex w-full items-center justify-between gap-2 px-3 py-2 text-start text-sm hover:bg-white/5"
                onClick={() => {
                  onSec(u);
                  setAra('');
                  setListe([]);
                }}
              >
                <span className="truncate">{u.ad}</span>
                <span className="font-mono text-xs text-muted-foreground" dir="ltr">
                  {u.barkod}
                </span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

interface Satir {
  urun: Urun;
  miktar: string;
  maliyet: string;
}

function Satirlar({ satirlar, setSatirlar, maliyet }: { satirlar: Satir[]; setSatirlar: (s: Satir[]) => void; maliyet?: boolean }) {
  const { t, i18n } = useTranslation();
  const dil = i18n.language || 'tr';
  if (!satirlar.length) return <p className="py-3 text-center text-xs text-muted-foreground">{t('stokPos.stok.satirYok')}</p>;
  return (
    <ul className="divide-y divide-white/5">
      {satirlar.map((s, i) => (
        <li key={s.urun.id} className="flex flex-wrap items-center gap-2 py-2 text-sm" data-testid="stok-hareket-satir">
          <span className="min-w-0 flex-1 basis-40">
            {s.urun.ad}
            <span className="block text-xs text-muted-foreground">
              {t('stokPos.stok.mevcut', { miktar: miktarYaz(s.urun.stok.toplam, dil), birim: t(`stokPos.birim.${s.urun.birim}`) })}
            </span>
          </span>
          <input
            className={cn(GIRDI, 'h-9 w-24')}
            inputMode="decimal"
            value={s.miktar}
            onChange={(e) => setSatirlar(satirlar.map((x, j) => (j === i ? { ...x, miktar: e.target.value } : x)))}
            placeholder={t('stokPos.stok.miktar')}
            aria-label={t('stokPos.stok.miktar')}
            data-testid="stok-hareket-miktar"
          />
          {maliyet && (
            <input
              className={cn(GIRDI, 'h-9 w-28')}
              inputMode="decimal"
              value={s.maliyet}
              onChange={(e) => setSatirlar(satirlar.map((x, j) => (j === i ? { ...x, maliyet: e.target.value } : x)))}
              placeholder={t('stokPos.stok.birimMaliyet')}
              aria-label={t('stokPos.stok.birimMaliyet')}
            />
          )}
          <Button size="icon" variant="ghost" className="h-8 w-8 text-red-300" onClick={() => setSatirlar(satirlar.filter((_, j) => j !== i))} aria-label={t('stokPos.sil')}>
            <Trash2 className="h-4 w-4" aria-hidden="true" />
          </Button>
        </li>
      ))}
    </ul>
  );
}

function satirEkle(satirlar: Satir[], u: Urun): Satir[] {
  if (satirlar.some((s) => s.urun.id === u.id)) return satirlar.map((s) => (s.urun.id === u.id ? { ...s, miktar: String((sayiCevir(s.miktar) || 0) + 1) } : s));
  return [...satirlar, { urun: u, miktar: '1', maliyet: u.alis_fiyati ? (u.alis_fiyati / 100).toFixed(2).replace('.', ',') : '' }];
}

function HareketFormu({ api, meta, onMeta }: { api: StokApi; meta: Meta; onMeta: () => void }) {
  const { t } = useTranslation();
  const konumlar = meta.konumlar.filter((k) => k.aktif);
  const [tur, setTur] = useState('giris');
  const [konum, setKonum] = useState<number>((konumlar.find((k) => k.varsayilan) || konumlar[0])?.id);
  const [tedarikciler, setTedarikciler] = useState<Tedarikci[]>([]);
  const [tedarikci, setTedarikci] = useState('');
  const [belge, setBelge] = useState('');
  const [aciklama, setAciklama] = useState('');
  const [maliyetGuncelle, setMaliyetGuncelle] = useState(true);
  const [satirlar, setSatirlar] = useState<Satir[]>([]);
  const [mesaj, setMesaj] = useState<{ ok: boolean; metin: string } | null>(null);
  const [mesgul, setMesgul] = useState(false);
  useEffect(() => {
    api
      .tedarikciler()
      .then((r) => setTedarikciler(r.items.filter((x) => x.aktif)))
      .catch(() => undefined);
  }, [api]);
  const kaydet = async () => {
    setMesgul(true);
    setMesaj(null);
    try {
      const r = await api.hareketEkle({
        tur,
        konum_id: konum,
        tedarikci_id: tur === 'giris' && tedarikci ? Number(tedarikci) : undefined,
        belge_no: belge || undefined,
        aciklama: aciklama || undefined,
        maliyet_guncelle: maliyetGuncelle,
        kalemler: satirlar.map((s) => ({ urun_id: s.urun.id, miktar: s.miktar.replace(',', '.'), birim_maliyet: tur === 'giris' && s.maliyet ? s.maliyet : undefined })),
      });
      setSatirlar([]);
      setBelge('');
      setAciklama('');
      setMesaj({ ok: true, metin: t('stokPos.stok.kaydedildi', { sayi: r.kalem }) + (r.kritik.length ? ` ${t('stokPos.stok.kritikUyari', { sayi: r.kritik.length })}` : '') });
      onMeta();
    } catch (e) {
      setMesaj({ ok: false, metin: hataMetni(t, e) });
    } finally {
      setMesgul(false);
    }
  };
  return (
    <div className={`${KART} space-y-3 p-4`} data-testid="stok-hareket-formu">
      <div className="grid gap-3 sm:grid-cols-3">
        <Alan etiket={t('stokPos.stok.tur')}>
          <select className={SECIM} value={tur} onChange={(e) => setTur(e.target.value)} data-testid="stok-hareket-tur">
            {meta.elle_hareketler.map((h) => (
              <option key={h} value={h}>
                {t(`stokPos.hareket.${h}`)}
              </option>
            ))}
          </select>
        </Alan>
        {konumlar.length > 1 && (
          <Alan etiket={t('stokPos.konum')}>
            <select className={SECIM} value={konum} onChange={(e) => setKonum(Number(e.target.value))}>
              {konumlar.map((k) => (
                <option key={k.id} value={k.id}>
                  {k.ad}
                </option>
              ))}
            </select>
          </Alan>
        )}
        {tur === 'giris' && (
          <Alan etiket={t('stokPos.stok.tedarikci')}>
            <select className={SECIM} value={tedarikci} onChange={(e) => setTedarikci(e.target.value)}>
              <option value="">—</option>
              {tedarikciler.map((x) => (
                <option key={x.id} value={x.id}>
                  {x.ad}
                </option>
              ))}
            </select>
          </Alan>
        )}
        <Alan etiket={t('stokPos.stok.belgeNo')}>
          <input className={GIRDI} value={belge} onChange={(e) => setBelge(e.target.value)} maxLength={40} />
        </Alan>
        <Alan etiket={t('stokPos.stok.aciklama')} className="sm:col-span-2">
          <input className={GIRDI} value={aciklama} onChange={(e) => setAciklama(e.target.value)} maxLength={300} />
        </Alan>
      </div>
      <p className="text-xs text-muted-foreground">{t(`stokPos.hareketAciklama.${tur}`)}</p>
      <UrunSecici api={api} onSec={(u) => setSatirlar(satirEkle(satirlar, u))} testid="stok-hareket-ara" />
      <Satirlar satirlar={satirlar} setSatirlar={setSatirlar} maliyet={tur === 'giris'} />
      {tur === 'giris' && <Anahtar acik={maliyetGuncelle} onDegis={setMaliyetGuncelle} etiket={t('stokPos.stok.maliyetGuncelle')} />}
      {mesaj && (
        <p className={`text-sm ${mesaj.ok ? 'text-emerald-300' : 'text-red-300'}`} role="status" data-testid="stok-hareket-mesaj">
          {mesaj.metin}
        </p>
      )}
      <div className="flex justify-end">
        <Button onClick={() => void kaydet()} disabled={mesgul || !satirlar.length} data-testid="stok-hareket-kaydet">
          {t('stokPos.kaydet')}
        </Button>
      </div>
    </div>
  );
}

function TransferFormu({ api, meta }: { api: StokApi; meta: Meta }) {
  const { t } = useTranslation();
  const konumlar = meta.konumlar.filter((k) => k.aktif);
  const [kaynak, setKaynak] = useState<number>(konumlar[0]?.id);
  const [hedef, setHedef] = useState<number>(konumlar[1]?.id);
  const [aciklama, setAciklama] = useState('');
  const [satirlar, setSatirlar] = useState<Satir[]>([]);
  const [mesaj, setMesaj] = useState<{ ok: boolean; metin: string } | null>(null);
  const kaydet = async () => {
    try {
      await api.transfer({ kaynak_konum_id: kaynak, hedef_konum_id: hedef, aciklama: aciklama || undefined, kalemler: satirlar.map((s) => ({ urun_id: s.urun.id, miktar: s.miktar.replace(',', '.') })) });
      setSatirlar([]);
      setMesaj({ ok: true, metin: t('stokPos.stok.transferTamam') });
    } catch (e) {
      setMesaj({ ok: false, metin: hataMetni(t, e) });
    }
  };
  return (
    <div className={`${KART} space-y-3 p-4`}>
      <div className="grid gap-3 sm:grid-cols-3">
        <Alan etiket={t('stokPos.stok.kaynak')}>
          <select className={SECIM} value={kaynak} onChange={(e) => setKaynak(Number(e.target.value))}>
            {konumlar.map((k) => (
              <option key={k.id} value={k.id}>
                {k.ad}
              </option>
            ))}
          </select>
        </Alan>
        <Alan etiket={t('stokPos.stok.hedef')}>
          <select className={SECIM} value={hedef} onChange={(e) => setHedef(Number(e.target.value))}>
            {konumlar.map((k) => (
              <option key={k.id} value={k.id}>
                {k.ad}
              </option>
            ))}
          </select>
        </Alan>
        <Alan etiket={t('stokPos.stok.aciklama')}>
          <input className={GIRDI} value={aciklama} onChange={(e) => setAciklama(e.target.value)} maxLength={300} />
        </Alan>
      </div>
      <UrunSecici api={api} onSec={(u) => setSatirlar(satirEkle(satirlar, u))} />
      <Satirlar satirlar={satirlar} setSatirlar={setSatirlar} />
      {mesaj && <p className={`text-sm ${mesaj.ok ? 'text-emerald-300' : 'text-red-300'}`}>{mesaj.metin}</p>}
      <div className="flex justify-end">
        <Button onClick={() => void kaydet()} disabled={!satirlar.length || kaynak === hedef}>
          <ArrowLeftRight className="h-4 w-4" aria-hidden="true" />
          {t('stokPos.stok.transferEt')}
        </Button>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Sayım
// ---------------------------------------------------------------------------
function Sayimlar({ api, meta, onMeta }: { api: StokApi; meta: Meta; onMeta: () => void }) {
  const { t, i18n } = useTranslation();
  const dil = i18n.language || 'tr';
  const [liste, setListe] = useState<Sayim[] | null>(null);
  const [acik, setAcik] = useState<Sayim | null>(null);
  const [hata, setHata] = useState<string | null>(null);
  const konumlar = meta.konumlar.filter((k) => k.aktif);
  const [konum, setKonum] = useState<number>((konumlar.find((k) => k.varsayilan) || konumlar[0])?.id);
  const yukle = useCallback(async () => {
    try {
      setListe((await api.sayimlar()).items);
    } catch (e) {
      setHata(hataMetni(t, e));
    }
  }, [api, t]);
  useEffect(() => {
    void yukle();
  }, [yukle]);
  const ac = async (id: number) => {
    try {
      setAcik(await api.sayim(id));
    } catch (e) {
      setHata(hataMetni(t, e));
    }
  };
  const baslat = async () => {
    try {
      const s = await api.sayimBaslat({ konum_id: konum });
      await ac(s.id);
      void yukle();
    } catch (e) {
      setHata(hataMetni(t, e));
    }
  };
  if (acik) return <SayimEkrani api={api} sayim={acik} meta={meta} onGeri={() => { setAcik(null); void yukle(); onMeta(); }} />;
  return (
    <div className="space-y-3">
      <div className={`${KART} flex flex-wrap items-end gap-2 p-4`}>
        <p className="w-full text-sm text-muted-foreground">{t('stokPos.sayim.aciklama')}</p>
        {konumlar.length > 1 && (
          <Alan etiket={t('stokPos.konum')} className="w-48">
            <select className={SECIM} value={konum} onChange={(e) => setKonum(Number(e.target.value))}>
              {konumlar.map((k) => (
                <option key={k.id} value={k.id}>
                  {k.ad}
                </option>
              ))}
            </select>
          </Alan>
        )}
        <Button onClick={() => void baslat()} className="gap-1.5" data-testid="stok-sayim-baslat">
          <Plus className="h-4 w-4" aria-hidden="true" />
          {t('stokPos.sayim.yeni')}
        </Button>
      </div>
      {hata && <p className="text-sm text-red-300">{hata}</p>}
      {!liste ? (
        <Yukleniyor />
      ) : !liste.length ? (
        <Bos>{t('stokPos.sayim.yok')}</Bos>
      ) : (
        <ul className={`${KART} divide-y divide-white/5`}>
          {liste.map((s) => (
            <li key={s.id} className="flex flex-wrap items-center gap-2 px-3 py-2 text-sm">
              <span>#{s.id}</span>
              <span className="text-muted-foreground">{konumlar.find((k) => k.id === s.konum_id)?.ad}</span>
              <span className="text-xs text-muted-foreground">{tarihSaat(s.baslangic, dil)}</span>
              <Rozet renk={s.durum === 'acik' ? 'border-sky-400/40 bg-sky-500/15 text-sky-200' : undefined}>{t(`stokPos.sayim.durum.${s.durum}`)}</Rozet>
              {s.ozet && <span className="text-xs text-muted-foreground">{t('stokPos.sayim.ozet', { kalem: s.ozet.kalem, farkli: s.ozet.farkli })}</span>}
              <Button size="sm" variant="ghost" className="ms-auto" onClick={() => void ac(s.id)}>
                {s.durum === 'acik' ? t('stokPos.sayim.devam') : t('stokPos.ac')}
              </Button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function SayimEkrani({ api, sayim, meta, onGeri }: { api: StokApi; sayim: Sayim; meta: Meta; onGeri: () => void }) {
  const { t, i18n } = useTranslation();
  const dil = i18n.language || 'tr';
  const [s, setS] = useState(sayim);
  const [kod, setKod] = useState('');
  const [hata, setHata] = useState<string | null>(null);
  const [sifirla, setSifirla] = useState(false);
  const [kamera, setKamera] = useState(false);
  const acik = s.durum === 'acik';
  const yenile = async () => setS(await api.sayim(s.id));
  const okut = async (k: string, sayilan?: number) => {
    try {
      setHata(null);
      await api.sayimOkut(s.id, sayilan === undefined ? { kod: k } : { kod: k, sayilan });
      await yenile();
    } catch (e) {
      setHata(hataMetni(t, e));
    }
  };
  const onayla = async () => {
    if (!window.confirm(t('stokPos.sayim.onaylaOnay'))) return;
    try {
      setS(await api.sayimOnayla(s.id, sifirla));
      const tam = await api.sayim(s.id);
      setS(tam);
    } catch (e) {
      setHata(hataMetni(t, e));
    }
  };
  const iptal = async () => {
    try {
      await api.sayimIptal(s.id);
      onGeri();
    } catch (e) {
      setHata(hataMetni(t, e));
    }
  };
  return (
    <div className="space-y-3" data-testid="stok-sayim-ekrani">
      <div className="flex flex-wrap items-center gap-2">
        <Button size="sm" variant="ghost" onClick={onGeri}>
          ← {t('stokPos.geri')}
        </Button>
        <strong>
          {t('stokPos.sayim.baslik', { no: s.id })} · {meta.konumlar.find((k) => k.id === s.konum_id)?.ad}
        </strong>
        <Rozet>{t(`stokPos.sayim.durum.${s.durum}`)}</Rozet>
      </div>
      {acik && (
        <form
          className="flex gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            if (kod.trim()) void okut(kod.trim());
            setKod('');
          }}
        >
          <input className={cn(GIRDI, 'h-12 text-base')} value={kod} onChange={(e) => setKod(e.target.value)} placeholder={t('stokPos.sayim.okutIpucu')} autoFocus data-testid="stok-sayim-kod" autoComplete="off" />
          <Button type="button" variant="outline" className={`${DIS_DUGME} h-12 w-12 p-0`} onClick={() => setKamera(true)} aria-label={t('stokPos.kasa.kamera')}>
            <Camera className="h-5 w-5" aria-hidden="true" />
          </Button>
        </form>
      )}
      {hata && <p className="text-sm text-red-300">{hata}</p>}
      {s.ozet && (
        <p className="rounded-lg border border-emerald-400/30 bg-emerald-500/10 p-2 text-sm text-emerald-100" data-testid="stok-sayim-ozet">
          {t('stokPos.sayim.onaylandi', { kalem: s.ozet.kalem, farkli: s.ozet.farkli, arti: s.ozet.fark_arti, eksi: s.ozet.fark_eksi, deger: para(s.ozet.deger_farki, meta.ayarlar.para_birimi, dil) })}
        </p>
      )}
      <div className={`${KART} overflow-x-auto`}>
        <table className="w-full min-w-[480px] text-sm">
          <thead className="text-xs text-muted-foreground">
            <tr className="border-b border-white/10">
              <th className="p-2 text-start">{t('stokPos.urun.ad')}</th>
              <th className="p-2 text-end">{t('stokPos.sayim.sayilan')}</th>
              <th className="p-2 text-end">{t('stokPos.sayim.sistem')}</th>
              <th className="p-2 text-end">{t('stokPos.sayim.fark')}</th>
            </tr>
          </thead>
          <tbody>
            {(s.kalemler || []).map((k) => (
              <tr key={k.urun_id} className="border-b border-white/5" data-testid="stok-sayim-satir">
                <td className="p-2">
                  {k.ad}
                  <span className="block font-mono text-[11px] text-muted-foreground" dir="ltr">
                    {k.barkod}
                  </span>
                </td>
                <td className="p-2 text-end">
                  {acik ? (
                    <input
                      className={cn(GIRDI, 'ms-auto h-8 w-20 text-end')}
                      inputMode="decimal"
                      defaultValue={String(k.sayilan)}
                      onBlur={(e) => {
                        const v = sayiCevir(e.target.value);
                        if (v !== null && v !== k.sayilan && k.barkod) void okut(k.barkod, v);
                      }}
                      aria-label={t('stokPos.sayim.sayilan')}
                    />
                  ) : (
                    miktarYaz(k.sayilan, dil)
                  )}
                </td>
                <td className="p-2 text-end tabular-nums">{miktarYaz(k.sistem, dil)}</td>
                <td className={`p-2 text-end font-semibold tabular-nums ${k.fark < 0 ? 'text-red-300' : k.fark > 0 ? 'text-emerald-300' : ''}`} data-testid="stok-sayim-fark">
                  {k.fark > 0 ? '+' : ''}
                  {miktarYaz(k.fark, dil)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {!s.kalemler?.length && <Bos>{t('stokPos.sayim.bos')}</Bos>}
      </div>
      {acik && (
        <div className="flex flex-wrap items-center gap-3">
          <Anahtar acik={sifirla} onDegis={setSifirla} etiket={t('stokPos.sayim.sifirla')} />
          <Button variant="ghost" className="ms-auto" onClick={() => void iptal()}>
            {t('stokPos.sayim.iptal')}
          </Button>
          <Button onClick={() => void onayla()} disabled={!s.kalemler?.length} data-testid="stok-sayim-onayla">
            {t('stokPos.sayim.onayla')}
          </Button>
        </div>
      )}
      {kamera && (
        <Suspense fallback={null}>
          <Okutucu onKod={(k) => void okut(k)} onKapat={() => setKamera(false)} />
        </Suspense>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Geçmiş
// ---------------------------------------------------------------------------
function Gecmis({ api, meta }: { api: StokApi; meta: Meta }) {
  const { t, i18n } = useTranslation();
  const dil = i18n.language || 'tr';
  const [tur, setTur] = useState('');
  const [bas, setBas] = useState(gunOnce(29));
  const [bit, setBit] = useState(bugun());
  const [sayfa, setSayfa] = useState(1);
  const [veri, setVeri] = useState<{ items: Hareket[]; toplam: number } | null>(null);
  const [hata, setHata] = useState<string | null>(null);
  useEffect(() => {
    api
      .hareketler({ tur: tur || undefined, bas, bit, sayfa })
      .then(setVeri)
      .catch((e) => setHata(hataMetni(t, e)));
  }, [api, tur, bas, bit, sayfa, t]);
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap gap-2">
        <select className={cn(SECIM, 'w-auto')} value={tur} onChange={(e) => { setTur(e.target.value); setSayfa(1); }} aria-label={t('stokPos.stok.tur')}>
          <option value="">{t('stokPos.stok.tumTurler')}</option>
          {meta.hareket_turleri.map((h) => (
            <option key={h} value={h}>
              {t(`stokPos.hareket.${h}`)}
            </option>
          ))}
        </select>
        <input type="date" className={cn(GIRDI, 'w-auto')} value={bas} onChange={(e) => setBas(e.target.value)} aria-label={t('stokPos.rapor.bas')} />
        <input type="date" className={cn(GIRDI, 'w-auto')} value={bit} onChange={(e) => setBit(e.target.value)} aria-label={t('stokPos.rapor.bit')} />
      </div>
      {hata && <p className="text-sm text-red-300">{hata}</p>}
      {!veri ? (
        <Yukleniyor />
      ) : !veri.items.length ? (
        <Bos>{t('stokPos.stok.hareketYok')}</Bos>
      ) : (
        <ul className={`${KART} divide-y divide-white/5`} data-testid="stok-gecmis">
          {veri.items.map((h) => (
            <li key={h.id} className="flex flex-wrap items-center gap-x-3 gap-y-0.5 px-3 py-2 text-sm">
              <Rozet>{t(`stokPos.hareket.${h.tur}`)}</Rozet>
              <span className="min-w-0 flex-1 truncate">{h.urun_ad}</span>
              <span className={`font-semibold tabular-nums ${h.miktar < 0 ? 'text-red-300' : 'text-emerald-300'}`}>
                {h.miktar > 0 ? '+' : ''}
                {miktarYaz(h.miktar, dil)}
              </span>
              <span className="w-20 text-end text-xs text-muted-foreground">→ {miktarYaz(h.sonra, dil)}</span>
              <span className="w-full text-xs text-muted-foreground sm:w-auto">
                {tarihSaat(h.zaman, dil)} · {meta.konumlar.find((k) => k.id === h.konum_id)?.ad} {h.kisi ? `· ${h.kisi}` : ''} {h.belge_no ? `· ${h.belge_no}` : ''}
              </span>
            </li>
          ))}
        </ul>
      )}
      {veri && veri.toplam > 50 && (
        <div className="flex justify-center gap-2">
          <Button size="sm" variant="ghost" disabled={sayfa <= 1} onClick={() => setSayfa(sayfa - 1)}>
            ←
          </Button>
          <span className="text-sm text-muted-foreground">{sayfa}</span>
          <Button size="sm" variant="ghost" disabled={sayfa * 50 >= veri.toplam} onClick={() => setSayfa(sayfa + 1)}>
            →
          </Button>
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Tedarikçiler
// ---------------------------------------------------------------------------
function Tedarikciler({ api }: { api: StokApi }) {
  const { t } = useTranslation();
  const [liste, setListe] = useState<Tedarikci[] | null>(null);
  const [form, setForm] = useState<Partial<Tedarikci> | null>(null);
  const [hata, setHata] = useState<string | null>(null);
  const yukle = useCallback(async () => {
    try {
      setListe((await api.tedarikciler()).items);
    } catch (e) {
      setHata(hataMetni(t, e));
    }
  }, [api, t]);
  useEffect(() => {
    void yukle();
  }, [yukle]);
  const kaydet = async () => {
    if (!form) return;
    try {
      const govde = { ad: form.ad, yetkili: form.yetkili || null, telefon: form.telefon || null, eposta: form.eposta || null, vergi_no: form.vergi_no || null, notlar: form.notlar || null };
      if (form.id) await api.tedarikciGuncelle(form.id, govde);
      else await api.tedarikciEkle(govde);
      setForm(null);
      void yukle();
    } catch (e) {
      setHata(hataMetni(t, e));
    }
  };
  const sil = async (x: Tedarikci) => {
    if (!window.confirm(t('stokPos.stok.tedarikciSilOnay', { ad: x.ad }))) return;
    try {
      await api.tedarikciSil(x.id);
      void yukle();
    } catch (e) {
      setHata(hataMetni(t, e));
    }
  };
  return (
    <div className="space-y-3">
      <Button size="sm" className="gap-1.5" onClick={() => setForm({})}>
        <Plus className="h-4 w-4" aria-hidden="true" />
        {t('stokPos.stok.yeniTedarikci')}
      </Button>
      {hata && <p className="text-sm text-red-300">{hata}</p>}
      {!liste ? (
        <Yukleniyor />
      ) : !liste.length ? (
        <Bos>{t('stokPos.stok.tedarikciYok')}</Bos>
      ) : (
        <ul className={`${KART} divide-y divide-white/5`}>
          {liste.map((x) => (
            <li key={x.id} className={`flex flex-wrap items-center gap-2 px-3 py-2 text-sm ${x.aktif ? '' : 'opacity-60'}`}>
              <span className="min-w-0 flex-1">
                {x.ad}
                <span className="block text-xs text-muted-foreground">{[x.yetkili, x.telefon, x.eposta].filter(Boolean).join(' · ')}</span>
              </span>
              <Button size="sm" variant="ghost" onClick={() => setForm(x)}>
                {t('stokPos.duzenle')}
              </Button>
              <Button size="icon" variant="ghost" className="h-8 w-8 text-red-300" onClick={() => void sil(x)} aria-label={t('stokPos.sil')}>
                <Trash2 className="h-4 w-4" aria-hidden="true" />
              </Button>
            </li>
          ))}
        </ul>
      )}
      {form && (
        <Pencere baslik={form.id ? t('stokPos.duzenle') : t('stokPos.stok.yeniTedarikci')} onKapat={() => setForm(null)}>
          <div className="grid gap-2 sm:grid-cols-2">
            <Alan etiket={t('stokPos.alici.ad')} className="sm:col-span-2">
              <input className={GIRDI} value={form.ad || ''} onChange={(e) => setForm({ ...form, ad: e.target.value })} />
            </Alan>
            <Alan etiket={t('stokPos.stok.yetkili')}>
              <input className={GIRDI} value={form.yetkili || ''} onChange={(e) => setForm({ ...form, yetkili: e.target.value })} />
            </Alan>
            <Alan etiket={t('stokPos.alici.telefon')}>
              <input className={GIRDI} value={form.telefon || ''} onChange={(e) => setForm({ ...form, telefon: e.target.value })} />
            </Alan>
            <Alan etiket={t('stokPos.alici.eposta')}>
              <input className={GIRDI} value={form.eposta || ''} onChange={(e) => setForm({ ...form, eposta: e.target.value })} />
            </Alan>
            <Alan etiket={t('stokPos.alici.vergiNo')}>
              <input className={GIRDI} value={form.vergi_no || ''} onChange={(e) => setForm({ ...form, vergi_no: e.target.value })} inputMode="numeric" />
            </Alan>
            <Alan etiket={t('stokPos.urun.notlar')} className="sm:col-span-2">
              <textarea className={METIN_ALANI} value={form.notlar || ''} onChange={(e) => setForm({ ...form, notlar: e.target.value })} />
            </Alan>
          </div>
          <div className="mt-3 flex justify-end">
            <Button onClick={() => void kaydet()} disabled={!form.ad?.trim()}>
              {t('stokPos.kaydet')}
            </Button>
          </div>
        </Pencere>
      )}
    </div>
  );
}
