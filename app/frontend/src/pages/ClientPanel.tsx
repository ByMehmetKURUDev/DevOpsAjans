import { Link, useLocation, useNavigate } from 'react-router-dom';
import { ekliLazy } from '@/i18n/ekliLazy';
import { Suspense, lazy, useCallback, useEffect, useLayoutEffect, useMemo, useState } from 'react';
import {
  Loader2,
  LogIn,
  ExternalLink,
  Briefcase,
  CheckCircle2,
  Clock,
  Receipt,
  MessageSquare,
  UserCog,
  Send,
  UserPlus,
  FileText,
  ShieldCheck,
  Gauge,
  Coins,
  FolderOpen,
  MessagesSquare,
  Bot,
  QrCode,
  IdCard,
  UtensilsCrossed,
  KeyRound,
  CalendarCheck,
  Workflow,
  PenTool,
  BotMessageSquare,
  Wrench,
  Ticket,
  ScanBarcode,
  GraduationCap,
  UsersRound,
  Scale,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { Label } from '@/components/ui/label';
import { toast } from 'sonner';
import { useTranslation } from 'react-i18next';
import ProjectTimeline from '@/components/ProjectTimeline';
import TalepYazismasi from '@/components/TalepYazismasi';
import RaporArsivi from '@/components/RaporArsivi';
import SiteBakimIzni from '@/components/SiteBakimIzni';
import { HIZMETLER } from '@/lib/talepler';
import { useStageLabels } from '@/lib/projectEvents';
import { client, oturumIziVarMi } from '@/lib/sdkClient';
import { isAdminUser, useSiteSettings } from '@/lib/siteSettings';
import { modullerimiGetir, type Modullerim as ModulBilgisi } from '@/lib/moduller';
import { modulIkonu } from '@/lib/modulIkonlari';
import { IZINLER, SEKME_IZINLERI, hesaplarimiGetir, type Hesap } from '@/lib/hesapEkibi';
import { hesapSec, seciliHesap } from '@/lib/hesapSecimi';
import { ozetGetir as mesajOzeti } from '@/lib/mesajlar';
import { useYoklama } from '@/hooks/useYoklama';
import { DUZ_MENU_EN_DAR, grupluMenuMu, sonMusteriSekmesi, sonMusteriSekmesiniYaz } from '@/lib/musteriMenusu';
import {
  CevrimdisiIskelet,
  CevrimdisiSerit,
  UygulamaYukleDugmesi,
  useCevrimdisiAcilis,
  usePanelKabugu,
} from '@/lib/uygulamaKabugu';

// Site analizi sekmesi ayrı parçada: rapor görünümü panele her girişte inmesin.
const SiteAnalizim = ekliLazy('siteAnalizi', () => import('@/components/SiteAnalizim'));
// Profil altındaki "Hesap hareketleri" (denetim kaydının müşteriye açık kısmı).
const HesapHareketleri = ekliLazy('denetim', () => import('@/components/HesapHareketleri'));
// Faz 2D: Profil › Oturumlarım (bu cihaz, diğerlerini kapat) ve Silinenler (geri al).
const Oturumlarim = ekliLazy('guvenlik', () => import('@/components/Oturumlarim'));
const Silinenlerim = ekliLazy('copKutusu', () => import('@/components/Silinenlerim'));
// Profil › Bildirim tercihleri (olay × kanal, tarayıcı bildirimi).
const BildirimTercihleri = ekliLazy('bildirim', () => import('@/components/BildirimTercihleri'));
// Kredilerim (Kullandıkça Öde) ve genel görünümdeki küçük bakiye kartı.
const Kredilerim = ekliLazy('kredi', () => import('@/components/Kredilerim'));
const KrediOzetKarti = ekliLazy('kredi', () => import('@/components/KrediOzetKarti'));
// Onay bekleyen imzalı işlemler (teklif kabulü, teslim onayı) — yoksa hiç çizilmez.
const OnayBekleyenler = ekliLazy('islem', () => import('@/components/OnayBekleyenler'));
// Profil › Modüllerim (açık / yakında / paketinize eklenebilir modüller).
const Modullerim = ekliLazy('modul', () => import('@/components/Modullerim'));
// Faz 4L: Profil › Marka (marka teması modülü açıksa; yeni üst sekme yok).
const MarkaAyari = ekliLazy('markaTemasi', () => import('@/components/marka/MarkaAyari'));
// Faz 2A: "Sitem" sekmesindeki bakım/uptime kartı (ek paket `siteBakim`).
const SitemBakim = ekliLazy('siteBakim', () => import('@/components/SitemBakim'));
// Faz 2C: Dosyalar sekmesi; Destek'te bilgi bankası + SLA bilgisi ve talep
// açarken makale önerisi; Raporlar'da aylık rapor arşivi.
// Faz 5B: "Dosyalar ve belgeler" — Dosyalar · Belgeler · Strateji alt bölümleri (yeni sekme yok).
const DosyalarVeBelgeler = ekliLazy('belgeler', () => import('@/components/belgeler/DosyalarVeBelgeler'));
const DestekYardim = ekliLazy('yardim', () => import('@/components/DestekYardim'));
const KbOnerileri = ekliLazy('yardim', () => import('@/components/KbOnerileri'));
// Faz 2F: e-postadan gelen talep rozeti ve "e-postayla da yanıtlayabilirsiniz" ipucu.
const EpostaRozeti = ekliLazy('yardim', () => import('@/components/EpostaRozeti'));
const EpostaIpucu = ekliLazy('yardim', () => import('@/components/EpostaIpucu'));
const AylikRaporArsivi = ekliLazy('aylikRapor', () => import('@/components/AylikRaporArsivi'));
// Faz 2B — proje görevleri, revizyon sayacı, hata bildir, duyurular, öneri kutusu.
const ProjeGorevGorunumu = ekliLazy('gorevler', () => import('@/components/ProjeGorevGorunumu'));
const RevizyonGostergesi = ekliLazy('gorevler', () => import('@/components/RevizyonGostergesi'));
const HataBildir = ekliLazy('geriBildirim', () => import('@/components/HataBildir'));
const GeriBildirimlerim = ekliLazy('geriBildirim', () => import('@/components/GeriBildirimlerim'));
const DuyuruSeridi = ekliLazy('duyurular', () => import('@/components/DuyuruSeridi'));
const OneriKutusu = ekliLazy('duyurular', () => import('@/components/OneriKutusu'));
// Faz 2E — hesap seçici + "başka hesapta çalışıyorsunuz" şeridi ve Profil › Ekip.
const HesapSecici = ekliLazy('hesapEkibi', () => import('@/components/HesapSecici'));
const HesapEkibi = ekliLazy('hesapEkibi', () => import('@/components/HesapEkibi'));
// Faz 2G — müşteri ↔ ajans mesajlaşma (sohbet arayüzü ayrı parçada, ek paket `mesajlar`).
const Mesajlar = ekliLazy('mesajlar', () => import('@/components/Mesajlar'));
// Faz 3U — Uzman Asistanlar (yapay zekâ sohbetleri; ek paket `uzmanAsistanlar`).
const UzmanAsistanlar = ekliLazy('uzmanAsistanlar', () => import('@/components/UzmanAsistanlar'));
// Faz 4Q — dinamik QR ve kısa link (yönetici paneliyle aynı bileşen, müşteri modu; ek paket `dinamikQr`).
const DinamikQr = ekliLazy('dinamikQr', () => import('@/components/DinamikQr'));
// Faz 4K — dijital kartvizit + Google yorum sayfası (yönetici paneliyle aynı bileşen, müşteri modu).
const Kartvizit = ekliLazy('kartvizit', () => import('@/components/Kartvizit'));
// Faz 4M — QR menü ve WhatsApp katalog (yönetici paneliyle aynı bileşen, müşteri modu).
const QrMenu = ekliLazy(['qrMenu', 'qrMenuSayfa'], () => import('@/components/QrMenu'));
// Faz 4A — API anahtarları, webhook'lar, API belgeleri ve MCP (yönetici paneliyle aynı bileşen, müşteri modu).
const ApiErisimi = ekliLazy('apiErisimi', () => import('@/components/ApiErisimi'));
// Faz 5R — randevu ve toplantılar (yönetici paneliyle aynı bileşen, müşteri modu).
const Randevu = ekliLazy('randevu', () => import('@/components/Randevu'));
// Faz 4W — otomasyon kuralları (yönetici paneliyle aynı bileşen, müşteri modu).
const Otomasyon = ekliLazy(['otomasyon', 'ozelAlanlar'], () => import('@/components/Otomasyon'));
// Faz 4W — projenin müşteriye görünür özel alanları (salt okunur).
const OzelAlanlarBolumu = ekliLazy('ozelAlanlar', () => import('@/components/OzelAlanlarBolumu'));
// Faz 5A — AI asistan + bilgi bankası (yönetici paneliyle aynı bileşen, müşteri modu).
const AiAsistan = ekliLazy(['aiAsistan', 'asistanSayfa'], () => import('@/components/AiAsistan'));
// Faz 5M — e-posta pazarlama (yönetici paneliyle aynı bileşen, müşteri modu).
// Faz 5I — İçerik stüdyosu (yönetici paneliyle aynı bileşen, müşteri modu) ve modülden bağımsız
// "Onay bekleyen içerikler" kartı (ajansın müşteri için hazırladığı içerik).
const IcerikStudyosu = ekliLazy(['icerikStudyosu', 'icerikOnay'], () => import('@/components/IcerikStudyosu'));
const IcerikOnaylari = ekliLazy('icerikOnay', () => import('@/components/IcerikOnaylari'));
const EpostaPazarlama = ekliLazy('epostaPazarlama', () => import('@/components/EpostaPazarlama'));
// Faz 6S — saha servisi: sevk panosu, iş emirleri, teknisyen ekranı (yönetici paneliyle aynı bileşen).
const SahaServisi = ekliLazy('sahaServisi', () => import('@/components/SahaServisi'));
// Faz 6E — etkinlik ve bilet (yönetici paneliyle aynı bileşen, müşteri modu; `etkinlik_giris` izinli üyeye yalnız okutma).
const Etkinlik = ekliLazy('etkinlik', () => import('@/components/Etkinlik'));
// Faz 6P — stok ve POS (yönetici paneliyle aynı bileşen, müşteri modu; `kasa` izinli üyeye yalnız satış ekranı).
const StokPos = ekliLazy('stokPos', () => import('@/components/StokPos'));
// Faz 6K — eğitim (yönetici paneliyle aynı bileşen, müşteri modu; `egitim_egitmen` izinli üyeye yalnız kendi kursları).
const Egitim = ekliLazy('egitim', () => import('@/components/Egitim'));
// Faz 6I — insan kaynakları (yönetici paneliyle aynı bileşen, müşteri modu; ekip izni `ik`).
const Ik = ekliLazy('ik', () => import('@/components/Ik'));
// Faz 6H — hukuk bürosu (müvekkil, dosya, takvim, süre hesaplayıcı, masraf, müvekkil portalı); ekip izni `hukuk`.
const Hukuk = ekliLazy('hukuk', () => import('@/components/Hukuk'));
// Faz 3T — Faturalar sekmesi: teklifler, sözleşmeler (basit e-imza) ve faturalar (bakiye, ödemeler, PDF).
const Faturalarim = ekliLazy(['fatura', 'teklif', 'sozlesme'], () => import('@/components/Faturalarim'));
// Faz 3Z — proje kartında harcanan süre (modül + proje ayarı açıksa) ve ajans
// personelinin kendi zaman kayıtları (yalnız personele; ek paket `zamanTakibi`).
const HarcananSureKarti = ekliLazy('zamanTakibi', () => import('@/components/HarcananSureKarti'));
const PersonelZaman = ekliLazy('zamanTakibi', () => import('@/components/PersonelZaman'));
// Faz 7M — sekme sayısı DUZ_MENU_SINIRI'nı aşınca gruplu menü (yönetici menüsüyle aynı bileşen).
const MusteriMenusu = ekliLazy('panelKabugu', () => import('@/components/MusteriMenusu'));
/** Panel açık, Mesajlar sekmesi kapalıyken yalnız okunmamış sayısı (30–60 sn). */
const MESAJ_OZETI_ARALIGI = 45000;

interface AuthUser {
  id?: string;
  email?: string;
  name?: string;
  [key: string]: unknown;
}

interface Project {
  id: number | string;
  title: string;
  description: string;
  category: string;
  image_url?: string;
  project_url?: string;
  status?: string;
  stage?: string;
  progress?: number;
  tech_stack?: string;
  client_name?: string;
  client_email?: string;
  created_at?: string;
}

interface Invoice {
  id: number | string;
  invoice_no: string;
  client_email?: string;
  description?: string;
  amount: number;
  currency?: string;
  status?: string;
  issue_date?: string;
  due_date?: string;
}

interface Ticket {
  id: number | string;
  client_email?: string;
  client_name?: string;
  subject: string;
  message: string;
  reply?: string;
  status?: string;
  priority?: string;
  hizmet?: string;
  kaynak?: string;
  created_at?: string;
}

type Tab =
  | 'projects'
  | 'invoices'
  | 'krediler'
  | 'tickets'
  | 'mesajlar'
  | 'asistanlar'
  | 'raporlar'
  | 'sitem'
  | 'analiz'
  | 'qr'
  | 'kartvizit'
  | 'menu'
  | 'randevu'
  | 'otomasyon'
  | 'aiAsistan'
  | 'icerik'
  | 'epostaPazarlama'
  | 'sahaServisi'
  | 'etkinlik'
  | 'stokPos'
  | 'egitim'
  | 'ik'
  | 'hukuk'
  | 'dosyalar'
  | 'api'
  | 'profile';

/**
 * Bugünkü bütün sekmeler, bugünkü sırayla. Modül bilgisi (`/api/v1/modullerim`)
 * gelene kadar ya da gelmezse (hata) bu liste gösteriliyor — güvenli geri dönüş.
 */
const SEKMELER: Tab[] = [
  'projects',
  'invoices',
  'krediler',
  'tickets',
  'mesajlar',
  'asistanlar',
  'raporlar',
  'sitem',
  'analiz',
  'qr',
  'kartvizit',
  'menu',
  'randevu',
  'otomasyon',
  'aiAsistan',
  'icerik',
  'epostaPazarlama',
  'sahaServisi',
  'etkinlik',
  'stokPos',
  'egitim',
  'ik',
  'hukuk',
  'dosyalar',
  'api',
  'profile',
];

/**
 * Varsayılan KAPALI modüllerin sekmeleri: modül bilgisi gelmeden (ya da
 * gelmezse) gösterilmiyor — açık olduğu bilinmeden sekme 403 alan bir ekran
 * açmasın. `?sekme=` ile istenmişse bilgi gelince açılıyor.
 */
const VARSAYILAN_KAPALI: Tab[] = ['asistanlar', 'qr', 'kartvizit', 'menu', 'api', 'randevu', 'otomasyon', 'aiAsistan', 'icerik', 'epostaPazarlama', 'sahaServisi', 'etkinlik', 'stokPos', 'egitim', 'ik', 'hukuk'];

/**
 * `/client?sekme=krediler` gibi bildirim bağlantıları doğrudan sekmeyi açsın.
 * Bağlantı yoksa gruplu menüde son açılan sekme (Faz 7M; düz çubukta yazılmaz).
 */
function ilkSekme(): Tab {
  if (typeof window === 'undefined') return 'projects';
  const istenen = new URLSearchParams(window.location.search).get('sekme') as Tab | null;
  if (istenen && SEKMELER.includes(istenen)) return istenen;
  const son = sonMusteriSekmesi() as Tab | null;
  return son && SEKMELER.includes(son) ? son : 'projects';
}


export default function ClientPanel() {
  const { t, i18n } = useTranslation();
  const stageLabel = useStageLabels();
  const { settings } = useSiteSettings();

  /** Durum kodunu seçili dile çevirir; karşılığı yoksa ham kodu gösterir. */
  const statusLabel = (status?: string, fallbackKey = 'planning') =>
    t(`ui.status.${status || fallbackKey}`, { defaultValue: status || '' });
  const [authLoading, setAuthLoading] = useState(true);
  const [user, setUser] = useState<AuthUser | null>(null);
  // Faz 7M: oturum isteği bağlantı yüzünden düşerse giriş ekranı yerine çevrimdışı iskelet.
  const cevrimdisiAcilis = useCevrimdisiAcilis();
  const [tab, setTab] = useState<Tab>(ilkSekme);
  const location = useLocation();
  const navigate = useNavigate();
  // Bildirim bağlantısı panel açıkken tıklanırsa (aynı rota, yeni `?sekme=`) sekmeye geç.
  useEffect(() => {
    try {
      const istenen = new URLSearchParams(location.search).get('sekme') as Tab | null;
      if (istenen && SEKMELER.includes(istenen)) setTab(istenen);
    } catch {
      /* tarayıcı dışı */
    }
  }, [location.search]);
  // Faz 2G — Mesajlar sekmesindeki okunmamış rozeti.
  const [okunmamisMesaj, setOkunmamisMesaj] = useState(0);

  const [projects, setProjects] = useState<Project[]>([]);
  const [invoices, setInvoices] = useState<Invoice[]>([]);
  const [tickets, setTickets] = useState<Ticket[]>([]);
  const [dataLoading, setDataLoading] = useState(false);
  const [error, setError] = useState('');

  const [ticketForm, setTicketForm] = useState({ subject: '', message: '', hizmet: 'genel' });
  // Yazismasi acik olan talep. Ayni anda tek talep aciliyor: uzun
  // listede hepsi acik olsa ekran okunmaz hale geliyor.
  const [acikTalep, setAcikTalep] = useState<number | null>(null);
  const [sending, setSending] = useState(false);
  // "Hata bildir" ile yeni kayıt gönderilince Destek'teki liste yenilensin.
  const [geriBildirimSayaci, setGeriBildirimSayaci] = useState(0);

  const [profile, setProfile] = useState({ name: '', phone: '', company: '' });

  // Faz 1F — modül kaydı. `null` = henüz gelmedi ya da gelmedi (hata):
  // o durumda bugünkü bütün sekmeler ve kartlar gösteriliyor.
  const [modulBilgisi, setModulBilgisi] = useState<ModulBilgisi | null>(null);
  const [modulHatasi, setModulHatasi] = useState(false);

  useEffect(() => {
    // Oturum izi yoksa cagri kesin 401 doner; bos yere istek atmiyoruz.
    if (!oturumIziVarMi()) {
      setAuthLoading(false);
      return;
    }
    client.auth
      .me()
      .then((res) => {
        if (res?.data) setUser(res.data as AuthUser);
        cevrimdisiAcilis.sonuc();
      })
      .catch((e) => cevrimdisiAcilis.sonuc(e))
      .finally(() => setAuthLoading(false));
    // Bağlantı gelince (`deneme`) oturum isteği yinelenir.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [cevrimdisiAcilis.deneme]);

  const email = (user?.email || '').toLowerCase();

  // Faz 7M: uygulama (manifest `start_url` = /client?kaynak=uygulama) yöneticide yönetim paneliyle açılsın.
  useEffect(() => {
    if (!user) return;
    try {
      if (new URLSearchParams(window.location.search).get('kaynak') !== 'uygulama') return;
    } catch {
      return;
    }
    if (isAdminUser(user, settings)) navigate('/admin', { replace: true });
  }, [user, settings, navigate]);

  // Faz 3Z — ajans personeli mi? (yönetici değil, ekip listesinde aktif). Tek
  // küçük istek; personelse zaman bölümü (ayrı parça + ek paket) iner.
  const [personel, setPersonel] = useState(false);
  useEffect(() => {
    if (!email) return;
    let iptal = false;
    client.apiCall
      .invoke({ method: 'GET', url: '/api/v1/zaman/ben' })
      .then((y: unknown) => {
        const g = (y && typeof y === 'object' && 'data' in (y as Record<string, unknown>) ? (y as { data: unknown }).data : y) as
          | { personel?: boolean; yonetici?: boolean }
          | undefined;
        if (!iptal) setPersonel(!!g?.personel && !g?.yonetici);
      })
      .catch(() => {
        if (!iptal) setPersonel(false);
      });
    return () => {
      iptal = true;
    };
  }, [email]);

  // Faz 2E — erişilebilen hesaplar ve etkin hesap. `null` = henüz bilinmiyor:
  // veriler etkin hesap belli olmadan çekilmiyor (yanlış hesaba istek gitmesin).
  const [hesaplar, setHesaplar] = useState<Hesap[] | null>(null);
  const [etkinEmail, setEtkinEmail] = useState('');

  useEffect(() => {
    if (!email) return;
    let iptal = false;
    const sec = (liste: Hesap[]) => {
      let istenen = '';
      try {
        istenen = (new URLSearchParams(window.location.search).get('hesap') || '').trim().toLowerCase();
      } catch {
        /* tarayıcı dışı */
      }
      const aday = istenen || seciliHesap(email) || email;
      const secilen = liste.some((h) => h.hesap_email === aday) ? aday : email;
      hesapSec(email, secilen); // geçersiz (silinmiş üyelik) seçim de burada temizleniyor
      if (!iptal) {
        setHesaplar(liste);
        setEtkinEmail(secilen);
      }
    };
    hesaplarimiGetir()
      .then((g) => sec(g.hesaplar))
      .catch(() => sec([]));
    return () => {
      iptal = true;
    };
  }, [email]);

  const etkin = useMemo<Hesap>(
    () =>
      hesaplar?.find((h) => h.hesap_email === etkinEmail) ?? {
        hesap_email: email,
        rol: 'sahip',
        izinler: [...IZINLER],
        kendi: true,
      },
    [hesaplar, etkinEmail, email]
  );
  /** Etkin hesapta izinlerden biri var mı? Sunucu zaten 403 veriyor; bu yalnız düzen için. */
  const izinVar = useCallback(
    (izinler: string[]) => etkin.kendi || izinler.some((i) => (etkin.izinler as string[]).includes(i)),
    [etkin]
  );
  const hesapHazir = hesaplar !== null && !!etkinEmail;

  const hesapDegistir = useCallback(
    (yeni: string) => {
      hesapSec(email, yeni);
      setModulBilgisi(null);
      setEtkinEmail(yeni);
    },
    [email]
  );

  // Faz 2G: panel açıkken başka hesabın bildirim bağlantısına (`&hesap=`) tıklanırsa
  // o hesaba geç (yalnız erişebildiği hesaplardan biriyse).
  useEffect(() => {
    if (!hesaplar) return;
    let istenen = '';
    try {
      istenen = (new URLSearchParams(location.search).get('hesap') || '').trim().toLowerCase();
    } catch {
      return;
    }
    if (istenen && istenen !== etkinEmail && hesaplar.some((h) => h.hesap_email === istenen)) hesapDegistir(istenen);
    // Yalnız adres değişince; hesap listesi ilk geldiğinde seçim zaten URL'yi okuyor.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [location.search]);

  useEffect(() => {
    if (!user) return;
    try {
      const raw = window.localStorage.getItem(`mk_profile_${email}`);
      if (raw) setProfile(JSON.parse(raw));
      else
        setProfile({
          name: (user.name as string) || '',
          phone: '',
          company: '',
        });
    } catch {
      /* yoksay */
    }
  }, [user, email]);

  const loadData = useCallback(async () => {
    if (!email || !hesapHazir) return;
    setDataLoading(true);
    setError('');
    // Faz 2E: veriler etkin hesabın; izni olmayan bölüm hiç istenmiyor.
    const hesap = etkinEmail;
    try {
      const bos = Promise.resolve(null);
      const [pRes, iRes, tRes] = await Promise.all([
        izinVar(['projeler']) ? client.entities.projects.query({ sort: '-created_at', limit: 100 }) : bos,
        izinVar(['faturalar']) ? client.entities.invoices.query({ sort: '-created_at', limit: 100 }) : bos,
        izinVar(['destek'])
          ? client.entities.support_tickets.query({
              sort: '-created_at',
              limit: 100,
            })
          : bos,
      ]);
      const allProjects = (pRes?.data?.items ?? []) as Project[];
      const allInvoices = (iRes?.data?.items ?? []) as Invoice[];
      const allTickets = (tRes?.data?.items ?? []) as Ticket[];

      setProjects(
        allProjects.filter(
          (p) => (p.client_email || '').toLowerCase() === hesap
        )
      );
      setInvoices(
        allInvoices.filter(
          (i) => (i.client_email || '').toLowerCase() === hesap
        )
      );
      setTickets(
        allTickets.filter((t) => (t.client_email || '').toLowerCase() === hesap)
      );
    } catch (e) {
      const err = e as { message?: string };
      setError(err?.message || t('ui.dataLoadError'));
    } finally {
      setDataLoading(false);
    }
  }, [email, hesapHazir, etkinEmail, izinVar]);

  useEffect(() => {
    if (user) loadData();
  }, [user, loadData]);

  useEffect(() => {
    if (!user || !hesapHazir) return;
    let iptal = false;
    modullerimiGetir()
      .then((b) => {
        if (!iptal) {
          setModulBilgisi(b);
          setModulHatasi(false);
        }
      })
      .catch(() => {
        if (!iptal) setModulHatasi(true);
      });
    return () => {
      iptal = true;
    };
  }, [user, hesapHazir, etkinEmail]);

  /** Modül açık mı? Bilgi yoksa (yükleniyor/hata) açık say: bugünkü davranış. */
  const modulAcik = useCallback(
    (anahtar: string) => {
      if (!modulBilgisi) return true;
      const m = modulBilgisi.moduller.find((x) => x.anahtar === anahtar);
      return m ? m.acik && m.durum !== 'yakinda' : true;
    },
    [modulBilgisi]
  );

  // Faz 5B: ajansın bu hesapla paylaştığı belge var mı? Dosyalar modülü kapalı müşteride de
  // "Dosyalar ve belgeler" sekmesi görünsün diye tek küçük istek (sekme zaten görünüyorsa atılmıyor).
  // Yanıt hesaba bağlı tutuluyor: yanıt gelene kadar `?sekme=dosyalar` bağlantısı ilk sekmeye atılmasın.
  const [paylasilanBelge, setPaylasilanBelge] = useState<{ hesap: string; var: boolean } | null>(null);
  const belgeOzetiGerekli = useMemo(() => {
    if (!hesapHazir || !modulBilgisi || !izinVar(['dosyalar', 'belgeler'])) return false;
    const dosyalarModulu = modulBilgisi.moduller.find((m) => m.anahtar === 'dosyalar');
    return !(dosyalarModulu?.acik && izinVar(['dosyalar']));
  }, [hesapHazir, modulBilgisi, izinVar]);
  useEffect(() => {
    if (!belgeOzetiGerekli) return;
    let iptal = false;
    const hesap = etkinEmail;
    client.apiCall
      .invoke({ method: 'GET', url: '/api/v1/belgelerim/ozet' })
      .then((y: unknown) => {
        const g = (y && typeof y === 'object' && 'data' in (y as Record<string, unknown>) ? (y as { data: unknown }).data : y) as
          | { paylasilan?: number }
          | undefined;
        if (!iptal) setPaylasilanBelge({ hesap, var: (g?.paylasilan ?? 0) > 0 });
      })
      .catch(() => {
        if (!iptal) setPaylasilanBelge({ hesap, var: false });
      });
    return () => {
      iptal = true;
    };
  }, [belgeOzetiGerekli, etkinEmail]);
  const paylasilanBelgeVar = belgeOzetiGerekli && paylasilanBelge?.hesap === etkinEmail && paylasilanBelge.var;
  const belgeOzetiBekleniyor = belgeOzetiGerekli && paylasilanBelge?.hesap !== etkinEmail;
  const belgeSekmesi = (modulAcik('belgeler') && izinVar(['belgeler'])) || paylasilanBelgeVar;

  /** Görünen sekmeler: sunucu sırası + açık olanlar; bilgi yoksa hepsi. */
  const gorunenSekmeler = useMemo<{ key: Tab; ikon?: string }[]>(() => {
    // Faz 2E: etkin hesaptaki rolün izni olmayan sekmeler gizli.
    const izinli = (key: Tab) => !SEKME_IZINLERI[key] || izinVar(SEKME_IZINLERI[key]);
    if (!modulBilgisi) return SEKMELER.filter((k) => izinli(k) && !VARSAYILAN_KAPALI.includes(k)).map((key) => ({ key }));
    const liste: { key: Tab; ikon?: string }[] = [];
    for (const m of modulBilgisi.moduller) {
      const sekme = m.musteri_sekmesi as Tab | null;
      if (!sekme || !SEKMELER.includes(sekme) || liste.some((x) => x.key === sekme)) continue;
      if (!m.acik || m.durum === 'yakinda' || !izinli(sekme)) continue;
      liste.push({ key: sekme, ikon: m.ikon });
    }
    // Faz 4K: Google yorum sayfası modülünün kendi sekmesi yok — yalnız o açıksa da
    // "kartvizit" sekmesi (manifest sırasındaki yerinde) görünsün.
    if (
      !liste.some((x) => x.key === 'kartvizit') &&
      izinli('kartvizit') &&
      modulBilgisi.moduller.some((m) => m.anahtar === 'google_yorum_sayfasi' && m.acik && m.durum !== 'yakinda')
    ) {
      const sira = SEKMELER.indexOf('kartvizit');
      const yer = liste.findIndex((x) => SEKMELER.indexOf(x.key) > sira);
      liste.splice(yer < 0 ? liste.length : yer, 0, { key: 'kartvizit', ikon: 'Star' });
    }
    // Faz 4M: tek motor iki modül — yalnız WhatsApp katalog açıksa da "menu" sekmesi
    // (katalog modülünün kendi sekmesi yok; sırası QR menünün yerinde).
    if (!liste.some((x) => x.key === 'menu') && izinli('menu')) {
      const katalog = modulBilgisi.moduller.find((m) => m.anahtar === 'whatsapp_katalog');
      const menuSirasi = modulBilgisi.moduller.findIndex((m) => m.anahtar === 'qr_menu');
      if (katalog?.acik && katalog.durum !== 'yakinda') {
        const once = new Set(modulBilgisi.moduller.slice(0, Math.max(0, menuSirasi)).map((m) => m.musteri_sekmesi));
        const yer = liste.filter((x) => once.has(x.key)).length;
        liste.splice(yer, 0, { key: 'menu', ikon: katalog.ikon });
      }
    }
    // Faz 5B: "Dosyalar ve belgeler" — dosyalar modülü kapalıyken de belgeler modülü (ya da ajansın
    // paylaştığı belge) varsa görünür; yeri manifestteki dosyalar sırası.
    if (!liste.some((x) => x.key === 'dosyalar') && izinli('dosyalar')) {
      const belgeler = modulBilgisi.moduller.find((m) => m.anahtar === 'belgeler');
      if ((belgeler?.acik && belgeler.durum !== 'yakinda' && izinVar(['belgeler'])) || paylasilanBelgeVar) {
        const sira = modulBilgisi.moduller.findIndex((m) => m.anahtar === 'dosyalar');
        const once = new Set(modulBilgisi.moduller.slice(0, Math.max(0, sira)).map((m) => m.musteri_sekmesi));
        const yer = liste.filter((x) => once.has(x.key)).length;
        liste.splice(yer, 0, { key: 'dosyalar', ikon: 'FolderOpen' });
      }
    }
    // Projeler ve profil çekirdek: sunucu ne derse desin sekme çubuğunda kalır
    // (projeler yalnız etkin hesapta izni varsa).
    if (!liste.some((x) => x.key === 'projects') && izinli('projects')) liste.unshift({ key: 'projects' });
    if (!liste.some((x) => x.key === 'profile')) liste.push({ key: 'profile' });
    return liste;
  }, [modulBilgisi, izinVar, paylasilanBelgeVar]);

  // Faz 2G: okunmamış rozeti — sohbet kapalıyken 45 sn'de bir özet (sohbet açıkken
  // Mesajlar bileşeni kendi yoklamasıyla bildiriyor). Sekme gizliyken durur.
  const mesajlarAcik =
    hesapHazir && (modulBilgisi !== null || modulHatasi) && modulAcik('mesajlar') && izinVar(['mesajlar']);
  useEffect(() => {
    setOkunmamisMesaj(0);
  }, [etkinEmail]);
  useYoklama(
    async () => {
      const o = await mesajOzeti('client');
      setOkunmamisMesaj(o.okunmamis);
    },
    { aralik: MESAJ_OZETI_ARALIGI, etkin: mesajlarAcik && tab !== 'mesajlar', anahtar: etkinEmail }
  );

  // Açık sekme kapatılmış bir modüle (ya da izni olmayan bölüme) aitse ilk görünen sekmeye dön.
  useEffect(() => {
    // Varsayılan kapalı modülün sekmesi (`?sekme=asistanlar`): modül bilgisi gelene kadar bekle.
    if (!modulBilgisi && !modulHatasi && VARSAYILAN_KAPALI.includes(tab)) return;
    // Faz 5B: paylaşılan belge sorusu sürerken "Dosyalar ve belgeler" bağlantısını bekle.
    if (tab === 'dosyalar' && belgeOzetiBekleniyor) return;
    if (!gorunenSekmeler.some((x) => x.key === tab)) setTab(gorunenSekmeler[0]?.key ?? 'profile');
  }, [gorunenSekmeler, tab, modulBilgisi, modulHatasi, belgeOzetiBekleniyor]);

  // Faz 7M: görünür sekme sayısı DUZ_MENU_SINIRI'nı aşınca gruplu menü; son açılan
  // sekme yalnız orada hatırlanır (düz çubuklu müşteri panele bugünkü gibi Projelerim ile girer).
  const grupluSayi = grupluMenuMu(gorunenSekmeler.length);
  useEffect(() => {
    if (grupluSayi && gorunenSekmeler.some((x) => x.key === tab)) sonMusteriSekmesiniYaz(tab);
  }, [grupluSayi, tab, gorunenSekmeler]);
  // Faz 7K: düz çubuk (≤ 10 sekme) DUZ_MENU_EN_DAR ve üstünde sığmıyorsa (1024 px, uzun Almanca/Rusça adlar,
  // Modern/Nebula'nın geniş aralığı) sekmeler çubuğun dışına taşıyordu (yatay kaydırmada gizli). Ölçülür;
  // sığmıyorsa gruplu menüye geçilir, kabuk o genişliğe ulaşınca düz çubuğa dönülür (salınım yok: gereken
  // genişlik ölçülmüş). Dil ya da sekme listesi değişince yeniden ölçülür. Mobilde düz çubuk kaydırılır (eskisi gibi).
  // Durum olarak tutulan öğeler (geri çağırmalı ref): çubuk giriş ekranından sonra belirince de ölçülsün.
  const [menuKabugu, setMenuKabugu] = useState<HTMLDivElement | null>(null);
  const [duzCubuk, setDuzCubuk] = useState<HTMLDivElement | null>(null);
  const sekmeImzasi = `${i18n.language}|${gorunenSekmeler.map((x) => x.key).join(',')}`;
  // Ölçüm hangi dil/sekme listesi için yapıldıysa yalnız onda geçerli (değişince kendiliğinden düz çubuk + yeni ölçüm).
  const [duzOlcum, setDuzOlcum] = useState<{ imza: string; gerekli: number } | null>(null);
  const duzGerekli = duzOlcum && duzOlcum.imza === sekmeImzasi ? duzOlcum.gerekli : null;
  useLayoutEffect(() => {
    const c = duzCubuk;
    if (grupluSayi || duzGerekli !== null || !c) return;
    let bitti = false;
    const olc = () => {
      if (!bitti && window.innerWidth >= DUZ_MENU_EN_DAR && c.scrollWidth > c.clientWidth + 1) {
        setDuzOlcum({ imza: sekmeImzasi, gerekli: c.scrollWidth });
      }
    };
    olc();
    if (typeof ResizeObserver === 'undefined') return;
    const izle = new ResizeObserver(olc);
    izle.observe(c);
    for (const d of Array.from(c.children)) izle.observe(d);
    document.fonts?.ready.then(olc).catch(() => undefined);
    return () => {
      bitti = true;
      izle.disconnect();
    };
  }, [grupluSayi, duzGerekli, sekmeImzasi, duzCubuk]);
  useEffect(() => {
    const k = menuKabugu;
    if (duzGerekli === null || !k || typeof ResizeObserver === 'undefined') return;
    const izle = new ResizeObserver(() => {
      if (window.innerWidth < DUZ_MENU_EN_DAR || k.clientWidth >= duzGerekli) setDuzOlcum(null);
    });
    izle.observe(k);
    return () => izle.disconnect();
  }, [duzGerekli, menuKabugu]);
  const grupluMenu = grupluSayi || duzGerekli !== null;
  // Panel iskeleti ve yüklenen parçalar çevrimdışı açılış için saklansın (servis çalışanı).
  usePanelKabugu('/client', tab);

  const submitTicket = async () => {
    if (!ticketForm.subject.trim() || !ticketForm.message.trim()) {
      toast.error(t('ui.ticketRequired'));
      return;
    }
    setSending(true);
    try {
      await client.entities.support_tickets.create({
        data: {
          // Sunucu sahipliği etkin hesaptan kendisi yazıyor; bu yalnız tutarlılık için.
          client_email: etkinEmail || email,
          client_name: profile.name || user?.name || email,
          subject: ticketForm.subject.trim(),
          message: ticketForm.message.trim(),
          status: 'open',
          priority: 'normal',
          hizmet: ticketForm.hizmet || 'genel',
          kaynak: 'panel',
          // Müşterinin tek projesi varsa talebi ona bağlıyoruz. Birden
          // çok proje varsa boş bırakıyoruz: yanlış projeye bağlamak,
          // hiç bağlamamaktan kötü.
          project_id: projects.length === 1 ? Number(projects[0].id) : undefined,
        },
      });
      toast.success(t('ui.ticketSent'));
      setTicketForm({ subject: '', message: '', hizmet: 'genel' });
      loadData();
    } catch (e) {
      const err = e as { message?: string };
      toast.error(err?.message || t('ui.ticketSendError'));
    } finally {
      setSending(false);
    }
  };

  const saveProfile = () => {
    try {
      window.localStorage.setItem(
        `mk_profile_${email}`,
        JSON.stringify(profile)
      );
      toast.success(t('ui.profileSaved'));
    } catch {
      toast.error(t('ui.profileSaveError'));
    }
  };

  // "Hata bildir" formunun proje seçimi (her çizimde yeni dizi olmasın).
  const hataProjeleri = useMemo(() => projects.map((p) => ({ id: p.id, title: p.title })), [projects]);

  const stats = useMemo(
    () => ({
      total: projects.length,
      active: projects.filter((p) => p.status === 'in_progress').length,
      done: projects.filter((p) => p.status === 'completed').length,
      openInvoices: invoices.filter((i) => !['paid', 'cancelled', 'iade'].includes(i.status || '')).length,
    }),
    [projects, invoices]
  );

  if (authLoading) {
    return (
      <div className="min-h-[60vh] flex items-center justify-center">
        <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
      </div>
    );
  }

  if (!user && cevrimdisiAcilis.cevrimdisi) {
    return (
      <Suspense fallback={null}>
        <CevrimdisiIskelet ust={t('ui.clientPanelTitle')} onYenidenDene={cevrimdisiAcilis.yenidenDene} />
      </Suspense>
    );
  }

  if (!user) {
    return (
      <div className="min-h-[60vh] flex items-center justify-center px-4">
        <div className="max-w-md text-center p-10 rounded-2xl glass">
          <LogIn className="h-10 w-10 mx-auto text-purple-400 mb-4" />
          <h1 className="text-3xl font-bold mb-3">{t('ui.clientPanelTitle')}</h1>
          <p className="text-muted-foreground mb-6">
            {t('clientPanel.loginDesc')}
          </p>
          <div className="space-y-3">
            <Button
              onClick={() => client.auth.toLogin()}
              className="w-full h-11 gap-2 bg-gradient-to-r from-purple-600 to-pink-600 text-white border-0"
            >
              <LogIn className="h-4 w-4" /> {t('nav.signIn')}
            </Button>
            <Button
              onClick={() => client.auth.toLogin()}
              variant="outline"
              className="w-full h-11 gap-2 !bg-transparent !hover:bg-transparent border-white/20 text-foreground"
            >
              <UserPlus className="h-4 w-4" /> {t('nav.signUp')}
            </Button>
          </div>
        </div>
      </div>
    );
  }

  // Sekme anahtarı → etiket ve varsayılan ikon (bileşen eşlemesi aşağıda, kodda).
  // Görünürlük, sıra ve ikon adı sunucudaki modül kaydından geliyor.
  const SEKME_TANIMLARI: Record<Tab, { label: string; icon: typeof Briefcase }> = {
    projects: { label: t('ui.tabMyProjects'), icon: Briefcase },
    invoices: { label: t('ui.tabInvoices'), icon: Receipt },
    krediler: { label: t('ui.tabKredilerim'), icon: Coins },
    tickets: { label: t('ui.tabSupport'), icon: MessageSquare },
    mesajlar: { label: t('ui.tabMesajlar'), icon: MessagesSquare },
    asistanlar: { label: t('ui.tabUzmanAsistanlar'), icon: Bot },
    raporlar: { label: t('rapor.sekme'), icon: FileText },
    sitem: { label: t('sitem.sekme'), icon: ShieldCheck },
    analiz: { label: t('ui.tabAnaliz'), icon: Gauge },
    qr: { label: t('ui.tabDinamikQr'), icon: QrCode },
    kartvizit: { label: t('ui.tabKartvizit'), icon: IdCard },
    menu: { label: t('ui.tabQrMenu'), icon: UtensilsCrossed },
    randevu: { label: t('ui.tabRandevu'), icon: CalendarCheck },
    otomasyon: { label: t('ui.tabOtomasyon'), icon: Workflow },
    aiAsistan: { label: t('ui.tabAiAsistan'), icon: BotMessageSquare },
    icerik: { label: t('ui.tabIcerikStudyosu'), icon: PenTool },
    epostaPazarlama: { label: t('ui.tabEpostaPazarlama'), icon: Send },
    sahaServisi: { label: t('ui.tabSahaServisi'), icon: Wrench },
    etkinlik: { label: t('ui.tabEtkinlik'), icon: Ticket },
    stokPos: { label: t('ui.tabStokPos'), icon: ScanBarcode },
    egitim: { label: t('ui.tabEgitim'), icon: GraduationCap },
    ik: { label: t('ui.tabIk'), icon: UsersRound },
    hukuk: { label: t('ui.tabHukuk'), icon: Scale },
    dosyalar: { label: t('ui.tabDosyalar'), icon: FolderOpen },
    api: { label: t('ui.tabApi'), icon: KeyRound },
    profile: { label: t('ui.tabProfile'), icon: UserCog },
  };
  const TABS: { key: Tab; label: string; icon: typeof Briefcase }[] = gorunenSekmeler.map((s) => ({
    key: s.key,
    label: SEKME_TANIMLARI[s.key].label,
    icon: s.ikon ? modulIkonu(s.ikon) : SEKME_TANIMLARI[s.key].icon,
  }));

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-16">
      <div className="mb-10 flex flex-wrap items-start justify-between gap-4">
        <div>
          <p className="text-xs uppercase tracking-[0.3em] text-purple-400 mb-2">
            {t('ui.clientPanelTitle')}
          </p>
          <h1 className="text-4xl md:text-5xl font-bold">
            {t('ui.controlCenter')} <span className="gradient-text">{t('ui.controlCenterHighlight')}</span>
          </h1>
          <p className="text-muted-foreground mt-2">
            {t('ui.session')}:{' '}
            <span className="text-foreground">
              {user.email || user.name}
            </span>
          </p>
        </div>
        {/* Faz 7M: "Uygulama olarak yükle" (yüklüyse, gizlendiyse ya da tarayıcı desteklemiyorsa çizilmez). */}
        <Suspense fallback={null}>
          <UygulamaYukleDugmesi />
        </Suspense>
      </div>
      <Suspense fallback={null}>
        <CevrimdisiSerit />
      </Suspense>

      {/* Faz 2E: birden çok hesaba erişim varsa hesap seçici; başka hesaptaysa şerit. */}
      {hesapHazir && ((hesaplar?.length ?? 0) > 1 || !etkin.kendi) && (
        <Suspense fallback={null}>
          <HesapSecici hesaplar={hesaplar ?? []} etkin={etkin} ben={email} onSec={hesapDegistir} />
        </Suspense>
      )}

      {!hesapHazir ? (
        <div className="py-16 flex items-center justify-center text-muted-foreground">
          <Loader2 className="h-5 w-5 animate-spin mr-2" /> {t('ui.loading')}
        </div>
      ) : (
      // Hesap değişince bütün alt bileşenler yeniden kurulsun (kendi verilerini yeniden çeksinler).
      <div key={etkinEmail}>
      {personel && (
        <Suspense fallback={null}>
          <PersonelZaman />
        </Suspense>
      )}
      {/* Duyurular: kapatılabilir şerit + "Tüm duyurular" listesi. */}
      {modulAcik('duyurular') && (
        <Suspense fallback={null}>
          <DuyuruSeridi />
        </Suspense>
      )}

      {/* Genel görünümün en üstü: müşterinin kararını bekleyen işler. */}
      {modulAcik('islem') && izinVar(['faturalar', 'projeler', 'raporlar']) && (
        <Suspense fallback={null}>
          <OnayBekleyenler onDegisti={loadData} />
        </Suspense>
      )}
      {/* Faz 5I: ajansın onaya sunduğu içerikler — İçerik stüdyosu modülü kapalı olsa da. */}
      {izinVar(['icerik']) && tab !== 'icerik' && (
        <Suspense fallback={null}>
          <IcerikOnaylari />
        </Suspense>
      )}

      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4 mb-10">
        {[
          {
            label: t('ui.statTotalProjects'),
            value: stats.total,
            icon: Briefcase,
            color: 'from-purple-600 to-pink-600',
          },
          {
            label: t('ui.statInProgress'),
            value: stats.active,
            icon: Clock,
            color: 'from-cyan-500 to-purple-600',
          },
          {
            label: t('ui.statCompleted'),
            value: stats.done,
            icon: CheckCircle2,
            color: 'from-emerald-500 to-cyan-500',
          },
          {
            label: t('ui.statUnpaidInvoices'),
            value: stats.openInvoices,
            icon: Receipt,
            color: 'from-orange-500 to-pink-500',
          },
        ]
          // Faz 2E: izni olmayan bölümün sayacı (hep 0) gösterilmiyor.
          .filter((s) => (s.label === t('ui.statUnpaidInvoices') ? izinVar(['faturalar']) : izinVar(['projeler'])))
          .map((s) => (
          <div
            key={s.label}
            className="p-6 rounded-2xl glass flex items-center gap-4"
          >
            <div
              className={`w-12 h-12 rounded-xl bg-gradient-to-br ${s.color} flex items-center justify-center shrink-0`}
            >
              <s.icon className="h-5 w-5 text-white" />
            </div>
            <div>
              <p className="text-xs uppercase tracking-widest text-muted-foreground">
                {s.label}
              </p>
              <p className="cam-parla text-3xl font-bold">{s.value}</p>
            </div>
          </div>
        ))}
      </div>

      {modulAcik('krediler') && izinVar(['krediler']) && (
        <Suspense fallback={null}>
          <KrediOzetKarti onAc={() => setTab('krediler')} />
        </Suspense>
      )}

      {/* Tabs — kalabalıksa (Faz 7M) ya da düz çubuk sığmıyorsa (Faz 7K) gruplu menü, değilse bugünkü düz çubuk. */}
      <div ref={setMenuKabugu} data-menu-kabugu={grupluMenu ? (grupluSayi ? 'gruplu' : 'gruplu-genislik') : 'duz'}>
      {grupluMenu ? (
        <Suspense fallback={<div className="mb-8 h-24" aria-hidden="true" />}>
          <MusteriMenusu
            sekmeler={TABS}
            aktif={tab}
            onSec={(k) => setTab(k as Tab)}
            rozetler={{ mesajlar: okunmamisMesaj }}
            modulDurumu={modulBilgisi ? 'sunucu' : modulHatasi ? 'hata' : 'yukleniyor'}
          />
        </Suspense>
      ) : (
      <div
        ref={setDuzCubuk}
        className="cam-sekmeler flex gap-1 mb-8 border-b border-white/10 overflow-x-auto"
        data-sekme-cubugu
        data-moduller={modulBilgisi ? 'sunucu' : modulHatasi ? 'hata' : 'yukleniyor'}
      >
        {TABS.map((tItem) => (
          <button
            key={tItem.key}
            data-sekme={tItem.key}
            data-secili={tab === tItem.key ? 'evet' : undefined}
            onClick={() => setTab(tItem.key)}
            className={`px-5 py-3 text-sm font-medium transition-colors relative inline-flex items-center gap-2 whitespace-nowrap max-2xl:px-4 max-xl:px-3 ${
              tab === tItem.key
                ? 'text-foreground'
                : 'text-muted-foreground hover:text-foreground'
            }`}
          >
            <tItem.icon className="h-4 w-4" />
            {tItem.label}
            {tItem.key === 'mesajlar' && okunmamisMesaj > 0 && (
              <span
                className="inline-flex min-w-[1.25rem] items-center justify-center rounded-full bg-pink-600 px-1.5 text-[11px] font-semibold leading-5 text-white"
                data-rozet={okunmamisMesaj}
                aria-label={t('ui.tabMesajlar') + ': ' + okunmamisMesaj}
              >
                {okunmamisMesaj > 99 ? '99+' : okunmamisMesaj}
              </span>
            )}
            {tab === tItem.key && (
              <span className="absolute bottom-0 left-0 right-0 h-0.5 bg-gradient-to-r from-purple-500 to-pink-500" />
            )}
          </button>
        ))}
      </div>
      )}
      </div>

      {dataLoading ? (
        <div className="py-16 flex items-center justify-center text-muted-foreground">
          <Loader2 className="h-5 w-5 animate-spin mr-2" /> {t('ui.loading')}
        </div>
      ) : error ? (
        <div className="p-6 rounded-xl bg-destructive/10 border border-destructive/30 text-destructive text-sm">
          {error}
          <Button
            onClick={loadData}
            variant="outline"
            size="sm"
            className="ml-4 !bg-transparent border-white/20"
          >
            {t('ui.retry')}
          </Button>
        </div>
      ) : (
        <>
          {/*
            Hiçbir kaydı olmayan müşteriye sebebini söylüyoruz.
            Panel kayıtları `client_email` ile eşleştiriyor; müşteri
            projedekinden farklı bir adresle kaydolduysa üç sekme de boş
            geliyor ve bunun sebebi ekranda hiçbir yerde yazmıyordu —
            müşteri "panel çalışmıyor" diye arıyordu. Boş bir ekranın
            "kaydınız yok" mu "yanlış hesap" mı demek olduğu belli olmalı.
          */}
          {etkin.kendi && projects.length === 0 && invoices.length === 0 && tickets.length === 0 && (
            <div className="mb-6 rounded-2xl border border-amber-500/30 bg-amber-500/10 p-5">
              <p className="text-sm font-medium text-amber-200">
                {t('ui.emailMismatchTitle')}
              </p>
              <p className="mt-2 text-sm leading-relaxed text-amber-200/80">
                {t('ui.emailMismatchDesc', { email })}
              </p>
              <Link to="/contact" className="mt-4 inline-block">
                <Button
                  size="sm"
                  variant="outline"
                  className="!bg-transparent border-amber-400/40 text-amber-100 hover:border-amber-300"
                >
                  {t('ui.emailMismatchCta')}
                </Button>
              </Link>
            </div>
          )}

          {tab === 'projects' && modulAcik('gorevler') && izinVar(['gorevler']) && projects.length > 0 && (
            <Suspense fallback={null}>
              <RevizyonGostergesi />
            </Suspense>
          )}

          {tab === 'projects' && (
            <div className="grid gap-4">
              {projects.length === 0 ? (
                <div className="p-10 rounded-2xl glass text-center">
                  <p className="text-muted-foreground mb-4">
                    {t('ui.noProjectsDesc')}
                  </p>
                  <Button
                    /*
                      Eskiden iletişim sayfasına gidiyordu: oturumu açık
                      müşteriyi herkese açık bir forma göndermek, zaten
                      bildiğimiz bilgileri ona tekrar yazdırmak demekti.
                      Artık panelin kendi talep sekmesini açıyor.
                    */
                    onClick={() => setTab('tickets')}
                    className="bg-gradient-to-r from-purple-600 to-pink-600 text-white border-0"
                  >
                    {t('ui.startProject')}
                  </Button>
                </div>
              ) : (
                projects.map((p) => (
                  <div
                    key={p.id}
                    className="p-5 rounded-2xl glass flex flex-col md:flex-row gap-5 hover:border-purple-500/40 transition-colors"
                  >
                    <div className="md:w-48 aspect-video rounded-xl overflow-hidden bg-gradient-to-br from-purple-950/40 to-pink-950/40 shrink-0">
                      {p.image_url ? (
                        <img
                          src={p.image_url}
                          alt={p.title}
                          className="w-full h-full object-cover"
                        />
                      ) : (
                        <div className="w-full h-full flex items-center justify-center text-3xl font-bold gradient-text">
                          {p.title.charAt(0)}
                        </div>
                      )}
                    </div>
                    <div className="min-w-0 flex-1">
                      <div className="flex flex-wrap items-center gap-2 mb-2">
                        <span className="text-[10px] uppercase tracking-widest text-purple-400">
                          {p.category}
                        </span>
                        <span
                          className={`text-[10px] uppercase tracking-widest px-2 py-0.5 rounded-full ${
                            p.status === 'completed'
                              ? 'bg-emerald-500/15 text-emerald-300'
                              : p.status === 'in_progress'
                                ? 'bg-cyan-500/15 text-cyan-300'
                                : 'bg-white/10 text-muted-foreground'
                          }`}
                        >
                          {statusLabel(p.status, 'planning')}
                        </span>
                      </div>
                      <h3 className="text-xl font-semibold mb-2">{p.title}</h3>
                      <p className="text-sm text-muted-foreground line-clamp-2 mb-3">
                        {p.description}
                      </p>

                      {/* Aşama & ilerleme */}
                      <div className="mb-3">
                        <div className="flex items-center justify-between text-xs mb-1.5">
                          <span className="text-muted-foreground">
                            {t('ui.stage')}: {stageLabel(p.stage) || t('ui.notSet')}
                          </span>
                          <span className="text-purple-300 font-medium">
                            {typeof p.progress === 'number' ? p.progress : 0}%
                          </span>
                        </div>
                        <div className="h-2 rounded-full bg-white/10 overflow-hidden">
                          <div
                            className="h-full rounded-full bg-gradient-to-r from-purple-500 to-pink-500 transition-all"
                            style={{
                              width: `${Math.min(Math.max(p.progress ?? 0, 0), 100)}%`,
                            }}
                          />
                        </div>
                      </div>

                      {/*
                        Proje geçmişi katlanmış geliyor: müşteri birden çok
                        projeye sahipse liste açıkken okunmaz oluyordu.
                        `details` içeriği HTML'de duruyor, tıklayınca açılıyor.
                      */}
                      {modulAcik('gorevler') && izinVar(['gorevler']) && (
                        <Suspense fallback={null}>
                          <ProjeGorevGorunumu projeId={Number(p.id)} />
                        </Suspense>
                      )}

                      {/* Varsayılan kapalı modül: bilgi gelmeden parça indirilmesin. */}
                      {modulBilgisi && modulAcik('zaman_takibi') && izinVar(['projeler']) && (
                        <Suspense fallback={null}>
                          <HarcananSureKarti projeId={Number(p.id)} />
                        </Suspense>
                      )}

                      {/* Faz 4W: projenin müşteriye görünür özel alanları (salt okunur; yoksa çizilmez). */}
                      {izinVar(['projeler']) && (
                        <Suspense fallback={null}>
                          <OzelAlanlarBolumu varlik="proje" kimlik={Number(p.id)} mod="musteri" className="mb-3" />
                        </Suspense>
                      )}

                      <details className="mb-3 rounded-xl border border-white/10 bg-white/[0.02] p-3">
                        <summary className="cursor-pointer text-sm font-semibold text-purple-300 hover:text-pink-300">
                          {t('projectStages.history')}
                        </summary>
                        <div className="mt-4">
                          <ProjectTimeline projectId={Number(p.id)} clientView />
                        </div>
                      </details>

                      {p.tech_stack && (
                        <div className="flex flex-wrap gap-1.5 mb-3">
                          {p.tech_stack
                            .split(',')
                            .slice(0, 5)
                            .map((tech) => (
                              <span
                                key={tech}
                                className="text-[10px] uppercase tracking-wider px-2 py-1 rounded-full bg-white/5 text-muted-foreground"
                              >
                                {tech.trim()}
                              </span>
                            ))}
                        </div>
                      )}
                      {p.project_url && (
                        <a
                          href={p.project_url}
                          target="_blank"
                          rel="noreferrer"
                          className="inline-flex items-center gap-1.5 text-sm text-purple-400 hover:text-pink-400 transition-colors"
                        >
                          {t('ui.viewLive')}{' '}
                          <ExternalLink className="h-3.5 w-3.5" />
                        </a>
                      )}
                    </div>
                  </div>
                ))
              )}
            </div>
          )}

          {tab === 'invoices' && (
            // Faz 3T: teklifler + sözleşmeler (imza) + faturalar (bakiye, ödemeler, PDF, öde).
            <Suspense fallback={<div className="flex justify-center py-16"><Loader2 className="h-6 w-6 animate-spin text-muted-foreground" /></div>}>
              <Faturalarim key={etkinEmail || email} />
            </Suspense>
          )}

          {tab === 'tickets' && (
            <Suspense fallback={null}>
              <DestekYardim kbAcik={modulAcik('bilgi_bankasi')} />
            </Suspense>
          )}

          {tab === 'tickets' && (
            <div className="grid gap-8 lg:grid-cols-2">
              <div className="p-6 rounded-2xl glass h-fit">
                <h3 className="text-lg font-semibold mb-4">
                  {t('ui.newTicket')}
                </h3>
                <div className="space-y-4">
                  {/*
                    Hizmet düğmeleri. Müşteri "sitemde şunu değiştir"
                    derken hangi iş kalemi olduğunu seçiyor; talep
                    panele o etiketle düşüyor ve doğru kişiye gidiyor.
                    Boş bırakılamıyor: varsayılan "genel".
                  */}
                  <div>
                    <Label className="mb-2 block text-xs uppercase tracking-widest text-muted-foreground">
                      {t('talep.hizmetSec')}
                    </Label>
                    <div className="flex flex-wrap gap-2">
                      {HIZMETLER.map((h) => (
                        <button
                          key={h}
                          type="button"
                          onClick={() => setTicketForm({ ...ticketForm, hizmet: h })}
                          aria-pressed={ticketForm.hizmet === h}
                          className={`rounded-full border px-3 py-1.5 text-xs transition-colors ${
                            ticketForm.hizmet === h
                              ? 'border-purple-400/60 bg-purple-500/20 text-white'
                              : 'border-white/10 bg-white/[0.03] text-muted-foreground hover:border-white/25'
                          }`}
                        >
                          {t(`talep.hizmetler.${h}`)}
                        </button>
                      ))}
                    </div>
                  </div>
                  <div>
                    <Label className="mb-2 block text-xs uppercase tracking-widest text-muted-foreground">
                      {t('ui.subject')} *
                    </Label>
                    <Input
                      value={ticketForm.subject}
                      onChange={(e) =>
                        setTicketForm({
                          ...ticketForm,
                          subject: e.target.value,
                        })
                      }
                      placeholder={t('ui.ticketSubjectPlaceholder')}
                      className="bg-white/5 border-white/10"
                      data-testid="talep-konu"
                    />
                  </div>
                  {modulAcik('bilgi_bankasi') && (
                    <Suspense fallback={null}>
                      <KbOnerileri konu={ticketForm.subject} />
                    </Suspense>
                  )}
                  <div>
                    <Label className="mb-2 block text-xs uppercase tracking-widest text-muted-foreground">
                      {t('ui.message')} *
                    </Label>
                    <Textarea
                      rows={5}
                      value={ticketForm.message}
                      onChange={(e) =>
                        setTicketForm({
                          ...ticketForm,
                          message: e.target.value,
                        })
                      }
                      placeholder={t('ui.ticketMessagePlaceholder')}
                      className="bg-white/5 border-white/10"
                      data-testid="talep-mesaj"
                    />
                  </div>
                  <Button
                    onClick={submitTicket}
                    disabled={sending}
                    data-testid="talep-gonder"
                    className="w-full h-11 gap-2 bg-gradient-to-r from-purple-600 to-pink-600 text-white border-0"
                  >
                    {sending ? (
                      <Loader2 className="h-4 w-4 animate-spin" />
                    ) : (
                      <Send className="h-4 w-4" />
                    )}
                    {t('ui.send')}
                  </Button>
                </div>
              </div>

              <div className="grid gap-3">
                <h3 className="text-lg font-semibold">
                  {t('ui.myTickets')} ({tickets.length})
                </h3>
                {tickets.length === 0 ? (
                  <div className="p-8 rounded-2xl glass text-center text-muted-foreground text-sm">
                    {t('ui.noTickets')}
                  </div>
                ) : (
                  tickets.map((tk) => (
                    <div key={tk.id} className="p-5 rounded-2xl glass">
                      <div className="flex items-center gap-2 mb-2">
                        <h4 className="font-semibold">{tk.subject}</h4>
                        <span
                          className={`text-[10px] uppercase tracking-widest px-2 py-0.5 rounded-full ${
                            tk.status === 'closed'
                              ? 'bg-white/10 text-muted-foreground'
                              : tk.status === 'answered'
                                ? 'bg-emerald-500/15 text-emerald-300'
                                : 'bg-pink-500/15 text-pink-300'
                          }`}
                        >
                          {statusLabel(tk.status, 'open')}
                        </span>
                        {tk.hizmet ? (
                          <span className="rounded-full border border-white/10 px-2 py-0.5 text-[10px] uppercase tracking-widest text-muted-foreground">
                            {t(`talep.hizmetler.${tk.hizmet}`, { defaultValue: tk.hizmet })}
                          </span>
                        ) : null}
                        {tk.kaynak === 'eposta' ? (
                          <Suspense fallback={null}>
                            <EpostaRozeti />
                          </Suspense>
                        ) : null}
                      </div>
                      {acikTalep !== Number(tk.id) ? (
                        <p className="text-sm text-muted-foreground whitespace-pre-wrap line-clamp-2">
                          {tk.message}
                        </p>
                      ) : null}

                      <button
                        type="button"
                        onClick={() =>
                          setAcikTalep(acikTalep === Number(tk.id) ? null : Number(tk.id))
                        }
                        className="mt-3 text-xs font-medium text-purple-300 hover:text-purple-200"
                      >
                        {acikTalep === Number(tk.id) ? t('talep.kapat') : t('talep.ac')}
                      </button>

                      {acikTalep === Number(tk.id) ? (
                        <>
                          <TalepYazismasi ticketId={Number(tk.id)} bizKimiz="musteri" />
                          <Suspense fallback={null}>
                            <EpostaIpucu />
                          </Suspense>
                        </>
                      ) : null}
                    </div>
                  ))
                )}
              </div>
              {(modulAcik('geri_bildirim') || modulAcik('oneri_kutusu')) && (
                <div className="grid gap-8 lg:col-span-2 lg:grid-cols-2">
                  {modulAcik('geri_bildirim') && (
                    <Suspense fallback={null}>
                      <GeriBildirimlerim yenile={geriBildirimSayaci} />
                    </Suspense>
                  )}
                  {modulAcik('oneri_kutusu') && (
                    <Suspense fallback={null}>
                      <OneriKutusu />
                    </Suspense>
                  )}
                </div>
              )}
            </div>
          )}

          {tab === 'raporlar' && modulAcik('raporlar') && (
            <div>
              {modulAcik('aylik_rapor') && (
                <Suspense fallback={null}>
                  <AylikRaporArsivi />
                </Suspense>
              )}
              <h3 className="mb-4 text-lg font-semibold">{t('rapor.sekme')}</h3>
              <RaporArsivi />
            </div>
          )}

          {tab === 'sitem' && modulAcik('sitem') && (
            <div>
              <h3 className="mb-4 text-lg font-semibold">{t('sitem.sekme')}</h3>
              <SiteBakimIzni />
              <Suspense fallback={null}>
                <SitemBakim />
              </Suspense>
            </div>
          )}

          {tab === 'mesajlar' && modulAcik('mesajlar') && (
            <Suspense
              fallback={
                <div className="py-16 flex items-center justify-center text-muted-foreground">
                  <Loader2 className="h-5 w-5 animate-spin" />
                </div>
              }
            >
              <Mesajlar
                projeler={projects.map((p) => ({ id: Number(p.id), baslik: p.title }))}
                onOkunmamis={setOkunmamisMesaj}
              />
            </Suspense>
          )}

          {tab === 'asistanlar' && modulBilgisi !== null && modulAcik('uzman_asistanlar') && izinVar(['asistanlar']) && (
            <Suspense
              fallback={
                <div className="flex items-center justify-center py-20 text-muted-foreground">
                  <Loader2 className="h-5 w-5 animate-spin" />
                </div>
              }
            >
              <UzmanAsistanlar />
            </Suspense>
          )}

          {tab === 'qr' && modulBilgisi !== null && modulAcik('dinamik_qr') && izinVar(['qr']) && (
            <Suspense
              fallback={
                <div className="flex items-center justify-center py-20 text-muted-foreground">
                  <Loader2 className="h-5 w-5 animate-spin" />
                </div>
              }
            >
              <DinamikQr mod="musteri" />
            </Suspense>
          )}

          {tab === 'kartvizit' &&
            modulBilgisi !== null &&
            (modulAcik('dijital_kartvizit') || modulAcik('google_yorum_sayfasi')) &&
            izinVar(['kartvizit']) && (
              <Suspense
                fallback={
                  <div className="flex items-center justify-center py-20 text-muted-foreground">
                    <Loader2 className="h-5 w-5 animate-spin" />
                  </div>
                }
              >
                <Kartvizit mod="musteri" kartAcik={modulAcik('dijital_kartvizit')} yorumAcik={modulAcik('google_yorum_sayfasi')} />
              </Suspense>
            )}
          {tab === 'menu' && modulBilgisi !== null && (modulAcik('qr_menu') || modulAcik('whatsapp_katalog')) && izinVar(['menu']) && (
            <Suspense
              fallback={
                <div className="flex items-center justify-center py-20 text-muted-foreground">
                  <Loader2 className="h-5 w-5 animate-spin" />
                </div>
              }
            >
              <QrMenu mod="musteri" />
            </Suspense>
          )}
          {tab === 'otomasyon' && modulBilgisi !== null && modulAcik('otomasyon') && izinVar(['otomasyon']) && (
            <Suspense
              fallback={
                <div className="flex items-center justify-center py-20 text-muted-foreground">
                  <Loader2 className="h-5 w-5 animate-spin" />
                </div>
              }
            >
              <Otomasyon mod="musteri" />
            </Suspense>
          )}
          {tab === 'randevu' && modulBilgisi !== null && modulAcik('randevu') && izinVar(['randevu']) && (
            <Suspense
              fallback={
                <div className="flex items-center justify-center py-20 text-muted-foreground">
                  <Loader2 className="h-5 w-5 animate-spin" />
                </div>
              }
            >
              <Randevu mod="musteri" />
            </Suspense>
          )}
          {tab === 'aiAsistan' && modulBilgisi !== null && modulAcik('ai_asistan') && izinVar(['asistan']) && (
            <Suspense
              fallback={
                <div className="flex items-center justify-center py-20 text-muted-foreground">
                  <Loader2 className="h-5 w-5 animate-spin" />
                </div>
              }
            >
              <AiAsistan mod="musteri" />
            </Suspense>
          )}

          {tab === 'icerik' && modulBilgisi !== null && modulAcik('icerik_studyosu') && izinVar(['icerik']) && (
            <Suspense
              fallback={
                <div className="flex items-center justify-center py-20 text-muted-foreground">
                  <Loader2 className="h-5 w-5 animate-spin" />
                </div>
              }
            >
              <IcerikStudyosu mod="musteri" />
            </Suspense>
          )}

          {tab === 'epostaPazarlama' && modulBilgisi !== null && modulAcik('eposta_pazarlama') && izinVar(['pazarlama']) && (
            <Suspense
              fallback={
                <div className="flex items-center justify-center py-20 text-muted-foreground">
                  <Loader2 className="h-5 w-5 animate-spin" />
                </div>
              }
            >
              <EpostaPazarlama mod="musteri" />
            </Suspense>
          )}

          {tab === 'sahaServisi' && modulBilgisi !== null && modulAcik('saha_servisi') && izinVar(['saha_yonetim', 'saha_teknisyen']) && (
            <Suspense
              fallback={
                <div className="flex items-center justify-center py-20 text-muted-foreground">
                  <Loader2 className="h-5 w-5 animate-spin" />
                </div>
              }
            >
              <SahaServisi mod="musteri" />
            </Suspense>
          )}

          {tab === 'etkinlik' && modulBilgisi !== null && modulAcik('etkinlik_bilet') && izinVar(['etkinlik', 'etkinlik_giris']) && (
            <Suspense
              fallback={
                <div className="flex items-center justify-center py-20 text-muted-foreground">
                  <Loader2 className="h-5 w-5 animate-spin" />
                </div>
              }
            >
              <Etkinlik mod="musteri" yalnizGiris={!izinVar(['etkinlik'])} />
            </Suspense>
          )}

          {tab === 'stokPos' && modulBilgisi !== null && modulAcik('stok_pos') && izinVar(['stok', 'kasa']) && (
            <Suspense
              fallback={
                <div className="flex items-center justify-center py-20 text-muted-foreground">
                  <Loader2 className="h-5 w-5 animate-spin" />
                </div>
              }
            >
              <StokPos mod="musteri" />
            </Suspense>
          )}

          {tab === 'egitim' && modulBilgisi !== null && modulAcik('egitim') && izinVar(['egitim', 'egitim_egitmen']) && (
            <Suspense
              fallback={
                <div className="flex items-center justify-center py-20 text-muted-foreground">
                  <Loader2 className="h-5 w-5 animate-spin" />
                </div>
              }
            >
              <Egitim mod="musteri" />
            </Suspense>
          )}

          {tab === 'ik' && modulBilgisi !== null && modulAcik('insan_kaynaklari') && izinVar(['ik']) && (
            <Suspense
              fallback={
                <div className="flex items-center justify-center py-20 text-muted-foreground">
                  <Loader2 className="h-5 w-5 animate-spin" />
                </div>
              }
            >
              <Ik mod="musteri" />
            </Suspense>
          )}

          {tab === 'hukuk' && modulBilgisi !== null && modulAcik('hukuk_burosu') && izinVar(['hukuk']) && (
            <Suspense
              fallback={
                <div className="flex items-center justify-center py-20 text-muted-foreground">
                  <Loader2 className="h-5 w-5 animate-spin" />
                </div>
              }
            >
              <Hukuk mod="musteri" />
            </Suspense>
          )}

          {tab === 'api' && modulBilgisi !== null && modulAcik('api_erisimi') && izinVar(['api']) && (
            <Suspense
              fallback={
                <div className="flex items-center justify-center py-20 text-muted-foreground">
                  <Loader2 className="h-5 w-5 animate-spin" />
                </div>
              }
            >
              <ApiErisimi mod="musteri" />
            </Suspense>
          )}

          {tab === 'dosyalar' && (modulAcik('dosyalar') || belgeSekmesi) && (
            <Suspense
              fallback={
                <div className="flex items-center justify-center py-20 text-muted-foreground">
                  <Loader2 className="h-5 w-5 animate-spin" />
                </div>
              }
            >
              <DosyalarVeBelgeler
                mod="musteri"
                dosyalarAcik={modulAcik('dosyalar') && izinVar(['dosyalar'])}
                belgelerAcik={modulAcik('belgeler') && izinVar(['belgeler'])}
              />
            </Suspense>
          )}

          {tab === 'krediler' && modulAcik('krediler') && (
            <Suspense
              fallback={
                <div className="flex items-center justify-center py-20 text-muted-foreground">
                  <Loader2 className="h-5 w-5 animate-spin" />
                </div>
              }
            >
              <Kredilerim eposta={etkinEmail || user.email} ad={etkin.kendi ? user.name : etkin.ad || undefined} />
            </Suspense>
          )}

          {tab === 'analiz' && modulAcik('site_analizi') && (
            <Suspense
              fallback={
                <div className="flex items-center justify-center py-20 text-muted-foreground">
                  <Loader2 className="h-5 w-5 animate-spin" />
                </div>
              }
            >
              <SiteAnalizim />
            </Suspense>
          )}

          {tab === 'profile' && (
            <div className="space-y-6">
              <div className="max-w-xl p-6 rounded-2xl glass">
                <h3 className="text-lg font-semibold mb-4">{t('ui.profileSettings')}</h3>
                <div className="space-y-4">
                  <div>
                    <Label className="mb-2 block text-xs uppercase tracking-widest text-muted-foreground">
                      {t('ui.emailReadonly')}
                    </Label>
                    <Input
                      value={user.email || ''}
                      disabled
                      className="bg-white/5 border-white/10 opacity-70"
                    />
                  </div>
                  <div>
                    <Label className="mb-2 block text-xs uppercase tracking-widest text-muted-foreground">
                      {t('ui.fullName')}
                    </Label>
                    <Input
                      value={profile.name}
                      onChange={(e) =>
                        setProfile({ ...profile, name: e.target.value })
                      }
                      className="bg-white/5 border-white/10"
                    />
                  </div>
                  <div>
                    <Label className="mb-2 block text-xs uppercase tracking-widest text-muted-foreground">
                      {t('ui.phone')}
                    </Label>
                    <Input
                      value={profile.phone}
                      onChange={(e) =>
                        setProfile({ ...profile, phone: e.target.value })
                      }
                      className="bg-white/5 border-white/10"
                    />
                  </div>
                  <div>
                    <Label className="mb-2 block text-xs uppercase tracking-widest text-muted-foreground">
                      {t('ui.company')}
                    </Label>
                    <Input
                      value={profile.company}
                      onChange={(e) =>
                        setProfile({ ...profile, company: e.target.value })
                      }
                      className="bg-white/5 border-white/10"
                    />
                  </div>
                  <Button
                    onClick={saveProfile}
                    className="h-11 bg-gradient-to-r from-purple-600 to-pink-600 text-white border-0"
                  >
                    {t('ui.save')}
                  </Button>
                  <p className="text-xs text-muted-foreground pt-2 border-t border-white/10">
                    {t('ui.forQuestions')}:{' '}
                    <a
                      href={`mailto:${settings.contact_email}`}
                      className="text-purple-400 hover:text-pink-400"
                    >
                      {settings.contact_email}
                    </a>
                  </p>
                </div>
              </div>
              <Suspense
                fallback={
                  <div className="flex max-w-xl items-center justify-center py-10 text-muted-foreground">
                    <Loader2 className="h-5 w-5 animate-spin" aria-hidden="true" />
                  </div>
                }
              >
                <HesapEkibi />
              </Suspense>
              {modulAcik('marka_temasi') && (
                <Suspense
                  fallback={
                    <div className="flex max-w-xl items-center justify-center py-10 text-muted-foreground">
                      <Loader2 className="h-5 w-5 animate-spin" aria-hidden="true" />
                    </div>
                  }
                >
                  <MarkaAyari />
                </Suspense>
              )}
              <Suspense
                fallback={
                  <div className="flex max-w-xl items-center justify-center py-10 text-muted-foreground">
                    <Loader2 className="h-5 w-5 animate-spin" />
                  </div>
                }
              >
                <BildirimTercihleri />
              </Suspense>
              <Suspense
                fallback={
                  <div className="flex max-w-xl items-center justify-center py-10 text-muted-foreground">
                    <Loader2 className="h-5 w-5 animate-spin" aria-hidden="true" />
                  </div>
                }
              >
                <Oturumlarim />
              </Suspense>
              <Suspense
                fallback={
                  <div className="flex max-w-xl items-center justify-center py-10 text-muted-foreground">
                    <Loader2 className="h-5 w-5 animate-spin" aria-hidden="true" />
                  </div>
                }
              >
                <Silinenlerim />
              </Suspense>
              {modulAcik('denetim') && (
                <Suspense
                  fallback={
                    <div className="flex max-w-xl items-center justify-center py-10 text-muted-foreground">
                      <Loader2 className="h-5 w-5 animate-spin" aria-hidden="true" />
                    </div>
                  }
                >
                  <HesapHareketleri />
                </Suspense>
              )}
              <Suspense
                fallback={
                  <div className="flex items-center justify-center py-10 text-muted-foreground">
                    <Loader2 className="h-5 w-5 animate-spin" aria-hidden="true" />
                  </div>
                }
              >
                <Modullerim bilgi={modulBilgisi} hata={modulHatasi} />
              </Suspense>
            </div>
          )}
        </>
      )}

      {/* "Hata bildir": her sekmede sağ altta küçük düğme. */}
      {modulAcik('geri_bildirim') && izinVar(['projeler', 'destek']) && (
        <Suspense fallback={null}>
          <HataBildir
            projeler={hataProjeleri}
            onGonderildi={() => setGeriBildirimSayaci((s) => s + 1)}
          />
        </Suspense>
      )}
      </div>
      )}
    </div>
  );
}