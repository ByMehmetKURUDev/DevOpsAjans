"""Markdown → güvenli HTML (bilgi bankası makaleleri).

Neden kendi yazdığımız?
-----------------------
`bleach`/`nh3`/`markdown` gibi paketler `requirements.txt`'de yok; Render'a
yeni bağımlılık eklemek yerine iki küçük adım:

1. `markdown_html`: sade bir markdown alt kümesi (başlık, paragraf, liste,
   kalın/eğik, satır içi kod, kod bloğu, alıntı, bağlantı, yatay çizgi).
   Satır içi ham HTML de geçiyor (makale yazarı `<kbd>` yazabilsin) — ama
   GÜVENLİK SINIRI burası değil:
2. `temizle`: stdlib `HTMLParser` ile İZİNLİ ETİKET LİSTESİ. Listede
   olmayan etiket atılıyor (içindeki metin kalıyor); `script`, `style`,
   `iframe`, `object`, `svg`, `math`, `template`, `noscript` içeriğiyle
   birlikte atılıyor; `on*` olay öznitelikleri ve izinli olmayan
   öznitelikler düşüyor; `href`/`src` yalnız http(s), mailto, göreli yol ve
   `#`. `javascript:`/`data:`/`vbscript:` — araya boşluk, denetim karakteri
   ya da HTML varlığı sıkıştırılmış olsa bile — reddediliyor. Metin ve
   öznitelik değerleri yeniden kaçışlanıyor.

Çıktı her zaman `temizle`den geçiyor; markdown dönüştürücüsündeki bir
hata XSS'e dönüşmüyor.
"""

import html
import re
from html.parser import HTMLParser
from typing import Dict, List, Optional, Tuple

IZINLI_ETIKETLER = frozenset({
    "p", "br", "hr", "h2", "h3", "h4", "h5", "ul", "ol", "li", "strong", "b", "em", "i", "u", "s",
    "code", "pre", "blockquote", "a", "img", "kbd", "sub", "sup", "table", "thead", "tbody", "tr",
    "th", "td", "span",
})
BOS_ETIKETLER = frozenset({"br", "hr", "img"})
ICERIGIYLE_ATILAN = frozenset({
    "script", "style", "iframe", "object", "embed", "svg", "math", "template", "noscript",
    "textarea", "select", "form", "frame", "frameset", "applet", "head", "title", "xmp", "plaintext",
})
IZINLI_OZNITELIKLER: Dict[str, frozenset] = {
    "a": frozenset({"href", "title"}),
    "img": frozenset({"src", "alt", "title"}),
    "th": frozenset({"colspan", "rowspan"}),
    "td": frozenset({"colspan", "rowspan"}),
}
URL_OZNITELIKLERI = frozenset({"href", "src"})
_GUVENLI_SEMA = re.compile(r"^(https?:|mailto:)", re.I)
_SEMA = re.compile(r"^[a-z][a-z0-9+.\-]*:", re.I)


def url_guvenli_mi(deger: str) -> bool:
    # Tarayıcının yok saydığı karakterleri at: "java\tscript:", "\x01javascript:".
    ham = html.unescape(deger or "")
    sade = re.sub(r"[\x00-\x20\x7f-\x9f]", "", ham)
    if not sade:
        return False
    if _GUVENLI_SEMA.match(sade):
        return True
    if _SEMA.match(sade):
        return False  # javascript:, data:, vbscript:, file:...
    # Göreli yol, çapa, sorgu. "//evil" protokolsüz dış adres: yine http(s) sayılır, izinli.
    return True


#: Faz 5B — belge kipinde ek öznitelikler: yapılacak maddesinin satır numarası ve durumu
#: (ön yüz tıklamayla işaretlemek için). Değerleri ayrıca sınırlanıyor (`_belge_ozniteligi`).
BELGE_EK_OZNITELIKLER: Dict[str, frozenset] = {"li": frozenset({"data-satir", "data-tamam"})}


def _belge_ozniteligi(ad: str, deger: str) -> bool:
    if ad == "data-satir":
        return bool(re.fullmatch(r"\d{1,6}", deger))
    if ad == "data-tamam":
        return deger in ("0", "1")
    return False


