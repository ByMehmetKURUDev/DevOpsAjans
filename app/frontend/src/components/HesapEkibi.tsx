import { useCallback, useEffect, useState, type FormEvent } from 'react';
import { Copy, Loader2, MailPlus, RefreshCw, Save, Trash2, UserMinus, UserCheck, Users } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';

import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import {
  EkipHatasi,
  davetiYenile,
  uyeDavetEt,
  uyeGuncelle,
  uyeleriGetir,
  uyeSil,
  type DavetYaniti,
  type HesapUyesi,
  type Izin,
  type UyeListesi,
  type UyeRolu,
} from '@/lib/hesapEkibi';

/**
 * Faz 2E — "Ekip": hesaptaki kişiler, davet, rol/izin, pasif/sil, davet yenile.
 *
 * İki yerde kullanılıyor:
 *  * Müşteri paneli › Profil (etkin hesap; sahip ve hesap yöneticisi düzenler,
 *    `uye`/`fatura` rolü salt okunur görür),
 *  * Yönetici paneli › Müşteriler (`hesapEmail` verilir; ajans müşteri adına yönetir).
 * Sunucu her işlemi kendisi de denetliyor; buradaki gizleme yalnız düzen için.
 */

const ROLLER: UyeRolu[] = ['uye', 'fatura', 'yonetici'];
const SECIM =
  'h-10 rounded-md border border-white/10 bg-white/5 px-3 text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-purple-500/40';

function DurumRozeti({ durum }: { durum: HesapUyesi['durum'] }) {
  const { t } = useTranslation();
  const renk =
    durum === 'aktif'
      ? 'border-emerald-400/30 bg-emerald-500/10 text-emerald-300'
      : durum === 'davet'
        ? 'border-sky-400/30 bg-sky-500/10 text-sky-300'
        : 'border-white/15 bg-white/5 text-muted-foreground';
  return (
    <span className={`rounded-full border px-2 py-0.5 text-[10px] uppercase tracking-widest ${renk}`} data-durum={durum}>
      {t(`hesapEkibi.durum.${durum}`)}
    </span>
  );
}

