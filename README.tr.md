# Webcam QR Scanner

[English](README.md) | **Türkçe**

Bilgisayar kamerasından veya doğrudan ekrandan QR kod okuyan hızlı ve güvenli
bir Windows masaüstü uygulaması.

![Webcam QR Scanner arayüzü](docs/assets/webcam-qr-scanner.png)

## Kullanım videosu

Tanıtımda bu public GitHub reposunun adresini içeren QR kod okunur, bağlantı
varsayılan tarayıcıda açılır ve QR Scanner otomatik olarak kapanır.

![Webcam QR Scanner kullanım videosu](docs/assets/webcam-qr-scanner-demo.gif)

## Özellikler

- Modern turkuaz arayüzle canlı kamera görüntüsü
- Aynı zamanda gerçek QR analiz alanı olan görünür tarama çerçevesi
- Tüm bağlı ekranları tek sefer tarayan ayrı `Scan Screen` seçeneği
- Ekran taramalarında hedef alan adını gösteren bağlantı onayı
- Farklı QR kodlar birlikte bulunursa hiçbirini açmayan belirsizlik koruması
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

Son GitHub Release içinden `Webcam-QR-Scanner-v0.1.1-windows-x64.zip` dosyasını
indirin ve arşivden çıkarın. Python veya OpenCV'yi ayrıca kurmanız gerekmez.

### Kamerayla tarama

`QR-Scanner.exe` dosyasına çift tıklayın:

1. Windows kamera izni isterse izin verin.
2. QR kodun tamamını turkuaz çerçevenin içine yerleştirin.
3. Geçerli web bağlantısı varsayılan tarayıcıda açılır.
4. İlk başarılı okumadan sonra QR Scanner kapanır.

### Bilgisayar ekranında görünen QR kodu tarama

Ekranda yalnızca bir QR kodu açık bırakın ve `Scan Screen.vbs` dosyasına çift
tıklayın.

1. Uygulama bağlı ekranların tamamını bir kez yakalar.
2. Görüntü yalnızca bellekte tutulur ve hiçbir zaman kaydedilmez.
3. QR geçerli bir HTTP/HTTPS bağlantısı içeriyorsa onay penceresinde hedef alan
   adı ve tam adres gösterilir.
4. Açmak için **Yes**, vazgeçmek için **No** seçin.

Aynı anda farklı QR kodlar algılanırsa hiçbir bağlantı açılmaz. Diğerlerini
gizleyip `Scan Screen.vbs` dosyasını yeniden çalıştırın. Ekran sürekli izlenmez.

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

# Bağlı ekranların tamamını bir kez tara
.\.venv\Scripts\python.exe app.py --screen
```

`QR Scanner.vbs` kaynak sürümü terminal göstermeden başlatır.
`Scan Screen.vbs` ayrı, tek seferlik ekran taramasını terminal göstermeden
başlatır. `start_qr_scanner.bat` ise sorun giderme günlükleri için terminali
açık tutar.

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
dist\Webcam-QR-Scanner-v0.1.1-windows-x64.zip
```

ZIP içinde `QR-Scanner.exe`, `Scan Screen.vbs` başlatıcısı, proje MIT lisansı,
üçüncü taraf bildirimi ve pakete dahil bağımlılıkların eksiksiz lisans metinleri
bulunur. Bütünlük kontrolü için ayrıca `SHA256SUMS.txt` üretilir.

## Proje yapısı

- `app.py`: uygulama akışı ve komut satırı seçenekleri
- `camera.py`: kamera seçimi, Full HD ölçümü ve 720p geri dönüşü
- `qr_reader.py`: hızlı ve kapsamlı QR çözümleme
- `screen_capture.py`: tek seferlik, çoklu monitör Windows ekran yakalama
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

Kamera kareleri yalnızca bilgisayar belleğinde yerel olarak işlenir; kaydedilmez
ve bilgisayar dışına gönderilmez. Uygulama konum bilgisi istemez; analiz,
telemetri veya cihaz kimliği toplamaz. Geçerli bir URL açıldıktan sonra hedef
site varsayılan tarayıcı tarafından işlenir ve tarayıcının gizlilik ayarlarına
tabidir.

Ekran taraması kullanıcı tarafından açıkça başlatılır ve sanal masaüstünü
yalnızca bir kez yakalar. Yakalanan pikseller yerel olarak bellekte işlenir,
diske yazılmaz. Ekrandaki bir QR bağlantısı onay alınmadan açılmaz; aynı anda
farklı QR içerikleri bulunursa uygulama keyfî seçim yapmak yerine işlemi
reddeder.

Uygulama URL şemasını doğrular ancak bir sitenin güvenilir veya zararlı olduğunu
belirleyemez. Ekrandaki QR bağlantısını açmadan önce onay penceresinde gösterilen
alan adını kontrol edin.

## Yol haritası

### v0.1 — Windows masaüstü sürümü

- [x] Kaynak kodu GitHub reposunda yayımlama
- [x] Terminal göstermeyen bağımsız Windows EXE paketi
- [x] GitHub Releases üzerinden `v0.1.0` yayımlama
- [x] Ekran görüntüsü, kullanım GIF'i ve sürüm notları

### v0.1.1 — Bilgisayar ekranındaki QR kodları okuma

- [x] Ayrı `Scan Screen` başlatıcısı ekleme
- [x] Bağlı ekranların tamamını görüntü kaydetmeden bir kez yakalama
- [x] Ekran URL'sini açmadan önce alan adını gösterme ve onay isteme
- [x] Farklı QR içerikleri bulunan belirsiz taramaları engelleme
- [x] Otomatik testleri ve bağımsız Windows paketini hazırlama

### v0.2 — Telefon-PC köprüsü

Kısa süre geçerli QR kod ve bilgisayarda tek seferlik onay ile hesapsız
eşleştirme planlanıyor. QR içeriği telefonda uçtan uca şifrelenecek ve içeriği
okuyamayan bir internet aracısı üzerinden iletilecek. Böylece telefon, yerel ağ
ve konum izni gerektirmeden mobil veri üzerinden bağlantı gönderebilecek.
Bilgisayar içeriği doğrulayacak ve varsayılan olarak açmadan önce kullanıcıdan
onay isteyecek.

### v0.2.1 — Şifreli kuyruk ve hatırlatmalar

Bilgisayar çevrimdışıysa şifreli öğe bilgisayar yeniden bağlanana kadar
telefonda tutulacak. İsteğe bağlı hatırlatmalar ve süresi dolan öğelerin otomatik
silinmesi planlanıyor; otomatik açma açık bir kullanıcı tercihi olarak kalacak.

### v0.2.2 — İsteğe bağlı yerel ağ modu

İki cihaz aynı ağdayken internet aracısı kullanmak istemeyen kullanıcılar için
doğrudan yerel ağ aktarımı daha sonra isteğe bağlı alternatif olarak
eklenebilir.

## Lisans

Telif hakkı © 2026 [alpkonakci](https://github.com/alpkonakci).

Bu proje [MIT Lisansı](LICENSE) ile lisanslanmıştır.
Paketlenen bağımlılıkların lisansları
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) dosyasında açıklanmıştır.
