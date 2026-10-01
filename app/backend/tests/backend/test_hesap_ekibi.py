"""Faz 2E — müşteri hesabında birden çok kişi (kişi bazlı yetki) + hesaplar arası geçiş.

Kapsam:
* Rol/izin matrisi: BÜTÜN müşteri uçları için sahip (başlıksız) geçer, izinli
  üye (`X-MK-Hesap`) geçer, izinsiz üye 403 `hesap_izni_yok`, üye olmayan 403
  `hesap_uyesi_degil`.
* Tarama: başkasının hesabını başlıkla isteyen üye-olmayan kişi, kişisel ya da
  herkese açık olarak işaretlenmemiş HİÇBİR uçtan 2xx almamalı (gözden kaçan uç kalmasın).
* Davet akışı, süre, tek kullanım, yanlış e-posta; üyelik silinince/pasifte
  erişim anında düşer; hesap yöneticisi yetki yükseltemez; bildirim alıcı
  genişletmesi; kişi yazar / hesap sahiplik ayrımı; güvenlik incelemesindeki
  IDOR düzeltmeleri.
"""

import io
import json
import uuid
from datetime import timedelta

import pytest
from sqlalchemy import select

from conftest import jeton_uret

BASLIK = "X-MK-Hesap"


def _e(on: str) -> str:
    return f"{on}-{uuid.uuid4().hex[:8]}@ekip.dev"


def _b(eposta: str, hesap: str | None = None, rol: str = "user") -> dict:
    h = {"Authorization": f"Bearer {jeton_uret(eposta, rol)}"}
    if hesap:
        h[BASLIK] = hesap
    return h


@pytest.fixture(autouse=True)
def _ortam(monkeypatch):
    """Modül kapısı bu dosyada konu değil: hepsi açık. Önbellek/hız sınırı temiz."""
    from routers import hesap_ekibi as r
    from services import hesap_ekibi as s
    from services import moduller

    async def _hep_acik(db, eposta, anahtar):
        return True

    monkeypatch.setattr(moduller, "modul_acik_mi", _hep_acik)
    from routers import site_bakim

    monkeypatch.setattr(site_bakim, "modul_acik_mi", _hep_acik)
    s.onbellegi_temizle()
    r._hiz.temizle()
    yield
    s.onbellegi_temizle()


async def _uye_ekle(db, hesap, uye, rol, izinler=None, durum="aktif"):
    from models.hesap_uyeleri import HesapUyeleri
    from services import hesap_ekibi as s

    satir = HesapUyeleri(
        hesap_email=hesap,
        uye_email=uye,
        rol=rol,
        izinler=json.dumps(list(izinler if izinler is not None else s.ROL_VARSAYILAN[rol])),
        durum=durum,
        olusturma=s.simdi(),
    )
    db.add(satir)
    await db.commit()
    await db.refresh(satir)
    s.onbellegi_temizle()
    return satir


async def _ekle(db, nesne):
    db.add(nesne)
    await db.commit()
    await db.refresh(nesne)
    return nesne


@pytest.fixture
async def ekip(db_oturumu):
    """Sahip + uye + fatura + kısıtlı (izinsiz) üye + yabancı; sahibin kayıtları."""
    from models.client_sites import Client_sites
    from models.dosyalar import BelgeTalepleri
    from models.geri_bildirim import FeedbackItems
    from models.inquiries import Inquiries
    from models.invoices import Invoices
    from models.pricing import Pricing_inquiries
    from models.projects import Projects
    from models.site_analyses import Site_analyses
    from models.support_tickets import Support_tickets
    from services import imzali_islem

    db = db_oturumu
    k = {
        "sahip": _e("sahip"),
        "uye": _e("uye"),
        "fatura": _e("fatura"),
        "kisitli": _e("kisitli"),
        "yabanci": _e("yabanci"),
    }
    await _uye_ekle(db, k["sahip"], k["uye"], "uye")
    await _uye_ekle(db, k["sahip"], k["fatura"], "fatura")
    await _uye_ekle(db, k["sahip"], k["kisitli"], "uye", izinler=[])

    s = k["sahip"]
    p = await _ekle(db, Projects(title="Gizli proje", description="d", category="Web", client_email=s,
                                  client_name="Sahip A.Ş.", published=False, status="in_progress"))
    f = await _ekle(db, Invoices(invoice_no=f"F-{uuid.uuid4().hex[:5]}", client_email=s, amount=100.0, status="unpaid"))
    t = await _ekle(db, Support_tickets(client_email=s, subject="Konu", message="Mesaj", status="open"))
    q = await _ekle(db, Inquiries(name="Sahip", email=s, message="Merhaba"))
    site = await _ekle(db, Client_sites(client_email=s, ad="Sahip sitesi", adres="https://sahip.example"))
    a = await _ekle(db, Site_analyses(alan_adi="sahip.example", url="https://sahip.example", durum="tamam", eposta=s,
                                       kaynak="musteri"))
    g = await _ekle(db, FeedbackItems(musteri_eposta=s, baslik="Hata", tur="hata", durum="yeni", oncelik="normal"))
    bt = await _ekle(db, BelgeTalepleri(client_email=s, baslik="Vergi levhası", durum="bekliyor"))
    teklif = await _ekle(db, Pricing_inquiries(scale_kod="kobi", profile_kod="standart", period="aylik",
                                               hesaplanan_tutar=100.0, musteri_eposta=s, kaynak="website"))
    _, islem_proje = await imzali_islem.olustur(db, "teslimat_onay", ("projects", p.id), s, "Teslim onayı")
    _, islem_teklif = await imzali_islem.olustur(db, "teklif_kabul", ("pricing_inquiries", teklif.id), s, "Teklif")
    # Faz 2G: sahibin konuşması ve ajansın bir mesajı.
    from models.mesajlar import KonusmaMesajlari, Konusmalar

    konusma = await _ekle(db, Konusmalar(hesap_email=s, konu="Ekip konuşması", durum="acik", degisiklik=0))
    ajans_mesaji = await _ekle(db, KonusmaMesajlari(konusma_id=konusma.id, yazan_email="yonetici@test.dev",
                                                    yazan_rol="admin", metin="Merhaba", silindi=False))
    konusma.son_mesaj_id = konusma.son_admin_mesaj_id = ajans_mesaji.id
    await db.commit()
    # Faz 3U: sahibin bir uzman asistan sohbeti (kişiye özel: üye 404 alır — "gecti").
    from models.uzman_asistanlar import AsistanSohbetleri

    asistan_sohbeti = await _ekle(db, AsistanSohbetleri(hesap_email=s, kisi_email=s, asistan_anahtar="seo-specialist",
                                                        baslik="Sahibin sohbeti", silindi=False))
    # Faz 4Q: sahibin bir dinamik QR kaydı.
    from models.dinamik_qr import DinamikQr

    qr = await _ekle(db, DinamikQr(hesap_email=s, kod=uuid.uuid4().hex[:7], ad="Sahibin QR'ı", tur="url",
                                   alanlar=json.dumps({"url": "https://sahip.example"}), hedef="https://sahip.example",
                                   tarama_sayisi=0))
    k.update(P=p.id, F=f.id, T=t.id, Q=q.id, S=site.id, A=a.id, G=g.id, B=bt.id,
             I_PROJE=islem_proje.id, I_TEKLIF=islem_teklif.id, K=konusma.id, KM=ajans_mesaji.id,
             AS=asistan_sohbeti.id, QR=qr.id)
    # Faz 4K: sahibin bir dijital kartviziti, yorum sayfası ve ikisine gelmiş birer mesaj.
    from models.kartvizit import KartvizitMesajlari, Kartvizitler, YorumSayfalari

    kart = await _ekle(db, Kartvizitler(hesap_email=s, kod="K" + uuid.uuid4().hex[:6], slug="sahip-" + uuid.uuid4().hex[:8],
                                        ad_soyad="Sahip Kişi", icerik=json.dumps({"ad_soyad": "Sahip Kişi"})))
    yorum = await _ekle(db, YorumSayfalari(hesap_email=s, kod="Y" + uuid.uuid4().hex[:6], slug="kafe-" + uuid.uuid4().hex[:8],
                                           isletme_adi="Sahip Kafe", place_id="ChIJN1t_tDeuEmsRUsoyG83frY4"))
    kart_mesaji = await _ekle(db, KartvizitMesajlari(sahip_tur="kart", sahip_id=kart.id, hesap_email=s, ad="Ziyaretçi",
                                                     eposta="z@ornek.com"))
    yorum_mesaji = await _ekle(db, KartvizitMesajlari(sahip_tur="yorum", sahip_id=yorum.id, hesap_email=s, mesaj="Geri bildirim"))
    k.update(KV=kart.id, YS=yorum.id, KVM=kart_mesaji.id, YSM=yorum_mesaji.id)
    # Faz 4M: sahibin bir QR menüsü (kategori + ürün + kupon + sipariş).
    from models.qr_menu import MenuKategorileri, MenuKuponlari, MenuMagazalari, MenuSiparisleri, MenuUrunleri

    menu = await _ekle(db, MenuMagazalari(hesap_email=s, slug=f"ekip-{uuid.uuid4().hex[:8]}", duzen="menu",
                                          ad="Sahibin menüsü", whatsapp="+905551112233"))
    mkat = await _ekle(db, MenuKategorileri(magaza_id=menu.id, ad="İçecekler", sira=1))
    murun = await _ekle(db, MenuUrunleri(magaza_id=menu.id, kategori_id=mkat.id, ad="Çay", fiyat=2000, sira=1))
    mkupon = await _ekle(db, MenuKuponlari(magaza_id=menu.id, kod="EKIP10", tur="yuzde", deger=10))
    msip = await _ekle(db, MenuSiparisleri(magaza_id=menu.id, siparis_no=uuid.uuid4().hex[:8].upper(), kalemler="[]",
                                           musteri_ad="Ali"))
    k.update(MM=menu.id, MK=mkat.id, MU=murun.id, MC=mkupon.id, MS=msip.id)
    return k


