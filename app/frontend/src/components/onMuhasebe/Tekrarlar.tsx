import { useCallback, useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Loader2, Pause, Pencil, Play, Plus, Trash2 } from 'lucide-react';

import { Button } from '@/components/ui/button';
import { Alan, Anahtar, Bos, DIS_DUGME, GIRDI, HataSatiri, KART, Not, Pencere, Rozet, SECIM, Yukleniyor } from '@/components/onMuhasebe/ortak';
import { bugun, gunYaz, hataMetni, kategoriAdi, kurusMetni, para, TUR_RENGI, type BolumProps, type Cari, type KategoriTuru, type Periyot, type Tekrar } from '@/lib/onMuhasebe';

/** Faz 6M — tekrarlayan gelir/gider (aylık kira vb.): vadesi gelen dönem kayda çevrilir (tekil). */
export default function Tekrarlar({ api, meta, yenile, surum }: BolumProps) {
  const { t, i18n } = useTranslation();
  const dil = i18n.language || 'tr';
  const salt = meta.salt_okunur;
  const [items, setItems] = useState<Tekrar[] | null>(null);
  const [hata, setHata] = useState<string | null>(null);
  const [form, setForm] = useState<Tekrar | 'yeni' | null>(null);

  const yukle = useCallback(async () => {
    setHata(null);
    try {
      setItems((await api.tekrarlar()).items);
    } catch (e) {
      setHata(hataMetni(t, e));
    }
  }, [api, t]);

  useEffect(() => {
    void yukle();
  }, [yukle, surum]);

  const durdur = async (x: Tekrar) => {
    try {
      await api.tekrarGuncelle(x.id, { aktif: !x.aktif });
      void yukle();
    } catch (e) {
      setHata(hataMetni(t, e));
    }
  };

  const sil = async (x: Tekrar) => {
    if (!window.confirm(t('onMuhasebe.tekrar.silOnay'))) return;
    try {
      await api.tekrarSil(x.id);
      void yukle();
    } catch (e) {
      setHata(hataMetni(t, e));
    }
  };

  const kategoriler = Object.fromEntries(meta.kategoriler.map((k) => [k.id, k]));
  const hesaplar = Object.fromEntries(meta.hesaplar.map((h) => [h.id, h]));
  return (
    <div className="space-y-3" data-testid="mh-tekrarlar">
      {!salt && (
        <Button type="button" size="sm" className="gap-1.5" onClick={() => setForm('yeni')} disabled={!meta.hesaplar.length} data-testid="mh-tekrar-yeni">
          <Plus className="h-4 w-4" aria-hidden="true" />
          {t('onMuhasebe.tekrar.yeni')}
        </Button>
      )}
      <Not>{t('onMuhasebe.tekrar.not')}</Not>
      <HataSatiri hata={hata} />
      {!items ? (
        <Yukleniyor />
      ) : !items.length ? (
        <Bos>{t('onMuhasebe.tekrar.bos')}</Bos>
      ) : (
        <ul className="grid gap-3 sm:grid-cols-2" data-testid="mh-tekrar-liste">
          {items.map((x) => (
            <li key={x.id} className={`${KART} space-y-1.5 p-4 ${x.aktif ? '' : 'opacity-60'}`} data-testid="mh-tekrar">
              <div className="flex items-start justify-between gap-2">
                <div className="min-w-0">
                  <p className="truncate font-semibold">{x.aciklama}</p>
                  <p className="text-xs text-muted-foreground">
                    {t(`onMuhasebe.periyot.${x.periyot}`)}
                    {x.kategori_id && kategoriler[x.kategori_id] ? ` · ${kategoriAdi(t, kategoriler[x.kategori_id])}` : ''}
                    {x.hesap_id && hesaplar[x.hesap_id] ? ` · ${hesaplar[x.hesap_id].ad}` : ''}
                  </p>
                </div>
                <Rozet renk={TUR_RENGI[x.tur]}>{t(`onMuhasebe.tur.${x.tur}`)}</Rozet>
              </div>
              <p className="text-lg font-semibold">{para(x.tutar, x.para_birimi, dil)}</p>
              <p className="text-xs text-muted-foreground">
                {x.sonraki ? t('onMuhasebe.tekrar.sonrakiMetin', { tarih: gunYaz(x.sonraki, dil) }) : t('onMuhasebe.tekrar.bitti')}
                {x.son_uretilen ? ` · ${t('onMuhasebe.tekrar.sonUretilenMetin', { tarih: gunYaz(x.son_uretilen, dil) })}` : ''}
                {!x.aktif ? ` · ${t('onMuhasebe.tekrar.durduruldu')}` : ''}
              </p>
              {!salt && (
                <div className="flex flex-wrap gap-1">
                  <Button type="button" size="sm" variant="ghost" className="h-8 gap-1 px-2" onClick={() => setForm(x)}>
                    <Pencil className="h-3.5 w-3.5" aria-hidden="true" />
                    {t('onMuhasebe.ortak.duzenle')}
                  </Button>
                  <Button type="button" size="sm" variant="ghost" className="h-8 gap-1 px-2" onClick={() => void durdur(x)}>
                    {x.aktif ? <Pause className="h-3.5 w-3.5" aria-hidden="true" /> : <Play className="h-3.5 w-3.5" aria-hidden="true" />}
                    {x.aktif ? t('onMuhasebe.tekrar.durdur') : t('onMuhasebe.tekrar.devam')}
                  </Button>
                  <Button type="button" size="sm" variant="ghost" className="h-8 gap-1 px-2 text-rose-200" onClick={() => void sil(x)}>
                    <Trash2 className="h-3.5 w-3.5" aria-hidden="true" />
                    {t('onMuhasebe.ortak.sil')}
                  </Button>
                </div>
              )}
            </li>
          ))}
        </ul>
      )}
      {form && (
        <TekrarFormu
          api={api}
          meta={meta}
          tekrar={form === 'yeni' ? null : form}
          onKaydet={() => {
            setForm(null);
            yenile();
          }}
          onKapat={() => setForm(null)}
        />
      )}
    </div>
  );
}

