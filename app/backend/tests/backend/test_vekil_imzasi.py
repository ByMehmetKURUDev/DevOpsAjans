"""Faz 4G — İstemci IP başlığına "vekil imzası" (`utils/istemci_ip.py`).

Render adresine doğrudan gelen biri `X-MK-Istemci-IP` uydurup IP tabanlı hız
sınırlarını atlatamasın: başlığa yalnız `X-MK-Vekil-Anahtari` ortak gizliyle
(`VEKIL_ANAHTARI`) eşleşirse güveniliyor. Üç durum + geçiş günlükleri + gerçek
bir hız sınırının uydurma IP'lerle aşılamadığı, ayrıca Pages Function'larının
Node testi (`scripts/vekil-imzasi.test.mjs`).
"""

import json
import logging
import shutil
import subprocess
import time
from pathlib import Path

import pytest
from starlette.requests import Request as _Istek

from utils import istemci_ip as modul
from utils.istemci_ip import istemci_ip, vekil_dogrulandi_mi

ON_YUZ = Path(__file__).resolve().parents[3] / "frontend"
ANAHTAR = "k" * 48


def istek(basliklar, istemci=("10.0.0.9", 1234)):
    return _Istek({"type": "http", "headers": [(k.lower().encode(), v.encode()) for k, v in basliklar.items()], "client": istemci})


@pytest.fixture(autouse=True)
def _temiz(monkeypatch):
    monkeypatch.delenv("VEKIL_ANAHTARI", raising=False)
    modul._son_uyari.clear()
    yield
    modul._son_uyari.clear()


def test_anahtar_yokken_eski_davranis_basliga_guvenilir():
    """Geçiş: Render'da değişken yoksa başlık imzasız da kabul (site bozulmasın)."""
    assert vekil_dogrulandi_mi(istek({})) is None
    assert istemci_ip(istek({"x-mk-istemci-ip": "203.0.113.7", "cf-connecting-ip": "2a06:98c0:3600::103"})) == "203.0.113.7"
    # Eski sıra korunuyor: CF → X-Forwarded-For → soket.
    assert istemci_ip(istek({"x-forwarded-for": "198.51.100.4, 10.1.1.1"})) == "198.51.100.4"
    assert istemci_ip(istek({})) == "10.0.0.9"


def test_anahtar_eslesince_basliga_guvenilir(monkeypatch):
    monkeypatch.setenv("VEKIL_ANAHTARI", f"  {ANAHTAR}\n")
    b = {"x-mk-istemci-ip": "203.0.113.7", "x-mk-vekil-anahtari": ANAHTAR, "cf-connecting-ip": "2a06:98c0:3600::103"}
    assert vekil_dogrulandi_mi(istek(b)) is True
    assert istemci_ip(istek(b)) == "203.0.113.7"
    # Bozuk IP değeri yine yok sayılır.
    assert istemci_ip(istek({**b, "x-mk-istemci-ip": "abc"})) == "2a06:98c0:3600::103"


def test_anahtar_eslesmezse_baglantinin_kendi_ipsi(monkeypatch, caplog):
    monkeypatch.setenv("VEKIL_ANAHTARI", ANAHTAR)
    caplog.set_level(logging.WARNING, logger="utils.istemci_ip")
    for yanlis in ("yanlis", ANAHTAR[:-1], ANAHTAR + "x", ""):
        b = {"x-mk-istemci-ip": "203.0.113.7", "x-mk-vekil-anahtari": yanlis, "cf-connecting-ip": "198.51.100.20"}
        assert vekil_dogrulandi_mi(istek(b)) is False
        # Cloudflare'in yazdığı (uydurulamayan) CF-Connecting-IP kullanılıyor.
        assert istemci_ip(istek(b)) == "198.51.100.20"
    # Anahtar tanımlıyken uydurulabilen X-Forwarded-For HİÇ kullanılmıyor.
    b = {"x-mk-istemci-ip": "203.0.113.7", "x-forwarded-for": "203.0.113.8"}
    assert istemci_ip(istek(b)) == "10.0.0.9"
    assert istemci_ip(istek({"true-client-ip": "198.51.100.30", "x-forwarded-for": "1.2.3.4"})) == "198.51.100.30"
    # İki ayrı (seyrek) uyarı: yanlış anahtar / anahtar yok (Pages'te değişken eksik).
    mesajlar = [r.getMessage() for r in caplog.records]
    assert sum("eşleşmedi" in m for m in mesajlar) == 1
    assert sum("Vekil-Anahtari yok" in m and "kaba" in m for m in mesajlar) == 1


