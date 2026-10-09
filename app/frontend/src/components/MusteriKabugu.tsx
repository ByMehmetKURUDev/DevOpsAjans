import { Suspense, useEffect, useRef, useState, type ReactNode } from 'react';
import { Link } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import {
  Check,
  Ellipsis,
  FolderKanban,
  Globe,
  House,
  Languages,
  LayoutDashboard,
  LifeBuoy,
  LogOut,
  Puzzle,
  Search,
  UserCog,
  X,
  type LucideIcon,
} from 'lucide-react';
import MarkaLogosu from '@/components/MarkaLogosu';
import NotificationBell from '@/components/NotificationBell';
import { useGrupluMenu, type MenuOgesi } from '@/components/GrupluMenu';
import { GENEL_BAKIS, MUSTERI_GRUPLARI, type MusteriGrubu } from '@/lib/musteriMenusu';
import { SUPPORTED_LANGUAGES, changeAppLanguage } from '@/i18n';
import { UygulamaYukleDugmesi } from '@/lib/uygulamaKabugu';
import './musteriKabugu.css';
// Faz 11G-1: panelin bütün bölümleri Genel bakışın cam kart dilinde (yalnız panel içerik alanı).
import '@/components/panel/panelBolumleri.css';

/**
 * Faz 11B — müşteri paneli kabuğu (Panel v2): önizleme 5'teki üst çubuk — logo, menü (gruplar yatay; en başta
 * "Genel bakış"), bildirim zili, hesap menüsü (dil, siteye dön, çıkış). Müşteride sol kenar çubuğu YOK
 * (kullanıcı kararı: yöneticiye özel).
 *
 * İki menü düzeni (karar ClientPanel'de, Faz 7M/7K kuralları aynı):
 *   gruplu  — üst çubukta gruplar (`data-grup` + `data-grup-sekmeler`), altında açık grubun bölümleri
 *             (`data-sekme-cubugu` içinde bütün `data-sekme` düğmeleri; seçili grubun dışındakiler `hidden`),
 *             arama kutusu (`data-menu-arama`, "/" kısayolu). Kök (`<header>`) `data-musteri-menusu` taşır.
 *   düz     — üst çubukta yalnız logo ve sağ taraf; altında bugünkü düz sekme çubuğu (sınıfları ve `data-sekme` /
 *             `data-secili` sözleşmesi aynı), en başta Genel bakış.
 * Genel bakış düğmesi bilerek `data-sekme` TAŞIMAZ (`data-ust-sekme`): sekme sayımları ve paylaşılan e2e
 * sözleşmesi değişmesin (yönetici panelindeki 11A deseni).
 *
 * Site düzeni: kabuk açıkken `<html data-panel-kabugu>` — sitenin üst menüsü/alt bilgisi CSS ile gizli (11A ile aynı
 * kural; Layout.tsx'e dokunulmadı). Telefonda (<768) menü bugünkü gibi üst üste satırlar (alt sekme çubuğu 11F'de).
 */

const GRUP_IKONU: Record<MusteriGrubu | 'diger', LucideIcon> = {
  projeler: FolderKanban,
  destek: LifeBuoy,
  sitem: Globe,
  araclar: Puzzle,
  hesap: UserCog,
  diger: Ellipsis,
};

export type KabukDurumu = 'duz' | 'gruplu' | 'gruplu-genislik';

interface Ortak<K extends string> {
  sekmeler: MenuOgesi<K>[];
  aktif: string;
  onSec: (sekme: string) => void;
  rozetler?: Partial<Record<K, number>>;
  /** Düz çubuktaki / bölüm satırındaki `data-moduller` (sunucu / hata / yukleniyor). */
  modulDurumu: string;
  /** Menü satırının genişliği (düz ↔ gruplu geçişi için ClientPanel ölçüyor). */
  satirRef: (el: HTMLDivElement | null) => void;
}

interface Props<K extends string> extends Ortak<K> {
  gruplu: boolean;
  kabukDurumu: KabukDurumu;
  duzCubukRef: (el: HTMLDivElement | null) => void;
  kullanici: { email?: string; name?: string };
  /** Etkin hesabın görünen adı (şirket); yoksa kişinin adı. */
  hesapAdi?: string | null;
  onCikis: () => void;
  children: ReactNode;
}