function TekrarFormu({
  api,
  meta,
  tekrar,
  onKaydet,
  onKapat,
}: {
  api: BolumProps['api'];
  meta: BolumProps['meta'];
  tekrar: Tekrar | null;
  onKaydet: () => void;
  onKapat: () => void;
}) {
  const { t } = useTranslation();
  const hesaplar = meta.hesaplar.filter((h) => !h.arsiv || h.id === tekrar?.hesap_id);
  const [tur, setTur] = useState<KategoriTuru>(tekrar?.tur ?? 'gider');
  const [aciklama, setAciklama] = useState(tekrar?.aciklama ?? '');
  const [tutar, setTutar] = useState(tekrar ? kurusMetni(tekrar.tutar) : '');
  const [kdv, setKdv] = useState(tekrar?.kdv_orani !== null && tekrar?.kdv_orani !== undefined ? String(tekrar.kdv_orani) : '');
  const [periyot, setPeriyot] = useState<Periyot>(tekrar?.periyot ?? 'aylik');
  const [baslangic, setBaslangic] = useState(tekrar?.baslangic ?? bugun());
  const [bitis, setBitis] = useState(tekrar?.bitis ?? '');
  const [hesapId, setHesapId] = useState(tekrar ? (tekrar.hesap_id ? String(tekrar.hesap_id) : '') : hesaplar[0] ? String(hesaplar[0].id) : '');
  const [cariId, setCariId] = useState(tekrar?.cari_id ? String(tekrar.cari_id) : '');
  const [kategoriId, setKategoriId] = useState(tekrar?.kategori_id ? String(tekrar.kategori_id) : '');
  const [gecmisi, setGecmisi] = useState(false);
  const [cariler, setCariler] = useState<Cari[]>([]);
  const [hata, setHata] = useState<string | null>(null);
  const [kaydediliyor, setKaydediliyor] = useState(false);

  useEffect(() => {
    api
      .cariler()
      .then((r) => setCariler(r.items))
      .catch(() => setCariler([]));
  }, [api]);

  const kaydet = async () => {
    setHata(null);
    setKaydediliyor(true);
    const g: Record<string, unknown> = {
      tur,
      aciklama,
      tutar,
      kdv_orani: kdv === '' ? null : Number(kdv),
      periyot,
      baslangic,
      bitis: bitis || null,
      hesap_id: hesapId ? Number(hesapId) : null,
      cari_id: cariId ? Number(cariId) : null,
      kategori_id: kategoriId ? Number(kategoriId) : null,
    };
    if (!tekrar) g.gecmisi_de = gecmisi;
    try {
      if (tekrar) await api.tekrarGuncelle(tekrar.id, g);
      else await api.tekrarEkle(g);
      onKaydet();
    } catch (e) {
      setHata(hataMetni(t, e));
    } finally {
      setKaydediliyor(false);
    }
  };

  return (
    <Pencere baslik={tekrar ? t('onMuhasebe.tekrar.duzenle') : t('onMuhasebe.tekrar.yeni')} onKapat={onKapat} testid="mh-tekrar-formu">
      <div className="space-y-3">
        <div className="grid gap-3 sm:grid-cols-2">
          <Alan etiket={t('onMuhasebe.ortak.tur')}>
            <select
              className={SECIM}
              value={tur}
              onChange={(e) => {
                setTur(e.target.value as KategoriTuru);
                setKategoriId('');
              }}
              data-testid="mh-tekrar-tur"
            >
              <option value="gider">{t('onMuhasebe.tur.gider')}</option>
              <option value="gelir">{t('onMuhasebe.tur.gelir')}</option>
            </select>
          </Alan>
          <Alan etiket={t('onMuhasebe.ortak.aciklama')}>
            <input className={GIRDI} maxLength={300} value={aciklama} onChange={(e) => setAciklama(e.target.value)} data-testid="mh-tekrar-aciklama" />
          </Alan>
          <Alan etiket={t('onMuhasebe.ortak.tutar')}>
            <input className={GIRDI} inputMode="decimal" placeholder="0,00" value={tutar} onChange={(e) => setTutar(e.target.value)} data-testid="mh-tekrar-tutar" />
          </Alan>
          <Alan etiket={t('onMuhasebe.ortak.kdvOrani')}>
            <select className={SECIM} value={kdv} onChange={(e) => setKdv(e.target.value)}>
              <option value="">{t('onMuhasebe.ortak.kdvYok')}</option>
              {meta.sabitler.kdv_oranlari.map((o) => (
                <option key={o} value={o}>
                  %{o}
                </option>
              ))}
            </select>
          </Alan>
          <Alan etiket={t('onMuhasebe.tekrar.periyot')}>
            <select className={SECIM} value={periyot} onChange={(e) => setPeriyot(e.target.value as Periyot)} data-testid="mh-tekrar-periyot">
              {meta.sabitler.periyotlar.map((p) => (
                <option key={p} value={p}>
                  {t(`onMuhasebe.periyot.${p}`)}
                </option>
              ))}
            </select>
          </Alan>
          <Alan etiket={t('onMuhasebe.ortak.kategori')}>
            <select className={SECIM} value={kategoriId} onChange={(e) => setKategoriId(e.target.value)}>
              <option value="">{t('onMuhasebe.kategorisiz')}</option>
              {meta.kategoriler
                .filter((k) => k.tur === tur && !k.arsiv)
                .map((k) => (
                  <option key={k.id} value={k.id}>
                    {kategoriAdi(t, k)}
                  </option>
                ))}
            </select>
          </Alan>
          <Alan etiket={t('onMuhasebe.tekrar.baslangic')}>
            <input type="date" className={GIRDI} value={baslangic} onChange={(e) => setBaslangic(e.target.value)} data-testid="mh-tekrar-baslangic" />
          </Alan>
          <Alan etiket={t('onMuhasebe.tekrar.bitis')}>
            <input type="date" className={GIRDI} value={bitis} min={baslangic} onChange={(e) => setBitis(e.target.value)} />
          </Alan>
          <Alan etiket={t('onMuhasebe.ortak.hesap')}>
            <select className={SECIM} value={hesapId} onChange={(e) => setHesapId(e.target.value)}>
              <option value="">{t('onMuhasebe.hareket.hesapsiz')}</option>
              {hesaplar.map((h) => (
                <option key={h.id} value={h.id}>
                  {h.ad} ({h.para_birimi})
                </option>
              ))}
            </select>
          </Alan>
          <Alan etiket={t('onMuhasebe.ortak.cari')}>
            <select className={SECIM} value={cariId} onChange={(e) => setCariId(e.target.value)}>
              <option value="">—</option>
              {cariler.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.ad} ({c.para_birimi})
                </option>
              ))}
            </select>
          </Alan>
        </div>
        {!tekrar && <Anahtar acik={gecmisi} onDegis={setGecmisi} etiket={t('onMuhasebe.tekrar.gecmisiDe')} />}
        <HataSatiri hata={hata} />
        <div className="flex flex-wrap justify-end gap-2">
          <Button type="button" variant="outline" className={DIS_DUGME} onClick={onKapat}>
            {t('onMuhasebe.ortak.iptal')}
          </Button>
          <Button type="button" onClick={() => void kaydet()} disabled={kaydediliyor || !aciklama.trim() || !tutar.trim()} data-testid="mh-tekrar-kaydet">
            {kaydediliyor && <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />}
            {t('onMuhasebe.ortak.kaydet')}
          </Button>
        </div>
      </div>
    </Pencere>
  );
}