class _Temizleyici(HTMLParser):
    def __init__(self, belge: bool = False) -> None:
        super().__init__(convert_charrefs=True)
        self.cikti: List[str] = []
        self.atlama = 0  # içeriğiyle atılan etiketin derinliği
        self.acik: List[str] = []
        self.belge = belge

    def handle_starttag(self, tag: str, attrs: List[Tuple[str, Optional[str]]]) -> None:
        tag = tag.lower()
        if tag in ICERIGIYLE_ATILAN:
            if tag not in BOS_ETIKETLER:
                self.atlama += 1
            return
        if self.atlama or tag not in IZINLI_ETIKETLER:
            return
        izinli = IZINLI_OZNITELIKLER.get(tag, frozenset())
        ek = BELGE_EK_OZNITELIKLER.get(tag, frozenset()) if self.belge else frozenset()
        parcalar = [tag]
        for ad, deger in attrs:
            ad = (ad or "").lower()
            if ad in ek:
                if _belge_ozniteligi(ad, deger or ""):
                    parcalar.append(f'{ad}="{html.escape(deger or "", quote=True)}"')
                continue
            if ad not in izinli or ad.startswith("on"):
                continue
            deger = deger or ""
            if ad in URL_OZNITELIKLERI and not url_guvenli_mi(deger):
                continue
            if tag == "img" and ad == "src" and not re.match(r"^https?://", deger.strip(), re.I):
                continue  # görsel yalnız mutlak http(s)
            parcalar.append(f'{ad}="{html.escape(deger, quote=True)}"')
        if tag == "a":
            parcalar.append('rel="noopener noreferrer nofollow"')
            parcalar.append('target="_blank"')
        if tag == "img" and not any(p.startswith("src=") for p in parcalar[1:]):
            return  # adresi reddedilen görsel hiç çizilmesin
        self.cikti.append("<" + " ".join(parcalar) + (" />" if tag in BOS_ETIKETLER else ">"))
        if tag not in BOS_ETIKETLER:
            self.acik.append(tag)

    def handle_startendtag(self, tag: str, attrs: List[Tuple[str, Optional[str]]]) -> None:
        tag = tag.lower()
        if tag in ICERIGIYLE_ATILAN:
            return
        if tag in BOS_ETIKETLER:
            self.handle_starttag(tag, attrs)
        else:
            self.handle_starttag(tag, attrs)
            self.handle_endtag(tag)

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in ICERIGIYLE_ATILAN:
            if self.atlama:
                self.atlama -= 1
            return
        if self.atlama or tag not in IZINLI_ETIKETLER or tag in BOS_ETIKETLER:
            return
        if tag in self.acik:
            # Arada kapanmamış etiketleri de kapat: çıktı her zaman düzgün iç içe.
            while self.acik:
                son = self.acik.pop()
                self.cikti.append(f"</{son}>")
                if son == tag:
                    break

    def handle_data(self, data: str) -> None:
        if self.atlama:
            return
        self.cikti.append(html.escape(data, quote=False))

    def handle_comment(self, data: str) -> None:
        return  # yorumlar (koşullu IE yorumları dahil) atılıyor

    def handle_decl(self, decl: str) -> None:
        return

    def handle_pi(self, data: str) -> None:
        return

    def unknown_decl(self, data: str) -> None:
        return

    def sonuc(self) -> str:
        while self.acik:
            self.cikti.append(f"</{self.acik.pop()}>")
        return "".join(self.cikti)


def temizle(ham_html: str, belge: bool = False) -> str:
    t = _Temizleyici(belge=belge)
    t.feed(ham_html or "")
    t.close()
    return t.sonuc()


# ---------------------------------------------------------------------------
# Markdown alt kümesi
# ---------------------------------------------------------------------------
# Adreste bir düzey parantez olabilir: [x](https://tr.wikipedia.org/wiki/A_(B)).
_ADRES = r"((?:[^()\s]|\([^()\s]*\))+)"
_BAGLANTI = re.compile(r"\[([^\]\n]+)\]\(" + _ADRES + r"(?:\s+\"([^\"]*)\")?\)")
_GORSEL = re.compile(r"!\[([^\]\n]*)\]\(" + _ADRES + r"\)")
_KALIN = re.compile(r"\*\*(.+?)\*\*|__(.+?)__")
_EGIK = re.compile(r"(?<![\*\w])\*(?!\s)(.+?)(?<!\s)\*(?!\*)|(?<![_\w])_(?!\s)(.+?)(?<!\s)_(?![_\w])")
_KOD = re.compile(r"`([^`\n]+)`")