# ---------------------------------------------------------------------------
# Müşteri uçları × izin matrisi
# ---------------------------------------------------------------------------
#: (metot, yol, izinler (biri yeterli; None = her aktif üye), gövde, sahip için beklenen)
#: Beklenen `"gecti"`: hesap/izin kontrolünden geçti (401 ya da hesap 403'ü değil);
#: kayıt yok (404), gövde geçersiz (422), iş kuralı (409) olabilir.
GOVDE_DOSYA = "__dosya__"
MUSTERI_UCLARI = [
    ("GET", "/api/v1/entities/projects", ("projeler",), None, 200),
    ("GET", "/api/v1/entities/projects/all", ("projeler",), None, 200),
    ("GET", "/api/v1/entities/projects/{P}", ("projeler",), None, 200),
    ("GET", "/api/v1/entities/project_events?project_id={P}", ("projeler",), None, 200),
    ("GET", "/api/v1/entities/inquiries", ("projeler",), None, 200),
    ("GET", "/api/v1/entities/inquiries/all", ("projeler",), None, 200),
    ("GET", "/api/v1/entities/inquiries/{Q}", ("projeler",), None, 200),
    ("GET", "/api/v1/entities/invoices", ("faturalar",), None, 200),
    ("GET", "/api/v1/entities/invoices/all", ("faturalar",), None, 200),
    ("GET", "/api/v1/entities/invoices/{F}", ("faturalar",), None, 200),
    ("GET", "/api/v1/entities/support_tickets", ("destek",), None, 200),
    ("GET", "/api/v1/entities/support_tickets/all", ("destek",), None, 200),
    ("GET", "/api/v1/entities/support_tickets/{T}", ("destek",), None, 200),
    ("POST", "/api/v1/entities/support_tickets", ("destek",), {"subject": "Yeni", "message": "Metin"}, 201),
    ("GET", "/api/v1/talep/{T}/mesajlar", ("destek",), None, 200),
    ("POST", "/api/v1/talep/{T}/mesaj", ("destek",), {"mesaj": "Ekipten yanıt"}, 200),
    ("POST", "/api/v1/talep/{T}/ekler/999999/indirme-baglantisi", ("destek",), None, "gecti"),
    ("GET", "/api/v1/destek/sla-bilgisi", ("destek",), None, 200),
    ("GET", "/api/v1/kredilerim", ("krediler",), None, 200),
    ("GET", "/api/v1/dosyalarim", ("dosyalar",), None, 200),
    ("POST", "/api/v1/dosyalarim/yukle", ("dosyalar",), GOVDE_DOSYA, "gecti"),
    ("POST", "/api/v1/dosyalarim/999999/indirme-baglantisi", ("dosyalar",), None, "gecti"),
    ("GET", "/api/v1/dosyalarim/talepler", ("dosyalar",), None, 200),
    ("POST", "/api/v1/dosyalarim/talepler/{B}/yukle", ("dosyalar",), GOVDE_DOSYA, "gecti"),
    ("GET", "/api/v1/gorevlerim/revizyon", ("gorevler",), None, 200),
    ("GET", "/api/v1/gorevlerim/proje/{P}", ("gorevler",), None, 200),
    ("GET", "/api/v1/islemlerim", ("faturalar", "projeler", "raporlar"), None, 200),
    ("POST", "/api/v1/islemlerim/{I_PROJE}", ("projeler",), {"sonuc": "onay"}, "gecti"),
    ("POST", "/api/v1/islemlerim/{I_TEKLIF}", ("faturalar",), {"sonuc": "red", "not": "pahalı"}, "gecti"),
    ("GET", "/api/v1/raporlarim", ("raporlar", "abonelikler"), None, 200),
    ("GET", "/api/v1/raporlarim/aylik", ("raporlar",), None, 200),
    ("GET", "/api/v1/site-analizi/benim", ("siteler",), None, 200),
    ("POST", "/api/v1/site-analizi/benim", ("siteler",), {}, "gecti"),
    ("GET", "/api/v1/site-analizi/benim/{A}", ("siteler",), None, 200),
    ("GET", "/api/v1/sitelerim", ("siteler",), None, 200),
    ("POST", "/api/v1/sitelerim/{S}/izin", ("siteler",), {"izin": True}, 200),
    ("GET", "/api/v1/sitelerim/{S}/gunluk", ("siteler",), None, 200),
    ("GET", "/api/v1/sitelerim-bakim", ("siteler",), None, 200),
    ("POST", "/api/v1/sitelerim-bakim/{S}/durum-sayfasi", ("siteler",), {"acik": False}, 200),
    # Faz 2H — teknik SEO + hız izleme (tarama ağsız: conftest DNS'i kapatıyor → hata satırı, 200).
    ("GET", "/api/v1/sitelerim/{S}/seo-gecmisi", ("siteler",), None, 200),
    ("POST", "/api/v1/sitelerim/{S}/seo-tara", ("siteler",), None, "gecti"),
    ("GET", "/api/v1/geri-bildirimlerim", ("projeler", "destek"), None, 200),
    ("POST", "/api/v1/geri-bildirimlerim", ("projeler", "destek"), {"__form__": {"baslik": "Buton bozuk"}}, 200),
    ("POST", "/api/v1/geri-bildirimlerim/{G}/ek", ("projeler", "destek"), GOVDE_DOSYA, "gecti"),
    ("GET", "/api/v1/geri-bildirim-ek/999999", ("projeler", "destek"), None, "gecti"),
    ("GET", "/api/v1/cop-kutum", None, None, 200),
    ("POST", "/api/v1/cop-kutum/999999/geri-al", None, None, "gecti"),
    ("GET", "/api/v1/denetim/benim", None, None, 200),
    ("GET", "/api/v1/modullerim", None, None, 200),
    ("GET", "/api/v1/duyurularim", None, None, 200),
    ("POST", "/api/v1/duyurularim/999999/okundu", None, None, "gecti"),
    ("POST", "/api/v1/duyurularim/999999/kapat", None, None, "gecti"),
    ("GET", "/api/v1/hesabim/uyeler", None, None, 200),
    # Faz 2G — mesajlaşma (`mesajlar` izni).
    ("GET", "/api/v1/mesajlarim/ozet", ("mesajlar",), None, 200),
    ("GET", "/api/v1/mesajlarim/konusmalar", ("mesajlar",), None, 200),
    ("POST", "/api/v1/mesajlarim/konusmalar", ("mesajlar",), {"konu": "Ekipten konu"}, 200),
    ("GET", "/api/v1/mesajlarim/konusmalar/{K}/mesajlar", ("mesajlar",), None, 200),
    ("POST", "/api/v1/mesajlarim/konusmalar/{K}/mesajlar", ("mesajlar",), {"metin": "Ekipten mesaj"}, 200),
    ("POST", "/api/v1/mesajlarim/konusmalar/{K}/okundu", ("mesajlar",), {"mesaj_id": 1}, 200),
    ("PUT", "/api/v1/mesajlarim/mesajlar/{KM}", ("mesajlar",), {"metin": "değiştir"}, "gecti"),
    ("DELETE", "/api/v1/mesajlarim/mesajlar/{KM}", ("mesajlar",), None, "gecti"),
    ("POST", "/api/v1/mesajlarim/ekler", ("mesajlar",), GOVDE_DOSYA, "gecti"),
    ("POST", "/api/v1/mesajlarim/mesajlar/{KM}/ekler/999999/indirme-baglantisi", ("mesajlar",), None, "gecti"),
    # Faz 3U — Uzman Asistanlar (model çağrısı conftest'te "ağ yok": mesaj ucu 503/409 → "gecti").
    ("GET", "/api/v1/asistanlarim", ("asistanlar",), None, 200),
    ("GET", "/api/v1/asistanlarim/sohbetler", ("asistanlar",), None, 200),
    ("POST", "/api/v1/asistanlarim/sohbetler", ("asistanlar",), {"asistan_anahtar": "seo-specialist"}, "gecti"),
    ("GET", "/api/v1/asistanlarim/sohbetler/{AS}", ("asistanlar",), None, 200),
    ("POST", "/api/v1/asistanlarim/sohbetler/{AS}/mesaj", ("asistanlar",), {"icerik": "Merhaba"}, "gecti"),
    ("DELETE", "/api/v1/asistanlarim/sohbetler/999999", ("asistanlar",), None, "gecti"),
    # Faz 4Q — Dinamik QR ve kısa link (`qr` izni).
    ("GET", "/api/v1/qr-kodlarim/meta", ("qr",), None, 200),
    ("GET", "/api/v1/qr-kodlarim", ("qr",), None, 200),
    ("POST", "/api/v1/qr-kodlarim", ("qr",), {"ad": "Ekip QR", "tur": "url", "alanlar": {"url": "https://ornek.com"}}, 200),
    ("POST", "/api/v1/qr-kodlarim/onizleme", ("qr",), {"tur": "url"}, 200),
    ("POST", "/api/v1/qr-kodlarim/toplu/onizleme", ("qr",), GOVDE_DOSYA, "gecti"),
    ("POST", "/api/v1/qr-kodlarim/toplu/olustur", ("qr",), {"satirlar": []}, "gecti"),
    ("POST", "/api/v1/qr-kodlarim/zip", ("qr",), {"idler": [999999], "bicim": "svg"}, "gecti"),
    ("GET", "/api/v1/qr-kodlarim/{QR}", ("qr",), None, 200),
    ("PUT", "/api/v1/qr-kodlarim/{QR}", ("qr",), {"ad": "Yeni ad"}, 200),
    ("GET", "/api/v1/qr-kodlarim/{QR}/analiz", ("qr",), None, 200),
    ("GET", "/api/v1/qr-kodlarim/{QR}/gorsel?bicim=svg", ("qr",), None, 200),
    ("DELETE", "/api/v1/qr-kodlarim/999999", ("qr",), None, "gecti"),
    # Faz 4K — Dijital kartvizit ve Google yorum sayfası (`kartvizit` izni).
    ("GET", "/api/v1/kartvizitlerim/meta", ("kartvizit",), None, 200),
    ("GET", "/api/v1/kartvizitlerim/slug-uygun?slug=ekip-karti", ("kartvizit",), None, 200),
    ("GET", "/api/v1/kartvizitlerim/mesajlar", ("kartvizit",), None, 200),
    ("PUT", "/api/v1/kartvizitlerim/mesajlar/{KVM}", ("kartvizit",), {"okundu": True}, 200),
    ("DELETE", "/api/v1/kartvizitlerim/mesajlar/999999", ("kartvizit",), None, "gecti"),
    ("GET", "/api/v1/kartvizitlerim", ("kartvizit",), None, 200),
    ("POST", "/api/v1/kartvizitlerim", ("kartvizit",), {"icerik": {"ad_soyad": "Ekip Kartı"}}, 200),
    ("GET", "/api/v1/kartvizitlerim/{KV}", ("kartvizit",), None, 200),
    ("PUT", "/api/v1/kartvizitlerim/{KV}", ("kartvizit",), {"aktif": True}, 200),
    ("POST", "/api/v1/kartvizitlerim/{KV}/gorsel", ("kartvizit",), GOVDE_DOSYA, "gecti"),
    ("DELETE", "/api/v1/kartvizitlerim/{KV}/gorsel/999999", ("kartvizit",), None, "gecti"),
    ("PUT", "/api/v1/kartvizitlerim/{KV}/galeri-sira", ("kartvizit",), {"idler": []}, 200),
    ("GET", "/api/v1/kartvizitlerim/{KV}/analiz", ("kartvizit",), None, 200),
    ("GET", "/api/v1/kartvizitlerim/{KV}/qr?bicim=svg", ("kartvizit",), None, 200),
    ("DELETE", "/api/v1/kartvizitlerim/999999", ("kartvizit",), None, "gecti"),
    ("GET", "/api/v1/yorum-sayfalarim/meta", ("kartvizit",), None, 200),
    ("GET", "/api/v1/yorum-sayfalarim/slug-uygun?slug=ekip-kafe", ("kartvizit",), None, 200),
    ("GET", "/api/v1/yorum-sayfalarim/geri-bildirimler", ("kartvizit",), None, 200),
    ("PUT", "/api/v1/yorum-sayfalarim/geri-bildirimler/{YSM}", ("kartvizit",), {"okundu": True}, 200),
    ("DELETE", "/api/v1/yorum-sayfalarim/geri-bildirimler/999999", ("kartvizit",), None, "gecti"),
    ("GET", "/api/v1/yorum-sayfalarim", ("kartvizit",), None, 200),
    ("POST", "/api/v1/yorum-sayfalarim", ("kartvizit",), {"isletme_adi": "Ekip Kafe", "place_id": "ChIJN1t_tDeuEmsRUsoyG83frY4"}, 200),
    ("GET", "/api/v1/yorum-sayfalarim/{YS}", ("kartvizit",), None, 200),
    ("PUT", "/api/v1/yorum-sayfalarim/{YS}", ("kartvizit",), {"aktif": True}, 200),
    ("POST", "/api/v1/yorum-sayfalarim/{YS}/logo", ("kartvizit",), GOVDE_DOSYA, "gecti"),
    ("DELETE", "/api/v1/yorum-sayfalarim/{YS}/logo", ("kartvizit",), None, 200),
    ("GET", "/api/v1/yorum-sayfalarim/{YS}/analiz", ("kartvizit",), None, 200),
    ("GET", "/api/v1/yorum-sayfalarim/{YS}/qr?bicim=svg", ("kartvizit",), None, 200),
    ("DELETE", "/api/v1/yorum-sayfalarim/999999", ("kartvizit",), None, "gecti"),
    # Faz 4M — QR menü ve WhatsApp katalog (`menu` izni). Sahibin zaten bir menüsü var:
    # yeni mağaza sınırda (409) → "gecti".
    ("GET", "/api/v1/menulerim/meta", ("menu",), None, 200),
    ("GET", "/api/v1/menulerim/siparis-ozeti", ("menu",), None, 200),
    ("GET", "/api/v1/menulerim", ("menu",), None, 200),
    ("POST", "/api/v1/menulerim", ("menu",), {"ad": "Ekip menüsü", "duzen": "menu"}, "gecti"),
    ("GET", "/api/v1/menulerim/{MM}", ("menu",), None, 200),
    ("PUT", "/api/v1/menulerim/{MM}", ("menu",), {"aciklama": "Ekipten"}, 200),
    ("GET", "/api/v1/menulerim/{MM}/icerik", ("menu",), None, 200),
    ("POST", "/api/v1/menulerim/{MM}/kategoriler", ("menu",), {"ad": "Tatlılar"}, 200),
    ("POST", "/api/v1/menulerim/{MM}/kategoriler/sirala", ("menu",), {"idler": []}, 200),
    ("PUT", "/api/v1/menulerim/{MM}/kategoriler/{MK}", ("menu",), {"ad": "Sıcak içecekler"}, 200),
    ("DELETE", "/api/v1/menulerim/{MM}/kategoriler/999999", ("menu",), None, "gecti"),
    ("POST", "/api/v1/menulerim/{MM}/urunler", ("menu",), {"kategori_id": 999999, "ad": "Kahve", "fiyat": "45"}, "gecti"),
    ("POST", "/api/v1/menulerim/{MM}/urunler/sirala", ("menu",), {"idler": []}, 200),
    ("PUT", "/api/v1/menulerim/{MM}/urunler/{MU}", ("menu",), {"fiyat": "25,50"}, 200),
    ("DELETE", "/api/v1/menulerim/{MM}/urunler/999999", ("menu",), None, "gecti"),
    ("POST", "/api/v1/menulerim/{MM}/gorsel", ("menu",), GOVDE_DOSYA, "gecti"),
    ("POST", "/api/v1/menulerim/{MM}/ceviri", ("menu",), {"tur": "magaza"}, "gecti"),
    ("GET", "/api/v1/menulerim/{MM}/kuponlar", ("menu",), None, 200),
    ("POST", "/api/v1/menulerim/{MM}/kuponlar", ("menu",), {"kod": "YENI5", "tur": "yuzde", "deger": 5}, "gecti"),
    ("PUT", "/api/v1/menulerim/{MM}/kuponlar/{MC}", ("menu",), {"aktif": True}, 200),
    ("DELETE", "/api/v1/menulerim/{MM}/kuponlar/999999", ("menu",), None, "gecti"),
    ("GET", "/api/v1/menulerim/{MM}/siparisler", ("menu",), None, 200),
    ("GET", "/api/v1/menulerim/{MM}/siparisler/{MS}", ("menu",), None, 200),
    ("PUT", "/api/v1/menulerim/{MM}/siparisler/{MS}", ("menu",), {"durum": "hazirlaniyor"}, 200),
    ("GET", "/api/v1/menulerim/{MM}/analiz", ("menu",), None, 200),
    ("GET", "/api/v1/menulerim/{MM}/qr?bicim=svg", ("menu",), None, 200),
    ("POST", "/api/v1/menulerim/{MM}/masa-qr", ("menu",), {"bas": 1, "bit": 2, "bicim": "svg"}, "gecti"),
    ("POST", "/api/v1/menulerim/{MM}/ice-aktar/onizleme", ("menu",), GOVDE_DOSYA, "gecti"),
    ("POST", "/api/v1/menulerim/{MM}/ice-aktar", ("menu",), {"satirlar": []}, "gecti"),
    ("DELETE", "/api/v1/menulerim/999999", ("menu",), None, "gecti"),
    # Faz 3T — faturalarım (bakiye, PDF, ödeme bağlantısı), tekliflerim, sözleşmelerim (`faturalar` izni).
    ("GET", "/api/v1/faturalarim", ("faturalar",), None, 200),
    ("GET", "/api/v1/faturalarim/{F}", ("faturalar",), None, 200),
    ("GET", "/api/v1/faturalarim/{F}/pdf", ("faturalar",), None, 200),
    ("POST", "/api/v1/faturalarim/{F}/odeme-baglantisi", ("faturalar",), None, 200),
    ("GET", "/api/v1/faturalarim/{F}/odemeler/999999/dekont", ("faturalar",), None, "gecti"),
    ("GET", "/api/v1/tekliflerim", ("faturalar",), None, 200),
    ("GET", "/api/v1/tekliflerim/999999", ("faturalar",), None, "gecti"),
    ("POST", "/api/v1/tekliflerim/999999/karar", ("faturalar",), {"sonuc": "kabul", "ad_soyad": "Ekip Üyesi"}, "gecti"),
    ("GET", "/api/v1/tekliflerim/999999/pdf", ("faturalar",), None, "gecti"),
    ("GET", "/api/v1/sozlesmelerim", ("faturalar",), None, 200),
    ("GET", "/api/v1/sozlesmelerim/999999", ("faturalar",), None, "gecti"),
    ("POST", "/api/v1/sozlesmelerim/999999/imza", ("faturalar",), {"ad_soyad": "Ekip Üyesi", "onay": True}, "gecti"),
    ("GET", "/api/v1/sozlesmelerim/999999/pdf", ("faturalar",), None, "gecti"),
    # Faz 3Z — projenin harcanan süre özeti (`projeler` izni; modül + proje ayarı kapalıysa 403/404 → "gecti").
    ("GET", "/api/v1/zamanim/proje/{P}", ("projeler",), None, "gecti"),
]