function basHarfler(ad?: string | null, eposta?: string): string {
  const kelimeler = (ad || '').trim().split(/\s+/).filter((k) => k && !k.endsWith('.'));
  if (kelimeler.length >= 2) return (kelimeler[0][0] + kelimeler[kelimeler.length - 1][0]).toLocaleUpperCase('tr');
  const kaynak = kelimeler[0] || (eposta || '').split('@')[0] || '?';
  return kaynak.slice(0, 2).toLocaleUpperCase('tr');
}

function Rozet({ sayi }: { sayi: number }) {
  if (sayi <= 0) return null;
  return (
    <span className="mpk-rozet" data-rozet={sayi}>
      {sayi > 99 ? '99+' : sayi}
    </span>
  );
}

/** Gruplu menü: üst çubukta gruplar + arama, altında açık grubun bölümleri. */
function GrupluBolum<K extends string>({ sekmeler, aktif, onSec, rozetler = {}, modulDurumu, satirRef }: Ortak<K>) {
  const menu = useGrupluMenu<K, MusteriGrubu>({
    sekmeler,
    aktif: aktif as K,
    onSec: (k) => onSec(k),
    rozetler,
    tanim: MUSTERI_GRUPLARI,
    paket: 'panelKabugu.menu',
  });
  const { t, gruplar, grupAdi, bulunanGrup, aranan, setAranan, arama, sonuclar, sonucAnahtarlari, aramaRef, sec, grubaGit, aramaTusu, grubunRozeti } = menu;
  const genel = aktif === GENEL_BAKIS;
  const gorunurBolum = !!arama || !!bulunanGrup;
  return (
    <>
      <nav className="mpk-menu" aria-label={t('panelKabugu.menu.menu')}>
        <div className="mpk-gruplar" data-grup-cubugu>
          <button
            type="button"
            className="mpk-grup"
            data-ust-sekme={GENEL_BAKIS}
            aria-current={genel && !arama ? 'page' : undefined}
            onClick={() => {
              setAranan('');
              onSec(GENEL_BAKIS);
            }}
          >
            <LayoutDashboard aria-hidden="true" />
            {t('panelKabugu.menu.genelBakis')}
          </button>
          {gruplar.map((g) => {
            const Ikon = GRUP_IKONU[g.anahtar];
            const secili = !arama && g.anahtar === bulunanGrup;
            return (
              <button
                key={g.anahtar}
                type="button"
                className="mpk-grup"
                data-grup={g.anahtar}
                data-grup-sekmeler={g.sekmeler.map((s) => s.key).join(' ')}
                aria-current={secili ? 'true' : undefined}
                onClick={() => grubaGit(g.anahtar)}
              >
                <Ikon aria-hidden="true" />
                {grupAdi(g.anahtar)}
                <Rozet sayi={grubunRozeti(g.anahtar)} />
              </button>
            );
          })}
        </div>
      </nav>

      <div className="mpk-arama" role="search">
        <Search className="mpk-arama-ikon" aria-hidden="true" />
        <input
          ref={aramaRef}
          type="search"
          value={aranan}
          onChange={(e) => setAranan(e.target.value)}
          onKeyDown={aramaTusu}
          placeholder={t('panelKabugu.menu.ara')}
          aria-label={t('panelKabugu.menu.ara')}
          data-menu-arama
          className="mpk-arama-girdi"
        />
        {aranan ? (
          <button
            type="button"
            className="mpk-arama-temizle"
            onClick={() => {
              setAranan('');
              aramaRef.current?.focus();
            }}
            aria-label={t('panelKabugu.menu.temizle')}
          >
            <X aria-hidden="true" />
          </button>
        ) : (
          <kbd className="mpk-kbd" aria-hidden="true">
            /
          </kbd>
        )}
      </div>

      <div className="mpk-satir2" ref={satirRef} data-bos={gorunurBolum ? undefined : ''}>
        <div className="mpk-bolumler cam-alt-sekmeler" aria-label={t('panelKabugu.menu.bolumler')} data-sekme-cubugu data-moduller={modulDurumu}>
          {gruplar.flatMap((g) =>
            g.sekmeler.map((s) => {
              const gorunur = arama ? sonucAnahtarlari.has(s.key) : g.anahtar === bulunanGrup;
              const secili = s.key === aktif;
              return (
                <button
                  key={s.key}
                  type="button"
                  hidden={!gorunur}
                  data-sekme={s.key}
                  data-secili={secili ? 'evet' : 'hayir'}
                  aria-current={secili ? 'page' : undefined}
                  onClick={() => sec(s.key)}
                  className="mpk-bolum"
                >
                  <s.icon aria-hidden="true" />
                  {s.label}
                  {arama && <span className="mpk-bolum-grup">· {grupAdi(g.anahtar)}</span>}
                  <Rozet sayi={rozetler[s.key] || 0} />
                </button>
              );
            }),
          )}
          {arama && sonuclar.length === 0 && (
            <p className="mpk-arama-bos" data-arama-bos>
              {t('panelKabugu.menu.sonucYok')}
            </p>
          )}
        </div>
      </div>
    </>
  );
}

