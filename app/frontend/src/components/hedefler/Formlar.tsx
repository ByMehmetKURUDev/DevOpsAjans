import { useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Loader2, Plus, Sparkles, Trash2 } from 'lucide-react';

import { Button } from '@/components/ui/button';
import { Alan, DIS_DUGME, GIRDI, HataSatiri, METIN_ALANI, Not, Pencere, SECIM } from '@/components/hedefler/ortak';
import {
  bugun,
  degerYaz,
  girdiMetni,
  hataMetni,
  type Donem,
  type DonemTuru,
  type Guven,
  type Hedef,
  type KilometreTasi,
  type Kr,
  type KrOnerisi,
  type KrTuru,
  type Meta,
  type OkrApi,
  type Yon,
} from '@/lib/okr';

const yil = () => Number(bugun().slice(0, 4));
const ceyrek = () => Math.floor((Number(bugun().slice(5, 7)) - 1) / 3) + 1;

// ---------------------------------------------------------------------------
// Dönem
// ---------------------------------------------------------------------------
export function DonemFormu({ api, donem, onKapat, onKaydet }: { api: OkrApi; donem: Donem | null; onKapat: () => void; onKaydet: (d: Donem) => void }) {
  const { t } = useTranslation();
  const [tur, setTur] = useState<DonemTuru>(donem?.tur ?? 'ceyrek');
  const [y, setY] = useState(String(donem?.yil ?? yil()));
  const [c, setC] = useState(String(donem?.ceyrek ?? ceyrek()));
  const [bas, setBas] = useState(donem?.baslangic ?? bugun());
  const [bit, setBit] = useState(donem?.bitis ?? '');
  const [ad, setAd] = useState(donem?.ad ?? '');
  const [etkin, setEtkin] = useState(donem ? donem.etkin : true);
  const [hata, setHata] = useState<string | null>(null);
  const [mesgul, setMesgul] = useState(false);
  const kapali = donem?.durum === 'kapandi';

  const kaydet = async () => {
    setMesgul(true);
    setHata(null);
    const govde: Record<string, unknown> = { ad, etkin };
    if (!kapali) {
      Object.assign(govde, { tur, yil: Number(y), ceyrek: Number(c) });
      if (tur === 'ozel') Object.assign(govde, { baslangic: bas, bitis: bit });
    }
    try {
      onKaydet(donem ? await api.donemGuncelle(donem.id, govde) : await api.donemEkle(govde));
    } catch (e) {
      setHata(hataMetni(t, e));
    } finally {
      setMesgul(false);
    }
  };
  const sil = async () => {
    if (!donem || !window.confirm(t('hedefler.donem.silOnay'))) return;
    try {
      await api.donemSil(donem.id);
      onKaydet({ ...donem, id: 0 });
    } catch (e) {
      setHata(hataMetni(t, e));
    }
  };

  return (
    <Pencere baslik={donem ? t('hedefler.donem.duzenle') : t('hedefler.donem.yeni')} onKapat={onKapat} testid="okr-donem-formu">
      <div className="grid gap-3">
        {!kapali && (
          <Alan etiket={t('hedefler.donem.tur')}>
            <select className={SECIM} value={tur} onChange={(e) => setTur(e.target.value as DonemTuru)} data-testid="okr-donem-tur">
              {(['ceyrek', 'yil', 'ozel'] as DonemTuru[]).map((x) => (
                <option key={x} value={x}>
                  {t(`hedefler.donem.turler.${x}`)}
                </option>
              ))}
            </select>
          </Alan>
        )}
        {!kapali && tur !== 'ozel' && (
          <div className="grid grid-cols-2 gap-3">
            <Alan etiket={t('hedefler.donem.yil')}>
              <input className={GIRDI} type="number" min={2000} max={2100} value={y} onChange={(e) => setY(e.target.value)} data-testid="okr-donem-yil" />
            </Alan>
            {tur === 'ceyrek' && (
              <Alan etiket={t('hedefler.donem.ceyrek')}>
                <select className={SECIM} value={c} onChange={(e) => setC(e.target.value)} data-testid="okr-donem-ceyrek">
                  {[1, 2, 3, 4].map((x) => (
                    <option key={x} value={x}>
                      {t('hedefler.donem.ceyrekKisa', { ceyrek: x })}
                    </option>
                  ))}
                </select>
              </Alan>
            )}
          </div>
        )}
        {!kapali && tur === 'ozel' && (
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <Alan etiket={t('hedefler.donem.baslangic')}>
              <input className={GIRDI} type="date" value={bas} onChange={(e) => setBas(e.target.value)} data-testid="okr-donem-bas" />
            </Alan>
            <Alan etiket={t('hedefler.donem.bitis')}>
              <input className={GIRDI} type="date" value={bit} onChange={(e) => setBit(e.target.value)} data-testid="okr-donem-bit" />
            </Alan>
          </div>
        )}
        <Alan etiket={t('hedefler.donem.ad')} ipucu={t('hedefler.donem.adIpucu')}>
          <input className={GIRDI} value={ad} maxLength={80} onChange={(e) => setAd(e.target.value)} data-testid="okr-donem-ad" />
        </Alan>
        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" className="h-4 w-4 accent-purple-500" checked={etkin} disabled={!!donem?.etkin} onChange={(e) => setEtkin(e.target.checked)} />
          {t('hedefler.donem.etkinYap')}
        </label>
        <HataSatiri hata={hata} />
        <div className="flex flex-wrap justify-between gap-2">
          {donem ? (
            <Button type="button" variant="ghost" className="gap-1.5 text-rose-300" onClick={() => void sil()}>
              <Trash2 className="h-4 w-4" aria-hidden="true" />
              {t('hedefler.ortak.sil')}
            </Button>
          ) : (
            <span />
          )}
          <Button type="button" disabled={mesgul} onClick={() => void kaydet()} className="bg-gradient-to-r from-purple-600 to-pink-600 text-white" data-testid="okr-donem-kaydet">
            {mesgul && <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />}
            {t('hedefler.ortak.kaydet')}
          </Button>
        </div>
      </div>
    </Pencere>
  );
}

