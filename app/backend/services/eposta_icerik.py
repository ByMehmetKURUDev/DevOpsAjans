"""Faz 5M — e-posta içeriği: blok doğrulama ve blok → e-posta uyumlu HTML + düz metin.

Saf modül (veritabanı yok). Panel blok tabanlı basit bir düzenleyici kullanıyor;
bloklar JSON olarak saklanıyor ve gönderimde buradan geçiyor.

Blok türleri
------------
* `logo`      — hesabın logosu (yoksa gönderen adı metin olarak)
* `baslik`    — {metin, seviye: 1|2, hiza}
* `metin`     — {metin, hiza}: boş satır = paragraf, `**kalın**`, `[yazı](https://adres)`
* `gorsel`    — {url (https ya da sitenin kendi görsel adresi), alt, baglanti?, genislik: 10..100 (%)}
* `dugme`     — {metin, url, hiza}
* `ayirici`   — {}
* `bosluk`    — {yukseklik: 8..64}
* `iki_sutun` — {sol: [blok], sag: [blok]} (iç bloklar: baslik/metin/gorsel/dugme; en çok 4)

Güvenlik
--------
* Kullanıcı metni HER ZAMAN önce kaçışlanıyor (`html.escape`), işaretleme
  (kalın, bağlantı) kaçışlı metnin üzerinde çalışıyor: `<script>` metin olarak çıkar.
* Bağlantılar yalnız http(s), mailto: ve tel:. `javascript:`, `data:` vb. 400.
  Bağlantı adresleri şablona doğrudan yazılmıyor; `<!--MK:L<i>-->` işaretiyle
  bırakılıp gönderimde (takip açıksa imzalı yönlendirme adresiyle) dolduruluyor.
  Kullanıcı metnindeki `<` kaçışlandığı için bu işaretler kullanıcıdan gelemez.
* Kişiselleştirme yer tutucuları (`{{ad}}`, `{{firma}}`, `{{eposta}}`,
  `{{ad|Değerli okurumuz}}`) yalnız metinde; değerler HTML'de kaçışlanıyor.
  Konuda satır sonu temizleniyor (başlık enjeksiyonu yok). Adreslerde yer
  tutucu yok (adres işaretle değişiyor).

İşaretler (gönderimde alıcıya göre doldurulur)
---------------------------------------------
`<!--MK:L<i>-->` bağlantı i · `<!--MK:RET-->` abonelikten çıkış · `<!--MK:TERCIH-->`
tercih sayfası · `<!--MK:NEDEN-->` "bu e-postayı neden aldınız" satırı ·
`<!--MK:PIKSEL-->` açılma pikseli (takip kapalıysa boş).
"""

import html as _html
import json
import re
from typing import Any, Callable, Dict, List, Optional, Tuple
from urllib.parse import urlparse

BLOK_TURLERI = ("logo", "baslik", "metin", "gorsel", "dugme", "ayirici", "bosluk", "iki_sutun")
SUTUN_BLOKLARI = ("baslik", "metin", "gorsel", "dugme")
EN_COK_BLOK = 60
EN_COK_SUTUN_BLOK = 4
METIN_SINIRI = 5000
BASLIK_SINIRI = 300
URL_SINIRI = 1000
HIZALAR = ("sol", "orta", "sag")
YER_TUTUCULAR = ("ad", "firma", "eposta")
VARSAYILAN_RENK = "#7c3aed"

_RENK = re.compile(r"^#[0-9a-fA-F]{6}$")
_YER_TUTUCU = re.compile(r"\{\{\s*(ad|firma|eposta)\s*(?:\|([^{}]{0,80}))?\}\}")
_BAGLANTI = re.compile(r"\[([^\]\n]{1,200})\]\(([^)\s]{1,1000})\)")
_KALIN = re.compile(r"\*\*(.+?)\*\*")
_ISARET = re.compile(r"<!--MK:([A-Z]+)(\d*)-->")

YAZI_TIPI = "-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif"


