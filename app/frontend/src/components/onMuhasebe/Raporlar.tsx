import { useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Download } from 'lucide-react';
import { Bar, BarChart, CartesianGrid, Cell, ComposedChart, Legend, Line, Pie, PieChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';

import { Button } from '@/components/ui/button';
import { Bos, DIS_DUGME, GIRDI, Hap, HataSatiri, KART, KovaTablosu, Not, SECIM, Yukleniyor } from '@/components/onMuhasebe/ortak';
import {
  ayYaz,
  bugun,
  hataMetni,
  kategoriAdi,
  KOVALAR,
  para,
  type AylikRapor,
  type BolumProps,
  type KarZarar,
  type KarZararKalemi,
  type KategoriRaporu,
  type KategoriTuru,
  type KdvRaporu,
  type NakitAkisi,
  type Yaslandirma,
} from '@/lib/onMuhasebe';

type Alt = 'aylik' | 'kategori' | 'karZarar' | 'nakit' | 'kdv' | 'yaslandirma';
const ALTLAR: Alt[] = ['aylik', 'kategori', 'karZarar', 'nakit', 'kdv', 'yaslandirma'];
const IPUCU = { background: '#150a2b', border: '1px solid rgba(167,139,250,0.4)', borderRadius: 12, color: '#ece6ff' };
const EKSEN = '#b9a9d6';

/**
 * Faz 6M — raporlar (recharts; yeni paket yok): aylık gelir-gider, kategori dağılımı, kâr-zarar (KDV hariç), nakit akışı
 * (geçmiş + tekrarlayan kayıtlardan 3 ay tahmin + 30/60/90 gün cari vadeleri), KDV özeti (bilgilendirme amaçlı), cari
 * yaşlandırma. Para birimleri ayrı gösterilir.
 */
export default function Raporlar({ api, surum }: BolumProps) {
  const { t, i18n } = useTranslation();
  const dil = i18n.language || 'tr';
  const [alt, setAlt] = useState<Alt>('aylik');
  const [yil, setYil] = useState(Number(bugun().slice(0, 4)));
  const [bas, setBas] = useState(`${bugun().slice(0, 7)}-01`);
  const [kzBas, setKzBas] = useState(`${bugun().slice(0, 4)}-01-01`);
  const [bit, setBit] = useState(bugun());
  const [ktur, setKtur] = useState<KategoriTuru>('gider');
  const [yon, setYon] = useState<'alacak' | 'borc'>('alacak');
  const [veri, setVeri] = useState<unknown>(null);
  const [pb, setPb] = useState<string>('');
  const [hata, setHata] = useState<string | null>(null);

  useEffect(() => {
    setVeri(null);
    setHata(null);
    let gecersiz = false;
    const is =
      alt === 'aylik'
        ? api.raporAylik(yil)
        : alt === 'kategori'
          ? api.raporKategori(bas, bit, ktur)
          : alt === 'karZarar'
            ? api.raporKarZarar(kzBas, bit)
          : alt === 'nakit'
            ? api.raporNakit(6)
            : alt === 'kdv'
              ? api.raporKdv(yil)
              : api.yaslandirma(yon);
    is.then((v: unknown) => !gecersiz && setVeri(v)).catch((e) => !gecersiz && setHata(hataMetni(t, e)));
    return () => {
      gecersiz = true;
    };
  }, [api, alt, yil, bas, kzBas, bit, ktur, yon, surum, t]);

  const pbler = useMemo(() => {
    const v = veri as { para_birimleri?: { para_birimi: string }[]; toplamlar?: { para_birimi: string }[] } | null;
    return (v?.para_birimleri || v?.toplamlar || []).map((x) => x.para_birimi);
  }, [veri]);
  const secili = pbler.includes(pb) ? pb : pbler[0] || '';
  const p = (n: number) => para(n, secili || 'TRY', dil);
  const kisa = (n: number) => {
    try {
      return new Intl.NumberFormat(dil === 'ar' ? 'ar-u-nu-latn' : dil, { notation: 'compact', maximumFractionDigits: 1 }).format(n / 100);
    } catch {
      return String(Math.round(n / 100));
    }
  };

  const csv = () => {
    const tur = alt === 'yaslandirma' ? null : alt === 'karZarar' ? 'kar_zarar' : alt;
    if (!tur) return;
    void api
      .raporCsv(
        tur,
        tur === 'aylik' || tur === 'kdv' ? { yil } : tur === 'kategori' ? { bas, bit, kategori_turu: ktur } : tur === 'kar_zarar' ? { bas: kzBas, bit } : {}
      )
      .catch((e) => setHata(hataMetni(t, e)));
  };

  const icerik = () => {
    if (!veri) return <Yukleniyor />;
    if (alt === 'aylik') {
      const r = veri as AylikRapor;
      const d = r.para_birimleri.find((x) => x.para_birimi === secili);
      if (!d) return <Bos>{t('onMuhasebe.rapor.veriYok')}</Bos>;
      const satirlar = d.aylar.map((a) => ({ ay: ayYaz(a.ay, dil), gelir: a.gelir, gider: a.gider, net: a.net }));
      return (
        <div className="space-y-3">
          <div className="grid gap-2 sm:grid-cols-3">
            <Ozet ad={t('onMuhasebe.ortak.gelir')} deger={p(d.gelir)} renk="text-emerald-300" />
            <Ozet ad={t('onMuhasebe.ortak.gider')} deger={p(d.gider)} renk="text-rose-300" />
            <Ozet ad={t('onMuhasebe.ortak.net')} deger={p(d.net)} renk={d.net >= 0 ? 'text-white' : 'text-rose-300'} />
          </div>
          <div className={`${KART} h-72 w-full p-3`} data-testid="mh-grafik-aylik">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={satirlar}>
                <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.08)" />
                <XAxis dataKey="ay" stroke={EKSEN} fontSize={11} tickLine={false} />
                <YAxis stroke={EKSEN} fontSize={11} tickLine={false} tickFormatter={kisa} width={48} />
                <Tooltip contentStyle={IPUCU} formatter={(v: number) => p(v)} />
                <Legend />
                <Bar dataKey="gelir" name={t('onMuhasebe.ortak.gelir')} fill="#34d399" radius={[6, 6, 0, 0]} />
                <Bar dataKey="gider" name={t('onMuhasebe.ortak.gider')} fill="#fb7185" radius={[6, 6, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
      );
    }
    if (alt === 'kategori') {
      const r = veri as KategoriRaporu;
      const d = r.para_birimleri.find((x) => x.para_birimi === secili);
      if (!d || !d.kalemler.length) return <Bos>{t('onMuhasebe.rapor.veriYok')}</Bos>;
      const dilim = d.kalemler.map((k) => ({ ad: kategoriAdi(t, k), tutar: k.tutar, oran: k.oran, renk: k.renk }));
      return (
        <div className="grid gap-3 lg:grid-cols-2">
          <div className={`${KART} h-72 w-full p-3`} data-testid="mh-grafik-kategori">
            <ResponsiveContainer width="100%" height="100%">
              <PieChart>
                <Pie data={dilim} dataKey="tutar" nameKey="ad" innerRadius="45%" outerRadius="80%" paddingAngle={2}>
                  {dilim.map((x, i) => (
                    <Cell key={i} fill={x.renk} />
                  ))}
                </Pie>
                <Tooltip contentStyle={IPUCU} formatter={(v: number) => p(v)} />
              </PieChart>
            </ResponsiveContainer>
          </div>
          <ul className={`${KART} divide-y divide-white/5 p-2`}>
            {dilim.map((x, i) => (
              <li key={i} className="flex items-center justify-between gap-2 px-2 py-1.5 text-sm">
                <span className="flex min-w-0 items-center gap-2">
                  <span className="h-2.5 w-2.5 flex-none rounded-full" style={{ backgroundColor: x.renk }} aria-hidden="true" />
                  <span className="truncate">{x.ad}</span>
                </span>
                <span className="whitespace-nowrap tabular-nums">
                  {p(x.tutar)} <span className="text-xs text-muted-foreground">%{x.oran}</span>
                </span>
              </li>
            ))}
            <li className="flex justify-between px-2 py-1.5 text-sm font-semibold">
              <span>{t('onMuhasebe.ortak.toplam')}</span>
              <span>{p(d.toplam)}</span>
            </li>
          </ul>
        </div>
      );
    }
    if (alt === 'karZarar') {
      const r = veri as KarZarar;
      const d = r.para_birimleri.find((x) => x.para_birimi === secili);
      if (!d) return <Bos>{t('onMuhasebe.rapor.veriYok')}</Bos>;
      const liste = (baslik: string, kalemler: KarZararKalemi[], toplam: number, renk: string, testid: string) => (
        <div className={`${KART} p-3`} data-testid={testid}>
          <h4 className="mb-1 text-sm font-semibold">{baslik}</h4>
          <ul className="divide-y divide-white/5 text-sm">
            {kalemler.map((x) => (
              <li key={`${x.kategori_id}`} className="flex items-center justify-between gap-3 py-1.5">
                <span className="flex min-w-0 items-center gap-2">
                  <span className="h-2.5 w-2.5 flex-none rounded-full" style={{ backgroundColor: x.renk }} aria-hidden="true" />
                  <span className="truncate">{kategoriAdi(t, x)}</span>
                </span>
                <span className="whitespace-nowrap tabular-nums">{p(x.tutar)}</span>
              </li>
            ))}
            <li className={`flex justify-between py-1.5 font-semibold ${renk}`}>
              <span>{t('onMuhasebe.ortak.toplam')}</span>
              <span className="tabular-nums">{p(toplam)}</span>
            </li>
          </ul>
        </div>
      );
      return (
        <div className="space-y-3" data-testid="mh-kar-zarar">
          <div className="grid gap-2 sm:grid-cols-3">
            <Ozet ad={t('onMuhasebe.rapor.kz.gelir')} deger={p(d.toplam_gelir)} renk="text-emerald-300" />
            <Ozet ad={t('onMuhasebe.rapor.kz.gider')} deger={p(d.toplam_gider)} renk="text-rose-300" />
            <Ozet
              ad={d.sonuc >= 0 ? t('onMuhasebe.rapor.kz.kar') : t('onMuhasebe.rapor.kz.zarar')}
              deger={`${p(Math.abs(d.sonuc))}${d.marj !== null ? ` · %${d.marj}` : ''}`}
              renk={d.sonuc >= 0 ? 'text-white' : 'text-rose-300'}
            />
          </div>
          <div className="grid gap-3 lg:grid-cols-2">
            {liste(t('onMuhasebe.rapor.kz.gelirler'), d.gelirler, d.toplam_gelir, 'text-emerald-300', 'mh-kz-gelirler')}
            {liste(t('onMuhasebe.rapor.kz.giderler'), d.giderler, d.toplam_gider, 'text-rose-300', 'mh-kz-giderler')}
          </div>
          <Not testid="mh-kz-not">{t('onMuhasebe.rapor.kz.not')}</Not>
        </div>
      );
    }
    if (alt === 'nakit') {
      const r = veri as NakitAkisi;
      const d = r.para_birimleri.find((x) => x.para_birimi === secili);
      if (!d) return <Bos>{t('onMuhasebe.rapor.veriYok')}</Bos>;
      const satirlar = [...d.gecmis, ...d.tahmin].map((a) => ({
        ay: ayYaz(a.ay, dil) + (a.tahmin ? ' *' : ''),
        giris: a.giris,
        cikis: -a.cikis,
        bakiye: a.bakiye,
        tahmin: !!a.tahmin,
      }));
      return (
        <div className="space-y-3">
          <div className={`${KART} h-80 w-full p-3`} data-testid="mh-grafik-nakit">
            <ResponsiveContainer width="100%" height="100%">
              <ComposedChart data={satirlar}>
                <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.08)" />
                <XAxis dataKey="ay" stroke={EKSEN} fontSize={11} tickLine={false} />
                <YAxis stroke={EKSEN} fontSize={11} tickLine={false} tickFormatter={kisa} width={48} />
                <Tooltip contentStyle={IPUCU} formatter={(v: number) => p(Math.abs(v))} />
                <Legend />
                <Bar dataKey="giris" name={t('onMuhasebe.rapor.giris')} fill="#34d399" radius={[6, 6, 0, 0]}>
                  {satirlar.map((x, i) => (
                    <Cell key={i} fillOpacity={x.tahmin ? 0.45 : 1} />
                  ))}
                </Bar>
                <Bar dataKey="cikis" name={t('onMuhasebe.rapor.cikis')} fill="#fb7185" radius={[0, 0, 6, 6]}>
                  {satirlar.map((x, i) => (
                    <Cell key={i} fillOpacity={x.tahmin ? 0.45 : 1} />
                  ))}
                </Bar>
                <Line dataKey="bakiye" name={t('onMuhasebe.rapor.aySonuBakiye')} stroke="#a78bfa" strokeWidth={2} dot />
              </ComposedChart>
            </ResponsiveContainer>
          </div>
          <p className="text-xs text-muted-foreground">
            {t('onMuhasebe.rapor.buAyKalan', { giris: p(d.bu_ay_kalan.giris), cikis: p(d.bu_ay_kalan.cikis) })}
          </p>
          <div className="overflow-x-auto rounded-xl border border-white/10" data-testid="mh-nakit-beklenen">
            <table className="w-full min-w-[34rem] text-sm">
              <caption className="px-3 pt-2 text-start text-sm font-semibold">{t('onMuhasebe.rapor.beklenen.baslik')}</caption>
              <thead className="text-xs text-muted-foreground">
                <tr>
                  <th className="px-3 py-2 text-start font-medium" scope="col" />
                  <th className="px-3 py-2 text-end font-medium" scope="col">{t('onMuhasebe.rapor.beklenen.tahsilat')}</th>
                  <th className="px-3 py-2 text-end font-medium" scope="col">{t('onMuhasebe.rapor.beklenen.odeme')}</th>
                  <th className="px-3 py-2 text-end font-medium" scope="col">{t('onMuhasebe.rapor.beklenen.tekrar')}</th>
                  <th className="px-3 py-2 text-end font-medium" scope="col">{t('onMuhasebe.rapor.beklenen.bakiye')}</th>
                </tr>
              </thead>
              <tbody>
                {d.beklenen.map((x) => (
                  <tr key={x.gun} className="border-t border-white/5" data-ufuk={x.gun}>
                    <th className="px-3 py-2 text-start font-medium" scope="row">{t('onMuhasebe.rapor.beklenen.ufuk', { gun: x.gun })}</th>
                    <td className="px-3 py-2 text-end tabular-nums text-emerald-300">{p(x.tahsilat)}</td>
                    <td className="px-3 py-2 text-end tabular-nums text-rose-300">{p(x.odeme)}</td>
                    <td className="px-3 py-2 text-end tabular-nums text-muted-foreground">
                      {p(x.tekrar_giris)} / {p(x.tekrar_cikis)}
                    </td>
                    <td className="px-3 py-2 text-end font-semibold tabular-nums">{p(x.bakiye)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {(d.gecikmis.tahsilat > 0 || d.gecikmis.odeme > 0) && (
            <p className="text-xs text-amber-200">{t('onMuhasebe.rapor.beklenen.gecikmis', { tahsilat: p(d.gecikmis.tahsilat), odeme: p(d.gecikmis.odeme) })}</p>
          )}
          <Not>{t('onMuhasebe.rapor.tahminNot')}</Not>
        </div>
      );
    }
    if (alt === 'kdv') {
      const r = veri as KdvRaporu;
      const d = r.para_birimleri.find((x) => x.para_birimi === secili);
      return (
        <div className="space-y-3">
          <Not testid="mh-kdv-not">{t('onMuhasebe.rapor.kdvNot')}</Not>
          {!d ? (
            <Bos>{t('onMuhasebe.rapor.veriYok')}</Bos>
          ) : (
            <>
              <div className="grid gap-2 sm:grid-cols-3">
                <Ozet ad={t('onMuhasebe.rapor.hesaplanan')} deger={p(d.hesaplanan)} />
                <Ozet ad={t('onMuhasebe.rapor.indirilecek')} deger={p(d.indirilecek)} />
                <Ozet ad={d.fark >= 0 ? t('onMuhasebe.rapor.odenecek') : t('onMuhasebe.rapor.devreden')} deger={p(Math.abs(d.fark))} renk={d.fark >= 0 ? 'text-amber-200' : 'text-sky-200'} />
              </div>
              <div className="overflow-x-auto rounded-xl border border-white/10" data-testid="mh-kdv-tablo">
                <table className="min-w-full text-xs">
                  <thead className="bg-white/[0.04] text-muted-foreground">
                    <tr>
                      <th className="px-2 py-1.5 text-start font-medium">{t('onMuhasebe.ortak.ay')}</th>
                      <th className="px-2 py-1.5 text-end font-medium">{t('onMuhasebe.rapor.matrahSatis')}</th>
                      <th className="px-2 py-1.5 text-end font-medium">{t('onMuhasebe.rapor.hesaplanan')}</th>
                      <th className="px-2 py-1.5 text-end font-medium">{t('onMuhasebe.rapor.matrahAlis')}</th>
                      <th className="px-2 py-1.5 text-end font-medium">{t('onMuhasebe.rapor.indirilecek')}</th>
                      <th className="px-2 py-1.5 text-end font-medium">{t('onMuhasebe.rapor.fark')}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {d.aylar.map((a) => (
                      <tr key={a.ay} className="border-t border-white/5">
                        <td className="whitespace-nowrap px-2 py-1">{ayYaz(a.ay, dil)}</td>
                        <td className="px-2 py-1 text-end tabular-nums">{p(a.matrah_satis)}</td>
                        <td className="px-2 py-1 text-end tabular-nums">{p(a.hesaplanan)}</td>
                        <td className="px-2 py-1 text-end tabular-nums">{p(a.matrah_alis)}</td>
                        <td className="px-2 py-1 text-end tabular-nums">{p(a.indirilecek)}</td>
                        <td className={`px-2 py-1 text-end tabular-nums ${a.fark < 0 ? 'text-sky-200' : ''}`}>{p(a.fark)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          )}
        </div>
      );
    }
    const r = veri as Yaslandirma;
    const toplam = r.toplamlar.find((x) => x.para_birimi === secili);
    return (
      <div className="space-y-3" data-testid="mh-yaslandirma">
        {!toplam ? (
          <Bos>{t('onMuhasebe.rapor.veriYok')}</Bos>
        ) : (
          <>
            <KovaTablosu y={{ kovalar: toplam.kovalar, acik: toplam.acik, en_eski_gun: null }} pb={secili} baslik={t('onMuhasebe.ortak.toplam')} />
            <div className="overflow-x-auto rounded-xl border border-white/10">
              <table className="min-w-full text-xs">
                <thead className="bg-white/[0.04] text-muted-foreground">
                  <tr>
                    <th className="px-2 py-1.5 text-start font-medium">{t('onMuhasebe.ortak.cari')}</th>
                    {KOVALAR.map((k) => (
                      <th key={k} className="whitespace-nowrap px-2 py-1.5 text-end font-medium">
                        {t(`onMuhasebe.kova.${k}`)}
                      </th>
                    ))}
                    <th className="px-2 py-1.5 text-end font-medium">{t('onMuhasebe.ortak.toplam')}</th>
                  </tr>
                </thead>
                <tbody>
                  {r.satirlar
                    .filter((x) => x.para_birimi === secili)
                    .map((x) => (
                      <tr key={x.cari_id} className="border-t border-white/5">
                        <td className="px-2 py-1">{x.ad}</td>
                        {KOVALAR.map((k) => (
                          <td key={k} className={`px-2 py-1 text-end tabular-nums ${k === '90_ustu' && x.kovalar[k] ? 'text-rose-300' : ''}`}>
                            {x.kovalar[k] ? p(x.kovalar[k]) : '—'}
                          </td>
                        ))}
                        <td className="px-2 py-1 text-end font-semibold tabular-nums">{p(x.acik)}</td>
                      </tr>
                    ))}
                </tbody>
              </table>
            </div>
          </>
        )}
      </div>
    );
  };

  return (
    <div className="space-y-3" data-testid="mh-raporlar">
      <div className="flex flex-wrap gap-1" role="tablist">
        {ALTLAR.map((a) => (
          <Hap
            key={a}
            secili={alt === a}
            onClick={() => {
              setVeri(null);
              setAlt(a);
            }}
            testid={a}
          >
            {t(`onMuhasebe.rapor.${a}`)}
          </Hap>
        ))}
      </div>
      <div className="flex flex-wrap items-center gap-2">
        {(alt === 'aylik' || alt === 'kdv') && (
          <select className={`${SECIM} w-28`} value={yil} onChange={(e) => setYil(Number(e.target.value))} aria-label={t('onMuhasebe.rapor.yil')}>
            {Array.from({ length: 6 }, (_, i) => Number(bugun().slice(0, 4)) - i).map((y) => (
              <option key={y} value={y}>
                {y}
              </option>
            ))}
          </select>
        )}
        {alt === 'karZarar' && (
          <>
            <input type="date" className={`${GIRDI} w-40`} value={kzBas} onChange={(e) => setKzBas(e.target.value)} aria-label={t('onMuhasebe.ortak.bas')} />
            <input type="date" className={`${GIRDI} w-40`} value={bit} onChange={(e) => setBit(e.target.value)} aria-label={t('onMuhasebe.ortak.bit')} />
          </>
        )}
        {alt === 'kategori' && (
          <>
            <input type="date" className={`${GIRDI} w-40`} value={bas} onChange={(e) => setBas(e.target.value)} aria-label={t('onMuhasebe.ortak.bas')} />
            <input type="date" className={`${GIRDI} w-40`} value={bit} onChange={(e) => setBit(e.target.value)} aria-label={t('onMuhasebe.ortak.bit')} />
            <select className={`${SECIM} w-32`} value={ktur} onChange={(e) => setKtur(e.target.value as KategoriTuru)} aria-label={t('onMuhasebe.rapor.kategoriTuru')}>
              <option value="gider">{t('onMuhasebe.tur.gider')}</option>
              <option value="gelir">{t('onMuhasebe.tur.gelir')}</option>
            </select>
          </>
        )}
        {alt === 'yaslandirma' && (
          <select className={`${SECIM} w-56`} value={yon} onChange={(e) => setYon(e.target.value as 'alacak' | 'borc')} aria-label={t('onMuhasebe.ortak.tur')}>
            <option value="alacak">{t('onMuhasebe.rapor.yon.alacak')}</option>
            <option value="borc">{t('onMuhasebe.rapor.yon.borc')}</option>
          </select>
        )}
        {pbler.length > 1 && (
          <select className={`${SECIM} w-24`} value={secili} onChange={(e) => setPb(e.target.value)} aria-label={t('onMuhasebe.ortak.paraBirimi')} data-testid="mh-rapor-pb">
            {pbler.map((x) => (
              <option key={x} value={x}>
                {x}
              </option>
            ))}
          </select>
        )}
        <span className="flex-1" />
        {alt !== 'yaslandirma' && (
          <Button type="button" size="sm" variant="outline" className={DIS_DUGME} onClick={csv} data-testid="mh-rapor-csv">
            <Download className="h-4 w-4" aria-hidden="true" />
            CSV
          </Button>
        )}
      </div>
      <HataSatiri hata={hata} />
      {icerik()}
    </div>
  );
}

function Ozet({ ad, deger, renk = 'text-white' }: { ad: string; deger: string; renk?: string }) {
  return (
    <div className={`${KART} p-3`}>
      <p className="text-xs text-muted-foreground">{ad}</p>
      <p className={`text-lg font-semibold ${renk}`}>{deger}</p>
    </div>
  );
}