/** Düz menü: bugünkü sekme çubuğu (DOM sözleşmesi aynı), en başta Genel bakış. */
function DuzBolum<K extends string>({
  sekmeler,
  aktif,
  onSec,
  rozetler = {},
  modulDurumu,
  satirRef,
  duzCubukRef,
}: Ortak<K> & { duzCubukRef: (el: HTMLDivElement | null) => void }) {
  const { t } = useTranslation();
  const genel = aktif === GENEL_BAKIS;
  return (
    <div className="mpk-satir2 mpk-satir2-duz" ref={satirRef}>
      <div
        ref={duzCubukRef}
        className="cam-sekmeler flex gap-1 mb-8 border-b border-white/10 overflow-x-auto"
        data-sekme-cubugu
        data-moduller={modulDurumu}
      >
        <button
          type="button"
          data-ust-sekme={GENEL_BAKIS}
          aria-current={genel ? 'page' : undefined}
          onClick={() => onSec(GENEL_BAKIS)}
          className={`px-5 py-3 text-sm font-medium transition-colors relative inline-flex items-center gap-2 whitespace-nowrap max-2xl:px-4 max-xl:px-3 ${
            genel ? 'text-foreground' : 'text-muted-foreground hover:text-foreground'
          }`}
        >
          <LayoutDashboard className="h-4 w-4" aria-hidden="true" />
          {t('panelKabugu.menu.genelBakis')}
          {genel && <span className="absolute bottom-0 left-0 right-0 h-0.5 bg-gradient-to-r from-purple-500 to-pink-500" />}
        </button>
        {sekmeler.map((tItem) => {
          const rozet = rozetler[tItem.key] || 0;
          return (
            <button
              key={tItem.key}
              data-sekme={tItem.key}
              data-secili={aktif === tItem.key ? 'evet' : undefined}
              onClick={() => onSec(tItem.key)}
              className={`px-5 py-3 text-sm font-medium transition-colors relative inline-flex items-center gap-2 whitespace-nowrap max-2xl:px-4 max-xl:px-3 ${
                aktif === tItem.key ? 'text-foreground' : 'text-muted-foreground hover:text-foreground'
              }`}
            >
              <tItem.icon className="h-4 w-4" />
              {tItem.label}
              {rozet > 0 && (
                <span
                  className="inline-flex min-w-[1.25rem] items-center justify-center rounded-full bg-pink-600 px-1.5 text-[11px] font-semibold leading-5 text-white"
                  data-rozet={rozet}
                  aria-label={tItem.label + ': ' + rozet}
                >
                  {rozet > 99 ? '99+' : rozet}
                </span>
              )}
              {aktif === tItem.key && (
                <span className="absolute bottom-0 left-0 right-0 h-0.5 bg-gradient-to-r from-purple-500 to-pink-500" />
              )}
            </button>
          );
        })}
      </div>
    </div>
  );
}

