@echo off
chcp 65001 >nul
title mehmetkuru.dev - yerel onizleme
cd /d "%~dp0"

echo.
echo  ============================================
echo   mehmetkuru.dev  -  yerel onizleme
echo  ============================================
echo.
echo  Siteyi dogrudan cift tiklayarak acamazsiniz.
echo  Sayfalar birbirine /assets/... gibi kok adreslerle
echo  bagli; bunlar ancak bir sunucu uzerinden calisir.
echo  Bu pencere o sunucuyu baslatiyor.
echo.

rem Python 3 iki farkli isimle kurulu olabiliyor.
where py >nul 2>nul && (
  echo  Sunucu baslatiliyor...  Adres: http://localhost:4173
  echo  Kapatmak icin bu pencereyi kapatin.
  echo.
  start "" http://localhost:4173
  py -3 onizleme-sunucu.py 4173
  goto :son
)

where python >nul 2>nul && (
  echo  Sunucu baslatiliyor...  Adres: http://localhost:4173
  echo  Kapatmak icin bu pencereyi kapatin.
  echo.
  start "" http://localhost:4173
  python onizleme-sunucu.py 4173
  goto :son
)

rem Python yoksa Node ile dene.
where npx >nul 2>nul && (
  echo  Python bulunamadi, Node ile deneniyor...
  echo  Adres: http://localhost:4173
  echo.
  start "" http://localhost:4173
  npx --yes serve -s . -l 4173
  goto :son
)

echo  Bilgisayarinizda Python da Node da bulunamadi.
echo.
echo  En kolay cozum: python.org/downloads adresinden
echo  Python'u kurun, kurulumda "Add python.exe to PATH"
echo  kutusunu isaretleyin, sonra bu dosyaya tekrar cift tiklayin.
echo.

:son
pause