def _kod(yanit) -> str:
    try:
        d = yanit.json().get("detail")
    except Exception:  # noqa: BLE001
        return ""
    return d.get("kod", "") if isinstance(d, dict) else ""


async def _cagir(istemci, metot, yol, govde, basliklar):
    if govde == GOVDE_DOSYA:
        dosya = {"dosya" if "geri-bildirim" not in yol else "ekran": ("not.txt", io.BytesIO(b"merhaba"), "text/plain")}
        return await istemci.request(metot, yol, files=dosya, headers=basliklar)
    if isinstance(govde, dict) and "__form__" in govde:
        return await istemci.request(metot, yol, data=govde["__form__"], headers=basliklar)
    if govde is None:
        return await istemci.request(metot, yol, headers=basliklar)
    return await istemci.request(metot, yol, json=govde, headers=basliklar)


def _gecti_mi(yanit) -> bool:
    if yanit.status_code == 401:
        return False
    return not (yanit.status_code == 403 and _kod(yanit) in ("hesap_izni_yok", "hesap_uyesi_degil"))


def _beklenen(yanit, beklenen) -> bool:
    return _gecti_mi(yanit) if beklenen == "gecti" else yanit.status_code == beklenen


def _izinli_uye(k, izinler):
    from services.hesap_ekibi import ROL_VARSAYILAN

    if izinler is None:
        return k["kisitli"]
    for rol, kisi in (("uye", k["uye"]), ("fatura", k["fatura"])):
        if any(i in ROL_VARSAYILAN[rol] for i in izinler):
            return kisi
    raise AssertionError(izinler)


