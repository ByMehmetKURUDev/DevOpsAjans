#!/bin/bash
# mehmetkuru.dev — yerel önizleme (macOS / Linux)
#
# Siteyi dosyaya çift tıklayarak açamazsınız: sayfalar birbirine
# /assets/... gibi kök adreslerle bağlı ve bunlar ancak bir sunucu
# üzerinden çalışır. Bu dosya o sunucuyu başlatır.
#
# macOS'ta ilk kullanımda çalıştırma izni gerekebilir:
#   chmod +x BASLAT.command

cd "$(dirname "$0")" || exit 1
PORT=4173

echo
echo "  ============================================"
echo "   mehmetkuru.dev  -  yerel önizleme"
echo "  ============================================"
echo

ac() {
  # Tarayıcıyı sunucu ayağa kalktıktan sonra aç.
  sleep 1
  if command -v open >/dev/null 2>&1; then open "http://localhost:$PORT"
  elif command -v xdg-open >/dev/null 2>&1; then xdg-open "http://localhost:$PORT"
  fi
}

if command -v python3 >/dev/null 2>&1; then
  echo "  Adres: http://localhost:$PORT"
  echo "  Kapatmak için: Ctrl+C"
  echo
  ac &
  python3 onizleme-sunucu.py "$PORT"
elif command -v npx >/dev/null 2>&1; then
  echo "  Python bulunamadı, Node ile deneniyor..."
  echo "  Adres: http://localhost:$PORT"
  echo
  ac &
  npx --yes serve -s . -l "$PORT"
else
  echo "  Bilgisayarınızda Python da Node da bulunamadı."
  echo "  macOS'ta Terminal'i açıp şunu çalıştırın:  xcode-select --install"
  echo "  Sonra bu dosyaya tekrar çift tıklayın."
  echo
  read -r -p "  Kapatmak için Enter'a basın..."
fi
