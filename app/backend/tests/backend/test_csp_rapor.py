"""Faz 4G — CSP ihlal raporu ucu (`routers/csp_rapor.py`) ve CSP tek kaynak.

* `POST /api/v1/csp-rapor`: herkese açık, gövdesiz 204; iki rapor biçimi
  (report-uri / Reporting API); boyut sınırı (413), IP hız sınırı (429);
  aynı ihlal birleştiriliyor; tablo en çok 500 satır; jeton taşıyabilen yol
  kısaltılıyor, sorgu dizgesi atılıyor.
* `GET/DELETE /api/v1/csp-rapor/yonetim`: yalnız yönetici (anonim 401, müşteri 403).
* `scripts/csp-basliklari.test.mjs` (Node): `_headers` yer tutucusu, kod deneme
  alanının ayrılması, rapor moduna geri dönüş.
"""

import json
import shutil
import subprocess
from pathlib import Path

import pytest
from sqlalchemy import delete, func, select

UC = "/api/v1/csp-rapor"
YONETIM = "/api/v1/csp-rapor/yonetim"
ON_YUZ = Path(__file__).resolve().parents[3] / "frontend"


@pytest.fixture(autouse=True)
async def _temiz(db_oturumu):
    from models.csp_raporlari import CspRaporlari
    from routers import csp_rapor

    csp_rapor.hiz_sinirlarini_temizle()
    await db_oturumu.execute(delete(CspRaporlari))
    await db_oturumu.commit()
    yield
    csp_rapor.hiz_sinirlarini_temizle()


def _eski_bicim(**ek):
    rapor = {
        "document-uri": "https://mehmetkuru.dev/teklif/GIZLI-JETON-123?x=1#a",
        "violated-directive": "script-src-elem",
        "effective-directive": "script-src-elem",
        "blocked-uri": "https://kotu.example/betik.js?oturum=abc",
        "source-file": "https://mehmetkuru.dev/assets/index-abc.js?v=2",
        "line-number": 12,
        "column-number": 7,
        "disposition": "enforce",
        "script-sample": "",
        **ek,
    }
    return json.dumps({"csp-report": rapor}).encode()


def _yeni_bicim(n=1, **ek):
    return json.dumps([
        {
            "type": "csp-violation", "age": 10, "url": "https://mehmetkuru.dev/en/blog/yazi",
            "body": {
                "documentURL": "https://mehmetkuru.dev/en/blog/yazi?utm=1", "effectiveDirective": "connect-src",
                "blockedURL": f"https://www.google.de/ads/ga-audiences?v={i}", "disposition": "report",
                "sourceFile": "https://www.googletagmanager.com/gtag/js?id=G-1", "lineNumber": 3, "sample": "x" * 100, **ek,
            },
        }
        for i in range(n)
    ]).encode()


async def _gonder(istemci, govde, tur="application/csp-report", ip="198.51.100.9"):
    return await istemci.post(UC, content=govde, headers={"content-type": tur, "x-mk-istemci-ip": ip})


async def test_rapor_kaydedilir_govdesiz_204_ve_kisisel_veri_yok(istemci, db_oturumu):
    from models.csp_raporlari import CspRaporlari

    y = await _gonder(istemci, _eski_bicim())
    assert y.status_code == 204 and y.content == b""
    k = (await db_oturumu.execute(select(CspRaporlari))).scalar_one()
    # Jeton taşıyabilen yol kısaltıldı, sorgu dizgeleri atıldı.
    assert k.belge == "https://mehmetkuru.dev/teklif/…"
    assert k.engellenen == "https://kotu.example/betik.js"
    assert k.kaynak_dosya == "https://mehmetkuru.dev/assets/index-abc.js"
    assert (k.yonerge, k.satir, k.sutun, k.mod, k.sayi) == ("script-src-elem", 12, 7, "enforce", 1)

    # Reporting API biçimi (dizi), dil önekli yol korunur, örnek 40 karaktere kırpılır.
    y = await _gonder(istemci, _yeni_bicim(2), tur="application/reports+json")
    assert y.status_code == 204
    # İki rapor yalnız sorgu dizgesinde ayrışıyor → tek satırda birleşiyor (sayi 2).
    s = (await db_oturumu.execute(select(CspRaporlari).where(CspRaporlari.yonerge == "connect-src"))).scalar_one()
    assert s.belge == "https://mehmetkuru.dev/en/blog/…" and s.engellenen == "https://www.google.de/ads/ga-audiences"
    assert s.kaynak_dosya == "https://www.googletagmanager.com/gtag/js" and s.mod == "report"
    assert len(s.ornek) == 40 and s.sayi == 2