@pytest.mark.parametrize("metot,yol,izinler,govde,beklenen", MUSTERI_UCLARI, ids=[f"{m} {y}" for m, y, *_ in MUSTERI_UCLARI])
async def test_musteri_ucu_izin_matrisi(istemci, ekip, metot, yol, izinler, govde, beklenen):
    k = ekip
    yol = yol.format(**k)
    s = k["sahip"]

    # 1) Sahip, başlıksız (eski davranış) — ve kendi e-postasını başlıkta verse de aynı.
    y = await _cagir(istemci, metot, yol, govde, _b(s))
    assert _beklenen(y, beklenen), (yol, y.status_code, y.text[:300])
    y = await _cagir(istemci, metot, yol, govde, _b(s, s))
    assert _gecti_mi(y), (yol, y.status_code, y.text[:300])

    # 2) İzinli üye, sahibin hesabında.
    y = await _cagir(istemci, metot, yol, govde, _b(_izinli_uye(k, izinler), s))
    assert _gecti_mi(y), ("izinli üye", yol, y.status_code, y.text[:300])

    # 3) İzinsiz üye (hiç izni yok) → 403 hesap_izni_yok.
    if izinler is not None:
        y = await _cagir(istemci, metot, yol, govde, _b(k["kisitli"], s))
        assert y.status_code == 403 and _kod(y) == "hesap_izni_yok", ("izinsiz üye", yol, y.status_code, y.text[:300])

    # 4) Üye olmayan, başlıkla → 403 hesap_uyesi_degil (kendi hesabına sessizce düşmez).
    y = await _cagir(istemci, metot, yol, govde, _b(k["yabanci"], s))
    assert y.status_code == 403 and _kod(y) == "hesap_uyesi_degil", ("yabancı", yol, y.status_code, y.text[:300])


