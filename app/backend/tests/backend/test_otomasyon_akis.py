"""Faz 11C — Otomasyon › Akış görünümü: `GET .../akis-ozeti`.

Kapsam: yetki (anonim 401, modül kapalı müşteri 403), boş veride sıfırlar/None, örnek çalışmalarla
son 30 gün sayısı + günlük seri kovaları + başarı oranı (koşulu tutmayan hariç) + son 3 çalışma sırası,
sahiplik (başka hesabın kuralı 404, başka hesabın çalışması sayılmaz, ajans/müşteri ayrımı).
"""

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import delete

from conftest import jeton_uret

Y = "/api/v1/otomasyon/yonetim"
M = "/api/v1/otomasyonlarim"
MODUL = "/api/v1/moduller"


def _e(on: str = "akis") -> str:
    return f"{on}-{uuid.uuid4().hex[:8]}@oto.dev"


def _b(eposta: str) -> dict:
    return {"Authorization": f"Bearer {jeton_uret(eposta, 'user')}"}


@pytest.fixture(autouse=True)
async def _temiz(monkeypatch, db_oturumu):
    from models.otomasyon import OtomasyonCalismalari, OtomasyonKurallari
    from routers import otomasyon as r
    from services import otomasyon

    r.hiz_sinirlarini_temizle()
    otomasyon.onbellegi_temizle()
    # Elle eklenen "bekliyor" çalışmaları arka plan pompası işlemesin (sonraki test dosyalarına taşar).
    monkeypatch.setattr(otomasyon, "ANLIK_ISLEME", False)
    monkeypatch.setattr(otomasyon, "POMPA_GECIKMESI_SN", 0)
    # Önceki test dosyalarının bıraktığı kurallar/çalışmalar sayıları bozmasın.
    for model in (OtomasyonCalismalari, OtomasyonKurallari):
        await db_oturumu.execute(delete(model))
    await db_oturumu.commit()
    otomasyon.onbellegi_temizle()
    yield
    for model in (OtomasyonCalismalari, OtomasyonKurallari):
        await db_oturumu.execute(delete(model))
    await db_oturumu.commit()
    otomasyon.onbellegi_temizle()


async def _musteri(istemci, yb, acik=True) -> str:
    e = _e("musteri")
    y = await istemci.put(f"{MODUL}/musteri/{e}/otomasyon", json={"acik": acik}, headers=yb)
    assert y.status_code == 200, y.text
    return e


async def _kural(istemci, basliklar, yol=Y, ad="Akış kuralı") -> dict:
    y = await istemci.post(f"{yol}/kurallar", headers=basliklar, json={
        "ad": ad, "tetik": "destek.olusturuldu",
        "kosullar": {"baglac": "ve", "kosullar": [{"alan": "talep.oncelik", "islec": "esittir", "deger": "acil"}]},
        "eylemler": [{"tur": "bildirim", "alici": "hesap" if yol == M else "yoneticiler", "baslik": "Yeni talep"},
                     {"tur": "bekle", "miktar": 1, "birim": "saat"},
                     {"tur": "bildirim", "alici": "hesap" if yol == M else "yoneticiler", "baslik": "Hâlâ açık"}],
    })
    assert y.status_code == 200, y.text
    return y.json()


async def _calisma(db, kural: dict, durum: str, gun_once: float = 0, hesap: str | None = None):
    from models.otomasyon import OtomasyonCalismalari

    an = datetime.now(timezone.utc) - timedelta(days=gun_once)
    c = OtomasyonCalismalari(
        kural_id=kural["id"], sahip_tur=kural["sahip_tur"], hesap_email=kural["hesap_email"],
        olay_id=uuid.uuid4().hex, tur="destek.olusturuldu", olay_hesap=hesap, durum=durum,
        eylem_sonuclari="[]", created_at=an, updated_at=an,
    )
    db.add(c)
    await db.commit()
    await db.refresh(c)
    return c


async def test_yetki_ve_bos_veri(istemci, yonetici_basligi):
    assert (await istemci.get(f"{Y}/akis-ozeti")).status_code == 401
    assert (await istemci.get(f"{M}/akis-ozeti")).status_code == 401
    kapali = await _musteri(istemci, yonetici_basligi, acik=False)
    assert (await istemci.get(f"{M}/akis-ozeti", headers=_b(kapali))).status_code == 403
    # Müşteri yönetici yoluna giremez.
    assert (await istemci.get(f"{Y}/akis-ozeti", headers=_b(kapali))).status_code in (401, 403)

    y = await istemci.get(f"{Y}/akis-ozeti", headers=yonetici_basligi)
    assert y.status_code == 200, y.text
    d = y.json()
    assert d["pencere_gun"] == 30 and d["kural"] is None
    assert d["tumu"]["toplam"] == 0 and d["tumu"]["seri"] == [0] * 30
    assert d["tumu"]["basari"] == {"basarili": 0, "basarisiz": 0, "oran": None}
    # Var olmayan kural 404.
    assert (await istemci.get(f"{Y}/akis-ozeti?kural_id=999999", headers=yonetici_basligi)).status_code == 404


