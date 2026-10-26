# Gerçek cihaz kabul kaydı — 24 Ekim 2026

Test adayı: `ed884af09276c2b323a96975bcdd063be6b43ab4`.
EXE SHA256: `63E097D88CEB789FC7F6CB61A3D2DCD487D08050F204AD75F61584CA89CA26E3`.
HTTPS: https://qrwebcam-7vb0bftwl-alpkonakcis-projects.vercel.app/
Ortam: kullanıcının Windows PC'si ve iPhone/Safari.

Bu tablo kullanıcının bu sohbet içindeki gerçek cihaz bildirimlerine dayanır;
ajanın telefonda bağımsız çalıştırdığı bir otomasyon sonucu değildir.

| Kontrol | Kanıt / sonuç |
| --- | --- |
| Yeni TLS düzeltmeli EXE ile eşleştirme | Kullanıcı eşleştiğini bildirdi. |
| Bağlantı kontrolü | Paylaşılan ekran görüntüsünde Pairing saved: Alp ve PC reachable, son kontrol 04:43:13 göründü. |
| Telefondan gönderme ve PC'de onay/açılış | Kullanıcı her ikisini doğruladı. |
| Aynı QR'ı tekrar gönderme | Kullanıcı bağlantının yeniden açıldığını doğruladı. |
| Kaldırma sonrası telefon davranışı | Kullanıcı Connect to a PC / Scan the pairing QR shown on your PC ekranını bildirdi; gönderim için yeniden eşleştirme isteniyor. |
| Yeniden eşleştirme ve gönderme | Kullanıcı eşleştiğini ve açıldığını doğruladı. |
| Telefon sitesinin içindeki kamera ile PC eşleştirme QR'ını okuma | Güncel önizleme açıldıktan sonra kullanıcı çalıştığını bildirdi. |
| Üst X ile kapatma seçenekleri | Kullanıcı arka planda kal / tamamen çık seçiminin geldiğini doğruladı. |
| Tamamen çıkma | Kullanıcı tepsi simgesinin kaybolduğunu ve donmadan kapandığını doğruladı. |
| Aynı .cmd test başlatıcısıyla yeniden açma | Kullanıcı geçici bypass anahtarını tekrar girdikten sonra eşleşmiş telefonun korunduğunu doğruladı. |
| Gerçek klavyede Tab/Enter ile ana menü/ayarlar | Kullanıcı hiçbir işlemin çalışmadığını bildirdi. Başarısız/açık; otomatik doğrudan tuş işleyici testleri gerçek cihaz kabulü yerine sayılmıyor. |
| Klavye düzeltmeli 26869e8 adayı | Kullanıcı Tab ve Enter'ın çalıştığını doğruladı; Ayarlar'a geçerken uygulamanın arkaya düştüğünü bildirdi. Bu ayrı geçiş sorunu son adayda yeniden kabul bekliyor. |

Önceki ve güncel önizleme adreslerinin farklı olması, web tarayıcısının aynı-origin
eşleştirme kontrolünde uyuşmazlık ihtimalini doğurdu. Güncel adreste tekrar başarılı
oldu; eski sekmenin kesin kök neden olduğu bağımsız olarak gözlenmedi. Bu akış için
güvenlik kuralı gevşetilmedi, ürün kodu değiştirilmedi.

## Sonraki aday: 2c0e698

Aday: `2c0e6988ab04ffa6952b5b8715e9639d2105e5cf`.
EXE SHA256: `1ABCBA95EE9B9F52BD616BFD040286754A850D3D36E3D1F4EA14AA6B08155DC0`.
Kullanıcı bu adayda Ayarlar → Geri geçişinde pencerelerin önde kaldığını doğruladı.

Kullanıcı ayrıca %200 ölçekte ana menü kontrollerinin, Ayarlar/Geri'nin ve
eşleştirme QR'ı/İptal'in tamamen göründüğünü; kesilme veya üst üste binme olmadığını
bildirdi. Paylaşılan görsellerde ana menü, görünür klavye odak çerçevesi, eşleştirme
penceresi, %200 ölçek ve 2560×1600 çözünürlük seçimi görüldü. Görünen uygulama dili
İngilizceydi. QR içeriği çözülmedi veya kaydedilmedi.