def _satir_ici(metin: str) -> str:
    kodlar: List[str] = []

    def kod_sakla(m: "re.Match[str]") -> str:
        kodlar.append(f"<code>{html.escape(m.group(1), quote=False)}</code>")
        return f"\x00{len(kodlar) - 1}\x00"

    metin = _KOD.sub(kod_sakla, metin)
    metin = _GORSEL.sub(lambda m: f'<img src="{html.escape(m.group(2), quote=True)}" alt="{html.escape(m.group(1), quote=True)}" />', metin)
    metin = _BAGLANTI.sub(
        lambda m: f'<a href="{html.escape(m.group(2), quote=True)}"'
        + (f' title="{html.escape(m.group(3), quote=True)}"' if m.group(3) else "")
        + f">{m.group(1)}</a>",
        metin,
    )
    metin = _KALIN.sub(lambda m: f"<strong>{m.group(1) or m.group(2)}</strong>", metin)
    metin = _EGIK.sub(lambda m: f"<em>{m.group(1) or m.group(2)}</em>", metin)
    return re.sub(r"\x00(\d+)\x00", lambda m: kodlar[int(m.group(1))], metin)


def markdown_html(md: str) -> str:
    """Markdown alt kümesini HTML'e çevirir ve TEMİZLER."""
    satirlar = (md or "").replace("\r\n", "\n").replace("\r", "\n").split("\n")
    cikti: List[str] = []
    paragraf: List[str] = []
    liste: Optional[str] = None
    alinti: List[str] = []
    i = 0

    def paragrafi_bitir() -> None:
        nonlocal paragraf
        if paragraf:
            cikti.append("<p>" + "<br />".join(_satir_ici(s) for s in paragraf) + "</p>")
            paragraf = []

    def listeyi_bitir() -> None:
        nonlocal liste
        if liste:
            cikti.append(f"</{liste}>")
            liste = None

    def alintiyi_bitir() -> None:
        nonlocal alinti
        if alinti:
            cikti.append("<blockquote>" + markdown_html("\n".join(alinti)) + "</blockquote>")
            alinti = []

    while i < len(satirlar):
        satir = satirlar[i]
        yalin = satir.strip()
        if yalin.startswith("```"):
            paragrafi_bitir(); listeyi_bitir(); alintiyi_bitir()
            kod: List[str] = []
            i += 1
            while i < len(satirlar) and not satirlar[i].strip().startswith("```"):
                kod.append(satirlar[i])
                i += 1
            cikti.append("<pre><code>" + html.escape("\n".join(kod), quote=False) + "</code></pre>")
            i += 1
            continue
        if yalin.startswith(">"):
            paragrafi_bitir(); listeyi_bitir()
            alinti.append(yalin[1:].lstrip())
            i += 1
            continue
        alintiyi_bitir()
        if not yalin:
            paragrafi_bitir(); listeyi_bitir()
            i += 1
            continue
        baslik = re.match(r"^(#{1,4})\s+(.+?)\s*#*$", yalin)
        if baslik:
            paragrafi_bitir(); listeyi_bitir()
            # h1 sayfanın kendi başlığı; makale içi başlıklar h2'den başlıyor.
            seviye = min(len(baslik.group(1)) + 1, 5)
            cikti.append(f"<h{seviye}>{_satir_ici(baslik.group(2))}</h{seviye}>")
            i += 1
            continue
        if re.match(r"^(-{3,}|\*{3,}|_{3,})$", yalin):
            paragrafi_bitir(); listeyi_bitir()
            cikti.append("<hr />")
            i += 1
            continue
        madde = re.match(r"^([-*+])\s+(.*)$", yalin)
        sirali = re.match(r"^\d+[.)]\s+(.*)$", yalin)
        if madde or sirali:
            paragrafi_bitir()
            tur = "ul" if madde else "ol"
            if liste != tur:
                listeyi_bitir()
                cikti.append(f"<{tur}>")
                liste = tur
            icerik = madde.group(2) if madde else sirali.group(1)  # type: ignore[union-attr]
            cikti.append(f"<li>{_satir_ici(icerik)}</li>")
            i += 1
            continue
        listeyi_bitir()
        paragraf.append(yalin)
        i += 1
    paragrafi_bitir(); listeyi_bitir(); alintiyi_bitir()
    return temizle("\n".join(cikti))