export default function MusteriKabugu<K extends string>({
  gruplu,
  kabukDurumu,
  duzCubukRef,
  kullanici,
  hesapAdi,
  onCikis,
  children,
  ...menu
}: Props<K>) {
  const { t, i18n } = useTranslation();
  const k = (ad: string) => t(`panelKabugu.kabuk.${ad}`);
  const [hesapAcik, setHesapAcik] = useState(false);
  const hesapRef = useRef<HTMLDivElement>(null);

  // Panel tam ekran: site düzeninin üst menüsü/alt bilgisi CSS ile gizlenir (musteriKabugu.css; 11A ile aynı kural).
  useEffect(() => {
    const kok = document.documentElement;
    kok.setAttribute('data-panel-kabugu', '');
    return () => kok.removeAttribute('data-panel-kabugu');
  }, []);

  // Hesap menüsü: Esc ve dışarı tıklama kapatır.
  useEffect(() => {
    if (!hesapAcik) return;
    const tus = (e: globalThis.KeyboardEvent) => {
      if (e.key === 'Escape') setHesapAcik(false);
    };
    const tik = (e: MouseEvent) => {
      if (hesapRef.current && !hesapRef.current.contains(e.target as Node)) setHesapAcik(false);
    };
    document.addEventListener('keydown', tus);
    document.addEventListener('mousedown', tik);
    return () => {
      document.removeEventListener('keydown', tus);
      document.removeEventListener('mousedown', tik);
    };
  }, [hesapAcik]);

  const ad = (kullanici.name || '').trim();
  const ust = (hesapAdi || '').trim() || ad || kullanici.email || '';
  const alt = ust === ad ? kullanici.email || '' : ad || kullanici.email || '';
  const dil = i18n.language;

  return (
    <div className="mpk" data-panel-v2 data-musteri-kabugu>
      <header
        className={`mpk-ust ${gruplu ? 'mpk-ust-gruplu' : 'mpk-ust-duz'}`}
        data-menu-kabugu={kabukDurumu}
        {...(gruplu ? { 'data-musteri-menusu': '' } : {})}
      >
        <Link to="/" className="mpk-logo" aria-label={k('siteyeDon')}>
          <MarkaLogosu />
        </Link>

        {gruplu ? <GrupluBolum<K> {...menu} /> : <DuzBolum<K> {...menu} duzCubukRef={duzCubukRef} />}

        <div className="mpk-sag">
          <Suspense fallback={null}>
            <UygulamaYukleDugmesi />
          </Suspense>
          <div className="mpk-zil" data-pk-zil>
            <NotificationBell email={kullanici.email} />
          </div>
          <div className="mpk-acilir" ref={hesapRef}>
            <button
              type="button"
              className="mpk-kullanici"
              aria-haspopup="menu"
              aria-expanded={hesapAcik}
              aria-label={k('hesapMenusu')}
              onClick={() => setHesapAcik((a) => !a)}
              data-hesap-menu
            >
              <span className="mpk-avatar" aria-hidden="true">
                {basHarfler(ad, kullanici.email)}
              </span>
              <span className="mpk-kullanici-yazi">
                <span className="mpk-kullanici-ad">{ust}</span>
                {alt && alt !== ust && <span className="mpk-kullanici-alt">{alt}</span>}
              </span>
            </button>
            {hesapAcik && (
              <div className="mpk-acilir-panel" role="menu" aria-label={k('hesapMenusu')}>
                <p className="mpk-acilir-not">{kullanici.email}</p>
                <p className="mpk-acilir-baslik">
                  <Languages aria-hidden="true" />
                  {k('dil')}
                </p>
                <div className="mpk-diller">
                  {SUPPORTED_LANGUAGES.map((l) => (
                    <button
                      key={l.code}
                      type="button"
                      role="menuitemradio"
                      aria-checked={l.code === dil}
                      className="mpk-dil"
                      lang={l.htmlLang}
                      onClick={() => {
                        setHesapAcik(false);
                        void changeAppLanguage(l.code);
                      }}
                    >
                      {l.code === dil && <Check aria-hidden="true" />}
                      {l.full}
                    </button>
                  ))}
                </div>
                <button
                  type="button"
                  role="menuitem"
                  className="mpk-acilir-oge"
                  onClick={() => {
                    setHesapAcik(false);
                    menu.onSec('profile');
                  }}
                >
                  <UserCog aria-hidden="true" />
                  {k('profil')}
                </button>
                <Link to="/" role="menuitem" className="mpk-acilir-oge" onClick={() => setHesapAcik(false)}>
                  <House aria-hidden="true" />
                  {k('siteyeDon')}
                </Link>
                <button type="button" role="menuitem" className="mpk-acilir-oge mpk-cikis" onClick={onCikis}>
                  <LogOut aria-hidden="true" />
                  {k('cikis')}
                </button>
              </div>
            )}
          </div>
        </div>
      </header>

      <div className="mpk-icerik" id="mpk-icerik">
        {children}
      </div>
    </div>
  );
}
