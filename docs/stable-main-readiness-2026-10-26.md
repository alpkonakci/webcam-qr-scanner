# beta.9 → main / kararlı sürüm değerlendirmesi — 26 Ekim 2026

İncelenen HEAD: `79224368263e85cdc65a20315ee2d1c3b4179f1b`.

Production audit: **68/100, düzeltme gerekli**. Bu puan ölçülmüş güvenlik olasılığı
değil, aşağıdaki somut risklerin önceliklendirme özetidir. Kararlı sürüm onayı yok.
Main birleşimi, kararlı sürüm etiketi ve production dağıtımı ayrı kararlardır.

## Yeni doğrulanan engeller

1. **Önemli — Unicode alan adında yanıltıcı onay.**
   `bridge/protocol.py:763` Python IDNA2003 dönüşümü ile `faß.de` için `fass.de`
   üretiyor, fakat satır 770 özgün Unicode URL'yi koruyor. `native_dialogs.py:144`
   bu ASCII alan adını belirgin biçimde gösteriyor; `links.py:24` özgün URL'yi
   tarayıcıya iletiyor. WHATWG URL çözümlemesi `xn--fa-hia.de` sonucunu veriyor.
   Böylece kullanıcının belirgin onayladığı alan adı ile açılan hedef farklı.
   Tam URL de görünür ve onay hâlâ gerekir; otomatik kod çalıştırma iddia edilmiyor.
   İkinci güvenlik ajanının bulgusu ana ajan tarafından gerçek fonksiyonla yeniden
   üretildi; örnek adres ziyaret edilmedi. IDNA/URL normalizasyonu ve onay/açılış
   hedefi aynı kanonik biçime getirilmeli veya desteklenmeyen biçimler reddedilmeli.

2. **Önemli — Belgelenmiş derleme komutunda eski paket adı.**
   `build_exe.bat:56` hâlâ `v0.2.0-beta.8-preview.2` geçiriyor. beta.9 kaynaklarıyla
   bu komut eski adlandırılmış ZIP üretebilir. Yayımlanmış beta.9 ayrı açık sürüm
   komutuyla paketlendi ve hash'leri bağımsız ajan tarafından doğrulandı; bu bulgu
   mevcut indirmenin bozuk olduğunu göstermez.

3. **Operasyonel — Main dalı korumasız.**
   GitHub salt okunur API sonucu `protected:false`. PR #3 taslak, mergeable=true,
   mergeable_state=clean; Desktop/Web/Retention/Vercel sonuçları başarılı.
   Vercel proje ekranı production güncellemesi için `main` dalına push gerektiğini
   belirtiyor. Bu yüzden birleşim salt Git düzenlemesi gibi ele alınmamalı;
   production dağıtımını tetikleyebilir. Gerekli CI ve inceleme kuralları
   doğrulanmalı/ayarlanmalı; bu çalışmada ayar değiştirilmedi.

## Ek testler

- Canlı beta.9, beş temiz Chromium bağlamında: 360×800 en-US, 393×852 tr-TR,
  430×932 en-US, 768×1024 tr-TR, 1280×800 en-US.
  Ana sayfa, Ayarlar/Geri, yerel görsel QR okuma, yenilemede yeni nonce ve Tab
  odağı geçti. Yatay taşma, pageerror ve GET/HEAD dışı ağ isteği gözlenmedi.
  Bu Chrome motorudur; Safari, Samsung Internet veya fiziksel cihaz matrisi değildir.
- Gerçek gizli OpenCV/Windows pencere imleci, seçimde bağımsız artı imleci ve
  pencereyi yeniden açma smoke testi geçti.
- Python bağımlılık tutarlılığı (`pip check`) başarılı; bu CVE taraması değildir.
- 66 odaklı protokol/vektör/DPAPI-depolama/replay regresyonu geçti. Yeni Unicode
  hedef uyumsuzluğunu mevcut testlerin yakalamadığı ayrıca gösterildi.
