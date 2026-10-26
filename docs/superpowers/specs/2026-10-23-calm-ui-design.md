# Sakin araç — onaylanan A tasarımı

Kullanıcı 23 Ekim'de UI Designer incelemesindeki A yaklaşımını seçip uygulanmasını
istedi. Temel: `docs/ui-designer-review-2026-10-23.md`.

Amaç: mevcut lacivert/turkuaz kimliği, güvenlik kararlarını ve ekran akışlarını
koruyarak daha kısa, okunabilir, klavye ile kullanılabilir bir araç sunmak.

- Telefon: 28–36px ana başlık, kısa açıklama, kayıtlı PC/gerçek erişim durumu tek
  kartta; kamera ve görsel okuma işlemleri görünür. Yardım açılır alanda toplu.
- Eşleşmiş mobil sonuçta PC'ye gönder ilk ve görsel birincil; eşleşme yoksa veya
  masaüstündeyse normal bağlantı açma birincil. Teslimat bekleniyor/alındı/iptal
  davranışları ve tekrar gönderim koruması aynı kalır.
- Küçük metinde en az 4.5:1 kontrast; etkileşimli kontrollerde belirgin odak.
- Windows: native kontroller korunur. Metin sığması iyileştirilir; QR ekranlarının
  talimat, sayaç ve İptal/Geri eylemleri native kabukta sunulur. QR yalnız bellekte.
- Normal ok imleci korunur; crosshair yalnız alan seçiminde.
- Yeni bağımlılık, yeni kullanıcı özelliği, protokol değişikliği veya canlı yayın yok.

Ek onay: uygulama sırasında npm kritik Next.js uyarısı doğrulandı. Kullanıcı aynı
çalışmada Next.js 16.4.3 güvenlik yamasını ve yeniden test edilmesini açıkça onayladı.
Yeni bağımlılık eklenmeden Next ve eşleşen eslint-config-next sürümü güncellenir.

Alternatif B (tek yeniden boyutlanabilir çalışma yüzeyi) kullanıcı tarafından
seçilmedi. Sabit pencereyi kaldırmak yerine mevcut akışta metin ölçümü kullanmak
bu uygulamanın sınırlı kapsam tercihidir. TR/EN, dar/geniş web görünümü, klavye,
çevrimdışı kayıt ve teslimat kilitleri doğrulanır; fiziksel ekran okuyucu ve
Windows %200 testi yapılmadıysa ayrıca belirtilir.