def duz_metin(md: str, sinir: int = 220) -> str:
    """Özet için: işaretleri ve etiketleri atılmış kısa metin."""
    metin = re.sub(r"<[^>]*>", " ", markdown_html(md))
    metin = html.unescape(re.sub(r"\s+", " ", metin)).strip()
    return metin if len(metin) <= sinir else metin[: sinir - 1].rstrip() + "…"


# ---------------------------------------------------------------------------
# Faz 5B — belge kipi (belgeler / wiki / notlar)
# ---------------------------------------------------------------------------
# Bilgi bankasından farkları:
# * Ham HTML HİÇ geçmiyor: metin önce kaçışlanıyor, yalnız Markdown işaretleri
#   etikete dönüşüyor (`<b>` yazan kullanıcı ekranda `<b>` görür). Çıktı yine
#   `temizle`den geçiyor — iki kat güvence.
# * Tablo (`| a | b |` + `|---|---|`), yapılacak maddesi (`- [ ] metin`,
#   `- [x] metin`; `<li data-satir=… data-tamam=…>` — satır numarası Markdown
#   gövdesindeki satır, ön yüz tıklamayla işaretlemek için kullanıyor) ve
#   ~~üstü çizili~~.
# * Kod bloğundaki metin dokunulmadan kaçışlanıyor (``` içinde yapılacak yok).
_DENETIM_KARAKTERI = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_USTU_CIZILI = re.compile(r"~~(?=\S)(.+?)(?<=\S)~~")
_YAPILACAK = re.compile(r"^[-*+]\s+\[( |x|X)\]\s+(.*)$")
_TABLO_AYRAC = re.compile(r"^\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)*\|?$")
YAPILACAK_ACIK = "☐"
YAPILACAK_TAMAM = "☑"


def _vurgu(kacisli: str) -> str:
    kacisli = _KALIN.sub(lambda m: f"<strong>{m.group(1) or m.group(2)}</strong>", kacisli)
    kacisli = _EGIK.sub(lambda m: f"<em>{m.group(1) or m.group(2)}</em>", kacisli)
    return _USTU_CIZILI.sub(lambda m: f"<s>{m.group(1)}</s>", kacisli)


def _satir_ici_belge(metin: str) -> str:
    """Satır içi Markdown → HTML; geri kalan her şey KAÇIŞLI metin."""
    metin = _DENETIM_KARAKTERI.sub("", metin or "")
    saklanan: List[str] = []

    def sakla(parca: str) -> str:
        saklanan.append(parca)
        return f"\x00{len(saklanan) - 1}\x00"

    metin = _KOD.sub(lambda m: sakla(f"<code>{html.escape(m.group(1), quote=False)}</code>"), metin)
    metin = _GORSEL.sub(
        lambda m: sakla(f'<img src="{html.escape(m.group(2), quote=True)}" alt="{html.escape(m.group(1), quote=True)}" />'),
        metin,
    )
    metin = _BAGLANTI.sub(
        lambda m: sakla(
            f'<a href="{html.escape(m.group(2), quote=True)}"'
            + (f' title="{html.escape(m.group(3), quote=True)}"' if m.group(3) else "")
            + f">{_vurgu(html.escape(m.group(1), quote=False))}</a>"
        ),
        metin,
    )
    metin = _vurgu(html.escape(metin, quote=False))
    return re.sub(r"\x00(\d+)\x00", lambda m: saklanan[int(m.group(1))], metin)


def _tablo_hucreleri(satir: str) -> List[str]:
    s = satir.strip()
    if s.startswith("|"):
        s = s[1:]
    if s.endswith("|"):
        s = s[:-1]
    return [h.strip() for h in s.split("|")]