- İkinci sürüm inceleme ajanı beta.9 ZIP ve çıkarılmış EXE SHA256 değerlerini
  yeniden hesaplayıp yayın kaydıyla eşleştiğini bildirdi.

## Cihaz kabulü ve açık kalanlar

Kullanıcı beta.9 için Android/S24 ve iOS/iPhone 15 Plus üzerinde denediğini bildirdi.
Tarayıcı/işletim sistemi sürümleri, Chrome/Samsung Internet ayrımı ve kurulu PWA
modu ayrı doğrulanmadı. Önceki başarılı kullanıcı akışları geçerlidir, bu detayların
yerine sayılmaz. İkinci temiz Windows hesabı/makinesi sonucu bu turda alınmadı.
pywinauto mevcut ortamda kurulu olmadığı için yeni tam EXE/UIA akışı çalıştırılmadı;
ek paket kurulmadı ve kullanıcı uygulaması kapatılmadı.

Gerçek VoiceOver/TalkBack dinamik duyuruları, canlı geçerli sentetik kimliklerle
çapraz cihaz/revocation API testi, rate-limit kapsamı ve dış insan uzman tarafından
protokol/kriptografi incelemesi açık kalır. İki taze bağlamlı ajan incelemesi dış
bağımsız güvenlik sertifikası değildir; 319 dosyalık main farkının tamamının
satır satır incelendiği iddia edilmez.

## Main için yol

1. Yukarıdaki alan adı/onay ve derleme sürümü sorunlarını testlerle düzelt.
2. Yeni adayda hedefli testler, tüm CI ve gerekli gerçek cihaz kontrollerini al.
3. Main için gerekli inceleme/CI kurallarını doğrula; otomatik production etkisini
   ve önceki deployment'a dönüşü planla.
4. PR #3'ü hazır incelemeye geçir; insan onayı ve başarılı kontrollerden sonra
   GitHub PR üzerinden main'e birleştir. Doğrudan main push önerilmez.
5. Birleşim sonrasında production sürümü, nonce/sağlık ve temel gönderim akışını doğrula.
6. Main'deki sürüm beta.9 kalabilir. `v0.2.0` kararlı etiketi ve latest-stable
   değişikliği ancak açık kararlı-sürüm kabul kriterleri tamamlanınca yapılmalı.

Bu turda main, PR taslak durumu, dal kuralları, production ve yayın değiştirilmedi.

## Takip düzeltmesi — yerel aday

İlk iki bulgu kaynakta düzeltildi. `web_urls.py`, onay ve açılış için ortak
kanonik ASCII authority üretiyor. UTS46 non-transitional IDNA, sharp-s/final sigma
kimliğini koruyor; belirsiz joiner/encoded-host/legacy sayısal IPv4 biçimleri
reddediliyor. IPv4 gömülü IPv6 adresleri tarayıcıdaki hex biçimiyle gösteriliyor.
Yol, sorgu ve fragment metni korunuyor. Hem Phone-to-PC hem ekran onayı ve gerçek
browser-open çağrısı bu doğrulamayı kullanıyor. Zaten httpx üzerinden kullanılan
idna 3.18 artık doğrudan sabitlenmiş bağımlılık; yeni paket kurulmadı.

Derleme komutu eski sürüm parametresini geçirmiyor. Paket sürümü
`scripts/release_version.ps1` aracılığıyla APP_VERSION'dan türetiliyor; açıkça
verilen uyuşmaz/eskimiş sürüm etiketi paketleme başlamadan reddediliyor.