// ---------------------------------------------------------------------------
// Hedef
// ---------------------------------------------------------------------------
export function HedefFormu({ api, meta, donem, hedef, onKapat, onKaydet }: {
  api: OkrApi;
  meta: Meta;
  donem: Donem;
  hedef: Hedef | null;
  onKapat: () => void;
  onKaydet: (h: Hedef) => void;
}) {
  const { t } = useTranslation();
  // Üst hedef seçenekleri: bütün dönemlerin görünür hedefleri (yıllık hedefe çeyrek hedefi hizalanabilir); kendisi hariç.
  // Döngüyü sunucu da reddeder.
  const [hedefler, setHedefler] = useState<{ id: number; baslik: string; donem: string | null }[]>([]);
  useEffect(() => {
    api
      .agac()
      .then((r) => setHedefler(r.items.filter((x) => x.id !== hedef?.id).map((x) => ({ id: x.id, baslik: x.baslik, donem: x.donem }))))
      .catch(() => setHedefler([]));
  }, [api, hedef?.id]);
  const [baslik, setBaslik] = useState(hedef?.baslik ?? '');
  const [aciklama, setAciklama] = useState(hedef?.aciklama ?? '');
  const [sahip, setSahip] = useState(hedef?.sahip ?? meta.kisi);
  const [ust, setUst] = useState(hedef?.ust_id ? String(hedef.ust_id) : '');
  const [gorunurluk, setGorunurluk] = useState(hedef?.gorunurluk ?? 'ekip');
  const [durum, setDurum] = useState(hedef?.durum === 'taslak' ? 'taslak' : 'etkin');
  const [musteri, setMusteri] = useState(hedef?.musteri_email ?? '');
  const [paylas, setPaylas] = useState(hedef?.musteri_paylasim ?? false);
  const [hata, setHata] = useState<string | null>(null);
  const [mesgul, setMesgul] = useState(false);

  const kaydet = async () => {
    setMesgul(true);
    setHata(null);
    const govde: Record<string, unknown> = {
      baslik, aciklama, sahip, ust_id: ust ? Number(ust) : null, gorunurluk, durum,
    };
    if (meta.ajans) Object.assign(govde, { musteri_email: musteri || null, musteri_paylasim: paylas && !!musteri && gorunurluk === 'ekip' });
    try {
      onKaydet(hedef ? await api.hedefGuncelle(hedef.id, govde) : await api.hedefEkle({ ...govde, donem_id: donem.id }));
    } catch (e) {
      setHata(hataMetni(t, e));
    } finally {
      setMesgul(false);
    }
  };

  return (
    <Pencere baslik={hedef ? t('hedefler.hedef.duzenle') : t('hedefler.hedef.yeni')} onKapat={onKapat} testid="okr-hedef-formu" genis>
      <div className="grid gap-3">
        <Alan etiket={t('hedefler.hedef.baslik')} ipucu={t('hedefler.hedef.baslikIpucu')}>
          <input className={GIRDI} value={baslik} maxLength={200} onChange={(e) => setBaslik(e.target.value)} data-testid="okr-hedef-baslik" />
        </Alan>
        <Alan etiket={t('hedefler.hedef.aciklamaAlani')}>
          <textarea className={METIN_ALANI} value={aciklama} maxLength={4000} onChange={(e) => setAciklama(e.target.value)} data-testid="okr-hedef-aciklama" />
        </Alan>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <Alan etiket={t('hedefler.hedef.sahip')}>
            <select className={SECIM} value={sahip} onChange={(e) => setSahip(e.target.value)} data-testid="okr-hedef-sahip">
              {meta.ekip.map((k) => (
                <option key={k.email} value={k.email}>
                  {k.ad ? `${k.ad} — ${k.email}` : k.email}
                </option>
              ))}
            </select>
          </Alan>
          <Alan etiket={t('hedefler.hedef.ust')} ipucu={t('hedefler.hedef.ustIpucu')}>
            <select className={SECIM} value={ust} onChange={(e) => setUst(e.target.value)} data-testid="okr-hedef-ust">
              <option value="">{t('hedefler.hedef.ustYok')}</option>
              {hedefler.map((h) => (
                <option key={h.id} value={h.id}>
                  {h.baslik}
                  {h.donem ? ` (${h.donem})` : ''}
                </option>
              ))}
            </select>
          </Alan>
          <Alan etiket={t('hedefler.hedef.gorunurluk')}>
            <select className={SECIM} value={gorunurluk} onChange={(e) => setGorunurluk(e.target.value as 'ekip' | 'ozel')} data-testid="okr-hedef-gorunurluk">
              <option value="ekip">{t('hedefler.hedef.gorunurlukler.ekip')}</option>
              <option value="ozel">{t('hedefler.hedef.gorunurlukler.ozel')}</option>
            </select>
          </Alan>
          <Alan etiket={t('hedefler.hedef.durum')}>
            <select className={SECIM} value={durum} onChange={(e) => setDurum(e.target.value)} data-testid="okr-hedef-durum">
              <option value="etkin">{t('hedefler.hedef.durumlar.etkin')}</option>
              <option value="taslak">{t('hedefler.hedef.durumlar.taslak')}</option>
            </select>
          </Alan>
        </div>
        {meta.ajans && (
          <div className="grid gap-2 rounded-xl border border-white/10 p-3">
            <Alan etiket={t('hedefler.hedef.musteri')} ipucu={t('hedefler.hedef.musteriIpucu')}>
              <select className={SECIM} value={musteri} onChange={(e) => setMusteri(e.target.value)} data-testid="okr-hedef-musteri">
                <option value="">{t('hedefler.hedef.musteriYok')}</option>
                {musteri && !meta.musteri_hesaplari.some((m) => m.eposta === musteri) && <option value={musteri}>{musteri}</option>}
                {meta.musteri_hesaplari.map((m) => (
                  <option key={m.eposta} value={m.eposta}>
                    {m.ad ? `${m.ad} — ${m.eposta}` : m.eposta}
                  </option>
                ))}
              </select>
            </Alan>
            <label className={`flex items-start gap-2 text-sm ${!musteri || gorunurluk !== 'ekip' ? 'opacity-50' : ''}`}>
              <input
                type="checkbox"
                className="mt-0.5 h-4 w-4 accent-purple-500"
                checked={paylas && !!musteri && gorunurluk === 'ekip'}
                disabled={!musteri || gorunurluk !== 'ekip'}
                onChange={(e) => setPaylas(e.target.checked)}
                data-testid="okr-hedef-paylas"
              />
              <span>
                {t('hedefler.hedef.paylas')}
                <span className="block text-xs text-muted-foreground">{t('hedefler.hedef.paylasIpucu')}</span>
              </span>
            </label>
          </div>
        )}
        <HataSatiri hata={hata} />
        <div className="flex justify-end">
          <Button type="button" disabled={mesgul || !baslik.trim()} onClick={() => void kaydet()} className="bg-gradient-to-r from-purple-600 to-pink-600 text-white" data-testid="okr-hedef-kaydet">
            {mesgul && <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />}
            {t('hedefler.ortak.kaydet')}
          </Button>
        </div>
      </div>
    </Pencere>
  );
}

