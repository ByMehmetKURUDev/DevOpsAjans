import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Archive, Loader2, Plus, RefreshCw, RotateCcw, Save, Trash2 } from 'lucide-react';

import { Button } from '@/components/ui/button';
import { Alan, Anahtar, DIS_DUGME, GIRDI, HataSatiri, KART, Not, Rozet, SECIM } from '@/components/onMuhasebe/ortak';
import { bugun, hataMetni, kategoriAdi, type AktarimAyari, type BolumProps, type Kategori, type KategoriTuru } from '@/lib/onMuhasebe';

const AKTARIM_ALANLARI: Record<string, string[]> = {
  odeme: ['banka_hesap_id', 'nakit_hesap_id', 'cevrimici_hesap_id'],
  pos: ['nakit_hesap_id', 'kart_hesap_id', 'havale_hesap_id'],
  hukuk: ['hesap_id'],
  saha: ['hesap_id'],
};
const KAYNAK_MODULU: Record<string, string> = { pos: 'stok_pos', hukuk: 'hukuk_burosu', saha: 'saha_servisi' };

const ALAN_IPUCU: Record<string, string> = { havale_hesap_id: 'havaleIpucu', cevrimici_hesap_id: 'cevrimiciIpucu' };

/** Faz 6M — ayarlar: genel, otomatik aktarım (kaynak başına; varsayılan kapalı; "onayıma sun" → öneri), kategoriler, eşitleme. */
export default function Ayarlar({ api, meta, yenile }: BolumProps) {
  const { t, i18n } = useTranslation();
  const dil = i18n.language || 'tr';
  const salt = meta.salt_okunur;
  const a = meta.ayarlar;
  const [firma, setFirma] = useState(a.firma_adi);
  const [pb, setPb] = useState(a.para_birimi);
  const [yuzde, setYuzde] = useState(String(a.uyari_yuzde));
  const [aktarim, setAktarim] = useState<Record<string, AktarimAyari>>(() => JSON.parse(JSON.stringify(a.aktarim)));
  const [hata, setHata] = useState<string | null>(null);
  const [mesaj, setMesaj] = useState<string | null>(null);
  const [kaydediliyor, setKaydediliyor] = useState<string | null>(null);

  const genelKaydet = async () => {
    setHata(null);
    setKaydediliyor('genel');
    try {
      await api.ayarlarKaydet({ firma_adi: firma, para_birimi: pb, uyari_yuzde: Number(yuzde) });
      setMesaj(t('onMuhasebe.ayarlar.kaydedildi'));
      yenile();
    } catch (e) {
      setHata(hataMetni(t, e));
    } finally {
      setKaydediliyor(null);
    }
  };

  const aktarimKaydet = async (kaynak: string) => {
    setHata(null);
    setKaydediliyor(kaynak);
    try {
      const d = aktarim[kaynak];
      const govde: Record<string, unknown> = { acik: d.acik, onay: !!d.onay, baslangic: d.baslangic || (d.acik ? bugun() : null) };
      for (const alan of AKTARIM_ALANLARI[kaynak]) govde[alan] = d[alan] ? Number(d[alan]) : null;
      await api.ayarlarKaydet({ aktarim: { [kaynak]: govde } });
      const r = await api.esitle();
      setMesaj(esitlemeMetni(r));
      yenile();
    } catch (e) {
      setHata(hataMetni(t, e));
    } finally {
      setKaydediliyor(null);
    }
  };

  const esitle = async () => {
    setHata(null);
    setKaydediliyor('esitle');
    try {
      const r = await api.esitle();
      setMesaj(esitlemeMetni(r));
      yenile();
    } catch (e) {
      setHata(hataMetni(t, e));
    } finally {
      setKaydediliyor(null);
    }
  };

  const esitlemeMetni = (r: { olusturulan: number; ters: number; tekrar: number; oneri?: number }) =>
    t('onMuhasebe.ayarlar.esitlemeOzet', { olusturulan: r.olusturulan, ters: r.ters, tekrar: r.tekrar }) +
    (r.oneri ? ` · ${t('onMuhasebe.ayarlar.oneriOzet', { sayi: r.oneri })}` : '');
  // Müşteride "ödeme" kaynağı ajansa ödenen faturalar (gider); ajansta müşterilerden gelen tahsilatlar.
  const kaynakAnahtari = (k: string) => (k === 'odeme' && !meta.ajans ? 'odeme_musteri' : k);
  const setAlan = (kaynak: string, alan: string, deger: unknown) => setAktarim((x) => ({ ...x, [kaynak]: { ...x[kaynak], [alan]: deger } }));
  const hesaplar = meta.hesaplar.filter((h) => !h.arsiv);
  const son = a.son_esitleme;

  return (
    <div className="space-y-4" data-testid="mh-ayarlar">
      <HataSatiri hata={hata} />
      {mesaj && (
        <p className="text-sm text-emerald-300" role="status" data-testid="mh-ayar-mesaj">
          {mesaj}
        </p>
      )}
      <section className={`${KART} space-y-3 p-4`}>
        <h3 className="font-semibold">{t('onMuhasebe.ayarlar.genel')}</h3>
        <div className="grid gap-3 sm:grid-cols-3">
          <Alan etiket={t('onMuhasebe.ayarlar.firmaAdi')} ipucu={t('onMuhasebe.ayarlar.firmaIpucu')}>
            <input className={GIRDI} maxLength={160} value={firma} disabled={salt} onChange={(e) => setFirma(e.target.value)} data-testid="mh-ayar-firma" />
          </Alan>
          <Alan etiket={t('onMuhasebe.ayarlar.paraBirimi')}>
            <select className={SECIM} value={pb} disabled={salt} onChange={(e) => setPb(e.target.value)}>
              {meta.sabitler.para_birimleri.map((x) => (
                <option key={x} value={x}>
                  {x}
                </option>
              ))}
            </select>
          </Alan>
          <Alan etiket={t('onMuhasebe.ayarlar.uyariYuzde')}>
            <input className={GIRDI} type="number" min={1} max={100} value={yuzde} disabled={salt} onChange={(e) => setYuzde(e.target.value)} />
          </Alan>
        </div>
        {!salt && (
          <Button type="button" size="sm" className="gap-1.5" onClick={() => void genelKaydet()} disabled={kaydediliyor === 'genel'} data-testid="mh-ayar-kaydet">
            {kaydediliyor === 'genel' ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" /> : <Save className="h-4 w-4" aria-hidden="true" />}
            {t('onMuhasebe.ortak.kaydet')}
          </Button>
        )}
      </section>

      <section className={`${KART} space-y-3 p-4`} data-testid="mh-aktarim">
        <h3 className="font-semibold">{t('onMuhasebe.ayarlar.aktarim')}</h3>
        <p className="text-sm text-muted-foreground">{t('onMuhasebe.ayarlar.aktarimAciklama')}</p>
        <Not>{t('onMuhasebe.ayarlar.tersNot')}</Not>
        <div className="grid gap-3 lg:grid-cols-2">
          {meta.aktarim_kaynaklari.map((k) => {
            const d = aktarim[k] || { acik: false, baslangic: null, onay: false };
            const ka = kaynakAnahtari(k);
            const kapali = k in KAYNAK_MODULU && meta.aktarim_modulleri[k] === false;
            return (
              <div key={k} className="space-y-2 rounded-xl border border-white/10 p-3" data-testid={`mh-aktarim-${k}`}>
                <div className="flex items-start justify-between gap-2">
                  <div>
                    <p className="font-medium">{t(`onMuhasebe.ayarlar.kaynak.${ka}.ad`)}</p>
                    <p className="text-xs text-muted-foreground">{t(`onMuhasebe.ayarlar.kaynak.${ka}.aciklama`)}</p>
                  </div>
                  {a.aktarim[k]?.acik && <Rozet renk="border-emerald-400/40 bg-emerald-500/15 text-emerald-200">{t('onMuhasebe.ayarlar.acik')}</Rozet>}
                </div>
                {kapali && <p className="text-xs text-amber-200">{t('onMuhasebe.ayarlar.modulKapali', { modul: t(`onMuhasebe.ayarlar.kaynak.${ka}.ad`) })}</p>}
                <Anahtar acik={!!d.acik} devreDisi={salt} onDegis={(v) => setAlan(k, 'acik', v)} etiket={t('onMuhasebe.ayarlar.otomatikAktar')} testid={`mh-aktarim-${k}-acik`} />
                <Anahtar acik={!!d.onay} devreDisi={salt} onDegis={(v) => setAlan(k, 'onay', v)} etiket={t('onMuhasebe.ayarlar.onay')} testid={`mh-aktarim-${k}-onay`} />
                <p className="text-xs text-muted-foreground">{d.onay ? t('onMuhasebe.ayarlar.onayIpucu') : t('onMuhasebe.ayarlar.otomatikIpucu')}</p>
                {k === 'odeme' && <p className="text-xs text-muted-foreground">{t('onMuhasebe.ayarlar.faturaHepOneri')}</p>}
                <div className="grid gap-2 sm:grid-cols-2">
                  {AKTARIM_ALANLARI[k].map((alan) => (
                    <Alan
                      key={alan}
                      etiket={t(`onMuhasebe.ayarlar.alan.${alan}`)}
                      ipucu={k === 'saha' ? t('onMuhasebe.ayarlar.sahaHesapIpucu') : ALAN_IPUCU[alan] ? t(`onMuhasebe.ayarlar.${ALAN_IPUCU[alan]}`) : undefined}
                    >
                      <select
                        className={SECIM}
                        disabled={salt}
                        value={(d[alan] as number | null) ?? ''}
                        onChange={(e) => setAlan(k, alan, e.target.value ? Number(e.target.value) : null)}
                        data-testid={`mh-aktarim-${k}-${alan}`}
                      >
                        <option value="">—</option>
                        {hesaplar.map((h) => (
                          <option key={h.id} value={h.id}>
                            {h.ad} ({h.para_birimi})
                          </option>
                        ))}
                      </select>
                    </Alan>
                  ))}
                  <Alan etiket={t('onMuhasebe.ayarlar.baslangic')} ipucu={t('onMuhasebe.ayarlar.baslangicIpucu')}>
                    <input type="date" className={GIRDI} disabled={salt} value={d.baslangic || ''} onChange={(e) => setAlan(k, 'baslangic', e.target.value || null)} />
                  </Alan>
                </div>
                {!salt && (
                  <Button type="button" size="sm" variant="outline" className={DIS_DUGME} onClick={() => void aktarimKaydet(k)} disabled={kaydediliyor === k} data-testid={`mh-aktarim-${k}-kaydet`}>
                    {kaydediliyor === k ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" /> : <Save className="h-4 w-4" aria-hidden="true" />}
                    {t('onMuhasebe.ortak.kaydet')}
                  </Button>
                )}
              </div>
            );
          })}
        </div>
        <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
          {a.son_esitleme_at && (
            <span data-testid="mh-son-esitleme">
              {t('onMuhasebe.ayarlar.sonEsitleme', {
                zaman: new Intl.DateTimeFormat(dil === 'ar' ? 'ar-u-nu-latn' : dil, { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(a.son_esitleme_at)),
              })}
              {son ? ` — ${esitlemeMetni(son)}` : ''}
            </span>
          )}
          {!salt && (
            <Button type="button" size="sm" variant="outline" className={DIS_DUGME} onClick={() => void esitle()} disabled={kaydediliyor === 'esitle'} data-testid="mh-esitle">
              <RefreshCw className={`h-4 w-4 ${kaydediliyor === 'esitle' ? 'animate-spin' : ''}`} aria-hidden="true" />
              {t('onMuhasebe.ayarlar.simdiEsitle')}
            </Button>
          )}
        </div>
      </section>

      <Kategoriler api={api} kategoriler={meta.kategoriler} salt={salt} yenile={yenile} onHata={setHata} />
      <p className="text-xs text-muted-foreground">{t('onMuhasebe.ayarlar.ekip')}</p>
    </div>
  );
}

function Kategoriler({
  api,
  kategoriler,
  salt,
  yenile,
  onHata,
}: {
  api: BolumProps['api'];
  kategoriler: Kategori[];
  salt: boolean;
  yenile: () => void;
  onHata: (h: string | null) => void;
}) {
  const { t } = useTranslation();
  const [yeni, setYeni] = useState<{ tur: KategoriTuru; ad: string; renk: string }>({ tur: 'gider', ad: '', renk: '#a78bfa' });
  const [adlar, setAdlar] = useState<Record<number, string>>({});

  const calis = async (is: () => Promise<unknown>) => {
    onHata(null);
    try {
      await is();
      yenile();
    } catch (e) {
      onHata(hataMetni(t, e));
    }
  };

  const liste = (tur: KategoriTuru) => (
    <div>
      <h4 className="mb-1 text-sm font-semibold">{tur === 'gelir' ? t('onMuhasebe.ayarlar.gelirKategorileri') : t('onMuhasebe.ayarlar.giderKategorileri')}</h4>
      <ul className="space-y-1" data-testid={`mh-kategoriler-${tur}`}>
        {kategoriler
          .filter((k) => k.tur === tur)
          .map((k) => (
            <li key={k.id} className={`flex flex-wrap items-center gap-2 text-sm ${k.arsiv ? 'opacity-50' : ''}`}>
              <input
                type="color"
                className="h-7 w-7 flex-none cursor-pointer rounded border border-white/10 bg-transparent"
                value={k.renk}
                disabled={salt}
                aria-label={t('onMuhasebe.ayarlar.renk')}
                onChange={(e) => void calis(() => api.kategoriGuncelle(k.id, { renk: e.target.value }))}
              />
              {salt ? (
                <span className="flex-1">{kategoriAdi(t, k)}</span>
              ) : (
                <input
                  className={`${GIRDI} h-8 flex-1`}
                  value={adlar[k.id] ?? kategoriAdi(t, k)}
                  onChange={(e) => setAdlar((x) => ({ ...x, [k.id]: e.target.value }))}
                  onBlur={() => {
                    const ad = (adlar[k.id] ?? '').trim();
                    if (ad && ad !== kategoriAdi(t, k)) void calis(() => api.kategoriGuncelle(k.id, { ad }));
                  }}
                />
              )}
              <span className="text-xs text-muted-foreground">{t('onMuhasebe.ayarlar.kullanim', { sayi: k.kullanim })}</span>
              {!salt && (
                <>
                  <button
                    type="button"
                    className="rounded p-1 text-muted-foreground hover:bg-white/10 hover:text-white"
                    title={k.arsiv ? t('onMuhasebe.hesap.arsivdenCikar') : t('onMuhasebe.hesap.arsiveAl')}
                    aria-label={k.arsiv ? t('onMuhasebe.hesap.arsivdenCikar') : t('onMuhasebe.hesap.arsiveAl')}
                    onClick={() => void calis(() => api.kategoriGuncelle(k.id, { arsiv: !k.arsiv }))}
                  >
                    <Archive className="h-4 w-4" aria-hidden="true" />
                  </button>
                  <button
                    type="button"
                    className="rounded p-1 text-muted-foreground hover:bg-white/10 hover:text-rose-200"
                    aria-label={t('onMuhasebe.ortak.sil')}
                    onClick={() => window.confirm(t('onMuhasebe.ayarlar.kategoriSilOnay')) && void calis(() => api.kategoriSil(k.id))}
                  >
                    <Trash2 className="h-4 w-4" aria-hidden="true" />
                  </button>
                </>
              )}
            </li>
          ))}
      </ul>
    </div>
  );

  return (
    <section className={`${KART} space-y-3 p-4`}>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 className="font-semibold">{t('onMuhasebe.ayarlar.kategoriler')}</h3>
        {!salt && (
          <Button type="button" size="sm" variant="ghost" className="gap-1.5" onClick={() => void calis(() => api.varsayilanKategoriler())}>
            <RotateCcw className="h-4 w-4" aria-hidden="true" />
            {t('onMuhasebe.ayarlar.varsayilanlar')}
          </Button>
        )}
      </div>
      <div className="grid gap-4 lg:grid-cols-2">
        {liste('gelir')}
        {liste('gider')}
      </div>
      {!salt && (
        <div className="flex flex-wrap items-end gap-2">
          <Alan etiket={t('onMuhasebe.ortak.tur')}>
            <select className={`${SECIM} w-28`} value={yeni.tur} onChange={(e) => setYeni((x) => ({ ...x, tur: e.target.value as KategoriTuru }))}>
              <option value="gider">{t('onMuhasebe.tur.gider')}</option>
              <option value="gelir">{t('onMuhasebe.tur.gelir')}</option>
            </select>
          </Alan>
          <Alan etiket={t('onMuhasebe.ayarlar.yeniKategori')} className="min-w-[12rem] flex-1">
            <input className={GIRDI} maxLength={80} value={yeni.ad} onChange={(e) => setYeni((x) => ({ ...x, ad: e.target.value }))} data-testid="mh-kategori-ad" />
          </Alan>
          <input
            type="color"
            className="h-10 w-10 cursor-pointer rounded border border-white/10 bg-transparent"
            value={yeni.renk}
            aria-label={t('onMuhasebe.ayarlar.renk')}
            onChange={(e) => setYeni((x) => ({ ...x, renk: e.target.value }))}
          />
          <Button
            type="button"
            size="sm"
            className="h-10 gap-1.5"
            disabled={!yeni.ad.trim()}
            onClick={() =>
              void calis(async () => {
                await api.kategoriEkle(yeni);
                setYeni((x) => ({ ...x, ad: '' }));
              })
            }
            data-testid="mh-kategori-ekle"
          >
            <Plus className="h-4 w-4" aria-hidden="true" />
            {t('onMuhasebe.ortak.ekle')}
          </Button>
        </div>
      )}
    </section>
  );
}