function IzinKutulari({
  izinler,
  secili,
  kullanilabilir,
  pasif,
  onDegis,
  onEk,
}: {
  izinler: Izin[];
  secili: Izin[];
  kullanilabilir: Izin[];
  pasif: boolean;
  onDegis: (yeni: Izin[]) => void;
  onEk: string;
}) {
  const { t } = useTranslation();
  return (
    <div className="flex flex-wrap gap-2">
      {izinler.map((izin) => {
        const isaretli = secili.includes(izin);
        const kapali = pasif || (!kullanilabilir.includes(izin) && !isaretli);
        return (
          <label
            key={izin}
            className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs ${
              isaretli ? 'border-purple-400/50 bg-purple-500/15 text-white' : 'border-white/10 text-muted-foreground'
            } ${kapali ? 'opacity-60' : 'cursor-pointer'}`}
          >
            <input
              type="checkbox"
              className="h-3.5 w-3.5 accent-purple-500"
              data-izin={`${onEk}-${izin}`}
              checked={isaretli}
              disabled={kapali}
              onChange={(e) =>
                onDegis(e.target.checked ? izinler.filter((i) => i === izin || secili.includes(i)) : secili.filter((i) => i !== izin))
              }
            />
            {t(`hesapEkibi.izin.${izin}`)}
          </label>
        );
      })}
    </div>
  );
}

export default function HesapEkibi({ hesapEmail }: { hesapEmail?: string }) {
  const { t, i18n } = useTranslation();
  const [liste, setListe] = useState<UyeListesi | null>(null);
  const [yukleniyor, setYukleniyor] = useState(true);
  const [hata, setHata] = useState('');
  const [calisan, setCalisan] = useState<string>('');
  const [form, setForm] = useState<{ email: string; rol: UyeRolu; izinler: Izin[] | null }>({
    email: '',
    rol: 'uye',
    izinler: null,
  });
  const [sonDavet, setSonDavet] = useState<DavetYaniti | null>(null);
  const [duzenleme, setDuzenleme] = useState<Record<number, { rol: UyeRolu; izinler: Izin[] }>>({});

  const hataMetni = useCallback(
    (h: unknown) => {
      const kod = h instanceof EkipHatasi ? h.kod : 'genel';
      return t(`hesapEkibi.hata.${kod}`, { defaultValue: t('hesapEkibi.hata.genel') });
    },
    [t]
  );

  const yukle = useCallback(async () => {
    setYukleniyor(true);
    setHata('');
    try {
      setListe(await uyeleriGetir(hesapEmail));
      setDuzenleme({});
    } catch (h) {
      setHata(hataMetni(h));
    } finally {
      setYukleniyor(false);
    }
  }, [hesapEmail, hataMetni]);

  useEffect(() => {
    void yukle();
  }, [yukle]);

  const tarih = (deger?: string | null) => {
    if (!deger) return '—';
    try {
      return new Date(deger).toLocaleString(i18n.language || 'tr', { dateStyle: 'medium', timeStyle: 'short' });
    } catch {
      return deger;
    }
  };

  const islem = async (anahtar: string, is: () => Promise<unknown>, basari: string) => {
    setCalisan(anahtar);
    try {
      await is();
      toast.success(basari);
      await yukle();
    } catch (h) {
      toast.error(hataMetni(h));
    } finally {
      setCalisan('');
    }
  };

  const davetGonder = async (e: FormEvent) => {
    e.preventDefault();
    if (!liste) return;
    setCalisan('davet');
    try {
      const yanit = await uyeDavetEt(
        { email: form.email.trim(), rol: form.rol, ...(form.izinler ? { izinler: form.izinler } : {}) },
        hesapEmail
      );
      setSonDavet(yanit);
      setForm({ email: '', rol: 'uye', izinler: null });
      toast.success(t('hesapEkibi.ekip.davetGonderildi'));
      await yukle();
    } catch (h) {
      toast.error(hataMetni(h));
    } finally {
      setCalisan('');
    }
  };

  const kopyala = async (metin: string) => {
    try {
      await navigator.clipboard.writeText(metin);
      toast.success(t('hesapEkibi.ekip.kopyalandi'));
    } catch {
      /* pano izni yok: bağlantı ekranda seçilebilir duruyor */
    }
  };

  if (yukleniyor && !liste) {
    return (
      <div className="flex items-center gap-2 py-6 text-sm text-muted-foreground">
        <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" /> {t('hesapEkibi.ekip.yukleniyor')}
      </div>
    );
  }
  if (!liste) {
    return (
      <div className="rounded-xl border border-destructive/30 bg-destructive/10 p-4 text-sm text-destructive">
        {hata || t('hesapEkibi.hata.genel')}
        <Button size="sm" variant="outline" className="ms-3 !bg-transparent border-white/20" onClick={() => void yukle()}>
          {t('hesapEkibi.ekip.yenile')}
        </Button>
      </div>
    );
  }

  const yonetebilir = liste.yonetebilir;
  const kullanilabilir = liste.izinlerim;
  const formIzinleri = form.izinler ?? liste.roller[form.rol] ?? [];

  return (
    <div
      className={hesapEmail ? 'space-y-4' : 'cam-kart max-w-3xl rounded-2xl border border-white/10 bg-white/[0.03] p-6 space-y-5'}
      data-hesap-ekibi
    >
      {!hesapEmail && (
        <div>
          <h3 className="flex items-center gap-2 text-lg font-semibold">
            <Users className="h-5 w-5 text-purple-300" aria-hidden="true" /> {t('hesapEkibi.ekip.baslik')}
          </h3>
          <p className="mt-1 text-sm text-muted-foreground">{t('hesapEkibi.ekip.aciklama')}</p>
        </div>
      )}
      {hesapEmail && <p className="text-xs text-muted-foreground">{t('hesapEkibi.ekip.yoneticiAciklama')}</p>}
      {!yonetebilir && (
        <p className="rounded-lg border border-white/10 bg-white/[0.03] px-3 py-2 text-xs text-muted-foreground" data-salt-okunur>
          {t('hesapEkibi.ekip.saltOkunur')}
        </p>
      )}

      <ul className="divide-y divide-white/10 rounded-xl border border-white/10">
        <li className="flex flex-wrap items-center justify-between gap-2 px-4 py-3 text-sm">
          <span className="font-medium">{liste.hesap_adi || liste.hesap_email}</span>
          <span className="text-xs text-muted-foreground">
            {t('hesapEkibi.ekip.sahipSatiri')} · {liste.hesap_email}
          </span>
        </li>
        {liste.uyeler.length === 0 && (
          <li className="px-4 py-4 text-sm text-muted-foreground">{t('hesapEkibi.ekip.bos')}</li>
        )}
        {liste.uyeler.map((u) => {
          const ben = u.uye_email === liste.ben;
          const d = duzenleme[u.id] ?? { rol: u.rol, izinler: u.izinler };
          const degisti = d.rol !== u.rol || d.izinler.join(',') !== u.izinler.join(',');
          const duzenlenebilir = yonetebilir && !ben;
          return (
            <li key={u.id} className="space-y-3 px-4 py-4" data-uye={u.uye_email}>
              <div className="flex flex-wrap items-center gap-2">
                <span className="font-medium break-all">{u.uye_email}</span>
                {ben && <span className="text-xs text-muted-foreground">({t('hesapEkibi.ekip.sen')})</span>}
                <DurumRozeti durum={u.durum} />
                <span className="ms-auto text-xs text-muted-foreground">
                  {u.durum === 'davet' || u.durum === 'suresi_doldu'
                    ? t('hesapEkibi.ekip.davetBitis', { tarih: tarih(u.davet_bitis) })
                    : u.son_kullanim
                      ? t('hesapEkibi.ekip.sonKullanim', { tarih: tarih(u.son_kullanim) })
                      : t('hesapEkibi.ekip.hicKullanmadi')}
                </span>
              </div>
              <div className="flex flex-wrap items-center gap-3">
                <select
                  aria-label={t('hesapEkibi.ekip.rol')}
                  data-rol-sec={u.uye_email}
                  className={SECIM}
                  value={d.rol}
                  disabled={!duzenlenebilir}
                  onChange={(e) => {
                    const rol = e.target.value as UyeRolu;
                    setDuzenleme((x) => ({ ...x, [u.id]: { rol, izinler: liste.roller[rol] ?? [] } }));
                  }}
                >
                  {ROLLER.map((r) => (
                    <option key={r} value={r} className="bg-background">
                      {t(`hesapEkibi.rol.${r}`)}
                    </option>
                  ))}
                </select>
                <span className="text-xs text-muted-foreground">{t(`hesapEkibi.rolAciklama.${d.rol}`)}</span>
              </div>
              <IzinKutulari
                izinler={liste.izinler}
                secili={d.izinler}
                kullanilabilir={kullanilabilir}
                pasif={!duzenlenebilir}
                onDegis={(izinler) => setDuzenleme((x) => ({ ...x, [u.id]: { rol: d.rol, izinler } }))}
                onEk={u.uye_email}
              />
              {duzenlenebilir && (
                <div className="flex flex-wrap gap-2">
                  {degisti && (
                    <Button
                      size="sm"
                      disabled={!!calisan}
                      className="gap-1.5 bg-gradient-to-r from-purple-600 to-pink-600 text-white border-0"
                      onClick={() =>
                        void islem(`k${u.id}`, () => uyeGuncelle(u.id, { rol: d.rol, izinler: d.izinler }, hesapEmail), t('hesapEkibi.ekip.guncellendi'))
                      }
                    >
                      {calisan === `k${u.id}` ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Save className="h-3.5 w-3.5" />}
                      {t('hesapEkibi.ekip.kaydet')}
                    </Button>
                  )}
                  {(u.durum === 'aktif' || u.durum === 'pasif') && (
                    <Button
                      size="sm"
                      variant="outline"
                      disabled={!!calisan}
                      className="gap-1.5 !bg-transparent border-white/20"
                      data-durum-degis={u.uye_email}
                      onClick={() =>
                        void islem(
                          `d${u.id}`,
                          () => uyeGuncelle(u.id, { durum: u.durum === 'aktif' ? 'pasif' : 'aktif' }, hesapEmail),
                          t('hesapEkibi.ekip.guncellendi')
                        )
                      }
                    >
                      {u.durum === 'aktif' ? <UserMinus className="h-3.5 w-3.5" /> : <UserCheck className="h-3.5 w-3.5" />}
                      {u.durum === 'aktif' ? t('hesapEkibi.ekip.pasifYap') : t('hesapEkibi.ekip.aktifYap')}
                    </Button>
                  )}
                  {(u.durum === 'davet' || u.durum === 'suresi_doldu') && (
                    <Button
                      size="sm"
                      variant="outline"
                      disabled={!!calisan}
                      className="gap-1.5 !bg-transparent border-white/20"
                      onClick={async () => {
                        setCalisan(`y${u.id}`);
                        try {
                          setSonDavet(await davetiYenile(u.id, hesapEmail));
                          toast.success(t('hesapEkibi.ekip.yenilendi'));
                          await yukle();
                        } catch (h) {
                          toast.error(hataMetni(h));
                        } finally {
                          setCalisan('');
                        }
                      }}
                    >
                      <RefreshCw className="h-3.5 w-3.5" /> {t('hesapEkibi.ekip.davetYenile')}
                    </Button>
                  )}
                  <Button
                    size="sm"
                    variant="ghost"
                    disabled={!!calisan}
                    className="gap-1.5 text-destructive hover:text-destructive"
                    data-uye-sil={u.uye_email}
                    onClick={() => {
                      if (!window.confirm(t('hesapEkibi.ekip.silOnay', { eposta: u.uye_email }))) return;
                      void islem(`s${u.id}`, () => uyeSil(u.id, hesapEmail), t('hesapEkibi.ekip.silindi'));
                    }}
                  >
                    <Trash2 className="h-3.5 w-3.5" /> {t('hesapEkibi.ekip.sil')}
                  </Button>
                </div>
              )}
            </li>
          );
        })}
      </ul>

      {sonDavet && (
        <div className="space-y-2 rounded-xl border border-purple-400/30 bg-purple-500/10 p-4 text-sm" data-davet-baglantisi>
          {sonDavet.eposta_durumu !== 'sent' && <p className="text-amber-200">{t('hesapEkibi.ekip.epostaGitmedi')}</p>}
          <p className="text-muted-foreground">{t('hesapEkibi.ekip.baglantiAciklama')}</p>
          <div className="flex flex-wrap items-center gap-2">
            <code className="min-w-0 flex-1 break-all rounded bg-black/30 px-2 py-1 text-xs" data-davet-adresi>
              {sonDavet.baglanti}
            </code>
            <Button size="sm" variant="outline" className="gap-1.5 !bg-transparent border-white/20" onClick={() => void kopyala(sonDavet.baglanti)}>
              <Copy className="h-3.5 w-3.5" /> {t('hesapEkibi.ekip.baglantiKopyala')}
            </Button>
          </div>
        </div>
      )}

      {yonetebilir && (
        <form onSubmit={davetGonder} className="space-y-3 rounded-xl border border-white/10 p-4" data-davet-formu>
          <h4 className="flex items-center gap-2 text-sm font-semibold">
            <MailPlus className="h-4 w-4 text-purple-300" aria-hidden="true" /> {t('hesapEkibi.ekip.davetEt')}
          </h4>
          <div className="flex flex-wrap gap-3">
            <label className="min-w-[14rem] flex-1">
              <span className="mb-1 block text-xs uppercase tracking-widest text-muted-foreground">{t('hesapEkibi.ekip.eposta')}</span>
              <Input
                type="email"
                required
                data-testid="davet-eposta"
                value={form.email}
                placeholder={t('hesapEkibi.ekip.epostaOrnek')}
                onChange={(e) => setForm((f) => ({ ...f, email: e.target.value }))}
                className="bg-white/5 border-white/10"
              />
            </label>
            <label>
              <span className="mb-1 block text-xs uppercase tracking-widest text-muted-foreground">{t('hesapEkibi.ekip.rol')}</span>
              <select
                data-testid="davet-rol"
                className={SECIM}
                value={form.rol}
                onChange={(e) => setForm((f) => ({ ...f, rol: e.target.value as UyeRolu, izinler: null }))}
              >
                {ROLLER.map((r) => (
                  <option key={r} value={r} className="bg-background">
                    {t(`hesapEkibi.rol.${r}`)}
                  </option>
                ))}
              </select>
            </label>
          </div>
          <p className="text-xs text-muted-foreground">{t(`hesapEkibi.rolAciklama.${form.rol}`)}</p>
          <div>
            <span className="mb-1 block text-xs uppercase tracking-widest text-muted-foreground">{t('hesapEkibi.ekip.izinler')}</span>
            <IzinKutulari
              izinler={liste.izinler}
              secili={formIzinleri}
              kullanilabilir={kullanilabilir}
              pasif={false}
              onDegis={(izinler) => setForm((f) => ({ ...f, izinler }))}
              onEk="yeni"
            />
          </div>
          <Button
            type="submit"
            disabled={!!calisan || !form.email.trim()}
            data-testid="davet-gonder"
            className="gap-2 bg-gradient-to-r from-purple-600 to-pink-600 text-white border-0"
          >
            {calisan === 'davet' ? <Loader2 className="h-4 w-4 animate-spin" /> : <MailPlus className="h-4 w-4" />}
            {t('hesapEkibi.ekip.gonder')}
          </Button>
        </form>
      )}
    </div>
  );
}