async def test_uye_sahibin_kayitlarini_gorur_yabanci_kendi_bos_hesabini(istemci, ekip):
    k = ekip
    y = await istemci.get("/api/v1/entities/projects/all", headers=_b(k["uye"], k["sahip"]))
    assert y.status_code == 200
    assert [p["id"] for p in y.json()["items"] if p["id"] == k["P"]] == [k["P"]]
    # Başlıksız aynı kişi: kendi (boş) hesabı.
    y = await istemci.get("/api/v1/entities/projects/all", headers=_b(k["uye"]))
    assert all(p["id"] != k["P"] for p in y.json()["items"])
    # Sorguda başka hesap yazmak işe yaramaz (süzgeç etkin hesabı zorluyor).
    sorgu = json.dumps({"client_email": k["sahip"]})
    y = await istemci.get(f"/api/v1/entities/invoices?query={sorgu}", headers=_b(k["yabanci"]))
    assert y.status_code == 200 and y.json()["items"] == []


async def test_fatura_rolu_proje_ve_destek_goremez(istemci, ekip):
    k = ekip
    b = _b(k["fatura"], k["sahip"])
    for yol in ("/api/v1/entities/projects", f"/api/v1/entities/support_tickets/{k['T']}", "/api/v1/gorevlerim/revizyon",
                f"/api/v1/talep/{k['T']}/mesajlar", "/api/v1/dosyalarim"):
        y = await istemci.get(yol, headers=b)
        assert y.status_code == 403 and _kod(y) == "hesap_izni_yok", (yol, y.text)
    y = await istemci.get("/api/v1/entities/invoices", headers=b)
    assert y.status_code == 200 and [i["id"] for i in y.json()["items"]] == [k["F"]]
    # İşlemler: yalnız teklif görünür; teslim onayı (projeler) kararı 403.
    y = await istemci.get("/api/v1/islemlerim", headers=b)
    assert {i["tur"] for i in y.json()} == {"teklif_kabul"}
    y = await istemci.post(f"/api/v1/islemlerim/{k['I_PROJE']}", json={"sonuc": "onay"}, headers=b)
    assert y.status_code == 403 and _kod(y) == "hesap_izni_yok"


async def test_uye_rolu_faturalari_goremez(istemci, ekip):
    k = ekip
    y = await istemci.get(f"/api/v1/entities/invoices/{k['F']}", headers=_b(k["uye"], k["sahip"]))
    assert y.status_code == 403 and _kod(y) == "hesap_izni_yok"
    y = await istemci.get("/api/v1/islemlerim", headers=_b(k["uye"], k["sahip"]))
    assert {i["tur"] for i in y.json()} == {"teslimat_onay"}


# ---------------------------------------------------------------------------
# Tarama: gözden kaçan müşteri ucu var mı?
# ---------------------------------------------------------------------------
#: Başlıktan bağımsız (kişiye ait ya da herkese açık) olduğu için üye-olmayan
#: kişinin başlıkla 2xx alabileceği uçlar. Buraya eklenen her satır bilinçli bir karar.
KISISEL_YA_DA_ACIK = {
    # Kişiye ait: oturumlar, bildirim tercihleri/çanı, profil, hesap listesi.
    ("GET", "/api/v1/oturumlarim"),
    ("POST", "/api/v1/oturumlarim/digerlerini-kapat"),
    ("GET", "/api/v1/bildirim/tercihlerim"),
    ("PUT", "/api/v1/bildirim/tercihlerim"),
    ("POST", "/api/v1/bildirim/push/dene"),
    # Ajans personeli: kendine atanmış siteler (müşteri hesabıyla ilgisi yok; müşteriye boş liste).
    ("GET", "/api/v1/musteri-sitesi"),
    # Faz 3Z: "personel miyim?" — kişiye ait (hesaptan bağımsız); veri yok, yalnız bayrak.
    ("GET", "/api/v1/zaman/ben"),
    ("GET", "/api/v1/bildirim/push/anahtar"),
    ("DELETE", "/api/v1/bildirim/push/abone"),
    ("GET", "/api/v1/entities/notifications"),
    ("GET", "/api/v1/hesaplarim"),
    ("GET", "/api/v1/auth/me"),
    # Herkese açık katalog / içerik.
    ("GET", "/api/v1/moduller"),
    ("GET", "/api/v1/marketplace"),
    # Faz 3K: sitedeki Kaynaklar listesi ve ayrıntısı (yalnız yayındakiler).
    ("GET", "/api/v1/kaynaklar"),
    ("GET", "/api/v1/kaynaklar/{slug}"),
    ("GET", "/api/v1/fiyat-hesapla"),
    ("GET", "/api/v1/talep/hizmetler"),
    ("GET", "/api/v1/destek/eposta-bilgisi"),
    ("GET", "/api/v1/entities/project_events/stages"),
}
# Faz 2H: `/api/v1/storage/` artık yalnız yönetici — taramadan çıkarılmadı, taranıyor.
TARAMA_ATLA_ONEK = ("/api/v1/auth/",)


def _yolu_doldur(yol: str, k: dict) -> str:
    import re

    yerine = {"hesap_email": k["sahip"], "eposta": k["sahip"]}
    return re.sub(r"\{(\w+)\}", lambda m: yerine.get(m.group(1), "1" if m.group(1).endswith("id") else "x"), yol)


def _rotalar(app):
    def gez(rotalar):
        for r in rotalar:
            if hasattr(r, "original_router"):
                yield from gez(r.original_router.routes)
                continue
            if getattr(r, "methods", None) and getattr(r, "endpoint", None) is not None:
                yield r

    return list(gez(app.routes))


async def test_tarama_uye_olmayan_baslikla_hicbir_hesap_ucundan_veri_alamaz(istemci, ekip, uygulama):
    k = ekip
    b = _b(k["yabanci"], k["sahip"])
    sizanlar = []
    for r in _rotalar(uygulama):
        if not r.path.startswith("/api/") or r.path.startswith(TARAMA_ATLA_ONEK):
            continue
        for metot in sorted(r.methods - {"HEAD", "OPTIONS"}):
            if (metot, r.path) in KISISEL_YA_DA_ACIK:
                continue
            yol = _yolu_doldur(r.path, k)
            if metot in ("GET", "DELETE"):
                y = await istemci.request(metot, yol, headers=b)
            else:
                y = await istemci.request(metot, yol, json={}, headers=b)
            if 200 <= y.status_code < 300:
                sizanlar.append(f"{metot} {r.path} → {y.status_code}")
    # Herkese açık okumalar (vitrin, blog, katalog, imzalı bağlantılar…) zaten
    # oturumsuz da açık; onları ayırmak için aynı isteği oturumsuz deniyoruz.
    gercek = []
    for satir in sizanlar:
        metot, yol = satir.split(" ")[0], satir.split(" ")[1]
        y = await istemci.request(metot, _yolu_doldur(yol, k), **({} if metot in ("GET", "DELETE") else {"json": {}}))
        if not (200 <= y.status_code < 300):
            gercek.append(satir)
    assert gercek == [], "Hesap bağlamına geçirilmemiş uç(lar):\n" + "\n".join(gercek)


# ---------------------------------------------------------------------------
# Davet akışı
# ---------------------------------------------------------------------------
def _jeton(yanit_json) -> str:
    baglanti = yanit_json["baglanti"]
    assert baglanti.startswith("https://mehmetkuru.dev/hesap-davet/")
    return baglanti.rsplit("/", 1)[1]


