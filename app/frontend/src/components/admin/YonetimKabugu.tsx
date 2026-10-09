import { Suspense, useEffect, useRef, useState, type ReactNode } from 'react';
import { Link } from 'react-router-dom';
import { Bell, Check, House, Inbox, Languages, LogOut, Menu, Plus, Search, X } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import MarkaLogosu from '@/components/MarkaLogosu';
import NotificationBell from '@/components/NotificationBell';
import { useGrupluMenu, type MenuOgesi } from '@/components/GrupluMenu';
import YonetimMenusu, {
  HIZLI_ISLEMLER,
  type HizliIslem,
  type KenarKipi,
  type UstSekme,
} from '@/components/admin/YonetimMenusu';
import { GENEL_BAKIS, GRUPLAR, kenarDarOku, kenarDarYaz, type GrupAnahtari } from '@/lib/yonetimMenusu';
import { SUPPORTED_LANGUAGES, changeAppLanguage } from '@/i18n';
import { UygulamaYukleDugmesi } from '@/lib/uygulamaKabugu';
import './yonetimKabugu.css';
// Faz 11G-1: panelin bütün bölümleri Genel bakışın cam kart dilinde (yalnız panel içerik alanı).
import '@/components/panel/panelBolumleri.css';

/**
 * Faz 11A — yönetici paneli kabuğu (komuta merkezi): sol kenar çubuğu + üst çubuk + içerik,
 * telefonda alt sekme çubuğu + "Menü" çekmecesi.
 *
 * Yerleşim (CSS ızgara alanları, `yonetimKabugu.css`): DOM sırası üst çubuk → `<nav
 * data-yonetim-menusu>` → içerik. Menünün hemen ardından içerik geldiği için paylaşılan e2e
 * testleri (t7y) "menüden sonraki kardeşler = bölüm içeriği" varsayımıyla çalışmaya devam ediyor.
 *
 * Site düzeni (Layout): panel tam ekran — kabuk açıkken `<html data-panel-kabugu>` konur ve bu
 * dosyanın CSS'i sitenin üst menüsünü/alt bilgisini gizler (Layout.tsx'e dokunulmadı; giriş
 * ekranı, yükleniyor ve yetkisiz durumlarında site düzeni olduğu gibi görünür). Üst menüde kalan
 * işler üst çubukta: bildirim zili (aynı bileşen), dil, siteye dön, çıkış.
 */

type Ekran = 'genis' | 'orta' | 'dar';

function ekranHesapla(): Ekran {
  if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') return 'genis';
  if (window.matchMedia('(min-width: 1024px)').matches) return 'genis';
  return window.matchMedia('(min-width: 768px)').matches ? 'orta' : 'dar';
}

function useEkran(): Ekran {
  const [ekran, setEkran] = useState<Ekran>(ekranHesapla);
  useEffect(() => {
    if (typeof window.matchMedia !== 'function') return;
    const sorgular = [window.matchMedia('(min-width: 1024px)'), window.matchMedia('(min-width: 768px)')];
    const degisti = () => setEkran(ekranHesapla());
    sorgular.forEach((s) => s.addEventListener('change', degisti));
    return () => sorgular.forEach((s) => s.removeEventListener('change', degisti));
  }, []);
  return ekran;
}

function basHarfler(ad?: string, eposta?: string): string {
  const kelimeler = (ad || '').trim().split(/\s+/).filter(Boolean);
  if (kelimeler.length >= 2) return (kelimeler[0][0] + kelimeler[kelimeler.length - 1][0]).toLocaleUpperCase('tr');
  const kaynak = kelimeler[0] || (eposta || '').split('@')[0] || '?';
  return kaynak.slice(0, 2).toLocaleUpperCase('tr');
}

interface Props<K extends string> {
  sekmeler: MenuOgesi<K>[];
  aktif: K;
  onSec: (sekme: K) => void;
  rozetler?: Partial<Record<K, number>>;
  grubaKatilmayan?: readonly K[];
  /** Üst çubuktaki sayfa başlığı (açık bölümün adı). */
  baslik: string;
  /** "Canlı" rozeti (veri kendiliğinden yenilenen bölümde). */
  canli?: boolean;
  kullanici: { email?: string; name?: string };
  onHizli: (tur: HizliIslem) => void;
  onCikis: () => void;
  children: ReactNode;
}