// ---------------------------------------------------------------------------
// Anahtar sonuç (KR) — "AI ile KR öner" (öneriler seçilmeden kaydedilmez)
// ---------------------------------------------------------------------------
export function KrFormu({ api, meta, hedef, kr, onKapat, onKaydet }: {
  api: OkrApi;
  meta: Meta;
  hedef: Pick<Hedef, 'id' | 'baslik'>;
  kr: Kr | null;
  onKapat: () => void;
  onKaydet: (k: Kr) => void;
}) {
  const { t, i18n } = useTranslation();
  const dil = i18n.language || 'tr';
  const [baslik, setBaslik] = useState(kr?.baslik ?? '');
  const [kaynak, setKaynak] = useState(kr?.kaynak ?? '');
  const [tur, setTur] = useState<KrTuru>(kr?.tur ?? 'sayi');
  const [birim, setBirim] = useState(kr?.birim ?? '');
  const [pb, setPb] = useState(kr?.para_birimi ?? kr?.kaynak_ayar?.para_birimi ?? 'TRY');
  const [proje, setProje] = useState(kr?.kaynak_ayar?.proje_id ? String(kr.kaynak_ayar.proje_id) : '');
  const [bas, setBas] = useState(kr ? girdiMetni(kr.tur, kr.baslangic) : '0');
  const [hedefDeger, setHedefDeger] = useState(kr ? girdiMetni(kr.tur, kr.hedef) : '');
  const [mevcut, setMevcut] = useState(kr ? girdiMetni(kr.tur, kr.mevcut) : '');
  const [yon, setYon] = useState<Yon>(kr?.yon ?? 'artir');
  const [agirlik, setAgirlik] = useState(String(kr?.agirlik ?? 1));
  const [sahip, setSahip] = useState(kr?.sahip ?? '');
  const [kmler, setKmler] = useState<KilometreTasi[]>(kr?.kilometre_taslari?.length ? kr.kilometre_taslari : [{ id: '', metin: '', tamam: false }]);
  const [oneriler, setOneriler] = useState<KrOnerisi[] | null>(null);
  const [oneriMesgul, setOneriMesgul] = useState(false);
  const [hata, setHata] = useState<string | null>(null);
  const [mesgul, setMesgul] = useState(false);
  const kaynakTanimi = useMemo(() => meta.kaynaklar.find((k) => k.anahtar === kaynak) || null, [meta.kaynaklar, kaynak]);
  const etkinTur: KrTuru = kaynakTanimi ? kaynakTanimi.tur : tur;
  const otomatik = !!kaynakTanimi;

  const oner = async () => {
    setOneriMesgul(true);
    setHata(null);
    try {
      setOneriler((await api.krOner({ hedef_id: hedef.id, sayi: 3, dil })).oneriler);
    } catch (e) {
      setHata(hataMetni(t, e));
    } finally {
      setOneriMesgul(false);
    }
  };
  const kullan = (o: KrOnerisi) => {
    setKaynak('');
    setBaslik(o.baslik);
    setTur(o.tur);
    setYon(o.yon);
    setBirim(o.birim || '');
    setBas(girdiMetni(o.tur, o.baslangic));
    setHedefDeger(girdiMetni(o.tur, o.hedef));
    setMevcut('');
    setOneriler(null);
  };

  const kaydet = async () => {
    setMesgul(true);
    setHata(null);
    const govde: Record<string, unknown> = { baslik, agirlik: Number(agirlik) || 1, sahip: sahip || null, kaynak: kaynak || null };
    if (otomatik && kaynakTanimi) {
      govde.kaynak_ayar = { ...(kaynakTanimi.para ? { para_birimi: pb } : {}), ...(kaynakTanimi.proje ? { proje_id: Number(proje) || null } : {}) };
    } else {
      govde.tur = tur;
      if (tur === 'para') govde.para_birimi = pb;
      if (tur === 'sayi') govde.birim = birim;
    }
    if (etkinTur === 'kilometre') {
      govde.kilometre_taslari = kmler.filter((k) => k.metin.trim()).map((k) => ({ ...(k.id ? { id: k.id } : {}), metin: k.metin, tamam: k.tamam }));
    } else if (etkinTur === 'evet_hayir') {
      if (!otomatik && !kr) govde.mevcut = false;
    } else {
      Object.assign(govde, { baslangic: bas || '0', hedef: hedefDeger, yon });
      if (!otomatik && mevcut !== '') govde.mevcut = mevcut;
    }
    try {
      onKaydet(kr ? await api.krGuncelle(kr.id, govde) : await api.krEkle(hedef.id, govde));
    } catch (e) {
      setHata(hataMetni(t, e));
    } finally {
      setMesgul(false);
    }
  };

  return (
    <Pencere baslik={kr ? t('hedefler.kr.duzenle') : t('hedefler.kr.yeni')} onKapat={onKapat} testid="okr-kr-formu" genis>
      <div className="grid gap-3">
        <p className="text-xs text-muted-foreground">
          {t('hedefler.kr.hedefi')}: <span className="text-white">{hedef.baslik}</span>
        </p>
        {meta.ai_hazir && !kr && (
          <div className="rounded-xl border border-purple-400/30 bg-purple-500/10 p-3" data-testid="okr-ai">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <p className="text-xs text-purple-100">{t('hedefler.ai.aciklama')}</p>
              <Button type="button" size="sm" variant="outline" className={DIS_DUGME} disabled={oneriMesgul} onClick={() => void oner()} data-testid="okr-ai-oner">
                {oneriMesgul ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" /> : <Sparkles className="h-4 w-4" aria-hidden="true" />}
                {t('hedefler.ai.oner')}
              </Button>
            </div>
            {oneriler && (
              <ul className="mt-2 grid gap-2" data-testid="okr-ai-oneriler">
                {oneriler.map((o, i) => (
                  <li key={i} className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-white/10 bg-black/20 p-2 text-sm">
                    <span className="min-w-0 flex-1">
                      <span className="block break-words">{o.baslik}</span>
                      <span className="block text-xs text-muted-foreground">
                        {degerYaz({ tur: o.tur, para_birimi: pb, birim: o.birim || '' }, o.baslangic, dil, t)} →{' '}
                        {degerYaz({ tur: o.tur, para_birimi: pb, birim: o.birim || '' }, o.hedef, dil, t)}
                        {o.gerekce ? ` · ${o.gerekce}` : ''}
                      </span>
                    </span>
                    <Button type="button" size="sm" variant="ghost" onClick={() => kullan(o)} data-testid="okr-ai-kullan">
                      {t('hedefler.ai.kullan')}
                    </Button>
                  </li>
                ))}
              </ul>
            )}
            <p className="mt-2 text-[11px] text-muted-foreground">{t('hedefler.ai.not')}</p>
          </div>
        )}
        <Alan etiket={t('hedefler.kr.baslik')} ipucu={t('hedefler.kr.baslikIpucu')}>
          <input className={GIRDI} value={baslik} maxLength={200} onChange={(e) => setBaslik(e.target.value)} data-testid="okr-kr-baslik" />
        </Alan>
        <Alan etiket={t('hedefler.kr.olcum')} ipucu={otomatik ? t('hedefler.kr.otomatikIpucu') : t('hedefler.kr.elleIpucu')}>
          <select className={SECIM} value={kaynak} onChange={(e) => setKaynak(e.target.value)} data-testid="okr-kr-kaynak">
            <option value="">{t('hedefler.kr.elle')}</option>
            {meta.kaynaklar.map((k) => (
              <option key={k.anahtar} value={k.anahtar}>
                {t(`hedefler.kaynak.${k.anahtar}`)}
              </option>
            ))}
          </select>
        </Alan>
        {meta.kaynaklar.length === 0 && !meta.ajans && <Not>{t('hedefler.kr.kaynakYok')}</Not>}
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          {!otomatik && (
            <Alan etiket={t('hedefler.kr.tur')}>
              <select className={SECIM} value={tur} onChange={(e) => setTur(e.target.value as KrTuru)} data-testid="okr-kr-tur">
                {meta.sabitler.kr_turleri.map((x) => (
                  <option key={x} value={x}>
                    {t(`hedefler.kr.turler.${x}`)}
                  </option>
                ))}
              </select>
            </Alan>
          )}
          {(etkinTur === 'para' || kaynakTanimi?.para) && (
            <Alan etiket={t('hedefler.kr.paraBirimi')}>
              <select className={SECIM} value={pb} onChange={(e) => setPb(e.target.value)} data-testid="okr-kr-pb">
                {meta.sabitler.para_birimleri.map((x) => (
                  <option key={x} value={x}>
                    {x}
                  </option>
                ))}
              </select>
            </Alan>
          )}
          {kaynakTanimi?.proje && (
            <Alan etiket={t('hedefler.kr.proje')}>
              <select className={SECIM} value={proje} onChange={(e) => setProje(e.target.value)} data-testid="okr-kr-proje">
                <option value="">—</option>
                {meta.projeler.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.ad}
                    {p.musteri ? ` (${p.musteri})` : ''}
                  </option>
                ))}
              </select>
            </Alan>
          )}
          {etkinTur === 'sayi' && !otomatik && (
            <Alan etiket={t('hedefler.kr.birim')} ipucu={t('hedefler.kr.birimIpucu')}>
              <input className={GIRDI} value={birim} maxLength={20} onChange={(e) => setBirim(e.target.value)} data-testid="okr-kr-birim" />
            </Alan>
          )}
        </div>
        {etkinTur === 'kilometre' ? (
          <div className="grid gap-2">
            <span className="text-sm font-medium text-white/90">{t('hedefler.kr.kilometreler')}</span>
            {kmler.map((k, i) => (
              <div key={i} className="flex items-center gap-2">
                <input
                  className={GIRDI}
                  value={k.metin}
                  maxLength={160}
                  placeholder={t('hedefler.kr.kilometreOrnek')}
                  onChange={(e) => setKmler(kmler.map((x, j) => (j === i ? { ...x, metin: e.target.value } : x)))}
                  aria-label={`${t('hedefler.kr.kilometre')} ${i + 1}`}
                  data-testid="okr-kr-kilometre"
                />
                <Button type="button" size="sm" variant="ghost" onClick={() => setKmler(kmler.filter((_, j) => j !== i))} aria-label={t('hedefler.ortak.sil')} disabled={kmler.length < 2}>
                  <Trash2 className="h-4 w-4" aria-hidden="true" />
                </Button>
              </div>
            ))}
            <Button type="button" size="sm" variant="outline" className={`${DIS_DUGME} w-fit`} onClick={() => setKmler([...kmler, { id: '', metin: '', tamam: false }])}>
              <Plus className="h-4 w-4" aria-hidden="true" />
              {t('hedefler.kr.kilometreEkle')}
            </Button>
          </div>
        ) : etkinTur === 'evet_hayir' ? (
          <Not>{t('hedefler.kr.evetHayirIpucu')}</Not>
        ) : (
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            <Alan etiket={t('hedefler.kr.yon')}>
              <select className={SECIM} value={yon} onChange={(e) => setYon(e.target.value as Yon)} data-testid="okr-kr-yon">
                <option value="artir">{t('hedefler.kr.yonler.artir')}</option>
                <option value="azalt">{t('hedefler.kr.yonler.azalt')}</option>
              </select>
            </Alan>
            <Alan etiket={t('hedefler.kr.baslangic')}>
              <input className={GIRDI} inputMode="decimal" value={bas} onChange={(e) => setBas(e.target.value)} data-testid="okr-kr-baslangic" />
            </Alan>
            <Alan etiket={t('hedefler.kr.hedefDeger')}>
              <input className={GIRDI} inputMode="decimal" value={hedefDeger} onChange={(e) => setHedefDeger(e.target.value)} data-testid="okr-kr-hedef" />
            </Alan>
            {!otomatik && (
              <Alan etiket={t('hedefler.kr.mevcut')}>
                <input className={GIRDI} inputMode="decimal" value={mevcut} placeholder={bas} onChange={(e) => setMevcut(e.target.value)} data-testid="okr-kr-mevcut" />
              </Alan>
            )}
          </div>
        )}
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <Alan etiket={t('hedefler.kr.agirlik')} ipucu={t('hedefler.kr.agirlikIpucu')}>
            <input className={GIRDI} type="number" min={1} max={meta.sabitler.en_cok_agirlik} value={agirlik} onChange={(e) => setAgirlik(e.target.value)} data-testid="okr-kr-agirlik" />
          </Alan>
          <Alan etiket={t('hedefler.kr.sahip')}>
            <select className={SECIM} value={sahip} onChange={(e) => setSahip(e.target.value)} data-testid="okr-kr-sahip">
              <option value="">{t('hedefler.kr.sahipHedef')}</option>
              {meta.ekip.map((k) => (
                <option key={k.email} value={k.email}>
                  {k.ad ? `${k.ad} — ${k.email}` : k.email}
                </option>
              ))}
            </select>
          </Alan>
        </div>
        <HataSatiri hata={hata} />
        <div className="flex justify-end">
          <Button type="button" disabled={mesgul || !baslik.trim()} onClick={() => void kaydet()} className="bg-gradient-to-r from-purple-600 to-pink-600 text-white" data-testid="okr-kr-kaydet">
            {mesgul && <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />}
            {t('hedefler.ortak.kaydet')}
          </Button>
        </div>
      </div>
    </Pencere>
  );
}

