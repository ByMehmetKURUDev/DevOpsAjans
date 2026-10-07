import { useEffect, useState, type ReactNode } from 'react';
import { useTranslation } from 'react-i18next';
import { Download, Printer } from 'lucide-react';

import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';
import { Bos, DIS_DUGME, GIRDI, KART, SECIM, Yukleniyor } from '@/components/stokPos/ortak';
import { ZRaporu } from '@/components/stokPos/Fis';
import { bugun, gunOnce, hataMetni, miktarYaz, para, tarihSaat, type Meta, type Ozet, type StokApi } from '@/lib/stokPos';

type Alt = 'gun' | 'donem' | 'kar' | 'stok' | 'hareketsiz';
const ALTLAR: Alt[] = ['gun', 'donem', 'kar', 'stok', 'hareketsiz'];

/** Faz 6P — raporlar: Z-benzeri gün sonu (mali değil), dönem satışları, ürün bazlı kâr, stok değeri, hareketsiz ürünler; CSV. */
export default function Raporlar({ api, meta }: { api: StokApi; meta: Meta }) {
  const { t, i18n } = useTranslation();
  const dil = i18n.language || 'tr';
  const pb = meta.ayarlar.para_birimi;
  const p = (n: number | null | undefined) => para(n ?? 0, pb, dil);
  const [alt, setAlt] = useState<Alt>('gun');
  const [tarih, setTarih] = useState(bugun());
  const [bas, setBas] = useState(gunOnce(29));
  const [bit, setBit] = useState(bugun());
  const [konum, setKonum] = useState<string>('');
  const [gun, setGun] = useState(30);
  const [veri, setVeri] = useState<unknown>(null);
  const [hata, setHata] = useState<string | null>(null);
  const [z, setZ] = useState<Ozet | null>(null);
  const konumlar = meta.konumlar;
  const k = konum ? Number(konum) : undefined;

  useEffect(() => {
    setVeri(null);
    setHata(null);
    const is =
      alt === 'gun'
        ? api.raporGun(tarih, k)
        : alt === 'donem'
          ? api.raporDonem(bas, bit, k)
          : alt === 'kar'
            ? api.raporKar(bas, bit, k)
            : alt === 'stok'
              ? api.raporStokDegeri(k)
              : api.raporHareketsiz(gun);
    is.then(setVeri).catch((e) => setHata(hataMetni(t, e)));
  }, [api, alt, tarih, bas, bit, k, gun, t]);

  const csv = () => {
    const tur = alt === 'stok' ? 'stok-degeri' : alt === 'gun' ? 'donem' : alt;
    void api.raporCsv(tur as 'donem' | 'kar' | 'stok-degeri' | 'hareketsiz', alt === 'hareketsiz' ? { gun } : alt === 'stok' ? { konum_id: k } : { bas: alt === 'gun' ? tarih : bas, bit: alt === 'gun' ? tarih : bit, konum_id: k }).catch((e) => setHata(hataMetni(t, e)));
  };

  return (
    <div className="space-y-3" data-testid="stok-raporlar">
      <div className="flex flex-wrap gap-1" role="tablist">
        {ALTLAR.map((a) => (
          <button
            key={a}
            type="button"
            role="tab"
            aria-selected={alt === a}
            onClick={() => setAlt(a)}
            className={`rounded-full border px-3 py-1.5 text-xs ${alt === a ? 'border-purple-400/60 bg-purple-500/20 text-white' : 'border-white/10 text-muted-foreground hover:text-white'}`}
            data-rapor={a}
          >
            {t(`stokPos.rapor.alt.${a}`)}
          </button>
        ))}
      </div>
      <div className="flex flex-wrap items-center gap-2">
        {alt === 'gun' && <input type="date" className={cn(GIRDI, 'w-auto')} value={tarih} onChange={(e) => setTarih(e.target.value)} aria-label={t('stokPos.z.tarih')} />}
        {(alt === 'donem' || alt === 'kar') && (
          <>
            <input type="date" className={cn(GIRDI, 'w-auto')} value={bas} onChange={(e) => setBas(e.target.value)} aria-label={t('stokPos.rapor.bas')} />
            <input type="date" className={cn(GIRDI, 'w-auto')} value={bit} onChange={(e) => setBit(e.target.value)} aria-label={t('stokPos.rapor.bit')} />
          </>
        )}
        {alt === 'hareketsiz' && (
          <select className={cn(SECIM, 'w-auto')} value={gun} onChange={(e) => setGun(Number(e.target.value))} aria-label={t('stokPos.rapor.gun')}>
            {[30, 60, 90, 180].map((g) => (
              <option key={g} value={g}>
                {t('stokPos.rapor.gunSecenek', { sayi: g })}
              </option>
            ))}
          </select>
        )}
        {alt !== 'hareketsiz' && konumlar.length > 1 && (
          <select className={cn(SECIM, 'w-auto')} value={konum} onChange={(e) => setKonum(e.target.value)} aria-label={t('stokPos.konum')}>
            <option value="">{t('stokPos.rapor.tumKonumlar')}</option>
            {konumlar.map((x) => (
              <option key={x.id} value={x.id}>
                {x.ad}
              </option>
            ))}
          </select>
        )}
        <Button size="sm" variant="outline" className={`${DIS_DUGME} ms-auto`} onClick={csv} data-testid="stok-rapor-csv">
          <Download className="h-4 w-4" aria-hidden="true" />
          CSV
        </Button>
      </div>
      {hata && <p className="text-sm text-red-300">{hata}</p>}
      {!veri ? (
        !hata && <Yukleniyor />
      ) : alt === 'gun' ? (
        <GunSonu ozet={veri as Ozet & { not: string }} p={p} onYazdir={() => setZ(veri as Ozet)} />
      ) : alt === 'donem' ? (
        <Tablo
          basliklar={[t('stokPos.z.tarih'), t('stokPos.z.satisSayisi'), t('stokPos.z.satisToplam'), t('stokPos.rapor.iade'), t('stokPos.z.net'), t('stokPos.odeme.nakit'), t('stokPos.odeme.kart'), t('stokPos.odeme.havale')]}
          satirlar={(veri as { gunler: Record<string, number | string>[] }).gunler.map((g) => [g.tarih, g.satis_sayisi, p(g.satis as number), p(g.iade as number), p(g.net as number), p(g.nakit as number), p(g.kart as number), p(g.havale as number)])}
          toplam={(() => {
            const tp = (veri as { toplam: Record<string, number> }).toplam;
            return [t('stokPos.rapor.toplam'), tp.satis_sayisi, p(tp.satis), p(tp.iade), p(tp.net), p(tp.nakit), p(tp.kart), p(tp.havale)];
          })()}
        />
      ) : alt === 'kar' ? (
        <Tablo
          basliklar={[t('stokPos.urun.ad'), t('stokPos.stok.miktar'), t('stokPos.rapor.ciro'), t('stokPos.rapor.maliyet'), t('stokPos.rapor.kar'), t('stokPos.rapor.marj')]}
          satirlar={(veri as { urunler: { ad: string; adet: number; birim: string; ciro: number; maliyet: number; kar: number; marj: number | null }[] }).urunler.map((u) => [
            u.ad,
            `${miktarYaz(u.adet, dil)} ${t(`stokPos.birim.${u.birim}`)}`,
            p(u.ciro),
            p(u.maliyet),
            p(u.kar),
            u.marj === null ? '—' : `%${u.marj}`,
          ])}
          toplam={(() => {
            const tp = (veri as { toplam: { ciro: number; maliyet: number; kar: number; marj: number | null } }).toplam;
            return [t('stokPos.rapor.toplam'), '', p(tp.ciro), p(tp.maliyet), p(tp.kar), tp.marj === null ? '—' : `%${tp.marj}`];
          })()}
          not={t('stokPos.rapor.karNotu')}
        />
      ) : alt === 'stok' ? (
        <Tablo
          basliklar={[t('stokPos.urun.ad'), t('stokPos.stok.miktar'), t('stokPos.rapor.maliyetDegeri'), t('stokPos.rapor.satisDegeri')]}
          satirlar={(veri as { urunler: { ad: string; miktar: number; birim: string; maliyet_degeri: number; satis_degeri: number }[] }).urunler.map((u) => [
            u.ad,
            `${miktarYaz(u.miktar, dil)} ${t(`stokPos.birim.${u.birim}`)}`,
            p(u.maliyet_degeri),
            p(u.satis_degeri),
          ])}
          toplam={(() => {
            const tp = (veri as { toplam: { maliyet_degeri: number; satis_degeri: number; urun: number } }).toplam;
            return [t('stokPos.rapor.urunSayisi', { sayi: tp.urun }), '', p(tp.maliyet_degeri), p(tp.satis_degeri)];
          })()}
        />
      ) : (
        <Tablo
          basliklar={[t('stokPos.urun.ad'), t('stokPos.stok.miktar'), t('stokPos.rapor.sonSatis'), t('stokPos.rapor.maliyetDegeri')]}
          satirlar={(veri as { urunler: { ad: string; miktar: number; birim: string; son_satis: string | null; maliyet_degeri: number }[] }).urunler.map((u) => [
            u.ad,
            `${miktarYaz(u.miktar, dil)} ${t(`stokPos.birim.${u.birim}`)}`,
            u.son_satis ? tarihSaat(u.son_satis, dil) : t('stokPos.rapor.hicSatilmadi'),
            p(u.maliyet_degeri),
          ])}
        />
      )}
      {z && <ZRaporu ozet={z} konum={k ? konumlar.find((x) => x.id === k)?.ad : t('stokPos.rapor.tumKonumlar')} onKapat={() => setZ(null)} />}
    </div>
  );
}