Bu, bu cihaz/ekran düzeninde kullanıcı kabulüdür; tüm monitör/çözünürlük/dil
kombinasyonlarının otomatik olarak geçtiği anlamına gelmez.

Kullanıcı Windows Ekran Okuyucusu ile ana menüde Tab gezinmesinde kontrol adlarının,
Ayarlar'daki dil seçimi, Windows başlangıç tercihi ve Geri kontrolünün tamamının
Türkçe okunabildiğini bildirdi. Bu, temel ad/rol ve gezinme kullanıcı kabulüdür;
ajan ses çıktısını bağımsız dinlemedi. Her hata durumu, canlı bağlantı/teslimat
duyurusu veya başka ekran okuyucu kombinasyonu bu sonuçla doğrulanmış sayılmaz.

## Android ve bağlantı kurtarma — 24–25 Ekim 2026

Kullanıcı Samsung Galaxy S24 FE'de Samsung Internet ile eşleştirme, QR okuma ve
PC'ye gönderimin çalıştığını bildirdi. Tarayıcı kapatılıp açıldığında eşleşme
korundu. Samsung Internet'ten ana ekrana eklenen simge üzerinden açıp gönderme de
kullanıcı tarafından başarılı olarak bildirildi. Kurulumun bağımsız PWA mı yoksa
tarayıcı kısayolu mu olduğu teknik olarak ölçülmedi; sonuç ana ekran simgesiyle
kullanım kabulüdür, tüm kurulu PWA depolama biçimlerine genellenmez.

Chrome'da eşleşme görünmemesi ilk başta kayıt kaybı şüphesi doğurdu; kullanıcı
eşleştirmenin varsayılan Samsung Internet'te açıldığını açıkladı. Bu iki farklı
tarayıcının aynı kaydı paylaşması beklenmediğinden Chrome bulgusu tek başına kayıt
kaybı kanıtı değildir. Aynı HTTPS önizleme alan adı kullanıcı tarafından doğrulandı.

25 Ekim'deki bağlantı kesme/geri getirme denemesinde telefon “PC not reachable at
last check” gösterdi; kullanıcı bağlantı kontrolünün otomatik çalıştığını ve PC'nin
interneti geri geldikten sonra Send to PC'nin yeniden başlatma gerektirmeden
çalıştığını bildirdi. Kesinti süresi bağımsız ölçülmedi. Önceki tek “relay could not
be reached” penceresi bu denemede tekrarlanmadı; kesin kök nedeni belirlenmedi.

Bu sonuçlar kullanıcı bildirimidir; ajanın gerçek Android cihaz otomasyonu değildir.
Tarayıcı/sistem sürümü ve bağımsız kurulu mod ölçümü alınmadı.

## Henüz tamamlanmış sayılmayanlar

- %200 ölçekli telefon listesi, Türkçe ve farklı ekran düzenleri; yukarıdaki ana menü/Ayarlar/QR kabulünün dışındadır.
- Ekran okuyucuda hata durumları ve dinamik bağlantı/teslimat duyuruları; temel ana menü/Ayarlar kontrol adları ve Tab gezinmesi yukarıda kullanıcı tarafından doğrulandı.
- Chrome'da bağımsız eşleştirme/yeniden açma ve bağımsız kurulu PWA modu; Samsung Internet/ana ekran simgesi kabulü yukarıda kayıtlıdır.
- Kaldırma işleminin API/kimlik bilgisi düzeyinde bağımsız canlı güvenlik testi;
  yukarıdaki cihaz sonucu yalnız normal kullanıcı arayüzü akışını doğrular.

Main birleştirme, production dağıtımı veya stabil GitHub yayını yapılmadı.
Bu kayıt, önceki adayın eksik TLS dosyası nedeniyle artık kabul edilmeyen
paketini değil, yukarıdaki hash'e sahip düzeltilmiş adayı kapsar.

Korumalı önizlemenin .cmd başlatıcısı bypass anahtarını yalnız süreç ortamında
tutar ve her yeni çalıştırmada yeniden ister. Bu test erişimi, kalıcı eşleşme
deposundan ayrıdır; tekrar anahtar istenmesi eşleşmenin kaybolduğu anlamına gelmez.
Production kullanımına bu yardımcı başlatıcı veya bypass istemi eklenmedi.
