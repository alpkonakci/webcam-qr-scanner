# Webcam QR Scanner

[English](README.md) | **Türkçe**

Bilgisayar kamerasından QR kod okuyup geçerli web bağlantılarını varsayılan
tarayıcıda açan hızlı ve güvenli bir Windows masaüstü uygulaması.

## Özellikler

- Modern turkuaz arayüzle canlı kamera görüntüsü
- Aynı zamanda gerçek QR analiz alanı olan görünür tarama çerçevesi
- Tek veya birden fazla QR kod algılama
- Geçerli HTTP/HTTPS bağlantılarını otomatik açma
- İlk başarılı okumadan sonra otomatik kapanma
- Aynı QR kodun tekrar tekrar açılmasını engelleme
- 1920×1080, 30 FPS hedefi ve otomatik 1280×720 geri dönüşü
- Yalnızca en güncel kareyi işleyen, görüntüyü dondurmayan arka plan analizi
- Küçük veya uzaktaki QR kodlar için belirli aralıklarla kapsamlı tarama
- Telefon ekranında gösterilen QR kodlar için ek görüntü işleme
- `--show-fps` ile isteğe bağlı geliştirici FPS göstergesi
- `Esc` veya pencerenin kapatma düğmesiyle güvenli çıkış
- Terminal göstermeyen bağımsız Windows EXE paketi

## İndirme ve kullanım

Son GitHub Release içinden `Webcam-QR-Scanner-v0.1.0-windows-x64.zip` dosyasını
indirin, arşivden çıkarın ve `QR-Scanner.exe` dosyasına çift tıklayın. Python
veya OpenCV'yi ayrıca kurmanız gerekmez.

1. Windows kamera izni isterse izin verin.
2. QR kodun tamamını turkuaz çerçevenin içine yerleştirin.
3. Geçerli web bağlantısı varsayılan tarayıcıda açılır.
4. İlk başarılı okumadan sonra QR Scanner kapanır.

Tek dosyalı paket, içindeki dosyaları hazırladığı için ilk açılış birkaç saniye
daha uzun sürebilir. İnternetten indirilen imzasız EXE'ler için Windows
SmartScreen uyarı gösterebilir.

## Telefon ekranından daha iyi tarama

- Ekran parlaklığını en yüksek seviyede kullanmayın. Yansıma ve aşırı pozlama QR
  kodun algılanmasını zorlaştırabilir.
- Orta seviye parlaklık genellikle daha iyi sonuç verir.
- Telefonu mümkün olduğunca düz tutun; yansımayı azaltmak için açısını hafifçe
  değiştirin.
- QR kodun tamamını çerçeveye alın ve yaklaşık 15–30 cm mesafeden başlayın.
- Dalgalı moiré deseni oluşursa telefonu birkaç santimetre ileri veya geri alın.

## Performans

Kamera yakalama ve QR çözümleme birbirinden bağımsız çalışır. Arka plan işçisi
kuyruk oluşturmak yerine yalnızca en güncel kareyi analiz eder; böylece QR
işleme kamera görüntüsünü dondurmaz. Analiz yalnızca turkuaz çerçevenin içinde
yapılır.

Uygulama başlangıçta 1920×1080, 30 FPS kamera akışını ölçer. Kamera bu
çözünürlüğü desteklemiyorsa veya ölçülen hız 24 FPS'nin altında kalıyorsa
1280×720, 30 FPS ayarına geçmeyi dener.

### Yerel benchmark

Bu değerler geliştirme bilgisayarında ölçülmüştür ve performans garantisi
değildir. Kamera, işlemci, Windows sürücüsü ve ortam ışığı sonucu etkileyebilir.

- Platform: Windows, OpenCV Media Foundation kamera arka ucu
- Kamera hedefi: 1920×1080, 30 FPS
- Kapsam: kamera yakalama, arka plan QR analizi ve arayüz çizimi
- Ölçülen tam işlem hattı: yaklaşık 30,1 FPS
- Ölçülen hızlı QR analiz kapasitesi: yaklaşık 48,7 FPS

FPS sayacı varsayılan olarak gizlidir. Geliştirici ölçümü için:

```powershell
.\.venv\Scripts\python.exe app.py --show-fps
```

Normal performans turkuaz, 24 FPS altındaki değerler amber renkte gösterilir.
Yeşil yalnızca başarılı QR okumasını belirtir.

## Kaynak koddan çalıştırma

Python 3.10 veya daha yeni bir sürüm gerekir:

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe app.py
```

Kullanışlı seçenekler:

```powershell
# Farklı kamera kullan
.\.venv\Scripts\python.exe app.py --camera 1

# Bağlantıları otomatik açma
.\.venv\Scripts\python.exe app.py --no-open

# İlk QR koddan sonra açık kal
.\.venv\Scripts\python.exe app.py --keep-open

# Geliştirici FPS göstergesini aç
.\.venv\Scripts\python.exe app.py --show-fps
```

`QR Scanner.vbs` kaynak sürümü terminal göstermeden başlatır.
`start_qr_scanner.bat` ise sorun giderme günlükleri için terminali açık tutar.

## Testler

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe app.py --self-test
```

Self-test, kamera açmadan OpenCV yüklemesini ve QR çözümlemeyi doğrular.

## Windows EXE oluşturma

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\build_exe.bat
```

Build sonunda terminal göstermeyen EXE ile dağıtıma hazır arşiv oluşturulur:

```text
dist\Webcam-QR-Scanner-v0.1.0-windows-x64.zip
```

ZIP içinde `QR-Scanner.exe`, proje MIT lisansı, üçüncü taraf bildirimi ve pakete
dahil bağımlılıkların eksiksiz lisans metinleri bulunur. Bütünlük kontrolü için
ayrıca `SHA256SUMS.txt` üretilir.

## Proje yapısı

- `app.py`: uygulama akışı ve komut satırı seçenekleri
- `camera.py`: kamera seçimi, Full HD ölçümü ve 720p geri dönüşü
- `qr_reader.py`: hızlı ve kapsamlı QR çözümleme
- `scan_worker.py`: yalnızca en güncel kareyi işleyen arka plan işçisi
- `scan_geometry.py`: gerçek tarama alanı ve koordinat dönüşümleri
- `ui.py`: arayüz, hareketli tarama çizgisi ve sonuç görünümü
- `links.py`: güvenli URL sınıflandırma ve tarayıcı açma
- `performance.py`: isteğe bağlı FPS ölçümü
- `tests/`: otomatik davranış, kamera seçimi ve QR okuyucu testleri

## Güvenlik

Yalnızca açıkça yazılmış, geçerli `http://` ve `https://` bağlantıları otomatik
açılır. `javascript:` veya `file:` gibi şemalar çalıştırılmaz. QR kod kamerada
tutulduğunda sürekli yeni tarayıcı sekmeleri açılmaz.

## Yol haritası

### v0.1 — Windows masaüstü sürümü

- [x] Kaynak kodu GitHub reposunda yayımlama
- [x] Terminal göstermeyen bağımsız Windows EXE paketi
- [x] GitHub Releases üzerinden `v0.1.0` yayımlama
- [ ] Ekran görüntüsü, kullanım GIF'i ve sürüm notları

### v0.1.1 — Bilgisayar ekranındaki QR kodları okuma

Varsayılan olarak kapalı olacak şekilde planlandı. Etkinleştirildiğinde aktif
ekranı veya kullanıcının seçtiği alanı tarayacak; ekran görüntülerini kalıcı
olarak saklamayacak. Tekrar koruması, HTTP/HTTPS doğrulaması, çoklu monitör
desteği ve isteğe bağlı onay seçeneği korunacak.

### v0.2 — Telefon-PC köprüsü

Telefon ve bilgisayarın güvenli biçimde eşleştirilmesi planlanıyor. Telefonla
okunan QR kod yerel ağ üzerinden bilgisayara iletilecek ve doğrulandıktan sonra
bilgisayarın varsayılan tarayıcısında açılacak.

## Lisans

Telif hakkı © 2026 [alpkonakci](https://github.com/alpkonakci).

Bu proje [MIT Lisansı](LICENSE) ile lisanslanmıştır.
Paketlenen bağımlılıkların lisansları
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) dosyasında açıklanmıştır.