function GunSonu({ ozet, p, onYazdir }: { ozet: Ozet & { not: string }; p: (n: number | null | undefined) => string; onYazdir: () => void }) {
  const { t, i18n } = useTranslation();
  const dil = i18n.language || 'tr';
  const kutu = (etiket: string, deger: ReactNode, testid?: string) => (
    <div className="rounded-xl bg-white/[0.04] p-3">
      <p className="text-[11px] uppercase tracking-wider text-muted-foreground">{etiket}</p>
      <p className="text-lg font-semibold tabular-nums" data-testid={testid}>
        {deger}
      </p>
    </div>
  );
  return (
    <div className="space-y-3" data-testid="stok-gun-sonu">
      <p className="rounded-lg border border-amber-400/30 bg-amber-500/10 p-2 text-xs text-amber-100">{t('stokPos.z.maliDegil')}</p>
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
        {kutu(t('stokPos.z.satisSayisi'), ozet.satis_sayisi)}
        {kutu(t('stokPos.z.satisToplam'), p(ozet.satis_toplam))}
        {kutu(t('stokPos.rapor.iade'), p(ozet.iade_toplam))}
        {kutu(t('stokPos.z.net'), p(ozet.net), 'stok-gun-net')}
      </div>
      <div className="grid gap-3 md:grid-cols-3">
        <div className={`${KART} p-3`}>
          <h4 className="mb-2 text-sm font-semibold">{t('stokPos.z.odemeler')}</h4>
          {(['nakit', 'kart', 'havale'] as const).map((tur) => (
            <p key={tur} className="flex justify-between text-sm">
              <span className="text-muted-foreground">{t(`stokPos.odeme.${tur}`)}</span>
              <span className="tabular-nums">{p(ozet.odemeler[tur])}</span>
            </p>
          ))}
        </div>
        <div className={`${KART} p-3`}>
          <h4 className="mb-2 text-sm font-semibold">{t('stokPos.z.kdvDokumu')}</h4>
          {ozet.kdv_dokumu.length ? (
            ozet.kdv_dokumu.map((d) => (
              <p key={d.oran} className="flex justify-between text-sm">
                <span className="text-muted-foreground">%{d.oran} · {p(d.matrah)}</span>
                <span className="tabular-nums">{p(d.kdv)}</span>
              </p>
            ))
          ) : (
            <p className="text-sm text-muted-foreground">—</p>
          )}
        </div>
        <div className={`${KART} p-3`}>
          <h4 className="mb-2 text-sm font-semibold">{t('stokPos.z.enCok')}</h4>
          {ozet.en_cok_satanlar.length ? (
            ozet.en_cok_satanlar.slice(0, 5).map((u) => (
              <p key={u.urun_id} className="flex justify-between gap-2 text-sm">
                <span className="truncate">{u.ad}</span>
                <span className="tabular-nums text-muted-foreground">{miktarYaz(u.adet, dil)}</span>
              </p>
            ))
          ) : (
            <p className="text-sm text-muted-foreground">—</p>
          )}
        </div>
      </div>
      {!!ozet.oturumlar?.length && (
        <div className={`${KART} p-3`}>
          <h4 className="mb-2 text-sm font-semibold">{t('stokPos.rapor.oturumlar')}</h4>
          <ul className="space-y-1 text-sm">
            {ozet.oturumlar.map((o) => (
              <li key={o.id} className="flex flex-wrap gap-x-3">
                <span>#{o.id}</span>
                <span className="text-muted-foreground">
                  {tarihSaat(o.acilis_at, dil)} – {o.kapanis_at ? tarihSaat(o.kapanis_at, dil) : t('stokPos.rapor.acik')}
                </span>
                <span>{o.acan}</span>
                {o.fark !== null && (
                  <span className={o.fark === 0 ? 'text-emerald-300' : 'text-amber-300'}>
                    {t('stokPos.z.fark')}: {p(o.fark)}
                  </span>
                )}
              </li>
            ))}
          </ul>
        </div>
      )}
      <Button size="sm" variant="outline" className={DIS_DUGME} onClick={onYazdir} data-testid="stok-gun-yazdir">
        <Printer className="h-4 w-4" aria-hidden="true" />
        {t('stokPos.rapor.yazdir')}
      </Button>
    </div>
  );
}