def _belge_bloklari(satirlar: List[str], satir_no: bool) -> List[str]:
    cikti: List[str] = []
    paragraf: List[str] = []
    liste: Optional[str] = None
    alinti: List[str] = []
    i = 0
    n = len(satirlar)

    def paragrafi_bitir() -> None:
        nonlocal paragraf
        if paragraf:
            cikti.append("<p>" + "<br />".join(_satir_ici_belge(s) for s in paragraf) + "</p>")
            paragraf = []

    def listeyi_bitir() -> None:
        nonlocal liste
        if liste:
            cikti.append(f"</{liste}>")
            liste = None

    def alintiyi_bitir() -> None:
        nonlocal alinti
        if alinti:
            cikti.append("<blockquote>" + "".join(_belge_bloklari(alinti, False)) + "</blockquote>")
            alinti = []

    def liste_ac(tur: str) -> None:
        nonlocal liste
        if liste != tur:
            listeyi_bitir()
            cikti.append(f"<{tur}>")
            liste = tur

    while i < n:
        satir = satirlar[i]
        yalin = satir.strip()
        if yalin.startswith("```"):
            paragrafi_bitir(); listeyi_bitir(); alintiyi_bitir()
            kod: List[str] = []
            i += 1
            while i < n and not satirlar[i].strip().startswith("```"):
                kod.append(_DENETIM_KARAKTERI.sub("", satirlar[i]))
                i += 1
            cikti.append("<pre><code>" + html.escape("\n".join(kod), quote=False) + "</code></pre>")
            i += 1
            continue
        if yalin.startswith(">"):
            paragrafi_bitir(); listeyi_bitir()
            alinti.append(yalin[1:].lstrip())
            i += 1
            continue
        alintiyi_bitir()
        if not yalin:
            paragrafi_bitir(); listeyi_bitir()
            i += 1
            continue
        baslik = re.match(r"^(#{1,4})\s+(.+?)\s*#*$", yalin)
        if baslik:
            paragrafi_bitir(); listeyi_bitir()
            seviye = min(len(baslik.group(1)) + 1, 5)
            cikti.append(f"<h{seviye}>{_satir_ici_belge(baslik.group(2))}</h{seviye}>")
            i += 1
            continue
        if re.match(r"^(-{3,}|\*{3,}|_{3,})$", yalin):
            paragrafi_bitir(); listeyi_bitir()
            cikti.append("<hr />")
            i += 1
            continue
        if yalin.startswith("|") and i + 1 < n and _TABLO_AYRAC.match(satirlar[i + 1].strip()):
            paragrafi_bitir(); listeyi_bitir()
            basliklar = _tablo_hucreleri(yalin)
            parca = ["<table><thead><tr>"] + [f"<th>{_satir_ici_belge(h)}</th>" for h in basliklar] + ["</tr></thead><tbody>"]
            i += 2
            while i < n and satirlar[i].strip().startswith("|"):
                hucreler = _tablo_hucreleri(satirlar[i])
                hucreler = (hucreler + [""] * len(basliklar))[: max(len(basliklar), 1)]
                parca.append("<tr>" + "".join(f"<td>{_satir_ici_belge(h)}</td>" for h in hucreler) + "</tr>")
                i += 1
            parca.append("</tbody></table>")
            cikti.append("".join(parca))
            continue
        gorev = _YAPILACAK.match(yalin)
        if gorev:
            paragrafi_bitir()
            liste_ac("ul")
            tamam = gorev.group(1) in ("x", "X")
            ozn = f' data-satir="{i}" data-tamam="{1 if tamam else 0}"' if satir_no else ""
            isaret = YAPILACAK_TAMAM if tamam else YAPILACAK_ACIK
            icerik = _satir_ici_belge(gorev.group(2))
            if tamam:
                icerik = f"<s>{icerik}</s>"
            cikti.append(f"<li{ozn}>{isaret} {icerik}</li>")
            i += 1
            continue
        madde = re.match(r"^([-*+])\s+(.*)$", yalin)
        sirali = re.match(r"^\d+[.)]\s+(.*)$", yalin)
        if madde or sirali:
            paragrafi_bitir()
            liste_ac("ul" if madde else "ol")
            icerik = madde.group(2) if madde else sirali.group(1)  # type: ignore[union-attr]
            cikti.append(f"<li>{_satir_ici_belge(icerik)}</li>")
            i += 1
            continue
        listeyi_bitir()
        paragraf.append(yalin)
        i += 1
    paragrafi_bitir(); listeyi_bitir(); alintiyi_bitir()
    return cikti


def belge_html(md: str) -> str:
    """Belge Markdown'ı → güvenli HTML (ham HTML yok; tablo ve yapılacak maddesi var)."""
    satirlar = (md or "").replace("\r\n", "\n").replace("\r", "\n").split("\n")
    return temizle("\n".join(_belge_bloklari(satirlar, True)), belge=True)


def belge_duz_metin(md: str, sinir: int = 200) -> str:
    """Liste özeti için işaretsiz kısa metin."""
    metin = re.sub(r"<[^>]*>", " ", belge_html(md))
    metin = html.unescape(re.sub(r"\s+", " ", metin)).strip()
    return metin if len(metin) <= sinir else metin[: sinir - 1].rstrip() + "…"