async def test_davet_olustur_kabul_erisim(istemci, db_oturumu):
    from models.hesap_uyeleri import HesapUyeleri
    from models.invoices import Invoices
    from services.hesap_ekibi import jeton_ozeti

    sahip, kisi = _e("sahip"), _e("yeni")
    await _ekle(db_oturumu, Invoices(invoice_no="D-1", client_email=sahip, amount=5.0))
    y = await istemci.post("/api/v1/hesabim/uyeler", json={"email": kisi.upper(), "rol": "fatura"}, headers=_b(sahip))
    assert y.status_code == 200, y.text
    govde = y.json()
    assert govde["uye"]["durum"] == "davet" and govde["uye"]["uye_email"] == kisi
    assert govde["uye"]["izinler"] == ["faturalar", "krediler", "abonelikler"]
    assert govde["eposta_durumu"] in ("sent", "skipped", "failed", "off")
    jeton = _jeton(govde)

    # Ham jeton veritabanında yok; yalnız özeti.
    satir = (await db_oturumu.execute(select(HesapUyeleri).where(HesapUyeleri.uye_email == kisi))).scalar_one()
    assert satir.davet_jetonu_ozet == jeton_ozeti(jeton) and jeton not in json.dumps(govde["uye"])

    # Davet henüz kabul edilmedi: erişim yok.
    y = await istemci.get("/api/v1/entities/invoices", headers=_b(kisi, sahip))
    assert y.status_code == 403 and _kod(y) == "hesap_uyesi_degil"

    # Girişsiz bilgi: maskeli.
    y = await istemci.get(f"/api/v1/hesap-davet/{jeton}")
    assert y.status_code == 200
    assert y.json()["davet_eposta"].startswith(kisi[0] + "***@") and y.json()["rol"] == "fatura"
    assert sahip not in y.text and kisi not in y.text

    # Girişsiz kabul → 401; başka e-postayla → 403 + açıklama.
    assert (await istemci.post(f"/api/v1/hesap-davet/{jeton}/kabul")).status_code == 401
    y = await istemci.post(f"/api/v1/hesap-davet/{jeton}/kabul", headers=_b(_e("baskasi")))
    assert y.status_code == 403 and _kod(y) == "eposta_uyusmuyor" and "***@" in y.json()["detail"]["beklenen"]

    y = await istemci.post(f"/api/v1/hesap-davet/{jeton}/kabul", headers=_b(kisi))
    assert y.status_code == 200 and y.json()["hesap_email"] == sahip

    # İkinci kullanım: bağlantı artık yok.
    y = await istemci.post(f"/api/v1/hesap-davet/{jeton}/kabul", headers=_b(kisi))
    assert y.status_code == 404
    assert (await istemci.get(f"/api/v1/hesap-davet/{jeton}")).status_code == 404

    # Erişim: faturaları görür, projeleri göremez; hesap listesinde sahip var.
    y = await istemci.get("/api/v1/entities/invoices", headers=_b(kisi, sahip))
    assert y.status_code == 200 and [i["invoice_no"] for i in y.json()["items"]] == ["D-1"]
    y = await istemci.get("/api/v1/entities/projects", headers=_b(kisi, sahip))
    assert y.status_code == 403
    y = await istemci.get("/api/v1/hesaplarim", headers=_b(kisi))
    hesaplar = {h["hesap_email"]: h for h in y.json()["hesaplar"]}
    assert hesaplar[kisi]["kendi"] is True and hesaplar[sahip]["rol"] == "fatura"


async def test_davet_suresi_dolmus_ve_yenileme(istemci, db_oturumu):
    from models.hesap_uyeleri import HesapUyeleri
    from services.hesap_ekibi import simdi

    sahip, kisi = _e("sahip"), _e("gec")
    y = await istemci.post("/api/v1/hesabim/uyeler", json={"email": kisi, "rol": "uye"}, headers=_b(sahip))
    jeton, uye_id = _jeton(y.json()), y.json()["uye"]["id"]
    satir = (await db_oturumu.execute(select(HesapUyeleri).where(HesapUyeleri.id == uye_id))).scalar_one()
    satir.davet_bitis = simdi() - timedelta(minutes=1)
    await db_oturumu.commit()

    assert (await istemci.get(f"/api/v1/hesap-davet/{jeton}")).json()["durum"] == "suresi_doldu"
    y = await istemci.post(f"/api/v1/hesap-davet/{jeton}/kabul", headers=_b(kisi))
    assert y.status_code == 410 and _kod(y) == "davet_suresi_doldu"

    # Yenile: eski bağlantı geçersiz, yenisi çalışır.
    y = await istemci.post(f"/api/v1/hesabim/uyeler/{uye_id}/davet-yenile", headers=_b(sahip))
    assert y.status_code == 200
    yeni = _jeton(y.json())
    assert yeni != jeton
    assert (await istemci.get(f"/api/v1/hesap-davet/{jeton}")).status_code == 404
    assert (await istemci.post(f"/api/v1/hesap-davet/{yeni}/kabul", headers=_b(kisi))).status_code == 200
    # Aktif üyenin daveti yenilenemez.
    y = await istemci.post(f"/api/v1/hesabim/uyeler/{uye_id}/davet-yenile", headers=_b(sahip))
    assert y.status_code == 409 and _kod(y) == "davet_degil"


async def test_davet_kurallari(istemci):
    sahip = _e("sahip")
    b = _b(sahip)
    assert (await istemci.post("/api/v1/hesabim/uyeler", json={"email": sahip, "rol": "uye"}, headers=b)).json()[
        "detail"
    ]["kod"] == "sahip_eklenemez"
    assert (await istemci.post("/api/v1/hesabim/uyeler", json={"email": "bozuk", "rol": "uye"}, headers=b)).status_code == 400
    y = await istemci.post("/api/v1/hesabim/uyeler", json={"email": _e("x"), "rol": "patron"}, headers=b)
    assert _kod(y) == "rol_gecersiz"
    y = await istemci.post("/api/v1/hesabim/uyeler", json={"email": _e("x"), "rol": "uye", "izinler": ["hepsi"]}, headers=b)
    assert _kod(y) == "izin_gecersiz"
    kisi = _e("iki")
    assert (await istemci.post("/api/v1/hesabim/uyeler", json={"email": kisi}, headers=b)).status_code == 200
    y = await istemci.post("/api/v1/hesabim/uyeler", json={"email": kisi}, headers=b)
    assert y.status_code == 409 and _kod(y) == "zaten_uye"
    # Özel izinler: yalnız destek.
    y = await istemci.post(
        "/api/v1/hesabim/uyeler", json={"email": _e("ozel"), "rol": "uye", "izinler": ["destek"]}, headers=b
    )
    assert y.json()["uye"]["izinler"] == ["destek"]


# ---------------------------------------------------------------------------
# Üyelik bitince erişim anında düşer
# ---------------------------------------------------------------------------
async def test_uye_silinince_ve_pasifte_erisim_aninda_duser(istemci, ekip):
    k = ekip
    b = _b(k["uye"], k["sahip"])
    assert (await istemci.get(f"/api/v1/entities/projects/{k['P']}", headers=b)).status_code == 200  # önbellek dolu

    liste = (await istemci.get("/api/v1/hesabim/uyeler", headers=_b(k["sahip"]))).json()["uyeler"]
    uye_id = next(u["id"] for u in liste if u["uye_email"] == k["uye"])

    y = await istemci.put(f"/api/v1/hesabim/uyeler/{uye_id}", json={"durum": "pasif"}, headers=_b(k["sahip"]))
    assert y.status_code == 200 and y.json()["durum"] == "pasif"
    y = await istemci.get(f"/api/v1/entities/projects/{k['P']}", headers=b)
    assert y.status_code == 403 and _kod(y) == "hesap_uyesi_degil"
    assert k["sahip"] not in {h["hesap_email"] for h in (await istemci.get("/api/v1/hesaplarim", headers=_b(k["uye"]))).json()["hesaplar"]}

    await istemci.put(f"/api/v1/hesabim/uyeler/{uye_id}", json={"durum": "aktif"}, headers=_b(k["sahip"]))
    assert (await istemci.get(f"/api/v1/entities/projects/{k['P']}", headers=b)).status_code == 200

    y = await istemci.delete(f"/api/v1/hesabim/uyeler/{uye_id}", headers=_b(k["sahip"]))
    assert y.status_code == 200
    y = await istemci.get(f"/api/v1/entities/projects/{k['P']}", headers=b)
    assert y.status_code == 403 and _kod(y) == "hesap_uyesi_degil"