TDD'de güvenlik testi eski kodda başarısızdı; düzeltilmiş kodda geçti. İlk tam
çalışmada 348/348 masaüstü testi ve 147/147 web testi/üretim derlemesi geçti.
Sekiz Unicode/IP/port örneği Node WHATWG çözümleyicisiyle çevrimdışı karşılaştırıldı.
Taze bağlamlı ayrı inceleme ajanı yerel farkta yeni bir engel bildirmedi.
Yeni test adayı `dist/candidate-url-identity-20261026/QR-Scanner.exe` olarak hazırlandı.
Son kodda tam masaüstü testleri tekrar 348/348 geçti. EXE'deki dört URL/onay
modülü çalışma kaynağıyla eşleşti, IDNA tabloları pakette bulundu ve EXE self-test
çıkış kodu 0 oldu. EXE SHA256:
`8D26C8DC14364138996106A286C029BD425CF2BC28EB22EEF16F103DF9C95226`.
Self-test sentetik QR okuma testidir; yeni EXE'nin gerçek telefonla kabulü yerine geçmez.
Bu düzeltmeler henüz yayımlanmış beta.9 EXE'sinde değildir. Dal kuralları, gerçek
cihaz ve dış inceleme eksikleri bu kod değişikliğiyle kapanmış sayılmaz.

## Son kontrol kapatma kaydı

Son çalışma: 348/348 masaüstü, 147/147 web testleri, ESLint ve TypeScript geçti.
Sekiz çevrimdışı WHATWG karşılaştırması, dört gömülü URL/onay modülü kaynak
eşleşmesi, IDNA tablo varlığı, pip check ve EXE self-test yeniden doğrulandı.
Bu sonuçlar yukarıda hash'i verilen yerel adayı kapsar.

| Madde | Durum / kapanış gereği |
| --- | --- |
| Unicode hedef/onay hatası | Kaynak ve test adayı düzeltildi; regresyon + ayrı ajan incelemesi tamam. |
| Yanlış paket sürümü | Kaynak düzeltildi; gerçek PowerShell sürüm çözümleme/reddetme testleri geçti. |
| Son aday yerel otomatik kontrolleri | Tamam, sonuçlar yukarıda. |
| Son aday uzak CI | Henüz yok: PR #3 head hâlâ 7922436; son yerel düzeltmeler commit/push edilmedi. Eski CI bu adaya atfedilmez. |
| GitHub main koruması | API yeniden protected=false döndürdü; ruleset listesi boş. Değişiklik için kullanıcı onayı ve inceleyici tercihi soruldu. |
| Son aday fiziksel telefon akışı | S24 ve iPhone 15 Plus için yeni EXE akışı/tarayıcı adları kullanıcıya soruldu; yanıt bekleniyor. |
| Temiz ikinci Windows ortamı | Ortam/kullanıcı sonucu bekleniyor. Get-Command kontrolünde adb/docker/psql/WindowsSandbox.exe bulunmadı; yeni araç/OS kurulmadı. |
| Dış insan protokol/kriptografi incelemesi | Sağlanmadı; ayrı ajan incelemesi yerine geçmez. |
| Canlı geçerli kimlikle çapraz cihaz/revocation | Güvenli test hesabı ve izole kayıt/temizleme planı sağlanmadan kullanıcı eşleşmeleri üzerinde çalıştırılmadı. Yerel regresyonlar geçti. |
| Main/prod değişikliği | Yapılmadı. |

Kontrol sonucu: yerel otomatik doğrulama tamam; tüm kararlı-sürüm kapıları
tamamlandı iddiası yok. Kalanlar yeni kod hatası keşfi değil, açıkça tanımlı
ortam/kanıt/yetki gereksinimleridir. Main'e sınırlı beta birleştirmesi ve kararlı
sürüm yayını için risk kabulü ayrı değerlendirilmelidir.

## Gerçek cihaz kabul güncellemesi

Kullanıcı son URL-kimliği test EXE'sinde eşleştirme → gönderme → kaldırma →
yeniden eşleştirme → çıkış akışının Samsung Internet ve iPhone 15 Plus/Safari'de
başarılı olduğunu ayrıca doğruladı. Bu iki tarayıcıdaki kullanıcı akış kontrolü
kapatıldı. İşletim sistemi/tarayıcı sürümleri, ayrı Chrome/kurulu PWA matrisi,
ikinci temiz Windows ortamı ve dış insan incelemesi bununla doğrulanmış sayılmaz.