// ---------------------------------------------------------------------------
// Check-in
// ---------------------------------------------------------------------------
export function CheckinFormu({ api, kr, onKapat, onKaydet }: { api: OkrApi; kr: Kr; onKapat: () => void; onKaydet: (k: Kr) => void }) {
  const { t, i18n } = useTranslation();
  const dil = i18n.language || 'tr';
  const [deger, setDeger] = useState(kr.tur === 'evet_hayir' ? (kr.mevcut >= 1 ? '1' : '0') : girdiMetni(kr.tur, kr.mevcut));
  const [guven, setGuven] = useState<Guven | ''>(kr.guven ?? 'yolunda');
  const [notlar, setNotlar] = useState('');
  const [tarih, setTarih] = useState(bugun());
  const [kmler, setKmler] = useState<KilometreTasi[]>(kr.kilometre_taslari || []);
  const [hata, setHata] = useState<string | null>(null);
  const [mesgul, setMesgul] = useState(false);
  const otomatik = !!kr.kaynak;

  const kaydet = async () => {
    setMesgul(true);
    setHata(null);
    const govde: Record<string, unknown> = { guven: guven || null, notlar, tarih };
    if (!otomatik) {
      if (kr.tur === 'kilometre') govde.kilometre = kmler.map((k) => ({ id: k.id, tamam: k.tamam }));
      else if (kr.tur === 'evet_hayir') govde.deger = deger === '1';
      else govde.deger = deger;
    }
    try {
      onKaydet((await api.checkin(kr.id, govde)).kr);
    } catch (e) {
      setHata(hataMetni(t, e));
    } finally {
      setMesgul(false);
    }
  };

  return (
    <Pencere baslik={t('hedefler.checkin.baslik')} onKapat={onKapat} testid="okr-checkin-formu">
      <div className="grid gap-3">
        <p className="break-words text-sm">{kr.baslik}</p>
        <p className="text-xs text-muted-foreground">
          {t('hedefler.checkin.simdiki')}: {degerYaz(kr, kr.mevcut, dil, t)} · {t('hedefler.kr.hedefDeger')}: {degerYaz(kr, kr.hedef, dil, t)}
        </p>
        {otomatik ? (
          <Not>{t('hedefler.checkin.otomatikNot')}</Not>
        ) : kr.tur === 'kilometre' ? (
          <fieldset className="grid gap-1.5">
            <legend className="mb-1 text-sm font-medium">{t('hedefler.kr.kilometreler')}</legend>
            {kmler.map((k) => (
              <label key={k.id} className="flex items-start gap-2 text-sm">
                <input
                  type="checkbox"
                  className="mt-0.5 h-4 w-4 accent-purple-500"
                  checked={k.tamam}
                  onChange={(e) => setKmler(kmler.map((x) => (x.id === k.id ? { ...x, tamam: e.target.checked } : x)))}
                  data-testid="okr-checkin-kilometre"
                />
                <span className="min-w-0 break-words">{k.metin}</span>
              </label>
            ))}
          </fieldset>
        ) : kr.tur === 'evet_hayir' ? (
          <Alan etiket={t('hedefler.checkin.deger')}>
            <select className={SECIM} value={deger} onChange={(e) => setDeger(e.target.value)} data-testid="okr-checkin-deger">
              <option value="0">{t('hedefler.ortak.hayir')}</option>
              <option value="1">{t('hedefler.ortak.evet')}</option>
            </select>
          </Alan>
        ) : (
          <Alan etiket={t('hedefler.checkin.deger')} ipucu={kr.tur === 'para' ? t('hedefler.checkin.paraIpucu', { pb: kr.para_birimi }) : undefined}>
            <input className={GIRDI} inputMode="decimal" value={deger} onChange={(e) => setDeger(e.target.value)} data-testid="okr-checkin-deger" />
          </Alan>
        )}
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <Alan etiket={t('hedefler.checkin.guven')}>
            <select className={SECIM} value={guven} onChange={(e) => setGuven(e.target.value as Guven | '')} data-testid="okr-checkin-guven">
              {(['yolunda', 'riskli', 'tehlikede'] as Guven[]).map((g) => (
                <option key={g} value={g}>
                  {t(`hedefler.guven.${g}`)}
                </option>
              ))}
            </select>
          </Alan>
          <Alan etiket={t('hedefler.checkin.tarih')}>
            <input className={GIRDI} type="date" max={bugun()} value={tarih} onChange={(e) => setTarih(e.target.value)} />
          </Alan>
        </div>
        <Alan etiket={t('hedefler.checkin.not')}>
          <textarea className={METIN_ALANI} value={notlar} maxLength={2000} onChange={(e) => setNotlar(e.target.value)} data-testid="okr-checkin-not" />
        </Alan>
        <HataSatiri hata={hata} />
        <div className="flex justify-end">
          <Button type="button" disabled={mesgul} onClick={() => void kaydet()} className="bg-gradient-to-r from-purple-600 to-pink-600 text-white" data-testid="okr-checkin-kaydet">
            {mesgul && <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />}
            {t('hedefler.checkin.kaydet')}
          </Button>
        </div>
      </div>
    </Pencere>
  );
}
