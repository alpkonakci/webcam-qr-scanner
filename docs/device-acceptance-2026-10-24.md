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

Önceki ve güncel önizleme adreslerinin farklı olması, web tarayıcısının aynı-origin
eşleştirme kontrolünde uyuşmazlık ihtimalini doğurdu. Güncel adreste tekrar başarılı
oldu; eski sekmenin kesin kök neden olduğu bağımsız olarak gözlenmedi. Bu akış için
güvenlik kuralı gevşetilmedi, ürün kodu değiştirilmedi.

## Henüz tamamlanmış sayılmayanlar

- Kullanıcının bildirdiği ana menü Tab/Enter sorununun odak/gerçek tuş girdisi düzeyinde teşhisi ve yeniden kabulü. Bu açıkken yayın kabulü verilmez.
- Fiziksel Windows %200 ölçeğinde ana menü/ayarlar/telefon listesi/QR kabuğu.
- Fiziksel ekran okuyucuda kontrol adları, odak ve sesli bildirim kabulü.
- Bu adaya ait Android ve tarayıcı–kurulu PWA depolama geçişi kabulü.
- Kaldırma işleminin API/kimlik bilgisi düzeyinde bağımsız canlı güvenlik testi;
  yukarıdaki cihaz sonucu yalnız normal kullanıcı arayüzü akışını doğrular.

Main birleştirme, production dağıtımı veya stabil GitHub yayını yapılmadı.
Bu kayıt, önceki adayın eksik TLS dosyası nedeniyle artık kabul edilmeyen
paketini değil, yukarıdaki hash'e sahip düzeltilmiş adayı kapsar.

Korumalı önizlemenin .cmd başlatıcısı bypass anahtarını yalnız süreç ortamında
tutar ve her yeni çalıştırmada yeniden ister. Bu test erişimi, kalıcı eşleşme
deposundan ayrıdır; tekrar anahtar istenmesi eşleşmenin kaybolduğu anlamına gelmez.
Production kullanımına bu yardımcı başlatıcı veya bypass istemi eklenmedi.