async def test_rol_degisince_izinler_aninda_gecerli(istemci, ekip):
    k = ekip
    liste = (await istemci.get("/api/v1/hesabim/uyeler", headers=_b(k["sahip"]))).json()["uyeler"]
    uye_id = next(u["id"] for u in liste if u["uye_email"] == k["uye"])
    b = _b(k["uye"], k["sahip"])
    assert (await istemci.get("/api/v1/entities/invoices", headers=b)).status_code == 403
    y = await istemci.put(f"/api/v1/hesabim/uyeler/{uye_id}", json={"rol": "fatura"}, headers=_b(k["sahip"]))
    assert y.json()["izinler"] == ["faturalar", "krediler", "abonelikler"]
    assert (await istemci.get("/api/v1/entities/invoices", headers=b)).status_code == 200
    assert (await istemci.get("/api/v1/entities/projects", headers=b)).status_code == 403


# ---------------------------------------------------------------------------
# Ekip yönetimi yetkileri
# ---------------------------------------------------------------------------
async def test_hesap_yoneticisi_yetki_yukseltemez(istemci, db_oturumu):
    sahip, yon, diger = _e("sahip"), _e("yon"), _e("diger")
    # Yönetici, faturaları hariç her şeye yetkili.
    await _uye_ekle(db_oturumu, sahip, yon, "yonetici",
                    izinler=["projeler", "gorevler", "destek", "dosyalar", "siteler", "raporlar"])
    genis = await _uye_ekle(db_oturumu, sahip, diger, "fatura")
    b = _b(yon, sahip)

    # Kendinde olmayan izni veremez.
    y = await istemci.post("/api/v1/hesabim/uyeler", json={"email": _e("a"), "rol": "fatura"}, headers=b)
    assert y.status_code == 403 and _kod(y) == "yetki_yukseltilemez"
    y = await istemci.post("/api/v1/hesabim/uyeler", json={"email": _e("a"), "rol": "yonetici"}, headers=b)
    assert y.status_code == 403 and _kod(y) == "yetki_yukseltilemez"
    # Alt kümeyle ekleyebilir.
    y = await istemci.post("/api/v1/hesabim/uyeler", json={"email": _e("a"), "rol": "uye", "izinler": ["destek"]}, headers=b)
    assert y.status_code == 200, y.text
    yeni_id = y.json()["uye"]["id"]
    y = await istemci.put(f"/api/v1/hesabim/uyeler/{yeni_id}", json={"izinler": ["destek", "faturalar"]}, headers=b)
    assert y.status_code == 403 and _kod(y) == "yetki_yukseltilemez"
    # Kendinden geniş izinli üyeye dokunamaz; kendini düzenleyemez.
    y = await istemci.delete(f"/api/v1/hesabim/uyeler/{genis.id}", headers=b)
    assert y.status_code == 403 and _kod(y) == "yetki_yukseltilemez"
    liste = (await istemci.get("/api/v1/hesabim/uyeler", headers=b)).json()
    assert liste["yonetebilir"] is True and liste["rolum"] == "yonetici"
    kendi_id = next(u["id"] for u in liste["uyeler"] if u["uye_email"] == yon)
    y = await istemci.put(f"/api/v1/hesabim/uyeler/{kendi_id}", json={"rol": "yonetici", "izinler": ["faturalar"]}, headers=b)
    assert y.status_code == 403 and _kod(y) in ("kendini_duzenleyemez", "yetki_yukseltilemez")
    # Sahip her şeyi yapabilir.
    assert (await istemci.delete(f"/api/v1/hesabim/uyeler/{genis.id}", headers=_b(sahip))).status_code == 200


async def test_uye_ve_fatura_rolu_ekibi_yonetemez(istemci, ekip):
    k = ekip
    for kisi in (k["uye"], k["fatura"]):
        b = _b(kisi, k["sahip"])
        y = await istemci.get("/api/v1/hesabim/uyeler", headers=b)
        assert y.status_code == 200 and y.json()["yonetebilir"] is False  # salt okunur
        y = await istemci.post("/api/v1/hesabim/uyeler", json={"email": _e("z")}, headers=b)
        assert y.status_code == 403 and _kod(y) == "ekip_yetkisi_yok"
        uyeler = (await istemci.get("/api/v1/hesabim/uyeler", headers=b)).json()["uyeler"]
        uye_id = next(u["id"] for u in uyeler if u["uye_email"] != kisi)
        y = await istemci.delete(f"/api/v1/hesabim/uyeler/{uye_id}", headers=b)
        assert y.status_code == 403


async def test_baska_hesabin_uyeligi_yok_sayilir(istemci, ekip):
    """Kendi hesabındaki sahip, başka hesabın üyelik kimliğini değiştiremez (404)."""
    k = ekip
    liste = (await istemci.get("/api/v1/hesabim/uyeler", headers=_b(k["sahip"]))).json()["uyeler"]
    uye_id = liste[0]["id"]
    y = await istemci.delete(f"/api/v1/hesabim/uyeler/{uye_id}", headers=_b(k["yabanci"]))
    assert y.status_code == 404 and _kod(y) == "uye_yok"


async def test_yonetici_basligi_yok_sayar_ve_musteri_adina_yonetir(istemci, ekip, yonetici_basligi):
    k = ekip
    b = {**yonetici_basligi, BASLIK: _e("rastgele")}
    y = await istemci.get("/api/v1/entities/invoices/all", headers=b)
    assert y.status_code == 200 and y.json()["total"] >= 1
    y = await istemci.get(f"/api/v1/musteri-hesaplari/{k['sahip']}/uyeler", headers=yonetici_basligi)
    assert y.status_code == 200 and len(y.json()["uyeler"]) == 3
    y = await istemci.post(
        f"/api/v1/musteri-hesaplari/{k['sahip']}/uyeler", json={"email": _e("ajans"), "rol": "uye"}, headers=yonetici_basligi
    )
    assert y.status_code == 200 and y.json()["uye"]["ekleyen"] == "yonetici@test.dev"
    uye_id = y.json()["uye"]["id"]
    y = await istemci.delete(f"/api/v1/musteri-hesaplari/{k['sahip']}/uyeler/{uye_id}", headers=yonetici_basligi)
    assert y.status_code == 200
    # Müşteri ajans ucunu kullanamaz.
    y = await istemci.get(f"/api/v1/musteri-hesaplari/{k['sahip']}/uyeler", headers=_b(k["sahip"]))
    assert y.status_code == 403


# ---------------------------------------------------------------------------
# Kişi yazar / hesap sahiplik
# ---------------------------------------------------------------------------
async def test_uye_talebi_hesap_adina_acar_yazar_kendisi(istemci, ekip, db_oturumu):
    from models.support_tickets import Support_tickets
    from models.ticket_replies import Ticket_replies

    k = ekip
    b = _b(k["uye"], k["sahip"])
    y = await istemci.post(
        "/api/v1/entities/support_tickets",
        json={"subject": "Ekipten", "message": "m", "client_email": "saldirgan@x.dev"},
        headers=b,
    )
    assert y.status_code == 201
    assert y.json()["client_email"] == k["sahip"] and y.json()["acan_email"] == k["uye"]

    y = await istemci.post(f"/api/v1/talep/{k['T']}/mesaj", json={"mesaj": "Ben yazdım"}, headers=b)
    assert y.status_code == 200
    satir = (
        await db_oturumu.execute(select(Ticket_replies).where(Ticket_replies.ticket_id == k["T"]).order_by(Ticket_replies.id.desc()))
    ).scalars().first()
    assert satir.yazan == "musteri" and satir.yazan_email == k["uye"]
    talep = (await db_oturumu.execute(select(Support_tickets).where(Support_tickets.id == k["T"]))).scalar_one()
    assert talep.client_email == k["sahip"]


