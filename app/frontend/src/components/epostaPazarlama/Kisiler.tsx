import { useCallback, useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Ban, FileUp, Loader2, Plus, Search, Trash2, UserPlus, Users } from 'lucide-react';
import { toast } from 'sonner';

import { Button } from '@/components/ui/button';
import { Alan, Anahtar, Bos, DIS_DUGME, GIRDI, IZIN_RENGI, KART, METIN_ALANI, Rozet, SECIM, Yukleniyor, sayiYaz } from '@/components/epostaPazarlama/ortak';
import {
  hataMetni,
  tarihYaz,
  type AliciTuru,
  type IceAktarmaOnizleme,
  type Kisi,
  type Liste,
  type Meta,
  type PazarlamaApi,
} from '@/lib/epostaPazarlama';

type Panel = null | 'ekle' | 'csv' | 'crm' | 'bastirma';

/**
 * Faz 5M — kişiler: izin durumu + kaynağı + zamanı (kanıt), alıcı türü, CSV içe aktarma
 * (izin kaynağı ve tarihi zorunlu sütun; yoksa izinsiz), CRM'den aktarma (yönetici),
 * bastırma listesi, ret ve kalıcı silme (KVKK).
 */
export default function Kisiler({ api, meta }: { api: PazarlamaApi; meta: Meta }) {
  const { t, i18n } = useTranslation();
  const dil = i18n.language || 'tr';
  const [kisiler, setKisiler] = useState<Kisi[] | null>(null);
  const [toplam, setToplam] = useState(0);
  const [listeler, setListeler] = useState<Liste[]>([]);
  const [ara, setAra] = useState('');
  const [izin, setIzin] = useState('');
  const [listeId, setListeId] = useState('');
  const [atla, setAtla] = useState(0);
  const [panel, setPanel] = useState<Panel>(null);
  const SINIR = 50;

  const yukle = useCallback(async () => {
    try {
      const [k, l] = await Promise.all([
        api.kisiler({ ara: ara.trim() || undefined, izin: izin || undefined, liste_id: listeId ? Number(listeId) : undefined, sinir: SINIR, atla }),
        api.listeler(),
      ]);
      setKisiler(k.items);
      setToplam(k.toplam);
      setListeler(l.items);
    } catch (e) {
      toast.error(hataMetni(t, e));
      setKisiler([]);
    }
  }, [api, ara, izin, listeId, atla, t]);

  useEffect(() => {
    const z = window.setTimeout(() => void yukle(), 250);
    return () => window.clearTimeout(z);
  }, [yukle]);

  const retEt = async (k: Kisi) => {
    if (!window.confirm(t('epostaPazarlama.kisi.retOnay', { eposta: k.eposta }))) return;
    try {
      await api.kisiRet(k.id);
      toast.success(t('epostaPazarlama.kisi.retEdildi'));
      void yukle();
    } catch (e) {
      toast.error(hataMetni(t, e));
    }
  };
  const sil = async (k: Kisi) => {
    if (!window.confirm(t('epostaPazarlama.kisi.silOnay', { eposta: k.eposta }))) return;
    try {
      await api.kisiSil(k.id);
      toast.success(t('epostaPazarlama.kisi.silindi'));
      void yukle();
    } catch (e) {
      toast.error(hataMetni(t, e));
    }
  };

  return (
    <div className="space-y-4" data-testid="ep-kisiler">
      <div className="flex flex-wrap gap-2">
        <Button size="sm" onClick={() => setPanel(panel === 'ekle' ? null : 'ekle')} className="gap-1.5" data-testid="ep-kisi-ekle-ac">
          <UserPlus className="h-4 w-4" aria-hidden="true" /> {t('epostaPazarlama.kisi.ekle')}
        </Button>
        <Button size="sm" variant="outline" className={DIS_DUGME} onClick={() => setPanel(panel === 'csv' ? null : 'csv')} data-testid="ep-csv-ac">
          <FileUp className="h-4 w-4" aria-hidden="true" /> {t('epostaPazarlama.csv.baslik')}
        </Button>
        {meta.yonetici && (
          <Button size="sm" variant="outline" className={DIS_DUGME} onClick={() => setPanel(panel === 'crm' ? null : 'crm')}>
            <Users className="h-4 w-4" aria-hidden="true" /> {t('epostaPazarlama.crm.baslik')}
          </Button>
        )}
        <Button size="sm" variant="outline" className={DIS_DUGME} onClick={() => setPanel(panel === 'bastirma' ? null : 'bastirma')} data-testid="ep-bastirma-ac">
          <Ban className="h-4 w-4" aria-hidden="true" /> {t('epostaPazarlama.bastirma.baslik')}
        </Button>
      </div>

      {panel === 'ekle' && <KisiFormu api={api} listeler={listeler} kapat={() => setPanel(null)} bitti={yukle} />}
      {panel === 'csv' && <CsvAktar api={api} listeler={listeler} bitti={yukle} />}
      {panel === 'crm' && <CrmAktar api={api} listeler={listeler} bitti={yukle} />}
      {panel === 'bastirma' && <Bastirma api={api} />}

      <div className={`${KART} p-4`}>
        <div className="mb-3 grid gap-2 sm:grid-cols-[1fr_auto_auto]">
          <label className="relative min-w-0">
            <Search className="pointer-events-none absolute start-3 top-3 h-4 w-4 text-muted-foreground" aria-hidden="true" />
            <input
              className={`${GIRDI} ps-9`}
              placeholder={t('epostaPazarlama.kisi.ara')}
              value={ara}
              onChange={(e) => {
                setAtla(0);
                setAra(e.target.value);
              }}
              aria-label={t('epostaPazarlama.kisi.ara')}
              data-testid="ep-kisi-ara"
            />
          </label>
          <select className={SECIM} value={izin} onChange={(e) => { setAtla(0); setIzin(e.target.value); }} aria-label={t('epostaPazarlama.kisi.izinDurumu')}>
            <option value="">{t('epostaPazarlama.kisi.tumIzinler')}</option>
            {(['izinli', 'izinsiz', 'bekliyor', 'reddetti'] as const).map((d) => (
              <option key={d} value={d}>
                {t(`epostaPazarlama.izin.${d}`)}
              </option>
            ))}
          </select>
          <select className={SECIM} value={listeId} onChange={(e) => { setAtla(0); setListeId(e.target.value); }} aria-label={t('epostaPazarlama.liste.liste')}>
            <option value="">{t('epostaPazarlama.kisi.tumListeler')}</option>
            {listeler.map((l) => (
              <option key={l.id} value={l.id}>
                {l.ad}
              </option>
            ))}
          </select>
        </div>
        {kisiler === null ? (
          <Yukleniyor />
        ) : kisiler.length === 0 ? (
          <Bos testid="ep-kisi-bos">{t('epostaPazarlama.kisi.bos')}</Bos>
        ) : (
          <>
            <ul className="divide-y divide-white/5" data-testid="ep-kisi-listesi">
              {kisiler.map((k) => (
                <li key={k.id} className="flex flex-col gap-2 py-3 sm:flex-row sm:items-center sm:justify-between" data-kisi={k.eposta}>
                  <div className="min-w-0">
                    <p className="truncate text-sm font-medium">{k.ad || k.eposta}</p>
                    <p className="truncate text-xs text-muted-foreground">
                      {k.ad ? `${k.eposta} · ` : ''}
                      {t(`epostaPazarlama.kaynak.${k.kaynak}`, { defaultValue: k.kaynak })}
                      {k.izin_zamani ? ` · ${tarihYaz(k.izin_zamani, dil)}` : ''}
                    </p>
                    {k.izin_kaynagi && <p className="truncate text-[11px] text-muted-foreground">{t('epostaPazarlama.kisi.kaynakEtiket', { kaynak: k.izin_kaynagi })}</p>}
                  </div>
                  <div className="flex flex-wrap items-center gap-1.5">
                    <Rozet renk={IZIN_RENGI[k.izin_durumu]} testid="ep-kisi-izin">{t(`epostaPazarlama.izin.${k.izin_durumu}`)}</Rozet>
                    <Rozet>{t(`epostaPazarlama.tur.${k.alici_turu}`)}</Rozet>
                    {k.bastirilmis && <Rozet renk={IZIN_RENGI.reddetti}>{t('epostaPazarlama.kisi.bastirildi')}</Rozet>}
                    {k.izin_durumu !== 'reddetti' && (
                      <Button size="sm" variant="ghost" className="h-8 px-2 text-xs" onClick={() => void retEt(k)} title={t('epostaPazarlama.kisi.retEt')}>
                        <Ban className="h-3.5 w-3.5" aria-hidden="true" />
                        <span className="sr-only">{t('epostaPazarlama.kisi.retEt')}</span>
                      </Button>
                    )}
                    <Button size="sm" variant="ghost" className="h-8 px-2 text-xs" onClick={() => void sil(k)} title={t('epostaPazarlama.genel.sil')}>
                      <Trash2 className="h-3.5 w-3.5" aria-hidden="true" />
                      <span className="sr-only">{t('epostaPazarlama.genel.sil')}</span>
                    </Button>
                  </div>
                </li>
              ))}
            </ul>
            <div className="mt-3 flex flex-wrap items-center justify-between gap-2 text-xs text-muted-foreground">
              <span>{t('epostaPazarlama.kisi.toplam', { sayi: sayiYaz(toplam, dil) })}</span>
              <span className="flex gap-2">
                <Button size="sm" variant="outline" className={DIS_DUGME} disabled={atla === 0} onClick={() => setAtla(Math.max(0, atla - SINIR))}>
                  {t('epostaPazarlama.genel.onceki')}
                </Button>
                <Button size="sm" variant="outline" className={DIS_DUGME} disabled={atla + SINIR >= toplam} onClick={() => setAtla(atla + SINIR)}>
                  {t('epostaPazarlama.genel.sonraki')}
                </Button>
              </span>
            </div>
          </>
        )}
      </div>
    </div>
  );
}

