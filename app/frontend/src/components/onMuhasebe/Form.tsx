import { useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Loader2 } from 'lucide-react';

import { Button } from '@/components/ui/button';
import { Alan, Anahtar, GIRDI, HataSatiri, Not, Pencere, SECIM } from '@/components/onMuhasebe/ortak';
import {
  bugun,
  hataMetni,
  kategoriAdi,
  kurusMetni,
  para,
  type Cari,
  type Hareket,
  type HareketTuru,
  type Meta,
  type MuhasebeApi,
} from '@/lib/onMuhasebe';

/** Girilen metin → kuruş (gösterim önizlemesi; sunucu yeniden ayrıştırır). Türkçe: "1.250,50"; "12,5"; "19.99". */
export function kurusTahmini(metin: string): number | null {
  let s = metin.trim().replace(/\s|₺|TL/gi, '');
  if (!s) return null;
  if (s.includes(',') && s.includes('.')) s = s.lastIndexOf(',') > s.lastIndexOf('.') ? s.replace(/\./g, '').replace(',', '.') : s.replace(/,/g, '');
  else if ((s.match(/,/g) || []).length > 1) s = s.replace(/,/g, '');
  else if (s.includes(',')) s = s.replace(',', '.');
  else if ((s.match(/\./g) || []).length > 1 || /^-?[1-9]\d{0,2}\.\d{3}$/.test(s)) s = s.replace(/\./g, '');
  const d = Number(s);
  return Number.isFinite(d) ? Math.round(d * 100) : null;
}

function kdvDahilden(tutar: number, oran: number): number {
  if (!oran) return 0;
  return Math.floor((Math.abs(tutar * oran) * 2 + (100 + oran)) / (2 * (100 + oran)));
}

const FORM_TURLERI: HareketTuru[] = ['gelir', 'gider', 'tahsilat', 'odeme'];