async def test_ayni_ihlal_birlesir_ve_ozel_kaynaklar(istemci, db_oturumu):
    from models.csp_raporlari import CspRaporlari

    for _ in range(3):
        assert (await _gonder(istemci, _eski_bicim(**{"blocked-uri": "inline", "script-sample": "alert(1)"}))).status_code == 204
    k = (await db_oturumu.execute(select(CspRaporlari))).scalar_one()
    assert k.engellenen == "inline" and k.sayi == 3 and k.ornek == "alert(1)"
    await _gonder(istemci, _eski_bicim(**{"blocked-uri": "data:image/png;base64,AAAA"}))
    assert (await db_oturumu.execute(select(func.count(CspRaporlari.id)).where(CspRaporlari.engellenen == "data"))).scalar() == 1


async def test_bozuk_ve_bos_govde(istemci, db_oturumu):
    from models.csp_raporlari import CspRaporlari

    for govde in (b"", b"{bozuk", b"[]", b"{}", json.dumps({"csp-report": {"document-uri": "x"}}).encode()):
        y = await _gonder(istemci, govde)
        assert y.status_code in (204, 400) and y.content == b"", govde
    assert (await db_oturumu.execute(select(func.count(CspRaporlari.id)))).scalar() == 0


async def test_boyut_siniri_413(istemci):
    from routers.csp_rapor import GOVDE_SINIRI

    y = await _gonder(istemci, b"[" + b" " * (GOVDE_SINIRI + 10) + b"]")
    assert y.status_code == 413 and y.content == b""


async def test_ip_hiz_siniri_429(istemci, db_oturumu):
    from models.csp_raporlari import CspRaporlari
    from routers.csp_rapor import IP_SINIRI

    durumlar = [(await _gonder(istemci, _eski_bicim(), ip="198.51.100.77")).status_code for _ in range(IP_SINIRI + 3)]
    assert durumlar[:IP_SINIRI] == [204] * IP_SINIRI and durumlar[IP_SINIRI:] == [429] * 3
    # Başka IP etkilenmiyor.
    assert (await _gonder(istemci, _eski_bicim(), ip="198.51.100.78")).status_code == 204
    k = (await db_oturumu.execute(select(CspRaporlari))).scalar_one()
    assert k.sayi == IP_SINIRI + 1


async def test_tablo_en_cok_500_satir(istemci, db_oturumu, monkeypatch):
    from models.csp_raporlari import CspRaporlari
    from routers import csp_rapor

    monkeypatch.setattr(csp_rapor, "TABLO_SINIRI", 5)
    for i in range(4):
        await _gonder(istemci, _yeni_bicim(2, blockedURL=f"https://a{i}.example/x"), tur="application/reports+json")
    for i in range(4, 9):
        await _gonder(istemci, _eski_bicim(**{"blocked-uri": f"https://b{i}.example/y"}))
    # 9 farklı ihlal geldi; en yeni 5'i kalıyor.
    satirlar = (await db_oturumu.execute(select(CspRaporlari).order_by(CspRaporlari.id))).scalars().all()
    assert len(satirlar) == 5
    assert [s.engellenen for s in satirlar][-1] == "https://b8.example/y"
    assert "https://a0.example/x" not in {s.engellenen for s in satirlar}


async def test_yonetim_yalniz_yonetici(istemci, yonetici_basligi, musteri_basligi):
    await _gonder(istemci, _eski_bicim())
    assert (await istemci.get(YONETIM)).status_code == 401
    assert (await istemci.get(YONETIM, headers=musteri_basligi())).status_code == 403
    assert (await istemci.delete(YONETIM, headers=musteri_basligi())).status_code == 403
    y = await istemci.get(YONETIM, headers=yonetici_basligi)
    assert y.status_code == 200
    g = y.json()
    assert g["toplam"] == 1 and g["sinir"] == 500
    assert g["items"][0]["yonerge"] == "script-src-elem" and g["items"][0]["belge"] == "https://mehmetkuru.dev/teklif/…"
    y = await istemci.delete(YONETIM, headers=yonetici_basligi)
    assert y.status_code == 200 and y.json() == {"silinen": 1}
    assert (await istemci.get(YONETIM, headers=yonetici_basligi)).json()["toplam"] == 0


@pytest.mark.skipif(shutil.which("node") is None, reason="node yok")
def test_csp_basliklari_node_testi():
    sonuc = subprocess.run(
        ["node", "--test", "scripts/csp-basliklari.test.mjs"],
        cwd=ON_YUZ, capture_output=True, text=True, timeout=120,
    )
    assert sonuc.returncode == 0, sonuc.stdout[-3000:] + sonuc.stderr[-2000:]
    assert "# fail 0" in sonuc.stdout