function Tablo({ basliklar, satirlar, toplam, not }: { basliklar: string[]; satirlar: (string | number)[][]; toplam?: (string | number)[]; not?: string }) {
  const { t } = useTranslation();
  if (!satirlar.length) return <Bos>{t('stokPos.rapor.veriYok')}</Bos>;
  return (
    <div className={`${KART} overflow-x-auto`}>
      <table className="w-full min-w-[520px] text-sm" data-testid="stok-rapor-tablo">
        <thead className="text-xs text-muted-foreground">
          <tr className="border-b border-white/10">
            {basliklar.map((b, i) => (
              <th key={i} className={`p-2 ${i === 0 ? 'text-start' : 'text-end'}`}>
                {b}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {satirlar.map((s, i) => (
            <tr key={i} className="border-b border-white/5">
              {s.map((h, j) => (
                <td key={j} className={`p-2 ${j === 0 ? '' : 'text-end tabular-nums'}`}>
                  {h}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
        {toplam && (
          <tfoot>
            <tr className="font-semibold">
              {toplam.map((h, j) => (
                <td key={j} className={`p-2 ${j === 0 ? '' : 'text-end tabular-nums'}`}>
                  {h}
                </td>
              ))}
            </tr>
          </tfoot>
        )}
      </table>
      {not && <p className="p-2 text-xs text-muted-foreground">{not}</p>}
    </div>
  );
}