export default function YonetimKabugu<K extends string>({
  sekmeler,
  aktif,
  onSec,
  rozetler = {},
  grubaKatilmayan = [],
  baslik,
  canli = false,
  kullanici,
  onHizli,
  onCikis,
  children,
}: Props<K>) {
  const { i18n } = useTranslation();
  const menu = useGrupluMenu<K, GrupAnahtari>({ sekmeler, aktif, onSec, rozetler, grubaKatilmayan, tanim: GRUPLAR, paket: 'yonetimMenusu' });
  const { t } = menu;
  const k = (ad: string) => t(`yonetimMenusu.kabuk.${ad}`);
  const ekran = useEkran();
  const [dar, setDar] = useState<boolean>(() => kenarDarOku());
  const [geciciAcik, setGeciciAcik] = useState(false);
  const [cekmece, setCekmece] = useState(false);
  const [acikGrup, setAcikGrup] = useState<string | null>(menu.bulunanGrup);
  const [acilir, setAcilir] = useState<'hizli' | 'hesap' | null>(null);
  const zilRef = useRef<HTMLDivElement>(null);
  const ustRef = useRef<HTMLElement>(null);

  // Açılan bölümün grubu akordeonda açık olsun (`?sekme=`, arama, hızlı işlem…).
  useEffect(() => {
    if (menu.bulunanGrup) setAcikGrup(menu.bulunanGrup);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [aktif, menu.bulunanGrup]);

  // Telefondan genişe geçince çekmece, genişlikte ray yoksa geçici açılım kapanır.
  useEffect(() => {
    if (ekran !== 'dar') setCekmece(false);
    setGeciciAcik(false);
  }, [ekran]);

  const kip: KenarKipi =
    ekran === 'dar'
      ? cekmece
        ? 'cekmece'
        : 'serit'
      : ekran === 'orta' || dar
        ? geciciAcik || menu.arama
          ? 'ray-acik'
          : 'ray'
        : 'genis';

  // Telefon şeridi: açık grubun çipi ve seçili bölüm yatay kaydırmada görünür kalsın (şerit ekrandaysa).
  useEffect(() => {
    if (kip !== 'serit') return;
    const kok = document.getElementById('pk-kenar');
    if (!kok) return;
    const r = kok.getBoundingClientRect();
    if (r.bottom < 0 || r.top > window.innerHeight) return;
    const goster = (el: Element | null) => el?.scrollIntoView({ block: 'nearest', inline: 'center', behavior: 'auto' });
    if (acikGrup) goster(kok.querySelector(`[data-grup="${acikGrup}"]`));
    goster(kok.querySelector('[data-sekme][aria-current="page"]'));
  }, [kip, acikGrup, aktif]);

  // Panel tam ekran: site düzeninin üst menüsü/alt bilgisi CSS ile gizlenir (bkz. yonetimKabugu.css).
  useEffect(() => {
    const kok = document.documentElement;
    kok.setAttribute('data-panel-kabugu', '');
    return () => kok.removeAttribute('data-panel-kabugu');
  }, []);

  // Çekmece açıkken sayfa kaymasın; ilk öğeye odaklan.
  useEffect(() => {
    if (kip !== 'cekmece') return;
    const kok = document.documentElement;
    const eski = kok.style.overflow;
    kok.style.overflow = 'hidden';
    document.querySelector<HTMLElement>('#pk-kenar .pk-ust-baglantilar a')?.focus();
    return () => {
      kok.style.overflow = eski;
    };
  }, [kip]);

  // Esc: önce açılır menü, sonra çekmece / geçici açılım kapanır. Dışarı tıklayınca açılır menü kapanır.
  useEffect(() => {
    const tus = (e: globalThis.KeyboardEvent) => {
      if (e.key !== 'Escape') return;
      if (acilir) setAcilir(null);
      else if (cekmece) setCekmece(false);
      else if (geciciAcik) setGeciciAcik(false);
    };
    const tik = (e: MouseEvent) => {
      if (acilir && ustRef.current && !(e.target as HTMLElement).closest('.pk-acilir')) setAcilir(null);
    };
    document.addEventListener('keydown', tus);
    document.addEventListener('mousedown', tik);
    return () => {
      document.removeEventListener('keydown', tus);
      document.removeEventListener('mousedown', tik);
    };
  }, [acilir, cekmece, geciciAcik]);

  const kapat = () => {
    setGeciciAcik(false);
    setCekmece(false);
  };

  const grupTikla = (g: GrupAnahtari | 'diger') => {
    const aramadaydi = !!menu.arama;
    if (aramadaydi) menu.setAranan('');
    // Açık grubun başlığı: akordeonu kapatır (ray'de ise geniş hâli açar).
    if (!aramadaydi && acikGrup === g && kip !== 'ray') {
      setAcikGrup(null);
      return;
    }
    setAcikGrup(g);
    if (kip === 'ray') setGeciciAcik(true);
    menu.grubaGit(g);
  };

  const bolumSec = (sekme: K) => {
    menu.sec(sekme);
    kapat();
  };

  const ustSec = (sekme: UstSekme) => {
    menu.setAranan('');
    onSec(sekme as K);
    kapat();
  };

  const hizli = (tur: HizliIslem) => {
    menu.setAranan('');
    setAcilir(null);
    kapat();
    onHizli(tur);
  };

  const darDegistir = () => {
    setDar((d) => {
      kenarDarYaz(!d);
      return !d;
    });
    setGeciciAcik(false);
  };

  const aramayaGit = () => {
    window.scrollTo({ top: 0, behavior: 'auto' });
    menu.aramaRef.current?.focus();
  };

  const bildirimleriAc = () => {
    window.scrollTo({ top: 0, behavior: 'auto' });
    zilRef.current?.querySelector('button')?.click();
  };

  const gelenSayisi = (rozetler as Record<string, number | undefined>).gelenKutusu || 0;
  const dil = i18n.language;

  return (
    <div className="pk" data-panel-v2 data-kip={kip}>
      <header className="pk-ust" ref={ustRef}>
        <div className="pk-ust-sol">
          <span className="pk-ust-logo">
            <MarkaLogosu yazi={false} />
          </span>
          <h1 className="pk-baslik">{baslik}</h1>
          {canli && (
            <span className="pk-canli" title={k('canliAciklama')} data-canli>
              <span className="pk-canli-nokta" aria-hidden="true" />
              <span className="pk-canli-yazi">{k('canli')}</span>
            </span>
          )}
        </div>

        <div className="pk-arama" role="search">
          <Search className="pk-arama-ikon" aria-hidden="true" />
          <input
            ref={menu.aramaRef}
            type="search"
            value={menu.aranan}
            onChange={(e) => menu.setAranan(e.target.value)}
            onKeyDown={menu.aramaTusu}
            placeholder={t('yonetimMenusu.ara')}
            aria-label={t('yonetimMenusu.ara')}
            aria-controls="pk-kenar"
            data-menu-arama
            className="pk-arama-girdi"
          />
          {menu.aranan ? (
            <button
              type="button"
              className="pk-arama-temizle"
              onClick={() => {
                menu.setAranan('');
                menu.aramaRef.current?.focus();
              }}
              aria-label={t('yonetimMenusu.temizle')}
            >
              <X aria-hidden="true" />
            </button>
          ) : (
            <kbd className="pk-kbd" aria-hidden="true">
              /
            </kbd>
          )}
        </div>

        <div className="pk-ust-sag">
          <div className="pk-acilir">
            <button
              type="button"
              className="pk-arti"
              aria-haspopup="menu"
              aria-expanded={acilir === 'hizli'}
              aria-label={k('hizliMenu')}
              title={k('hizliMenu')}
              onClick={() => setAcilir((a) => (a === 'hizli' ? null : 'hizli'))}
              data-hizli-menu
            >
              <Plus aria-hidden="true" />
            </button>
            {acilir === 'hizli' && (
              <div className="pk-acilir-panel" role="menu" aria-label={k('hizliIslemler')}>
                {HIZLI_ISLEMLER.map((h) => (
                  <button key={h.tur} type="button" role="menuitem" className="pk-acilir-oge" onClick={() => hizli(h.tur)}>
                    <h.ikon aria-hidden="true" />
                    {k(h.etiket)}
                  </button>
                ))}
              </div>
            )}
          </div>
          <Suspense fallback={null}>
            <UygulamaYukleDugmesi />
          </Suspense>
          <div className="pk-zil" ref={zilRef} data-pk-zil>
            <NotificationBell email={kullanici.email} />
          </div>
          <div className="pk-acilir">
            <button
              type="button"
              className="pk-kullanici"
              aria-haspopup="menu"
              aria-expanded={acilir === 'hesap'}
              aria-label={k('hesapMenusu')}
              onClick={() => setAcilir((a) => (a === 'hesap' ? null : 'hesap'))}
              data-hesap-menu
            >
              <span className="pk-avatar" aria-hidden="true">
                {basHarfler(kullanici.name, kullanici.email)}
              </span>
              <span className="pk-kullanici-yazi">
                <span className="pk-kullanici-ad">{kullanici.name || kullanici.email}</span>
                <span className="pk-kullanici-rol">{k('yonetici')}</span>
              </span>
            </button>
            {acilir === 'hesap' && (
              <div className="pk-acilir-panel pk-hesap-panel" role="menu" aria-label={k('hesapMenusu')}>
                <p className="pk-acilir-not">{kullanici.email}</p>
                <p className="pk-acilir-baslik">
                  <Languages aria-hidden="true" />
                  {k('dil')}
                </p>
                <div className="pk-diller">
                  {SUPPORTED_LANGUAGES.map((l) => (
                    <button
                      key={l.code}
                      type="button"
                      role="menuitemradio"
                      aria-checked={l.code === dil}
                      className="pk-dil"
                      lang={l.htmlLang}
                      onClick={() => {
                        setAcilir(null);
                        void changeAppLanguage(l.code);
                      }}
                    >
                      {l.code === dil && <Check aria-hidden="true" />}
                      {l.full}
                    </button>
                  ))}
                </div>
                <Link to="/" role="menuitem" className="pk-acilir-oge" onClick={() => setAcilir(null)}>
                  <House aria-hidden="true" />
                  {k('siteyeDon')}
                </Link>
                <button type="button" role="menuitem" className="pk-acilir-oge pk-cikis" onClick={onCikis}>
                  <LogOut aria-hidden="true" />
                  {k('cikis')}
                </button>
              </div>
            )}
          </div>
        </div>
      </header>

      <YonetimMenusu<K>
        menu={menu}
        aktif={aktif}
        acikGrup={acikGrup}
        kip={kip}
        ekran={ekran}
        dar={dar}
        gelenSayisi={gelenSayisi}
        onGrup={grupTikla}
        onBolum={bolumSec}
        onUst={ustSec}
        onHizli={hizli}
        onDarDegistir={darDegistir}
        onKapat={kapat}
      />

      <div className="pk-icerik" id="pk-icerik" aria-label={k('anaIcerik')} role="region">
        {children}
      </div>

      {(kip === 'cekmece' || (kip === 'ray-acik' && !menu.arama)) && (
        <div className={`pk-perde ${kip === 'ray-acik' ? 'pk-perde-saydam' : ''}`} onClick={kapat} aria-hidden="true" />
      )}

      <nav className="pk-alt" aria-label={k('altMenu')}>
        <button
          type="button"
          className="pk-alt-oge"
          aria-current={aktif === GENEL_BAKIS ? 'page' : undefined}
          onClick={() => ustSec(GENEL_BAKIS)}
        >
          <House aria-hidden="true" />
          <span>{k('sekmeGenel')}</span>
        </button>
        <button
          type="button"
          className="pk-alt-oge"
          aria-current={aktif === 'gelenKutusu' ? 'page' : undefined}
          onClick={() => ustSec('gelenKutusu')}
        >
          <span className="pk-alt-ikon">
            <Inbox aria-hidden="true" />
            {gelenSayisi > 0 && <span className="pk-alt-rozet">{gelenSayisi > 99 ? '99+' : gelenSayisi}</span>}
          </span>
          <span>{k('sekmeGelen')}</span>
        </button>
        <button type="button" className="pk-alt-oge" onClick={aramayaGit}>
          <Search aria-hidden="true" />
          <span>{k('sekmeAra')}</span>
        </button>
        <button type="button" className="pk-alt-oge" onClick={bildirimleriAc}>
          <Bell aria-hidden="true" />
          <span>{k('sekmeBildirim')}</span>
        </button>
        <button
          type="button"
          className="pk-alt-oge"
          aria-expanded={kip === 'cekmece'}
          aria-controls="pk-kenar"
          onClick={() => setCekmece((c) => !c)}
          data-alt-menu
        >
          {kip === 'cekmece' ? <X aria-hidden="true" /> : <Menu aria-hidden="true" />}
          <span>{k('sekmeMenu')}</span>
        </button>
      </nav>
    </div>
  );
}
