"""Faz 3Y — yasal sayfaların veri sorumlusu bilgileri (site ayarları).

* `yasal_*` anahtarları herkese açık okunur (sayfada gösteriliyorlar); gizli
  ayarlar (webhook jetonu, yönetici adresleri, yapay zekâ ayarları) hâlâ
  okunmaz — kara liste mantığı değişmedi.
* Yazma yalnız yöneticide: ziyaretçi 401, müşteri 403.
* Gömülebilir CRM formunda aydınlatma bağlantısı boşsa sitenin /gizlilik
  sayfası (seçili dilde) gösterilir; doluysa formunki.
"""

from routers.site_settings import GIZLI_ANAHTARLAR, YASAL_ANAHTARLAR, gizli_ayar_mi

A = "/api/v1/entities/site_settings"


def test_yasal_anahtarlar_gizli_sayilmiyor_kara_liste_ayni():
    assert len(YASAL_ANAHTARLAR) == 7
    for k in YASAL_ANAHTARLAR:
        assert not gizli_ayar_mi(k), k
        assert k not in GIZLI_ANAHTARLAR
    # Kara liste ve desen eskisi gibi çalışıyor.
    for k in ("shopier_webhook_token", "admin_emails", "notify_admin_phone", "ai_acik_model", "deneme_api_key", "smtp_password"):
        assert gizli_ayar_mi(k), k


async def test_yasal_ayarlar_herkese_acik_gizliler_kapali(istemci, yonetici_basligi, musteri_basligi):
    degerler = {
        "yasal_unvan": "Deneme Unvanı",
        "yasal_eposta": "kvkk@deneme.dev",
        "yasal_adres": "Deneme Mah. 1 Sok. No:2 İstanbul",
        "yasal_kep": "deneme@hs01.kep.tr",
        "yasal_vkn": "1234567890",
        "yasal_mersis": "0123456789012345",
        "yasal_son_guncelleme": "2026-10-01",
        "deneme_yasal_webhook_token": "cok-gizli-yasal",
    }
    olusan = []
    for anahtar, deger in degerler.items():
        r = await istemci.post(A, json={"setting_key": anahtar, "setting_value": deger, "group_name": "yasal"}, headers=yonetici_basligi)
        assert r.status_code == 201, r.text
        olusan.append(r.json()["id"])
    try:
        for baslik in ({}, musteri_basligi("yasal-musteri@test.dev")):
            r = await istemci.get(f"{A}?limit=2000", headers=baslik)
            assert r.status_code == 200
            harita = {o["setting_key"]: o["setting_value"] for o in r.json()["items"]}
            for k in YASAL_ANAHTARLAR:
                assert harita.get(k) == degerler[k], k
            assert "deneme_yasal_webhook_token" not in harita and "cok-gizli-yasal" not in r.text
            # Tek tek okuma: yasal açık, gizli 404.
            r1 = await istemci.get(f"{A}/{olusan[2]}", headers=baslik)
            assert r1.status_code == 200 and r1.json()["setting_value"] == degerler["yasal_adres"]
            assert (await istemci.get(f"{A}/{olusan[-1]}", headers=baslik)).status_code == 404
    finally:
        for i in olusan:
            await istemci.delete(f"{A}/{i}", headers=yonetici_basligi)


async def test_yasal_ayarlari_yalniz_yonetici_yazar(istemci, yonetici_basligi, musteri_basligi):
    govde = {"setting_key": "yasal_adres", "setting_value": "Sahte adres", "group_name": "yasal"}
    assert (await istemci.post(A, json=govde)).status_code == 401
    assert (await istemci.post(A, json=govde, headers=musteri_basligi("yazamaz@test.dev"))).status_code == 403

    r = await istemci.post(A, json={**govde, "setting_value": "Gerçek adres"}, headers=yonetici_basligi)
    assert r.status_code == 201
    kimlik = r.json()["id"]
    try:
        for baslik, beklenen in (({}, 401), (musteri_basligi("yazamaz@test.dev"), 403)):
            assert (await istemci.put(f"{A}/{kimlik}", json={"setting_value": "Değişti"}, headers=baslik)).status_code == beklenen
            assert (await istemci.delete(f"{A}/{kimlik}", headers=baslik)).status_code == beklenen
        assert (await istemci.get(f"{A}/{kimlik}")).json()["setting_value"] == "Gerçek adres"
        # Yönetici boşaltabiliyor (sayfada adres satırı o zaman hiç basılmıyor).
        r = await istemci.put(f"{A}/{kimlik}", json={"setting_value": ""}, headers=yonetici_basligi)
        assert r.status_code == 200 and r.json()["setting_value"] == ""
    finally:
        await istemci.delete(f"{A}/{kimlik}", headers=yonetici_basligi)


async def test_crm_formu_aydinlatma_varsayilani_gizlilik_sayfasi(istemci, yonetici_basligi):
    govde = {
        "ad": "Yasal varsayılan", "baslik": "Bize yazın",
        "kvkk_metni": "Kişisel verilerimin aydınlatma metnindeki amaçlarla işlenmesini kabul ediyorum.",
    }
    r = await istemci.post("/api/v1/crm/formlar", json=govde, headers=yonetici_basligi)
    assert r.status_code == 201, r.text
    f = r.json()
    assert f["aydinlatma_baglantisi"] is None  # panelde boş kalıyor
    tr = (await istemci.get(f"/api/v1/crm/form/{f['genel_anahtar']}", params={"dil": "tr"})).json()
    assert tr["kvkk"]["baglanti"] == "https://mehmetkuru.dev/gizlilik"
    en = (await istemci.get(f"/api/v1/crm/form/{f['genel_anahtar']}", params={"dil": "en"})).json()
    assert en["kvkk"]["baglanti"] == "https://mehmetkuru.dev/en/gizlilik"
    ar = (await istemci.get(f"/api/v1/crm/form/{f['genel_anahtar']}", params={"dil": "ar"})).json()
    assert ar["kvkk"]["baglanti"] == "https://mehmetkuru.dev/ar/gizlilik"

    # Panelde bağlantı girilince o kullanılıyor.
    r = await istemci.patch(f"/api/v1/crm/formlar/{f['id']}", json={"aydinlatma_baglantisi": "https://ornek.dev/kvkk"},
                            headers=yonetici_basligi)
    assert r.status_code == 200, r.text
    en = (await istemci.get(f"/api/v1/crm/form/{f['genel_anahtar']}", params={"dil": "en"})).json()
    assert en["kvkk"]["baglanti"] == "https://ornek.dev/kvkk"