function KisiFormu({ api, listeler, kapat, bitti }: { api: PazarlamaApi; listeler: Liste[]; kapat: () => void; bitti: () => void }) {
  const { t } = useTranslation();
  const [eposta, setEposta] = useState('');
  const [ad, setAd] = useState('');
  const [firma, setFirma] = useState('');
  const [tur, setTur] = useState<AliciTuru>('bireysel');
  const [izinli, setIzinli] = useState(false);
  const [kaynak, setKaynak] = useState('');
  const [zaman, setZaman] = useState('');
  const [kanit, setKanit] = useState('');
  const [secili, setSecili] = useState<number[]>([]);
  const [etiketler, setEtiketler] = useState('');
  const [kaydediliyor, setKaydediliyor] = useState(false);

  const kaydet = async () => {
    setKaydediliyor(true);
    try {
      await api.kisiEkle({
        eposta,
        ad,
        firma,
        alici_turu: tur,
        etiketler,
        listeler: secili,
        ...(izinli ? { izin: { durum: 'izinli', kaynak, zaman: zaman ? new Date(zaman).toISOString() : '', kanit } } : {}),
      });
      toast.success(t('epostaPazarlama.kisi.eklendi'));
      kapat();
      bitti();
    } catch (e) {
      toast.error(hataMetni(t, e));
    } finally {
      setKaydediliyor(false);
    }
  };

  return (
    <div className={`${KART} space-y-3 p-4`} data-testid="ep-kisi-formu">
      <div className="grid gap-3 sm:grid-cols-2">
        <Alan etiket={t('epostaPazarlama.kisi.eposta')}>
          <input className={GIRDI} type="email" value={eposta} onChange={(e) => setEposta(e.target.value)} data-testid="ep-kisi-eposta" />
        </Alan>
        <Alan etiket={t('epostaPazarlama.kisi.ad')}>
          <input className={GIRDI} value={ad} onChange={(e) => setAd(e.target.value)} data-testid="ep-kisi-ad" />
        </Alan>
        <Alan etiket={t('epostaPazarlama.kisi.firma')}>
          <input className={GIRDI} value={firma} onChange={(e) => setFirma(e.target.value)} />
        </Alan>
        <Alan etiket={t('epostaPazarlama.kisi.aliciTuru')} ipucu={t('epostaPazarlama.kisi.aliciTuruIpucu')}>
          <select className={SECIM} value={tur} onChange={(e) => setTur(e.target.value as AliciTuru)} data-testid="ep-kisi-tur">
            <option value="bireysel">{t('epostaPazarlama.tur.bireysel')}</option>
            <option value="kurumsal">{t('epostaPazarlama.tur.kurumsal')}</option>
          </select>
        </Alan>
        <Alan etiket={t('epostaPazarlama.kisi.etiketler')} ipucu={t('epostaPazarlama.kisi.etiketIpucu')}>
          <input className={GIRDI} value={etiketler} onChange={(e) => setEtiketler(e.target.value)} />
        </Alan>
      </div>
      {listeler.length > 0 && (
        <div className="flex flex-wrap gap-3">
          {listeler.map((l) => (
            <Anahtar
              key={l.id}
              acik={secili.includes(l.id)}
              onDegis={(v) => setSecili(v ? [...secili, l.id] : secili.filter((x) => x !== l.id))}
              etiket={l.ad}
              testid={`ep-kisi-liste-${l.id}`}
            />
          ))}
        </div>
      )}
      <div className="rounded-xl border border-white/10 p-3">
        <Anahtar acik={izinli} onDegis={setIzinli} etiket={t('epostaPazarlama.kisi.izinVar')} testid="ep-kisi-izinli" />
        <p className="mt-1 text-xs text-muted-foreground">{t('epostaPazarlama.kisi.izinIpucu')}</p>
        {izinli && (
          <div className="mt-3 grid gap-3 sm:grid-cols-2">
            <Alan etiket={t('epostaPazarlama.kisi.izinKaynagi')}>
              <input className={GIRDI} value={kaynak} onChange={(e) => setKaynak(e.target.value)} data-testid="ep-kisi-izin-kaynagi" />
            </Alan>
            <Alan etiket={t('epostaPazarlama.kisi.izinTarihi')}>
              <input className={GIRDI} type="datetime-local" value={zaman} onChange={(e) => setZaman(e.target.value)} data-testid="ep-kisi-izin-zamani" />
            </Alan>
            <Alan etiket={t('epostaPazarlama.kisi.kanit')} className="sm:col-span-2">
              <textarea className={METIN_ALANI} value={kanit} onChange={(e) => setKanit(e.target.value)} />
            </Alan>
          </div>
        )}
      </div>
      <div className="flex flex-wrap gap-2">
        <Button size="sm" onClick={() => void kaydet()} disabled={kaydediliyor || !eposta.trim()} className="gap-1.5" data-testid="ep-kisi-kaydet">
          {kaydediliyor ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" /> : <Plus className="h-4 w-4" aria-hidden="true" />}
          {t('epostaPazarlama.genel.kaydet')}
        </Button>
        <Button size="sm" variant="ghost" onClick={kapat}>
          {t('epostaPazarlama.genel.iptal')}
        </Button>
      </div>
    </div>
  );
}

function CsvAktar({ api, listeler, bitti }: { api: PazarlamaApi; listeler: Liste[]; bitti: () => void }) {
  const { t, i18n } = useTranslation();
  const dil = i18n.language || 'tr';
  const [dosya, setDosya] = useState<File | null>(null);
  const [tur, setTur] = useState<AliciTuru>('bireysel');
  const [listeId, setListeId] = useState('');
  const [not, setNot] = useState('');
  const [onizleme, setOnizleme] = useState<IceAktarmaOnizleme | null>(null);
  const [onay, setOnay] = useState(false);
  const [mesgul, setMesgul] = useState(false);

  const onizle = async (f: File) => {
    setDosya(f);
    setOnizleme(null);
    setMesgul(true);
    try {
      setOnizleme(await api.iceAktarOnizleme(f, tur));
    } catch (e) {
      toast.error(hataMetni(t, e));
    } finally {
      setMesgul(false);
    }
  };
  const aktar = async () => {
    if (!dosya) return;
    setMesgul(true);
    try {
      const s = await api.iceAktar(dosya, { liste_id: listeId ? Number(listeId) : null, varsayilan_tur: tur, kaynak_notu: not });
      toast.success(t('epostaPazarlama.csv.bitti', { eklenen: s.sayilar.eklenen, guncellenen: s.sayilar.guncellenen }));
      setDosya(null);
      setOnizleme(null);
      bitti();
    } catch (e) {
      toast.error(hataMetni(t, e));
    } finally {
      setMesgul(false);
    }
  };

  return (
    <div className={`${KART} space-y-3 p-4`} data-testid="ep-csv">
      <p className="text-sm text-muted-foreground">{t('epostaPazarlama.csv.aciklama')}</p>
      <p className="rounded-lg border border-amber-400/30 bg-amber-400/10 px-3 py-2 text-xs text-amber-100">{t('epostaPazarlama.csv.uyari')}</p>
      <code className="block overflow-x-auto whitespace-nowrap rounded-md bg-black/40 px-3 py-2 text-xs">eposta;ad;firma;alici_turu;izin_kaynagi;izin_tarihi;etiketler</code>
      <div className="grid gap-3 sm:grid-cols-3">
        <Alan etiket={t('epostaPazarlama.csv.varsayilanTur')}>
          <select className={SECIM} value={tur} onChange={(e) => setTur(e.target.value as AliciTuru)}>
            <option value="bireysel">{t('epostaPazarlama.tur.bireysel')}</option>
            <option value="kurumsal">{t('epostaPazarlama.tur.kurumsal')}</option>
          </select>
        </Alan>
        <Alan etiket={t('epostaPazarlama.liste.liste')}>
          <select className={SECIM} value={listeId} onChange={(e) => setListeId(e.target.value)}>
            <option value="">{t('epostaPazarlama.csv.listesiz')}</option>
            {listeler.map((l) => (
              <option key={l.id} value={l.id}>
                {l.ad}
              </option>
            ))}
          </select>
        </Alan>
        <Alan etiket={t('epostaPazarlama.csv.not')}>
          <input className={GIRDI} value={not} onChange={(e) => setNot(e.target.value)} />
        </Alan>
      </div>
      <input
        type="file"
        accept=".csv,text/csv"
        className="block w-full text-sm text-muted-foreground file:me-3 file:rounded-md file:border-0 file:bg-white/10 file:px-3 file:py-2 file:text-white"
        onChange={(e) => e.target.files?.[0] && void onizle(e.target.files[0])}
        aria-label={t('epostaPazarlama.csv.dosya')}
      />
      {mesgul && <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />}
      {onizleme && (
        <div className="space-y-2 text-sm">
          <ul className="grid grid-cols-2 gap-2 sm:grid-cols-4">
            {(['gecerli', 'izinli', 'izinsiz_bireysel', 'hatali'] as const).map((k) => (
              <li key={k} className="rounded-lg border border-white/10 px-3 py-2">
                <span className="block text-xs text-muted-foreground">{t(`epostaPazarlama.csv.ozet.${k}`)}</span>
                <span className="text-lg font-semibold">{sayiYaz(onizleme.ozet[k], dil)}</span>
              </li>
            ))}
          </ul>
          {onizleme.ozet.izinsiz_bireysel > 0 && (
            <p className="text-xs text-amber-200">{t('epostaPazarlama.csv.izinsizUyari', { sayi: onizleme.ozet.izinsiz_bireysel })}</p>
          )}
          <Anahtar acik={onay} onDegis={setOnay} etiket={t('epostaPazarlama.csv.beyan')} />
          <Button size="sm" disabled={!onay || mesgul} onClick={() => void aktar()}>
            {t('epostaPazarlama.csv.aktar')}
          </Button>
        </div>
      )}
    </div>
  );
}

function CrmAktar({ api, listeler, bitti }: { api: PazarlamaApi; listeler: Liste[]; bitti: () => void }) {
  const { t } = useTranslation();
  const [listeId, setListeId] = useState('');
  const [yalnizIzinli, setYalnizIzinli] = useState(true);
  const [tur, setTur] = useState<AliciTuru>('bireysel');
  const [mesgul, setMesgul] = useState(false);
  const aktar = async () => {
    setMesgul(true);
    try {
      const s = await api.crmAktar({ liste_id: listeId ? Number(listeId) : null, alici_turu: tur, yalniz_izinli: yalnizIzinli });
      toast.success(t('epostaPazarlama.crm.bitti', { eklenen: s.sayilar.eklenen, izinli: s.sayilar.izinli }));
      bitti();
    } catch (e) {
      toast.error(hataMetni(t, e));
    } finally {
      setMesgul(false);
    }
  };
  return (
    <div className={`${KART} space-y-3 p-4`}>
      <p className="text-sm text-muted-foreground">{t('epostaPazarlama.crm.aciklama')}</p>
      <div className="grid gap-3 sm:grid-cols-2">
        <Alan etiket={t('epostaPazarlama.liste.liste')}>
          <select className={SECIM} value={listeId} onChange={(e) => setListeId(e.target.value)}>
            <option value="">{t('epostaPazarlama.csv.listesiz')}</option>
            {listeler.map((l) => (
              <option key={l.id} value={l.id}>
                {l.ad}
              </option>
            ))}
          </select>
        </Alan>
        <Alan etiket={t('epostaPazarlama.kisi.aliciTuru')}>
          <select className={SECIM} value={tur} onChange={(e) => setTur(e.target.value as AliciTuru)}>
            <option value="bireysel">{t('epostaPazarlama.tur.bireysel')}</option>
            <option value="kurumsal">{t('epostaPazarlama.tur.kurumsal')}</option>
          </select>
        </Alan>
      </div>
      <Anahtar acik={yalnizIzinli} onDegis={setYalnizIzinli} etiket={t('epostaPazarlama.crm.yalnizIzinli')} />
      <Button size="sm" onClick={() => void aktar()} disabled={mesgul}>
        {t('epostaPazarlama.crm.aktar')}
      </Button>
    </div>
  );
}

function Bastirma({ api }: { api: PazarlamaApi }) {
  const { t, i18n } = useTranslation();
  const dil = i18n.language || 'tr';
  const [kayitlar, setKayitlar] = useState<{ id: number; eposta: string; neden: string; created_at: string | null }[] | null>(null);
  const [eposta, setEposta] = useState('');
  const yukle = useCallback(async () => {
    try {
      setKayitlar((await api.bastirma()).items);
    } catch (e) {
      toast.error(hataMetni(t, e));
    }
  }, [api, t]);
  useEffect(() => {
    void yukle();
  }, [yukle]);
  const ekle = async () => {
    try {
      await api.bastirmaEkle(eposta);
      setEposta('');
      void yukle();
    } catch (e) {
      toast.error(hataMetni(t, e));
    }
  };
  const sil = async (id: number) => {
    try {
      await api.bastirmaSil(id);
      void yukle();
    } catch (e) {
      toast.error(hataMetni(t, e));
    }
  };
  return (
    <div className={`${KART} space-y-3 p-4`} data-testid="ep-bastirma">
      <p className="text-sm text-muted-foreground">{t('epostaPazarlama.bastirma.aciklama')}</p>
      <div className="flex flex-col gap-2 sm:flex-row">
        <input className={GIRDI} type="email" value={eposta} onChange={(e) => setEposta(e.target.value)} placeholder="ornek@ornek.com" aria-label={t('epostaPazarlama.kisi.eposta')} />
        <Button size="sm" onClick={() => void ekle()} disabled={!eposta.trim()} className="shrink-0">
          {t('epostaPazarlama.bastirma.ekle')}
        </Button>
      </div>
      {kayitlar === null ? (
        <Yukleniyor />
      ) : kayitlar.length === 0 ? (
        <Bos>{t('epostaPazarlama.bastirma.bos')}</Bos>
      ) : (
        <ul className="divide-y divide-white/5 text-sm">
          {kayitlar.map((b) => (
            <li key={b.id} className="flex flex-wrap items-center justify-between gap-2 py-2">
              <span className="min-w-0 truncate">{b.eposta}</span>
              <span className="flex items-center gap-2 text-xs text-muted-foreground">
                {tarihYaz(b.created_at, dil)}
                <Rozet>{t(`epostaPazarlama.bastirma.neden.${b.neden}`)}</Rozet>
                {b.neden === 'elle' && (
                  <Button size="sm" variant="ghost" className="h-7 px-2" onClick={() => void sil(b.id)}>
                    <Trash2 className="h-3.5 w-3.5" aria-hidden="true" />
                    <span className="sr-only">{t('epostaPazarlama.genel.sil')}</span>
                  </Button>
                )}
              </span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