/** Gelir / gider / tahsilat / ödeme formu (yeni ya da düzenleme). */
export function HareketFormu({
  api,
  meta,
  hareket,
  varsayilanTur = 'gider',
  onKaydet,
  onKapat,
}: {
  api: MuhasebeApi;
  meta: Meta;
  hareket?: Hareket | null;
  varsayilanTur?: HareketTuru;
  onKaydet: (h: Hareket) => void;
  onKapat: () => void;
}) {
  const { t, i18n } = useTranslation();
  const dil = i18n.language || 'tr';
  const duzenle = !!hareket;
  const [tur, setTur] = useState<HareketTuru>(hareket?.tur ?? varsayilanTur);
  const [tarih, setTarih] = useState(hareket?.tarih ?? bugun());
  const [tutar, setTutar] = useState(hareket ? kurusMetni(hareket.tutar) : '');
  const [kdv, setKdv] = useState<string>(hareket?.kdv_orani !== null && hareket?.kdv_orani !== undefined ? String(hareket.kdv_orani) : '');
  const [kdvHaric, setKdvHaric] = useState(false);
  const hesaplar = meta.hesaplar.filter((h) => !h.arsiv || h.id === hareket?.hesap_id);
  const [hesapId, setHesapId] = useState<string>(hareket ? (hareket.hesap_id ? String(hareket.hesap_id) : '') : hesaplar[0] ? String(hesaplar[0].id) : '');
  const [cariId, setCariId] = useState<string>(hareket?.cari_id ? String(hareket.cari_id) : '');
  const [kategoriId, setKategoriId] = useState<string>(hareket?.kategori_id ? String(hareket.kategori_id) : '');
  const [vade, setVade] = useState(hareket?.vade_tarihi ?? '');
  const [aciklama, setAciklama] = useState(hareket?.aciklama ?? '');
  const [belgeNo, setBelgeNo] = useState(hareket?.belge_no ?? '');
  const [etiketler, setEtiketler] = useState((hareket?.etiketler ?? []).join(', '));
  const [cariler, setCariler] = useState<Cari[]>([]);
  const [hata, setHata] = useState<string | null>(null);
  const [kaydediliyor, setKaydediliyor] = useState(false);

  useEffect(() => {
    api
      .cariler()
      .then((r) => setCariler(r.items))
      .catch(() => setCariler([]));
  }, [api]);

  const gelirGider = tur === 'gelir' || tur === 'gider';
  const vadeli = gelirGider && !hesapId;
  const hesap = hesaplar.find((h) => String(h.id) === hesapId);
  const cari = cariler.find((c) => String(c.id) === cariId);
  const pb = hesap?.para_birimi || cari?.para_birimi || meta.ayarlar.para_birimi || 'TRY';
  const kategoriler = meta.kategoriler.filter((k) => k.tur === tur && (!k.arsiv || String(k.id) === kategoriId));
  const onizleme = useMemo(() => {
    const k = kurusTahmini(tutar);
    if (k === null || !gelirGider) return null;
    const oran = kdv ? Number(kdv) : 0;
    if (kdvHaric) {
      const vergi = Math.floor((Math.abs(k * oran) * 2 + 100) / 200);
      return { toplam: k + vergi, kdv: vergi };
    }
    return { toplam: k, kdv: kdvDahilden(k, oran) };
  }, [tutar, kdv, kdvHaric, gelirGider]);

  const kaydet = async () => {
    setHata(null);
    setKaydediliyor(true);
    const govde: Record<string, unknown> = {
      tur,
      tarih,
      tutar,
      hesap_id: hesapId ? Number(hesapId) : null,
      cari_id: cariId ? Number(cariId) : null,
      aciklama,
      belge_no: belgeNo,
      etiketler: etiketler.split(',').map((x) => x.trim()).filter(Boolean),
    };
    if (gelirGider) {
      govde.kdv_orani = kdv === '' ? null : Number(kdv);
      govde.kdv_dahil = !kdvHaric;
      govde.kategori_id = kategoriId ? Number(kategoriId) : null;
      govde.vade_tarihi = vadeli ? vade || null : null;
    }
    try {
      const h = duzenle && hareket ? await api.hareketGuncelle(hareket.id, govde) : await api.hareketEkle(govde);
      onKaydet(h);
    } catch (e) {
      setHata(hataMetni(t, e));
    } finally {
      setKaydediliyor(false);
    }
  };

  return (
    <Pencere baslik={duzenle ? t('onMuhasebe.hareket.baslikDuzenle') : t('onMuhasebe.hareket.baslikYeni')} onKapat={onKapat} testid="mh-form">
      <div className="space-y-3">
        <div className="flex flex-wrap gap-1" role="radiogroup" aria-label={t('onMuhasebe.ortak.tur')}>
          {FORM_TURLERI.map((x) => (
            <button
              key={x}
              type="button"
              role="radio"
              aria-checked={tur === x}
              onClick={() => {
                setTur(x);
                setKategoriId('');
              }}
              className={`rounded-full border px-3 py-1.5 text-xs ${tur === x ? 'border-purple-400/60 bg-purple-500/20 text-white' : 'border-white/10 text-muted-foreground hover:text-white'}`}
              data-testid={`mh-form-tur-${x}`}
            >
              {t(`onMuhasebe.tur.${x}`)}
            </button>
          ))}
        </div>
        <div className="grid gap-3 sm:grid-cols-2">
          <Alan etiket={t('onMuhasebe.ortak.tarih')}>
            <input type="date" className={GIRDI} value={tarih} onChange={(e) => setTarih(e.target.value)} data-testid="mh-form-tarih" />
          </Alan>
          <Alan etiket={`${t('onMuhasebe.ortak.tutar')} (${pb})`} ipucu={onizleme && gelirGider && kdv ? t('onMuhasebe.hareket.kdvHesaplandi', { toplam: para(onizleme.toplam, pb, dil), kdv: para(onizleme.kdv, pb, dil) }) : undefined}>
            <input
              className={GIRDI}
              inputMode="decimal"
              placeholder="0,00"
              value={tutar}
              onChange={(e) => setTutar(e.target.value)}
              data-testid="mh-form-tutar"
            />
          </Alan>
          {gelirGider && (
            <>
              <Alan etiket={t('onMuhasebe.ortak.kdvOrani')}>
                <select className={SECIM} value={kdv} onChange={(e) => setKdv(e.target.value)} data-testid="mh-form-kdv">
                  <option value="">{t('onMuhasebe.ortak.kdvYok')}</option>
                  {meta.sabitler.kdv_oranlari.map((o) => (
                    <option key={o} value={o}>
                      %{o}
                    </option>
                  ))}
                </select>
              </Alan>
              <div className="flex items-end pb-2">
                <Anahtar acik={kdvHaric} onDegis={setKdvHaric} etiket={t('onMuhasebe.hareket.kdvHaric')} testid="mh-form-kdv-haric" />
              </div>
            </>
          )}
          <Alan etiket={t('onMuhasebe.ortak.hesap')}>
            <select className={SECIM} value={hesapId} onChange={(e) => setHesapId(e.target.value)} data-testid="mh-form-hesap">
              {gelirGider && <option value="">{t('onMuhasebe.hareket.hesapsiz')}</option>}
              {!gelirGider && !hesapId && <option value="">—</option>}
              {hesaplar.map((h) => (
                <option key={h.id} value={h.id}>
                  {h.ad} ({h.para_birimi})
                </option>
              ))}
            </select>
          </Alan>
          <Alan etiket={t('onMuhasebe.ortak.cari')}>
            <select className={SECIM} value={cariId} onChange={(e) => setCariId(e.target.value)} data-testid="mh-form-cari">
              <option value="">{gelirGider && hesapId ? t('onMuhasebe.ortak.yok') : '—'}</option>
              {cariler.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.ad} ({c.para_birimi})
                </option>
              ))}
            </select>
          </Alan>
          {gelirGider && (
            <Alan etiket={t('onMuhasebe.ortak.kategori')}>
              <select className={SECIM} value={kategoriId} onChange={(e) => setKategoriId(e.target.value)} data-testid="mh-form-kategori">
                <option value="">{t('onMuhasebe.kategorisiz')}</option>
                {kategoriler.map((k) => (
                  <option key={k.id} value={k.id}>
                    {kategoriAdi(t, k)}
                  </option>
                ))}
              </select>
            </Alan>
          )}
          {vadeli && (
            <Alan etiket={t('onMuhasebe.ortak.vade')}>
              <input type="date" className={GIRDI} value={vade} min={tarih} onChange={(e) => setVade(e.target.value)} data-testid="mh-form-vade" />
            </Alan>
          )}
          <Alan etiket={t('onMuhasebe.ortak.aciklama')} className="sm:col-span-2">
            <input className={GIRDI} maxLength={300} value={aciklama} onChange={(e) => setAciklama(e.target.value)} data-testid="mh-form-aciklama" />
          </Alan>
          <Alan etiket={t('onMuhasebe.ortak.belgeNo')}>
            <input className={GIRDI} maxLength={60} value={belgeNo} onChange={(e) => setBelgeNo(e.target.value)} />
          </Alan>
          <Alan etiket={t('onMuhasebe.ortak.etiketler')} ipucu={t('onMuhasebe.ortak.etiketIpucu')}>
            <input className={GIRDI} value={etiketler} onChange={(e) => setEtiketler(e.target.value)} data-testid="mh-form-etiketler" />
          </Alan>
        </div>
        {vadeli && <Not>{t('onMuhasebe.hareket.vadeliNot')}</Not>}
        <HataSatiri hata={hata} />
        <div className="flex flex-wrap justify-end gap-2">
          <Button type="button" variant="outline" className="!bg-transparent border-white/20" onClick={onKapat}>
            {t('onMuhasebe.ortak.iptal')}
          </Button>
          <Button type="button" onClick={() => void kaydet()} disabled={kaydediliyor || !tutar.trim()} data-testid="mh-form-kaydet">
            {kaydediliyor && <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />}
            {t('onMuhasebe.ortak.kaydet')}
          </Button>
        </div>
      </div>
    </Pencere>
  );
}