async def test_sayilar_seri_basari_ve_son(istemci, yonetici_basligi, db_oturumu):
    k = await _kural(istemci, yonetici_basligi)
    diger = await _kural(istemci, yonetici_basligi, ad="Diğer")
    await _calisma(db_oturumu, k, "tamam", 0)
    await _calisma(db_oturumu, k, "tamam", 0)
    await _calisma(db_oturumu, k, "hata", 3)
    await _calisma(db_oturumu, k, "kosul_tutmadi", 3)
    c_atl = await _calisma(db_oturumu, k, "atlandi", 10)
    c_eski = await _calisma(db_oturumu, k, "tamam", 45)  # pencere dışında
    c_bekl = await _calisma(db_oturumu, k, "bekliyor", 0)
    await _calisma(db_oturumu, diger, "tamam", 1)

    d = (await istemci.get(f"{Y}/akis-ozeti?kural_id={k['id']}", headers=yonetici_basligi)).json()
    assert d["kural_sayisi"] == 2 and d["etkin_kural"] == 2
    t = d["tumu"]
    assert t["toplam"] == 7 and sum(t["seri"]) == 7 and len(t["seri"]) == 30
    kk = d["kural"]
    assert kk["id"] == k["id"] and kk["toplam"] == 6
    # Bugün: 2 tamam + 1 bekliyor; 3 gün önce: hata + koşul tutmadı; 10 gün önce: atlandı.
    assert kk["seri"][-1] == 3 and kk["seri"][-4] == 2 and kk["seri"][-11] == 1 and sum(kk["seri"]) == 6
    # Başarı: tamam / (tamam + hata + atlandı) = 2/4; koşul tutmadı ve bekleyen hariç.
    assert kk["basari"] == {"basarili": 2, "basarisiz": 2, "oran": 0.5}
    assert kk["durumlar"]["kosul_tutmadi"] == 1 and kk["durumlar"]["bekliyor"] == 1
    # Son 3: en son oluşturulan önce (kimlik sırası).
    assert [s["id"] for s in kk["son"]] == [c_bekl.id, c_eski.id, c_atl.id]
    assert kk["son"][0]["durum"] == "bekliyor" and kk["son"][0]["zaman"]


async def test_sahiplik_ve_hesap_ayrimi(istemci, yonetici_basligi, db_oturumu):
    a = await _musteri(istemci, yonetici_basligi)
    b = await _musteri(istemci, yonetici_basligi)
    ka = await _kural(istemci, _b(a), M)
    kb = await _kural(istemci, _b(b), M)
    ajans = await _kural(istemci, yonetici_basligi)
    await _calisma(db_oturumu, ka, "tamam", 0, hesap=a)
    await _calisma(db_oturumu, ka, "hata", 1, hesap=a)
    await _calisma(db_oturumu, kb, "tamam", 0, hesap=b)
    await _calisma(db_oturumu, ajans, "tamam", 0)

    # A yalnız kendi kuralını ve çalışmalarını görür.
    da = (await istemci.get(f"{M}/akis-ozeti?kural_id={ka['id']}", headers=_b(a))).json()
    assert da["kural_sayisi"] == 1 and da["tumu"]["toplam"] == 2 and da["kural"]["basari"]["oran"] == 0.5
    assert da["kural"]["son"][0]["olay_hesap"] == a
    # Başka hesabın kuralı 404; ajans kuralı müşteriye 404.
    assert (await istemci.get(f"{M}/akis-ozeti?kural_id={kb['id']}", headers=_b(a))).status_code == 404
    assert (await istemci.get(f"{M}/akis-ozeti?kural_id={ajans['id']}", headers=_b(a))).status_code == 404
    # Yönetici yalnız ajans kurallarını sayar; müşteri kuralı yönetici yolunda 404.
    dy = (await istemci.get(f"{Y}/akis-ozeti", headers=yonetici_basligi)).json()
    assert dy["kural_sayisi"] == 1 and dy["tumu"]["toplam"] == 1
    assert (await istemci.get(f"{Y}/akis-ozeti?kural_id={ka['id']}", headers=yonetici_basligi)).status_code == 404
