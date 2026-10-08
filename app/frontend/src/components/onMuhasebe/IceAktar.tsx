import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { CheckCircle2, Loader2 } from 'lucide-react';

import { Button } from '@/components/ui/button';
import { Alan, DIS_DUGME, HataSatiri, METIN_ALANI, Not, Pencere, SECIM } from '@/components/onMuhasebe/ortak';
import { gunYaz, hataMetni, kategoriAdi, para, type CsvOnizleme, type IceAktarSonucu, type Meta, type MuhasebeApi } from '@/lib/onMuhasebe';

const ALANLAR = ['tarih', 'aciklama', 'tutar', 'giris', 'cikis', 'belge_no'] as const;
type EslemeAlani = (typeof ALANLAR)[number];

/**
 * Faz 6M — banka ekstresi CSV içe aktarma: dosya ya da yapıştır → önizle (başlıklardan tahmini sütun eşlemesi,
 * son eşleme hatırlanır) → tarih biçimi, ondalık ayırıcı, hesap, kategoriler → dene (yazmadan) → içe aktar.
 * Artı tutar gelir, eksi gider; aynı satır ikinci yüklemede atlanır; hatalı satırlar numarasıyla listelenir.
 */
export default function IceAktar({ api, meta, onBitti, onKapat }: { api: MuhasebeApi; meta: Meta; onBitti: () => void; onKapat: () => void }) {
  const { t, i18n } = useTranslation();
  const dil = i18n.language || 'tr';
  const [csv, setCsv] = useState('');
  const [onizleme, setOnizleme] = useState<CsvOnizleme | null>(null);
  const [esleme, setEsleme] = useState<Record<EslemeAlani, number | null>>({ tarih: null, aciklama: null, tutar: null, giris: null, cikis: null, belge_no: null });
  const [ayri, setAyri] = useState(false);
  const [tarihBicimi, setTarihBicimi] = useState('otomatik');
  const [ondalik, setOndalik] = useState('otomatik');
  const hesaplar = meta.hesaplar.filter((h) => !h.arsiv);
  const [hesapId, setHesapId] = useState(hesaplar.find((h) => h.tur === 'banka')?.id ?? hesaplar[0]?.id ?? 0);
  const [gelirK, setGelirK] = useState('');
  const [giderK, setGiderK] = useState('');
  const [sonuc, setSonuc] = useState<IceAktarSonucu | null>(null);
  const [hata, setHata] = useState<string | null>(null);
  const [calisiyor, setCalisiyor] = useState(false);
  const hesap = hesaplar.find((h) => h.id === hesapId);

  const dosyaOku = async (f: File | undefined) => {
    if (!f) return;
    setCsv(await f.text());
    setOnizleme(null);
    setSonuc(null);
  };

  const onizle = async () => {
    setHata(null);
    setSonuc(null);
    setCalisiyor(true);
    try {
      const o = await api.csvOnizle(csv);
      setOnizleme(o);
      const e = { tarih: null, aciklama: null, tutar: null, giris: null, cikis: null, belge_no: null, ...o.esleme } as Record<EslemeAlani, number | null>;
      setEsleme(e);
      setAyri(e.tutar === null && (e.giris !== null || e.cikis !== null));
      setTarihBicimi(o.tarih_bicimi || 'otomatik');
      setOndalik(o.ondalik || 'otomatik');
    } catch (e) {
      setHata(hataMetni(t, e));
    } finally {
      setCalisiyor(false);
    }
  };

  const gonder = async (dene: boolean) => {
    setHata(null);
    setCalisiyor(true);
    try {
      const r = await api.iceAktar({
        csv,
        hesap_id: hesapId,
        esleme: ayri ? { ...esleme, tutar: null } : { ...esleme, giris: null, cikis: null },
        tarih_bicimi: tarihBicimi,
        ondalik,
        gelir_kategori_id: gelirK ? Number(gelirK) : null,
        gider_kategori_id: giderK ? Number(giderK) : null,
        dene,
      });
      setSonuc(r);
    } catch (e) {
      setHata(hataMetni(t, e));
    } finally {
      setCalisiyor(false);
    }
  };

  const sutunSecimi = (alan: EslemeAlani) => (
    <select
      className={SECIM}
      value={esleme[alan] ?? ''}
      onChange={(e) => setEsleme((x) => ({ ...x, [alan]: e.target.value === '' ? null : Number(e.target.value) }))}
      data-testid={`mh-esleme-${alan}`}
    >
      <option value="">{t('onMuhasebe.iceAktar.sutunYok')}</option>
      {(onizleme?.basliklar || []).map((b, i) => (
        <option key={i} value={i}>
          {b || `#${i + 1}`}
        </option>
      ))}
    </select>
  );

  return (
    <Pencere baslik={t('onMuhasebe.iceAktar.baslik')} onKapat={onKapat} genis testid="mh-ice-aktar">
      <div className="space-y-3">
        <p className="text-sm text-muted-foreground">{t('onMuhasebe.iceAktar.aciklama', { enCok: meta.sabitler.en_cok_csv })}</p>
        <div className="flex flex-wrap items-center gap-2">
          <label className="inline-flex cursor-pointer items-center gap-2 rounded-md border border-white/20 px-3 py-2 text-sm hover:bg-white/5">
            {t('onMuhasebe.iceAktar.dosya')}
            <input type="file" accept=".csv,text/csv,text/plain" className="sr-only" onChange={(e) => void dosyaOku(e.target.files?.[0])} data-testid="mh-csv-dosya" />
          </label>
          <span className="text-xs text-muted-foreground">{t('onMuhasebe.iceAktar.yaDaYapistir')}</span>
        </div>
        <textarea
          className={`${METIN_ALANI} font-mono text-xs`}
          rows={5}
          value={csv}
          onChange={(e) => {
            setCsv(e.target.value);
            setOnizleme(null);
            setSonuc(null);
          }}
          placeholder={t('onMuhasebe.iceAktar.ornek')}
          data-testid="mh-csv-metin"
        />
        <Button type="button" variant="outline" className={DIS_DUGME} disabled={!csv.trim() || calisiyor} onClick={() => void onizle()} data-testid="mh-csv-onizle">
          {calisiyor && !onizleme && <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />}
          {t('onMuhasebe.iceAktar.onizle')}
        </Button>
        {onizleme && (
          <>
            <div className="overflow-x-auto rounded-xl border border-white/10">
              <table className="min-w-full text-xs">
                <thead className="bg-white/[0.04]">
                  <tr>
                    {onizleme.basliklar.map((b, i) => (
                      <th key={i} className="whitespace-nowrap px-2 py-1.5 text-start font-medium">
                        {b}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {onizleme.ornek.slice(0, 5).map((s, i) => (
                    <tr key={i} className="border-t border-white/5">
                      {s.map((h, j) => (
                        <td key={j} className="whitespace-nowrap px-2 py-1">
                          {h}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <p className="text-xs text-muted-foreground">{t('onMuhasebe.iceAktar.satirSayisi', { sayi: onizleme.satir_sayisi })}</p>
            <div className="flex flex-wrap gap-3 text-sm">
              <label className="flex items-center gap-1.5">
                <input type="radio" checked={!ayri} onChange={() => setAyri(false)} className="accent-purple-500" />
                {t('onMuhasebe.iceAktar.tekTutar')}
              </label>
              <label className="flex items-center gap-1.5">
                <input type="radio" checked={ayri} onChange={() => setAyri(true)} className="accent-purple-500" data-testid="mh-csv-ayri" />
                {t('onMuhasebe.iceAktar.ayriSutun')}
              </label>
            </div>
            <div className="grid gap-3 sm:grid-cols-3">
              <Alan etiket={t('onMuhasebe.iceAktar.alan.tarih')}>{sutunSecimi('tarih')}</Alan>
              <Alan etiket={t('onMuhasebe.iceAktar.alan.aciklama')}>{sutunSecimi('aciklama')}</Alan>
              {ayri ? (
                <>
                  <Alan etiket={t('onMuhasebe.iceAktar.alan.giris')}>{sutunSecimi('giris')}</Alan>
                  <Alan etiket={t('onMuhasebe.iceAktar.alan.cikis')}>{sutunSecimi('cikis')}</Alan>
                </>
              ) : (
                <Alan etiket={t('onMuhasebe.iceAktar.alan.tutar')}>{sutunSecimi('tutar')}</Alan>
              )}
              <Alan etiket={t('onMuhasebe.iceAktar.alan.belge_no')}>{sutunSecimi('belge_no')}</Alan>
              <Alan etiket={t('onMuhasebe.iceAktar.tarihBicimi')}>
                <select className={SECIM} value={tarihBicimi} onChange={(e) => setTarihBicimi(e.target.value)} data-testid="mh-csv-tarih-bicimi">
                  {meta.sabitler.tarih_bicimleri.map((b) => (
                    <option key={b} value={b}>
                      {t(`onMuhasebe.iceAktar.bicim.${b}`, { defaultValue: b })}
                    </option>
                  ))}
                </select>
              </Alan>
              <Alan etiket={t('onMuhasebe.iceAktar.ondalik')}>
                <select className={SECIM} value={ondalik} onChange={(e) => setOndalik(e.target.value)} data-testid="mh-csv-ondalik">
                  <option value="otomatik">{t('onMuhasebe.iceAktar.ondalikSecenek.otomatik')}</option>
                  <option value=",">{t('onMuhasebe.iceAktar.ondalikSecenek.virgul')}</option>
                  <option value=".">{t('onMuhasebe.iceAktar.ondalikSecenek.nokta')}</option>
                </select>
              </Alan>
              <Alan etiket={t('onMuhasebe.ortak.hesap')}>
                <select className={SECIM} value={hesapId} onChange={(e) => setHesapId(Number(e.target.value))} data-testid="mh-csv-hesap">
                  {hesaplar.map((h) => (
                    <option key={h.id} value={h.id}>
                      {h.ad} ({h.para_birimi})
                    </option>
                  ))}
                </select>
              </Alan>
              <Alan etiket={t('onMuhasebe.iceAktar.gelirKategori')}>
                <select className={SECIM} value={gelirK} onChange={(e) => setGelirK(e.target.value)}>
                  <option value="">{t('onMuhasebe.kategorisiz')}</option>
                  {meta.kategoriler
                    .filter((k) => k.tur === 'gelir' && !k.arsiv)
                    .map((k) => (
                      <option key={k.id} value={k.id}>
                        {kategoriAdi(t, k)}
                      </option>
                    ))}
                </select>
              </Alan>
              <Alan etiket={t('onMuhasebe.iceAktar.giderKategori')}>
                <select className={SECIM} value={giderK} onChange={(e) => setGiderK(e.target.value)}>
                  <option value="">{t('onMuhasebe.kategorisiz')}</option>
                  {meta.kategoriler
                    .filter((k) => k.tur === 'gider' && !k.arsiv)
                    .map((k) => (
                      <option key={k.id} value={k.id}>
                        {kategoriAdi(t, k)}
                      </option>
                    ))}
                </select>
              </Alan>
            </div>
            <Not>{t('onMuhasebe.iceAktar.not')}</Not>
          </>
        )}
        {sonuc && (
          <div className="space-y-2 rounded-xl border border-white/10 p-3 text-sm" data-testid="mh-csv-sonuc" data-dene={sonuc.dene ? '1' : '0'}>
            <p className="flex items-center gap-2 font-medium">
              <CheckCircle2 className="h-4 w-4 text-emerald-300" aria-hidden="true" />
              {t(sonuc.dene ? 'onMuhasebe.iceAktar.denemeSonuc' : 'onMuhasebe.iceAktar.sonuc', { eklenen: sonuc.eklenen, tekrar: sonuc.tekrar, hata: sonuc.hata_sayisi })}
            </p>
            {sonuc.dene && sonuc.onizleme.length > 0 && (
              <ul className="space-y-0.5 text-xs text-muted-foreground">
                {sonuc.onizleme.map((x) => (
                  <li key={x.satir}>
                    {gunYaz(x.tarih, dil)} · {t(`onMuhasebe.tur.${x.tur}`)} · {para(x.tutar, hesap?.para_birimi || 'TRY', dil)} · {x.aciklama}
                  </li>
                ))}
              </ul>
            )}
            {sonuc.hatalar.length > 0 && (
              <ul className="space-y-0.5 text-xs text-amber-200" data-testid="mh-csv-hatalar">
                {sonuc.hatalar.map((x) => (
                  <li key={x.satir}>
                    {t('onMuhasebe.iceAktar.hataSatiri', { satir: x.satir, neden: t(`onMuhasebe.hata.${x.kod}`, { defaultValue: x.kod }) })}
                  </li>
                ))}
              </ul>
            )}
          </div>
        )}
        <HataSatiri hata={hata} />
        <div className="flex flex-wrap justify-end gap-2">
          {sonuc && !sonuc.dene ? (
            <Button type="button" onClick={onBitti} data-testid="mh-csv-bitti">
              {t('onMuhasebe.ortak.kapat')}
            </Button>
          ) : (
            <>
              <Button type="button" variant="outline" className={DIS_DUGME} disabled={!onizleme || calisiyor || !hesapId} onClick={() => void gonder(true)} data-testid="mh-csv-dene">
                {t('onMuhasebe.iceAktar.dene')}
              </Button>
              <Button type="button" disabled={!onizleme || calisiyor || !hesapId} onClick={() => void gonder(false)} data-testid="mh-csv-aktar">
                {calisiyor && <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />}
                {t('onMuhasebe.iceAktar.aktar')}
              </Button>
            </>
          )}
        </div>
      </div>
    </Pencere>
  );
}