def test_uyari_seyrek_yazilir(monkeypatch, caplog):
    monkeypatch.setenv("VEKIL_ANAHTARI", ANAHTAR)
    caplog.set_level(logging.WARNING, logger="utils.istemci_ip")
    for _ in range(20):
        istemci_ip(istek({"x-mk-istemci-ip": "203.0.113.7"}))
    assert len(caplog.records) == 1
    monkeypatch.setattr(modul, "UYARI_ARALIGI_SN", 0)
    modul._son_uyari["eksik"] = time.monotonic() - 1
    istemci_ip(istek({"x-mk-istemci-ip": "203.0.113.7"}))
    assert len(caplog.records) == 2


def test_acilis_uyarisi(monkeypatch, caplog):
    caplog.set_level(logging.WARNING, logger="utils.istemci_ip")
    assert "VEKIL_ANAHTARI tanımlı değil" in modul.acilis_uyarisi()
    monkeypatch.setenv("VEKIL_ANAHTARI", "kisa")
    assert "çok kısa" in modul.acilis_uyarisi()
    monkeypatch.setenv("VEKIL_ANAHTARI", ANAHTAR)
    assert modul.acilis_uyarisi() is None


async def test_uydurma_ip_ile_hiz_siniri_asilamaz(istemci, yonetici_basligi, monkeypatch):
    """Gerçek uç: CRM formu IP başına 10 dakikada 5 gönderim. Anahtarsız istekte her
    seferinde başka bir X-MK-Istemci-IP uydurmak sınırı aşmaya yetmiyor."""
    from routers import crm as r
    from services.crm_form import jeton_uret

    r.hiz_sinirlarini_temizle()
    y = await istemci.post("/api/v1/crm/formlar", json={"ad": "Vekil testi"}, headers=yonetici_basligi)
    f = y.json()

    async def gonder(i, basliklar):
        govde = {"ad": "Kişi", "email": f"vekil{i}-{time.time_ns()}@ornek-firma.com", "jeton": jeton_uret(f["id"], an=time.time() - 5)}
        return await istemci.post(
            f"/api/v1/crm/form/{f['genel_anahtar']}", content=json.dumps(govde).encode(),
            headers={"content-type": "text/plain", **basliklar},
        )

    monkeypatch.setenv("VEKIL_ANAHTARI", ANAHTAR)
    durumlar = [
        (await gonder(i, {"x-mk-istemci-ip": f"203.0.113.{i + 1}", "cf-connecting-ip": "198.51.100.66"})).status_code
        for i in range(6)
    ]
    assert durumlar == [200] * 5 + [429], durumlar

    # Doğru anahtarla gelen (Pages Function) istekte her ziyaretçi ayrı sayılıyor.
    r.hiz_sinirlarini_temizle()
    durumlar = [
        (await gonder(10 + i, {"x-mk-istemci-ip": f"203.0.113.{50 + i}", "x-mk-vekil-anahtari": ANAHTAR,
                               "cf-connecting-ip": "198.51.100.66"})).status_code
        for i in range(7)
    ]
    assert durumlar == [200] * 7, durumlar
    r.hiz_sinirlarini_temizle()


@pytest.mark.skipif(shutil.which("node") is None, reason="node yok")
def test_pages_fonksiyonlari_node_testi():
    sonuc = subprocess.run(
        ["node", "--test", "scripts/vekil-imzasi.test.mjs"],
        cwd=ON_YUZ, capture_output=True, text=True, timeout=120,
    )
    assert sonuc.returncode == 0, sonuc.stdout[-3000:] + sonuc.stderr[-2000:]
    assert "# fail 0" in sonuc.stdout


def test_dort_fonksiyon_ortak_yardimciyi_kullanir():
    for yol in ("api/[[path]].js", "q/[kod].js", "kart/[slug].js", "menu/[slug].js"):
        metin = (ON_YUZ / "functions" / yol).read_text(encoding="utf-8")
        assert "from '../_ortak/vekil.js'" in metin and "vekilBasliklari(" in metin, yol
    # Yardımcı klasörde rota olacak bir dışa aktarım yok (Pages yalnız onRequest* dışa aktaranı rota yapar).
    for dosya in (ON_YUZ / "functions" / "_ortak").glob("*.js"):
        assert "export function onRequest" not in dosya.read_text(encoding="utf-8")
        assert "export async function onRequest" not in dosya.read_text(encoding="utf-8")


def test_render_blueprint_degiskeni_tanimli():
    yaml = (ON_YUZ.parents[1] / "render.yaml").read_text(encoding="utf-8")
    assert "- key: VEKIL_ANAHTARI\n        sync: false" in yaml