async def test_uyelik_degisiklikleri_denetime_duser_jeton_ozeti_maskeli(istemci, db_oturumu):
    from models.audit_log import AuditLog

    sahip, kisi = _e("sahip"), _e("denetim")
    y = await istemci.post("/api/v1/hesabim/uyeler", json={"email": kisi, "rol": "uye"}, headers=_b(sahip))
    uye_id = y.json()["uye"]["id"]
    await istemci.put(f"/api/v1/hesabim/uyeler/{uye_id}", json={"izinler": ["destek"]}, headers=_b(sahip))
    satirlar = (
        await db_oturumu.execute(
            select(AuditLog).where(AuditLog.tablo == "hesap_uyeleri", AuditLog.kayit_id == str(uye_id)).order_by(AuditLog.id)
        )
    ).scalars().all()
    assert [s.islem for s in satirlar][:2] == ["olustur", "guncelle"]
    assert all(s.ilgili_eposta == sahip and s.aktor_eposta == sahip for s in satirlar)
    olusturma = json.loads(satirlar[0].degisiklik_json)
    assert olusturma["davet_jetonu_ozet"][1] == "***"
    # Sahibin "hesap hareketleri"nde görünüyor.
    y = await istemci.get("/api/v1/denetim/benim", headers=_b(sahip))
    assert any(h["tablo"] == "hesap_uyeleri" for h in y.json())


# ---------------------------------------------------------------------------
# Bildirim alıcı genişletmesi
# ---------------------------------------------------------------------------
async def test_bildirim_alicilari_izne_gore_genisler(ekip, db_oturumu):
    from models.notifications import Notifications
    from services.notify import dispatch

    k = ekip
    await _uye_ekle(db_oturumu, k["sahip"], _e("pasif"), "yonetici", durum="pasif")

    async def alicilar(olay):
        satirlar = await dispatch(
            db_oturumu,
            event_type=olay,
            title=f"{olay} {uuid.uuid4().hex[:6]}",
            body="b",
            recipients=[{"email": k["sahip"], "role": "client"}],
            link="/client?sekme=invoices",
        )
        return {s.recipient_email: s for s in satirlar if s.channel == "inapp"}

    fatura = await alicilar("invoice")
    assert set(fatura) == {k["sahip"], k["fatura"]}
    assert fatura[k["sahip"]].link == "/client?sekme=invoices"
    assert fatura[k["fatura"]].link == f"/client?sekme=invoices&hesap={k['sahip'].replace('@', '%40')}"
    assert set(await alicilar("ticket_reply")) == {k["sahip"], k["uye"]}
    # Kişisel / bağlantı taşıyan olaylar genişlemez.
    assert set(await alicilar("yeni_oturum")) == {k["sahip"]}
    assert set(await alicilar("imzali_islem")) == {k["sahip"]}
    assert (await db_oturumu.execute(select(Notifications).where(Notifications.recipient_email == k["kisitli"]))).first() is None


# ---------------------------------------------------------------------------
# Güvenlik incelemesi: eski IDOR'lar
# ---------------------------------------------------------------------------
async def test_proje_zaman_cizelgesi_yalniz_hesabin_projesi_ve_yalniz_acik_kayitlar(istemci, ekip, db_oturumu):
    from models.project_events import Project_events

    k = ekip
    db_oturumu.add(Project_events(project_id=k["P"], event_type="note", title="İç not", visible_to_client="0"))
    db_oturumu.add(Project_events(project_id=k["P"], event_type="note", title="Açık not", visible_to_client="1"))
    await db_oturumu.commit()
    y = await istemci.get(f"/api/v1/entities/project_events?project_id={k['P']}", headers=_b(k["yabanci"]))
    assert y.status_code == 404
    y = await istemci.get(f"/api/v1/entities/project_events?project_id={k['P']}&client_view=false", headers=_b(k["sahip"]))
    assert [e["title"] for e in y.json()["items"]] == ["Açık not"]


async def test_bildirimler_kisiye_daraltilir(istemci, ekip, db_oturumu):
    from services.notify import dispatch

    k = ekip
    await dispatch(db_oturumu, event_type="yeni_oturum", title="Gizli", body="", recipients=[{"email": k["sahip"], "role": "client"}])
    y = await istemci.get(f"/api/v1/entities/notifications?recipient_email={k['sahip']}", headers=_b(k["yabanci"]))
    assert y.status_code == 200 and y.json()["items"] == []
    y = await istemci.get(f"/api/v1/entities/notifications?recipient_email={k['sahip']}", headers=_b(k["sahip"]))
    assert any(i["title"] == "Gizli" for i in y.json()["items"])
    assert (await istemci.get("/api/v1/entities/notifications/log", headers=_b(k["sahip"]))).status_code == 403


async def test_toplu_olusturma_ve_teklif_okuma_yoneticide(istemci, ekip, yonetici_basligi):
    k = ekip
    y = await istemci.post(
        "/api/v1/entities/support_tickets/batch",
        json={"items": [{"subject": "s", "message": "m", "client_email": "baskasi@x.dev"}]},
        headers=_b(k["sahip"]),
    )
    assert y.status_code == 403
    assert (await istemci.post("/api/v1/entities/inquiries/batch", json={"items": []})).status_code == 401
    for tablo in ("pricing_inquiries", "content_posts", "analytics_snapshots", "marketplace_items"):
        assert (await istemci.get(f"/api/v1/entities/{tablo}", headers=_b(k["sahip"]))).status_code == 403, tablo
    assert (await istemci.get("/api/v1/entities/pricing_inquiries", headers=yonetici_basligi)).status_code == 200


async def test_imzali_baglanti_ve_durum_sayfasi_etkilenmez(istemci, ekip, db_oturumu):
    """1E imzalı işlem bağlantısı jetonla çalışır; başlık (geçersiz bile olsa) onu etkilemez."""
    from services import imzali_islem

    k = ekip
    from models.projects import Projects

    p = await _ekle(db_oturumu, Projects(title="T", description="d", category="W", client_email=k["sahip"], stage="review"))
    jeton, _ = await imzali_islem.olustur(db_oturumu, "teslimat_onay", ("projects", p.id), k["sahip"], "Onay")
    y = await istemci.get(f"/api/v1/islem/{jeton}", headers=_b(k["yabanci"], k["sahip"]))
    assert y.status_code == 200
    y = await istemci.get("/api/v1/durum/olmayan-sayfa", headers=_b(k["yabanci"], k["sahip"]))
    assert y.status_code == 404 and _kod(y) == "sayfa_yok"


async def test_destek_izinli_uye_epostayla_yanitlayabilir_izinsiz_yanitlayamaz(ekip, db_oturumu):
    """Faz 2F e-posta yanıtı: talep yanıt bildirimi `destek` izinli üyeye de gidiyor;
    onun yanıtı talebe ekleniyor, izinsiz üyeninki (fatura rolü) ayrı talep oluyor."""
    from models.ticket_replies import Ticket_replies
    from services.eposta_gelen import isle

    k = ekip

    async def yanitla(gonderen, metin):
        return await isle(
            db_oturumu,
            {"message_id": f"<{uuid.uuid4().hex}@t>", "gonderen": gonderen, "konu": f"Re: [#T-{k['T']}] Konu", "metin": metin},
        )

    s = await yanitla(k["uye"], "Ekipten e-posta yanıtı")
    assert s["neden"] == "mesaj_eklendi" and s["talep_id"] == k["T"], s
    db_oturumu.expire_all()
    son = (
        await db_oturumu.execute(select(Ticket_replies).where(Ticket_replies.ticket_id == k["T"]).order_by(Ticket_replies.id.desc()))
    ).scalars().first()
    assert son.yazan_email == k["uye"] and son.mesaj == "Ekipten e-posta yanıtı"

    s = await yanitla(k["fatura"], "Faturacıdan")
    assert s["talep_id"] != k["T"] and s["neden"] == "yeni_talep_yetkisiz_belirtec", s