class IcerikHatasi(Exception):
    def __init__(self, kod: str, alan: Optional[str] = None, indeks: Optional[int] = None):
        super().__init__(kod)
        self.kod = kod
        self.alan = alan
        self.indeks = indeks

    def detay(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {"kod": self.kod}
        if self.alan:
            d["alan"] = self.alan
        if self.indeks is not None:
            d["indeks"] = self.indeks
        return d


# ---------------------------------------------------------------------------
# Doğrulama
# ---------------------------------------------------------------------------
def renk_duzelt(ham: Any, varsayilan: str = VARSAYILAN_RENK) -> str:
    s = str(ham or "").strip()
    if not s:
        return varsayilan
    if not _RENK.match(s):
        raise IcerikHatasi("renk_gecersiz", "renk")
    return s.lower()


def adres_dogrula(ham: Any, alan: str, *, gorsel: bool = False, izinli_onek: Optional[str] = None) -> str:
    """Bağlantı/görsel adresi: http(s) (+ bağlantıda mailto:/tel:). Geçersizse IcerikHatasi."""
    s = str(ham or "").strip()
    if not s or len(s) > URL_SINIRI or any(c.isspace() for c in s) or "{{" in s or '"' in s or "<" in s:
        raise IcerikHatasi("adres_gecersiz", alan)
    kucuk = s.lower()
    if gorsel:
        # E-posta istemcileri http görseli engelleyebilir: https ya da sitenin kendi adresi.
        if kucuk.startswith("https://") or (izinli_onek and s.startswith(izinli_onek + "/")):
            p = urlparse(s)
            if p.hostname:
                return s
        raise IcerikHatasi("adres_gecersiz", alan)
    if kucuk.startswith(("mailto:", "tel:")):
        if len(s) > 7:
            return s
        raise IcerikHatasi("adres_gecersiz", alan)
    p = urlparse(s)
    if p.scheme not in ("http", "https") or not p.hostname:
        raise IcerikHatasi("adres_gecersiz", alan)
    return s


def _metin(ham: Any, alan: str, sinir: int, zorunlu: bool = False, tek_satir: bool = False) -> str:
    if ham is not None and not isinstance(ham, (str, int, float)):
        raise IcerikHatasi("metin_gecersiz", alan)
    s = str(ham if ham is not None else "").replace("\r\n", "\n").replace("\r", "\n")
    if tek_satir:
        s = " ".join(s.split())
    else:
        s = s.strip()
    if len(s) > sinir:
        raise IcerikHatasi("metin_uzun", alan)
    if zorunlu and not s:
        raise IcerikHatasi("metin_gerekli", alan)
    return s


def _hiza(ham: Any) -> str:
    return ham if ham in HIZALAR else "sol"


def _tek_blok(b: Any, i: int, izinli: Tuple[str, ...], izinli_onek: Optional[str]) -> Dict[str, Any]:
    if not isinstance(b, dict):
        raise IcerikHatasi("blok_gecersiz", indeks=i)
    tur = b.get("tur")
    if tur not in izinli:
        raise IcerikHatasi("blok_turu", "tur", i)
    try:
        if tur == "logo":
            return {"tur": "logo", "hiza": _hiza(b.get("hiza") or "orta")}
        if tur == "baslik":
            seviye = 2 if b.get("seviye") == 2 else 1
            return {"tur": "baslik", "metin": _metin(b.get("metin"), "metin", BASLIK_SINIRI, True, True),
                    "seviye": seviye, "hiza": _hiza(b.get("hiza"))}
        if tur == "metin":
            return {"tur": "metin", "metin": _metin(b.get("metin"), "metin", METIN_SINIRI, True), "hiza": _hiza(b.get("hiza"))}
        if tur == "gorsel":
            g = b.get("genislik", 100)
            if isinstance(g, bool) or not isinstance(g, (int, float)):
                g = 100
            d = {"tur": "gorsel", "url": adres_dogrula(b.get("url"), "url", gorsel=True, izinli_onek=izinli_onek),
                 "alt": _metin(b.get("alt"), "alt", 200, tek_satir=True), "genislik": max(10, min(100, int(g))),
                 "hiza": _hiza(b.get("hiza") or "orta")}
            if b.get("baglanti"):
                d["baglanti"] = adres_dogrula(b.get("baglanti"), "baglanti")
            return d
        if tur == "dugme":
            return {"tur": "dugme", "metin": _metin(b.get("metin"), "metin", 80, True, True),
                    "url": adres_dogrula(b.get("url"), "url"), "hiza": _hiza(b.get("hiza") or "orta")}
        if tur == "ayirici":
            return {"tur": "ayirici"}
        if tur == "bosluk":
            y = b.get("yukseklik", 24)
            if isinstance(y, bool) or not isinstance(y, (int, float)):
                y = 24
            return {"tur": "bosluk", "yukseklik": max(8, min(64, int(y)))}
        # iki_sutun
        sutunlar: Dict[str, Any] = {"tur": "iki_sutun"}
        for taraf in ("sol", "sag"):
            ic = b.get(taraf) or []
            if not isinstance(ic, list) or len(ic) > EN_COK_SUTUN_BLOK:
                raise IcerikHatasi("sutun_gecersiz", taraf, i)
            sutunlar[taraf] = [_tek_blok(x, i, SUTUN_BLOKLARI, izinli_onek) for x in ic]
        return sutunlar
    except IcerikHatasi as h:
        if h.indeks is None:
            h.indeks = i
        raise


def bloklari_dogrula(ham: Any, izinli_onek: Optional[str] = None) -> List[Dict[str, Any]]:
    """Panel gövdesi → temiz blok listesi. `izinli_onek`: sitenin kendi adresi (görseller)."""
    if ham in (None, ""):
        return []
    if isinstance(ham, str):
        try:
            ham = json.loads(ham)
        except ValueError:
            raise IcerikHatasi("blok_gecersiz")
    if not isinstance(ham, list):
        raise IcerikHatasi("blok_gecersiz")
    if len(ham) > EN_COK_BLOK:
        raise IcerikHatasi("blok_sayisi")
    return [_tek_blok(b, i, BLOK_TURLERI, izinli_onek) for i, b in enumerate(ham)]


def konu_duzelt(ham: Any, alan: str = "konu", zorunlu: bool = True) -> str:
    """Konu: tek satır (CR/LF yok — başlık enjeksiyonu), ≤ 200."""
    s = " ".join(str(ham or "").replace("\r", " ").replace("\n", " ").split())
    if len(s) > 200:
        raise IcerikHatasi("metin_uzun", alan)
    if zorunlu and not s:
        raise IcerikHatasi("metin_gerekli", alan)
    return s


# ---------------------------------------------------------------------------
# Kişiselleştirme
# ---------------------------------------------------------------------------
def kisisellestir(sablon: str, degerler: Dict[str, Any], html: bool) -> str:
    """`{{ad}}` / `{{ad|varsayılan}}` → değer (HTML'de kaçışlı). Bilinmeyen yer tutucu olduğu gibi kalır."""

    def degis(m: "re.Match[str]") -> str:
        deger = str(degerler.get(m.group(1)) or "").strip()
        if not deger:
            # Varsayılan, metnin kendisiyle birlikte zaten kaçışlandı (HTML) ya da düz (metin).
            return (m.group(2) or "").strip()
        return _html.escape(deger, quote=True) if html else deger

    return _YER_TUTUCU.sub(degis, sablon)


def konu_kisisellestir(konu: str, degerler: Dict[str, Any]) -> str:
    return " ".join(kisisellestir(konu, degerler, html=False).replace("\r", " ").replace("\n", " ").split())


# ---------------------------------------------------------------------------
# HTML
# ---------------------------------------------------------------------------
_HIZA_CSS = {"sol": "left", "orta": "center", "sag": "right"}


class _Baglam:
    def __init__(self, renk: str, rtl: bool, logo_url: Optional[str], gonderen_adi: str):
        self.renk = renk
        self.rtl = rtl
        self.logo_url = logo_url
        self.gonderen_adi = gonderen_adi
        self.baglantilar: List[str] = []

    def baglanti(self, url: str) -> str:
        self.baglantilar.append(url)
        return f"<!--MK:L{len(self.baglantilar) - 1}-->"

    def hiza(self, h: str) -> str:
        css = _HIZA_CSS.get(h, "left")
        if self.rtl and css != "center":
            return "right" if css == "left" else "left"
        return css


def _satir_ici(metin: str, bg: _Baglam) -> str:
    """Kaçışlı metin üzerinde kalın + bağlantı + satır sonu."""
    kacisli = _html.escape(metin, quote=True)

    def bag(m: "re.Match[str]") -> str:
        ham_url = _html.unescape(m.group(2))
        try:
            url = adres_dogrula(ham_url, "metin")
        except IcerikHatasi:
            return m.group(0)
        return f'<a href="{bg.baglanti(url)}" style="color:{bg.renk};text-decoration:underline;">{m.group(1)}</a>'

    kacisli = _BAGLANTI.sub(bag, kacisli)
    kacisli = _KALIN.sub(r"<strong>\1</strong>", kacisli)
    return kacisli.replace("\n", "<br>")


def _p_stil(hiza: str, boyut: int = 16) -> str:
    return f"margin:0 0 14px 0;font-family:{YAZI_TIPI};font-size:{boyut}px;line-height:1.6;color:#1f2937;text-align:{hiza};"


def _blok_html(b: Dict[str, Any], bg: _Baglam, sutun: bool = False) -> str:
    tur = b["tur"]
    if tur == "logo":
        hiza = bg.hiza(b.get("hiza", "orta"))
        if bg.logo_url:
            return (f'<div style="text-align:{hiza};"><img src="{_html.escape(bg.logo_url, quote=True)}" alt="{_html.escape(bg.gonderen_adi, quote=True)}" '
                    f'width="160" style="display:inline-block;max-width:160px;height:auto;border:0;"></div>')
        return (f'<div style="text-align:{hiza};font-family:{YAZI_TIPI};font-size:20px;font-weight:700;color:{bg.renk};">'
                f"{_html.escape(bg.gonderen_adi)}</div>")
    if tur == "baslik":
        boyut = 26 if b["seviye"] == 1 else 20
        etiket = "h1" if b["seviye"] == 1 else "h2"
        return (f'<{etiket} style="margin:0 0 12px 0;font-family:{YAZI_TIPI};font-size:{boyut}px;line-height:1.3;'
                f'color:#111827;text-align:{bg.hiza(b["hiza"])};">{_html.escape(b["metin"])}</{etiket}>')
    if tur == "metin":
        paragraflar = [p for p in re.split(r"\n\s*\n", b["metin"]) if p.strip()]
        return "".join(f'<p style="{_p_stil(bg.hiza(b["hiza"]))}">{_satir_ici(p.strip(), bg)}</p>' for p in paragraflar)
    if tur == "gorsel":
        genislik = 100 if sutun else b["genislik"]
        piksel = int(536 * genislik / 100) if not sutun else 240
        img = (f'<img src="{_html.escape(b["url"], quote=True)}" alt="{_html.escape(b.get("alt") or "", quote=True)}" width="{piksel}" '
               f'style="display:block;width:{genislik}%;max-width:{piksel}px;height:auto;border:0;margin:0 auto;">')
        if b.get("baglanti"):
            img = f'<a href="{bg.baglanti(b["baglanti"])}" style="text-decoration:none;">{img}</a>'
        return f'<div style="text-align:{bg.hiza(b.get("hiza", "orta"))};margin:0 0 14px 0;">{img}</div>'
    if tur == "dugme":
        hiza = bg.hiza(b["hiza"])
        return (f'<table role="presentation" cellpadding="0" cellspacing="0" border="0" align="{hiza}" style="margin:6px 0 16px 0;">'
                f'<tr><td style="border-radius:8px;background:{bg.renk};" bgcolor="{bg.renk}">'
                f'<a href="{bg.baglanti(b["url"])}" style="display:inline-block;padding:12px 22px;font-family:{YAZI_TIPI};'
                f'font-size:16px;font-weight:700;color:#ffffff;text-decoration:none;border-radius:8px;">{_html.escape(b["metin"])}</a>'
                f"</td></tr></table>")
    if tur == "ayirici":
        return '<div style="border-top:1px solid #e5e7eb;margin:8px 0 18px 0;line-height:1px;font-size:1px;">&nbsp;</div>'
    if tur == "bosluk":
        y = int(b["yukseklik"])
        return f'<div style="height:{y}px;line-height:{y}px;font-size:1px;">&nbsp;</div>'
    # iki_sutun: satır içi blok iki kutu — dar ekranda alt alta (medya sorgusu gerekmez).
    kutular = []
    for taraf in ("sol", "sag"):
        ic = "".join(_blok_html(x, bg, sutun=True) for x in b.get(taraf) or [])
        kutular.append(f'<div class="mk-sutun" style="display:inline-block;width:100%;max-width:262px;vertical-align:top;'
                       f'text-align:{bg.hiza("sol")};font-size:16px;margin:0 3px;">{ic}</div>')
    return f'<div style="font-size:0;text-align:center;">{"".join(kutular)}</div>'


def html_uret(
    bloklar: List[Dict[str, Any]],
    *,
    konu: str,
    onizleme: str = "",
    renk: str = VARSAYILAN_RENK,
    logo_url: Optional[str] = None,
    gonderen_adi: str = "",
    dil: str = "tr",
    alt_bilgi: Optional[Dict[str, str]] = None,
) -> Tuple[str, List[str]]:
    """(işaretli HTML, bağlantı listesi). Alt bilgi metinleri `alt_bilgi` sözlüğünden (dile göre)."""
    rtl = dil == "ar"
    bg = _Baglam(renk_duzelt(renk), rtl, logo_url, gonderen_adi or "")
    govde = "".join(
        f'<tr><td class="mk-k" style="padding:6px 32px;">{_blok_html(b, bg)}</td></tr>' for b in bloklar
    )
    ab = alt_bilgi or {}
    kimlik = _html.escape(ab.get("kimlik") or "")
    alt = (
        f'<p style="margin:0 0 8px 0;"><!--MK:NEDEN--></p>'
        + (f'<p style="margin:0 0 8px 0;">{kimlik}</p>' if kimlik else "")
        + f'<p style="margin:0;"><a href="<!--MK:RET-->" style="color:#4b5563;text-decoration:underline;">{_html.escape(ab.get("ret") or "")}</a>'
        + f' &nbsp;·&nbsp; <a href="<!--MK:TERCIH-->" style="color:#4b5563;text-decoration:underline;">{_html.escape(ab.get("tercih") or "")}</a></p>'
    )
    gizli = _html.escape(onizleme or "")
    belge = (
        f'<!doctype html><html lang="{_html.escape(dil)}" dir="{"rtl" if rtl else "ltr"}"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1"><meta name="x-apple-disable-message-reformatting">'
        f"<title>{_html.escape(konu)}</title>"
        "<style>@media (max-width:620px){.mk-k{padding-left:16px!important;padding-right:16px!important}"
        ".mk-sutun{max-width:100%!important;margin:0!important}}</style></head>"
        '<body style="margin:0;padding:0;background:#f3f4f6;">'
        f'<div style="display:none;max-height:0;overflow:hidden;opacity:0;color:transparent;">{gizli}'
        + "&#847;&zwnj;&nbsp;" * 30 + "</div>"
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="background:#f3f4f6;">'
        '<tr><td align="center" style="padding:24px 10px;">'
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" '
        'style="max-width:600px;background:#ffffff;border-radius:12px;">'
        f'<tr><td style="height:20px;line-height:20px;font-size:1px;">&nbsp;</td></tr>{govde}'
        '<tr><td style="height:20px;line-height:20px;font-size:1px;">&nbsp;</td></tr></table>'
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="max-width:600px;">'
        f'<tr><td class="mk-k" style="padding:18px 32px;font-family:{YAZI_TIPI};font-size:12px;line-height:1.6;'
        f'color:#6b7280;text-align:center;">{alt}</td></tr></table>'
        "</td></tr></table><!--MK:PIKSEL--></body></html>"
    )
    return belge, bg.baglantilar


# ---------------------------------------------------------------------------
# Düz metin
# ---------------------------------------------------------------------------
def _satir_ici_metin(metin: str, sayac: List[str]) -> str:
    def bag(m: "re.Match[str]") -> str:
        try:
            url = adres_dogrula(m.group(2), "metin")
        except IcerikHatasi:
            return m.group(0)
        sayac.append(url)
        return f"{m.group(1)} (<!--MK:L{len(sayac) - 1}-->)"

    s = _BAGLANTI.sub(bag, metin)
    return _KALIN.sub(r"\1", s)


def _blok_metin(b: Dict[str, Any], sayac: List[str], gonderen_adi: str) -> str:
    tur = b["tur"]
    if tur == "logo":
        return gonderen_adi
    if tur == "baslik":
        alt = ("=" if b["seviye"] == 1 else "-") * min(60, max(3, len(b["metin"])))
        return f"{b['metin']}\n{alt}"
    if tur == "metin":
        return _satir_ici_metin(b["metin"], sayac)
    if tur == "gorsel":
        satir = f"[{b['alt']}]" if b.get("alt") else ""
        if b.get("baglanti"):
            sayac.append(b["baglanti"])
            satir = (satir + " " if satir else "") + f"<!--MK:L{len(sayac) - 1}-->"
        return satir
    if tur == "dugme":
        sayac.append(b["url"])
        return f"{b['metin']}: <!--MK:L{len(sayac) - 1}-->"
    if tur == "ayirici":
        return "-" * 40
    if tur == "bosluk":
        return ""
    parcalar = []
    for taraf in ("sol", "sag"):
        for x in b.get(taraf) or []:
            parcalar.append(_blok_metin(x, sayac, gonderen_adi))
    return "\n\n".join(p for p in parcalar if p)


def metin_uret(bloklar: List[Dict[str, Any]], *, gonderen_adi: str = "", alt_bilgi: Optional[Dict[str, str]] = None) -> str:
    """İşaretli düz metin sürümü. Bağlantı sırası HTML ile aynı (aynı bağlantı listesi)."""
    sayac: List[str] = []
    parcalar = [_blok_metin(b, sayac, gonderen_adi) for b in bloklar]
    ab = alt_bilgi or {}
    alt = ["--", "<!--MK:NEDEN-->"]
    if ab.get("kimlik"):
        alt.append(ab["kimlik"])
    alt.append(f"{ab.get('ret') or ''}: <!--MK:RET-->")
    alt.append(f"{ab.get('tercih') or ''}: <!--MK:TERCIH-->")
    return "\n\n".join(p for p in parcalar if p.strip()) + "\n\n" + "\n".join(alt) + "\n"


# ---------------------------------------------------------------------------
# İşaretleri doldurma (alıcıya göre)
# ---------------------------------------------------------------------------
def isaretleri_doldur(
    sablon: str,
    *,
    html: bool,
    baglanti: Callable[[int], str],
    ret: str,
    tercih: str,
    neden: str,
    piksel: str = "",
) -> str:
    """İşaretli şablonu alıcının adresleriyle doldurur (HTML'de öznitelik kaçışlı)."""

    def kac(s: str) -> str:
        return _html.escape(s, quote=True) if html else s

    def degis(m: "re.Match[str]") -> str:
        ad, sayi = m.group(1), m.group(2)
        if ad == "L" and sayi:
            return kac(baglanti(int(sayi)))
        if ad == "RET":
            return kac(ret)
        if ad == "TERCIH":
            return kac(tercih)
        if ad == "NEDEN":
            return kac(neden)
        if ad == "PIKSEL":
            return piksel if html else ""
        return ""

    return _ISARET.sub(degis, sablon)


def piksel_html(adres: str) -> str:
    return (f'<img src="{_html.escape(adres, quote=True)}" width="1" height="1" alt="" '
            'style="display:block;width:1px;height:1px;border:0;opacity:0;">')


__all__ = [
    "BLOK_TURLERI", "IcerikHatasi", "bloklari_dogrula", "konu_duzelt", "renk_duzelt", "adres_dogrula",
    "kisisellestir", "konu_kisisellestir", "html_uret", "metin_uret", "isaretleri_doldur", "piksel_html",
]
