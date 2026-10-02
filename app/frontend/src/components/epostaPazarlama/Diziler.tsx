import { useCallback, useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { ArrowLeft, ChevronDown, ChevronUp, Clock, Loader2, Plus, Save, Trash2, Workflow } from 'lucide-react';
import { toast } from 'sonner';

import { Button } from '@/components/ui/button';
import BlokDuzenleyici from '@/components/epostaPazarlama/BlokDuzenleyici';
import { Alan, Anahtar, Bos, DIS_DUGME, GIRDI, KART, Rozet, SECIM, Yukleniyor, sayiYaz } from '@/components/epostaPazarlama/ortak';
import { hataMetni, type Dizi, type DiziAdimi, type Liste, type Meta, type PazarlamaApi } from '@/lib/epostaPazarlama';
import { sablonBloklari } from '@/lib/epostaSablonlari';

/**
 * Faz 5M — damla dizileri: tetik (listeye katıldı / abonelik onaylandı), adımlar (bekle N gün →
 * e-posta), çıkış (ret her zaman; isteğe bağlı hedef: tıklama, etiket, başka listeye katılma).
 * Olay tetikleri (Faz 4A olay altyapısı) sonraki faza bırakıldı.
 */
export default function Diziler({ api, meta }: { api: PazarlamaApi; meta: Meta }) {
  const { t } = useTranslation();
  const [diziler, setDiziler] = useState<Dizi[] | null>(null);
  const [listeler, setListeler] = useState<Liste[]>([]);
  const [secili, setSecili] = useState<Dizi | null>(null);
  const [ad, setAd] = useState('');
  const [listeId, setListeId] = useState('');

  const yukle = useCallback(async () => {
    try {
      const [d, l] = await Promise.all([api.diziler(), api.listeler()]);
      setDiziler(d.items);
      setListeler(l.items);
      if (!listeId && l.items[0]) setListeId(String(l.items[0].id));
    } catch (e) {
      toast.error(hataMetni(t, e));
      setDiziler([]);
    }
  }, [api, t, listeId]);
  useEffect(() => {
    void yukle();
  }, [yukle]);

  const olustur = async () => {
    try {
      const d = await api.diziEkle({
        ad: ad.trim(),
        liste_id: Number(listeId),
        tetik: 'abonelik_onaylandi',
        adimlar: [{ bekle_gun: 0, bekle_saat: 0, konu: t('epostaPazarlama.sablon.hosgeldin.baslik'), onizleme_metni: '', bloklar: sablonBloklari('hosgeldin', t) }],
      });
      setAd('');
      setSecili(d);
    } catch (e) {
      toast.error(hataMetni(t, e));
    }
  };

  if (secili)
    return (
      <DiziDuzenle
        api={api}
        meta={meta}
        listeler={listeler}
        dizi={secili}
        geri={() => {
          setSecili(null);
          void yukle();
        }}
      />
    );
  if (diziler === null) return <Yukleniyor />;
  return (
    <div className="space-y-4" data-testid="ep-diziler">
      <div className={`${KART} space-y-2 p-4`}>
        <p className="text-sm text-muted-foreground">{t('epostaPazarlama.dizi.aciklama')}</p>
        <div className="grid gap-2 sm:grid-cols-[1fr_1fr_auto]">
          <input className={GIRDI} value={ad} onChange={(e) => setAd(e.target.value)} placeholder={t('epostaPazarlama.dizi.yeniAd')} aria-label={t('epostaPazarlama.dizi.yeniAd')} data-testid="ep-dizi-ad" />
          <select className={SECIM} value={listeId} onChange={(e) => setListeId(e.target.value)} aria-label={t('epostaPazarlama.liste.liste')} data-testid="ep-dizi-liste">
            {listeler.map((l) => (
              <option key={l.id} value={l.id}>
                {l.ad}
              </option>
            ))}
          </select>
          <Button size="sm" onClick={() => void olustur()} disabled={!ad.trim() || !listeId} className="gap-1.5" data-testid="ep-dizi-yeni">
            <Plus className="h-4 w-4" aria-hidden="true" /> {t('epostaPazarlama.dizi.yeni')}
          </Button>
        </div>
        {listeler.length === 0 && <p className="text-xs text-amber-200">{t('epostaPazarlama.dizi.listeGerekli')}</p>}
      </div>
      {diziler.length === 0 ? (
        <Bos>{t('epostaPazarlama.dizi.bos')}</Bos>
      ) : (
        <ul className="space-y-2" data-testid="ep-dizi-listesi">
          {diziler.map((d) => (
            <li key={d.id} className={`${KART} flex flex-col gap-2 p-3 sm:flex-row sm:items-center sm:justify-between`} data-dizi={d.ad}>
              <div className="min-w-0">
                <p className="flex items-center gap-2 truncate font-medium">
                  <Workflow className="h-4 w-4 shrink-0 text-purple-300" aria-hidden="true" /> {d.ad}
                </p>
                <p className="truncate text-xs text-muted-foreground">
                  {t(`epostaPazarlama.dizi.tetikler.${d.tetik}`)} · {listeler.find((l) => l.id === d.liste_id)?.ad ?? '—'} ·{' '}
                  {t('epostaPazarlama.dizi.adimSayisi', { sayi: d.adimlar.length })}
                </p>
              </div>
              <div className="flex flex-wrap items-center gap-1.5">
                <Rozet renk={d.aktif ? 'border-emerald-400/30 bg-emerald-400/10 text-emerald-200' : undefined}>
                  {d.aktif ? t('epostaPazarlama.dizi.aktif') : t('epostaPazarlama.dizi.pasif')}
                </Rozet>
                {d.kayitlar && <Rozet>{t('epostaPazarlama.dizi.kayitAktif', { sayi: d.kayitlar.aktif ?? 0 })}</Rozet>}
                <Button size="sm" variant="outline" className={DIS_DUGME} onClick={() => setSecili(d)}>
                  {t('epostaPazarlama.genel.duzenle')}
                </Button>
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function DiziDuzenle({ api, meta, listeler, dizi, geri }: { api: PazarlamaApi; meta: Meta; listeler: Liste[]; dizi: Dizi; geri: () => void }) {
  const { t, i18n } = useTranslation();
  const dil = i18n.language || 'tr';
  const [d, setD] = useState<Dizi>(dizi);
  const [acik, setAcik] = useState<number | null>(0);
  const [mesgul, setMesgul] = useState(false);
  const [rapor, setRapor] = useState<{ adimlar: { id: number; gonderilen: number; acilan: number; tiklayan: number }[]; kayitlar: Record<string, number> } | null>(null);

  useEffect(() => {
    api.diziRapor(dizi.id).then(setRapor).catch(() => setRapor(null));
  }, [api, dizi.id]);

  const adimDegis = (i: number, a: Partial<DiziAdimi>) => setD({ ...d, adimlar: d.adimlar.map((x, j) => (j === i ? { ...x, ...a } : x)) });
  const hedef = d.cikis?.hedef ?? null;
  const kaydet = async () => {
    setMesgul(true);
    try {
      const yeni = await api.diziGuncelle(d.id, {
        ad: d.ad,
        tetik: d.tetik,
        liste_id: d.liste_id,
        gonderen_adi: d.gonderen_adi,
        dil: d.dil,
        cikis: d.cikis,
        aktif: d.aktif,
        adimlar: d.adimlar,
      });
      setD(yeni);
      toast.success(t('epostaPazarlama.genel.kaydedildi'));
    } catch (e) {
      toast.error(hataMetni(t, e));
    } finally {
      setMesgul(false);
    }
  };
  const sil = async () => {
    if (!window.confirm(t('epostaPazarlama.dizi.silOnay'))) return;
    try {
      await api.diziSil(d.id);
      geri();
    } catch (e) {
      toast.error(hataMetni(t, e));
    }
  };

  return (
    <div className="space-y-4" data-testid="ep-dizi-duzenle" data-dizi-id={d.id}>
      <Button size="sm" variant="ghost" className="gap-1.5" onClick={geri}>
        <ArrowLeft className="h-4 w-4 rtl:rotate-180" aria-hidden="true" /> {t('epostaPazarlama.genel.geri')}
      </Button>
      <div className={`${KART} grid gap-3 p-4 sm:grid-cols-2`}>
        <Alan etiket={t('epostaPazarlama.dizi.ad')}>
          <input className={GIRDI} value={d.ad} onChange={(e) => setD({ ...d, ad: e.target.value })} />
        </Alan>
        <Alan etiket={t('epostaPazarlama.dizi.tetik')}>
          <select className={SECIM} value={d.tetik} onChange={(e) => setD({ ...d, tetik: e.target.value as Dizi['tetik'] })} data-testid="ep-dizi-tetik">
            {meta.tetikler.map((x) => (
              <option key={x} value={x}>
                {t(`epostaPazarlama.dizi.tetikler.${x}`)}
              </option>
            ))}
          </select>
        </Alan>
        <Alan etiket={t('epostaPazarlama.liste.liste')}>
          <select className={SECIM} value={d.liste_id ?? ''} onChange={(e) => setD({ ...d, liste_id: Number(e.target.value) })}>
            {listeler.map((l) => (
              <option key={l.id} value={l.id}>
                {l.ad}
              </option>
            ))}
          </select>
        </Alan>
        <Alan etiket={t('epostaPazarlama.dizi.cikisHedefi')} ipucu={t('epostaPazarlama.dizi.cikisIpucu')}>
          <select
            className={SECIM}
            value={hedef?.tur ?? 'yok'}
            onChange={(e) => {
              const tur = e.target.value;
              setD({
                ...d,
                cikis: {
                  hedef: tur === 'tiklama' ? { tur: 'tiklama' } : tur === 'etiket' ? { tur: 'etiket', deger: 'musteri' } : tur === 'liste' && listeler[0] ? { tur: 'liste', liste_id: listeler[0].id } : null,
                },
              });
            }}
          >
            {['yok', 'tiklama', 'etiket', 'liste'].map((x) => (
              <option key={x} value={x}>
                {t(`epostaPazarlama.dizi.hedefler.${x}`)}
              </option>
            ))}
          </select>
        </Alan>
        {hedef?.tur === 'etiket' && (
          <Alan etiket={t('epostaPazarlama.dizi.hedefEtiket')}>
            <input className={GIRDI} value={hedef.deger} onChange={(e) => setD({ ...d, cikis: { hedef: { tur: 'etiket', deger: e.target.value } } })} />
          </Alan>
        )}
        {hedef?.tur === 'liste' && (
          <Alan etiket={t('epostaPazarlama.dizi.hedefListe')}>
            <select className={SECIM} value={hedef.liste_id} onChange={(e) => setD({ ...d, cikis: { hedef: { tur: 'liste', liste_id: Number(e.target.value) } } })}>
              {listeler.map((l) => (
                <option key={l.id} value={l.id}>
                  {l.ad}
                </option>
              ))}
            </select>
          </Alan>
        )}
        <div className="sm:col-span-2">
          <Anahtar acik={d.aktif} onDegis={(v) => setD({ ...d, aktif: v })} etiket={t('epostaPazarlama.dizi.aktiflestir')} testid="ep-dizi-aktif" />
          <p className="mt-1 text-xs text-muted-foreground">{t('epostaPazarlama.dizi.retNotu')}</p>
        </div>
      </div>

      {rapor && (
        <div className="flex flex-wrap gap-1.5 text-xs">
          {Object.entries(rapor.kayitlar).map(([k, v]) => (
            <Rozet key={k}>
              {t(`epostaPazarlama.dizi.kayitDurum.${k}`, { defaultValue: k })}: {sayiYaz(v, dil)}
            </Rozet>
          ))}
        </div>
      )}

      <ol className="space-y-3" data-testid="ep-dizi-adimlar">
        {d.adimlar.map((a, i) => {
          const r = rapor?.adimlar.find((x) => x.id === a.id);
          return (
            <li key={a.id ?? `yeni-${i}`} className={`${KART} p-3`} data-adim={i}>
              <div className="flex flex-wrap items-center justify-between gap-2">
                <button type="button" className="flex min-w-0 items-center gap-2 text-start" onClick={() => setAcik(acik === i ? null : i)}>
                  {acik === i ? <ChevronUp className="h-4 w-4 shrink-0" aria-hidden="true" /> : <ChevronDown className="h-4 w-4 shrink-0" aria-hidden="true" />}
                  <span className="truncate text-sm font-medium">
                    {i + 1}. {a.konu || '—'}
                  </span>
                </button>
                <span className="flex items-center gap-1.5 text-xs text-muted-foreground">
                  <Clock className="h-3.5 w-3.5" aria-hidden="true" />
                  {t('epostaPazarlama.dizi.bekleme', { gun: a.bekle_gun, saat: a.bekle_saat })}
                  {r && <Rozet>{t('epostaPazarlama.dizi.gonderilen', { sayi: sayiYaz(r.gonderilen, dil) })}</Rozet>}
                  <Button size="sm" variant="ghost" className="h-7 px-2" onClick={() => setD({ ...d, adimlar: d.adimlar.filter((_, j) => j !== i) })}>
                    <Trash2 className="h-3.5 w-3.5" aria-hidden="true" />
                    <span className="sr-only">{t('epostaPazarlama.genel.sil')}</span>
                  </Button>
                </span>
              </div>
              {acik === i && (
                <div className="mt-3 space-y-3">
                  <div className="grid gap-3 sm:grid-cols-4">
                    <Alan etiket={t('epostaPazarlama.dizi.bekleGun')}>
                      <input className={GIRDI} type="number" min={0} max={365} value={a.bekle_gun} onChange={(e) => adimDegis(i, { bekle_gun: Number(e.target.value) })} data-testid={`ep-adim-gun-${i}`} />
                    </Alan>
                    <Alan etiket={t('epostaPazarlama.dizi.bekleSaat')}>
                      <input className={GIRDI} type="number" min={0} max={23} value={a.bekle_saat} onChange={(e) => adimDegis(i, { bekle_saat: Number(e.target.value) })} />
                    </Alan>
                    <Alan etiket={t('epostaPazarlama.kampanya.konu')} className="sm:col-span-2">
                      <input className={GIRDI} value={a.konu} onChange={(e) => adimDegis(i, { konu: e.target.value })} data-testid={`ep-adim-konu-${i}`} />
                    </Alan>
                  </div>
                  <BlokDuzenleyici
                    api={api}
                    bloklar={a.bloklar}
                    onDegis={(b) => adimDegis(i, { bloklar: b })}
                    konu={a.konu}
                    onizlemeMetni={a.onizleme_metni}
                    dil={d.dil}
                    gonderenAdi={d.gonderen_adi}
                    testid={`ep-adim-bloklar-${i}`}
                  />
                </div>
              )}
            </li>
          );
        })}
      </ol>
      <div className="flex flex-wrap gap-2">
        <Button
          size="sm"
          variant="outline"
          className={DIS_DUGME}
          onClick={() => {
            setD({ ...d, adimlar: [...d.adimlar, { bekle_gun: 2, bekle_saat: 0, konu: '', onizleme_metni: '', bloklar: sablonBloklari('bos', t) }] });
            setAcik(d.adimlar.length);
          }}
          disabled={d.adimlar.length >= 20}
          data-testid="ep-adim-ekle"
        >
          <Plus className="h-4 w-4" aria-hidden="true" /> {t('epostaPazarlama.dizi.adimEkle')}
        </Button>
        <Button size="sm" onClick={() => void kaydet()} disabled={mesgul} className="gap-1.5" data-testid="ep-dizi-kaydet">
          {mesgul ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" /> : <Save className="h-4 w-4" aria-hidden="true" />}
          {t('epostaPazarlama.genel.kaydet')}
        </Button>
        <Button size="sm" variant="ghost" onClick={() => void sil()}>
          <Trash2 className="h-4 w-4" aria-hidden="true" /> {t('epostaPazarlama.genel.sil')}
        </Button>
      </div>
    </div>
  );
}