/** Hesaplar arası virman. */
export function VirmanFormu({ api, meta, onKaydet, onKapat }: { api: MuhasebeApi; meta: Meta; onKaydet: (h: Hareket) => void; onKapat: () => void }) {
  const { t } = useTranslation();
  const hesaplar = meta.hesaplar.filter((h) => !h.arsiv);
  const [kaynak, setKaynak] = useState(hesaplar[0] ? String(hesaplar[0].id) : '');
  const [hedef, setHedef] = useState(hesaplar[1] ? String(hesaplar[1].id) : '');
  const [tutar, setTutar] = useState('');
  const [hedefTutar, setHedefTutar] = useState('');
  const [tarih, setTarih] = useState(bugun());
  const [aciklama, setAciklama] = useState('');
  const [hata, setHata] = useState<string | null>(null);
  const [kaydediliyor, setKaydediliyor] = useState(false);
  const k = hesaplar.find((h) => String(h.id) === kaynak);
  const h = hesaplar.find((x) => String(x.id) === hedef);
  const farkli = !!k && !!h && k.para_birimi !== h.para_birimi;

  const kaydet = async () => {
    setHata(null);
    setKaydediliyor(true);
    try {
      onKaydet(
        await api.virman({
          kaynak_hesap_id: kaynak ? Number(kaynak) : null,
          hedef_hesap_id: hedef ? Number(hedef) : null,
          tutar,
          hedef_tutar: farkli ? hedefTutar : null,
          tarih,
          aciklama,
        })
      );
    } catch (e) {
      setHata(hataMetni(t, e));
    } finally {
      setKaydediliyor(false);
    }
  };

  return (
    <Pencere baslik={t('onMuhasebe.hareket.virmanBaslik')} onKapat={onKapat} testid="mh-virman">
      <div className="space-y-3">
        <div className="grid gap-3 sm:grid-cols-2">
          <Alan etiket={t('onMuhasebe.hareket.kaynakHesap')}>
            <select className={SECIM} value={kaynak} onChange={(e) => setKaynak(e.target.value)} data-testid="mh-virman-kaynak">
              {hesaplar.map((x) => (
                <option key={x.id} value={x.id}>
                  {x.ad} ({x.para_birimi})
                </option>
              ))}
            </select>
          </Alan>
          <Alan etiket={t('onMuhasebe.hareket.hedefHesap')}>
            <select className={SECIM} value={hedef} onChange={(e) => setHedef(e.target.value)} data-testid="mh-virman-hedef">
              <option value="">—</option>
              {hesaplar.map((x) => (
                <option key={x.id} value={x.id} disabled={String(x.id) === kaynak}>
                  {x.ad} ({x.para_birimi})
                </option>
              ))}
            </select>
          </Alan>
          <Alan etiket={`${t('onMuhasebe.ortak.tutar')}${k ? ` (${k.para_birimi})` : ''}`}>
            <input className={GIRDI} inputMode="decimal" placeholder="0,00" value={tutar} onChange={(e) => setTutar(e.target.value)} data-testid="mh-virman-tutar" />
          </Alan>
          {farkli && (
            <Alan etiket={`${t('onMuhasebe.hareket.hedefTutar')} (${h?.para_birimi})`} ipucu={t('onMuhasebe.hareket.hedefTutarIpucu')}>
              <input className={GIRDI} inputMode="decimal" value={hedefTutar} onChange={(e) => setHedefTutar(e.target.value)} data-testid="mh-virman-hedef-tutar" />
            </Alan>
          )}
          <Alan etiket={t('onMuhasebe.ortak.tarih')}>
            <input type="date" className={GIRDI} value={tarih} onChange={(e) => setTarih(e.target.value)} />
          </Alan>
          <Alan etiket={t('onMuhasebe.ortak.aciklama')} className="sm:col-span-2">
            <input className={GIRDI} maxLength={300} value={aciklama} onChange={(e) => setAciklama(e.target.value)} />
          </Alan>
        </div>
        <Not>{t('onMuhasebe.hareket.virmanNot')}</Not>
        <HataSatiri hata={hata} />
        <div className="flex flex-wrap justify-end gap-2">
          <Button type="button" variant="outline" className="!bg-transparent border-white/20" onClick={onKapat}>
            {t('onMuhasebe.ortak.iptal')}
          </Button>
          <Button type="button" onClick={() => void kaydet()} disabled={kaydediliyor || !tutar.trim() || !hedef} data-testid="mh-virman-kaydet">
            {kaydediliyor && <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />}
            {t('onMuhasebe.ortak.kaydet')}
          </Button>
        </div>
      </div>
    </Pencere>
  );
}
