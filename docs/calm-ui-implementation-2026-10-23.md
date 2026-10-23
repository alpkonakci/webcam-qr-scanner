# A yaklaşımı uygulama sonucu — 23 Ekim 2026

Agency Agents UI Designer incelemesi ve kullanıcının A seçimi üzerine uygulandı.
Değişiklikler yerel kaynak ve test EXE'sindedir; canlı sürüm değiştirilmedi.

## Uygulananlar

- Telefon başlığı kısaltıldı (375px görünümde 28px). Kamera/görsel okuma daha üstte.
- Kayıtlı PC ve doğrulanmış erişim durumu tek kartta; geri dönüş açıklamaları aynı
  kartın açılır yardımında. Kayıtlı eşleşme çevrimiçi kanıtı olarak sunulmuyor.
- Eşleşmiş mobil sonuçta PC'ye gönder ilk/birincil, telefonda aç ikincil. Eşleşme
  yoksa ve masaüstünde bağlantı açma birincil kalır. Beş teslimat kilidi korunur.
- Küçük eylem açıklamaları daha açık renkte. Özel düğme stillerindeki odak
  çakışmaları giderildi; gerçek klavye kontrolünde 3px turkuaz halka doğrulandı.
- Windows eşleştirme/geri dönüş QR'ları bellekte bitmap olarak gerçek native
  pencerede; talimat, sayaç ve İptal/Geri kontrolleri native. QR metni kontrol adına
  veya dosyaya yazılmıyor. Olay önceliği ve100ms denetim korunuyor.
- Native etiketler font ölçümüyle sığdırılıyor. Oluşturma hatasında pencere/GDI
  kaynakları kapanıyor; emoji içeren metin tam UTF-16 uzunluğuyla ölçülüyor.

## Doğrulama

| Kontrol | Sonuç |
| --- | --- |
| Tam web testleri ve üretim derlemesi | 145/145 başarılı |
| ESLint / TypeScript | Başarılı |
| Tam masaüstü testleri | 326/326 başarılı |
| Native kaynak temizliği ve emoji regresyonu | Kırmızı → yeşil doğrulandı |
| 375×812 TR /1440×900 EN | Yatay taşma yok; ana eylemler görünür |
| Klavyede odak | Görsel oku düğmesinde 3px solid turkuaz/4px aralık |
| Bağımsız kod incelemesi | Bir kaynak temizleme bulgusu ve Unicode ölçüm bulgusu giderildi |
| Yerel PyInstaller derlemesi / EXE self-test | Başarılı / çıkış0 |

Derleme sırasında npm, Next16.4.0 için kritik advisory bildirdi. Kullanıcı aynı
çalışmada güvenlik yamasını açıkça onayladı. Next ve eslint-config-next16.4.3'e
geçildi; kilit dosyası ve lisans envanteri yenilendi. Son `npm audit --json`
0 bilinen açık bildirdi; bu genel bir güvenlik sertifikası değildir.

## Yerel çıktılar ve sınırlar

Test EXE: `dist/calm-ui-20261023/QR-Scanner.exe`.
SHA256: `D1A81BFECFD4EBFB57A2D236131C5ECDC358C51CA5F92B372C60688607BDA245`.
Ekran görüntüleri ve test günlükleri: `build/calm-ui-20261023/`.
Bu EXE yerel test çıktısıdır; henüz kaynak arşivi/lisanslarıyla yeni yayın ZIP'i
hazırlanmadı ve GitHub/Vercel dağıtımı yapılmadı. Eski paketler korunuyor.

Sabit native pencere davranışı korundu; sınırsız yeniden boyutlandırma B yaklaşımı
olurdu. Fiziksel %200 Windows ölçeği, ekran okuyucuda sesli çıktı ve bu yeni QR
kabuğunun gerçek telefondan okunması ayrıca kabul testi gerektirir. Önceki adayın
iPhone testi bu yeni EXE için otomatik olarak geçerli sayılmadı.
