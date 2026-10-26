# Paketlenmiş TLS başlatma hatası — 24 Ekim 2026

Kullanıcının HTTPS adayında eşleştirme açarken gördüğü hata:
`Phone-to-PC pairing stopped safely. Technical reason: FileNotFoundError`.

## Kök neden ve yeniden üretim

Eski EXE certifi/cacert.pem içeriyordu. Native QR kabuğu kaynakta ve ayrı donmuş
tanı derlemesinde iş parçacığında açılabildi. Donmuş tanı derlemesinde yalnız
`httpx.Client()` oluşturmak, ağ isteği yapmadan aynı FileNotFoundError'ı üretti:
httpx/_config.py → ssl.create_default_context → SSLContext.__new__, ssl.py:440.

Derlemede kullanılan Python runtime'ının SSLContext'i, modülünün yanındaki
`codex-rejected-cas.pem` adlı ek kamuya açık güven politikası verisini yükler.
PyInstaller bunu otomatik toplamıyordu. Kaynak ortamda bulunan dosya EXE'nin
geçici açılım kökünde bulunmadığından TLS bağlantısından önce hata oluşuyordu.
Tanı aracı ağ, kamera veya eşleşme deposuna erişmedi; yalnız aşama/hata türü ve
kod dosyası adı/fonksiyon/satırını raporladı. Anahtar veya URL kaydetmedi.

## En küçük düzeltme

- Build recipe, aktif SSL runtime'ının yanındaki bu destek dosyası varsa onu
  donmuş ssl modülünün köküne ekler. Standart Python'da dosya yoksa ek girdi yoktur.
- Sertifika/hostname doğrulaması veya runtime'ın güven politikası kapatılmadı.
- `--self-test`, artık certifi ile doğrulanmış SSLContext oluşturmayı da denetler.
  Başarılı sayılmak için TLS ve arka plan QR çözümleme birlikte geçmelidir.
- Telefon sitesi, protokol, saklanan eşleşmeler ve anahtarlar değiştirilmedi.

## Kanıt

- Yeni regresyon testleri önce iki beklenen başarısızlığı yakaladı: eksik paket
  verisi ve TLS başlatma hatasına rağmen eski self-test'in başarılı sayılması.
- Düzeltme sonrası üç TLS paketleme testi ve tam 329 masaüstü testi geçti.
- Gerçek yeniden derlenmiş EXE'nin TLS + QR `--self-test` sonucu: çıkış 0.
- Ham düzeltilmiş EXE: `dist/tls-fix-20261024/QR-Scanner.exe`.
- EXE SHA256: `63E097D88CEB789FC7F6CB61A3D2DCD487D08050F204AD75F61584CA89CA26E3`.

Bu, eksik dosya nedeniyle TLS oluşturulamama hatasını doğrular ve giderir.
Gerçek telefon → PC eşleştirme/gönderme kabulünün tamamlandığı anlamına gelmez.
Bu yeni EXE için fiziksel test yeniden yapılmalıdır. Önceki aday doğrulama kaydı
tarihsel kanıttır; yeni hatanın bulunması nedeniyle yayın kabulü sayılmaz.
