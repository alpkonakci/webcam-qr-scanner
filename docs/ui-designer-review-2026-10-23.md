# Agency Agents / UI Designer incelemesi — 23 Ekim 2026

Kaynak: `9b79975`; Agency Agents **UI Designer** ajanıyla salt okunur kod
incelemesi ve ana ajan tarafından yerel PWA ekranı gözlemi. Windows birincil
yolu `accessible_desktop.py` / `accessible_controls.py`; OpenCV ana menü çizimi
yalnız yedek yol. Fiziksel Windows DPI/ekran okuyucu testi yapılmadı. Ürün
dosyaları değiştirilmedi, yayın yapılmadı. Bu rapor bir uygulama tasarımı onayı
veya erişilebilirlik uygunluk sertifikası değildir.

## Bulgular ve önerilen öncelik

| Öncelik | Kanıt | Öneri ve gerekçe |
| --- | --- | --- |
| P1 | `globals.css`: `--quiet:#6f8098` / panel `#0e1b2d`; eylem açıklamaları küçük metin. Hesaplanan kontrast yaklaşık 4.30:1. | Açıklamalarda mevcut `--muted` rengini kullan. Daha rahat okuma sağlar; normal metin için 4.5:1 hedefi kontrol edilmeli. |
| P1 | `.result-secondary-enabled:focus-visible` ve `.result-text-button:focus-visible` özel kuralları `outline:none` içeriyor; genel düğme kuralından daha güçlü. | Düğme varyantlarında ortak, belirgin odak halkası. Hover ve klavye odağını ayrı tanımla. |
| P1 | `accessible_controls.py`: sabit boyut; `accessible_desktop.py`: piksel tabanlı etiket/düğme sınırları. | TR/EN ve yüksek ölçeklemede metin sığmasını doğrula; içerik ölçümü, minimum boyut ve gerektiğinde kaydırma uygula. Kırpılma şu aşamada risk, görsel olarak kanıtlanmış hata değil. |
| P1 | `pairing_ui.py`, `phone_scanner_ui.py`: QR pencereleri OpenCV çizimi; ana menünün native kontrol altyapısını kullanmıyor. | QR görseli korunarak talimat/sayaç/Geri/İptal gerçek kontrollere taşınmalı. Tab/Enter ve UIA tutarlılığı sağlanır. |
| P2 | `PwaHome.tsx` hazır rozeti, `PcConnectionBadge` bağlantı kartı, geri dönüş paneli aynı kayıt bilgisini tekrarlıyor. | Tek durum kartı: kayıtlı PC adı + doğrulanmış erişim durumu. Yardımı açılır alanda birleştir; daha az tekrar ve daha az kaydırma. |
| P2 | `QrResultView.tsx`: telefonda açma eylemi dolu turkuaz; PC gönderimi ikincil. | Mobilde eşleşme varsa PC'ye gönder görsel birincil olabilir. Bu kullanıcı önceliği kararıdır; eşleşme yoksa telefonda açma korunmalı. Onay ve belirsiz teslimat mantığı değişmemeli. |
| P2 | Yerel ekranda büyük ana başlık ve giriş açıklaması eylemlerden önce geniş alan kullanıyor. | Başlığı yaklaşık 28–36px, giriş metnini tek kısa açıklama yap. Tarama eylemi ilk bakışta daha kolay bulunur. 375/390px görünümde ölçülmeli. |
| P3 | Native ana menüde tüm eylemler benzer ağırlıkta. | Tarama üst grup; telefon/QR üretme ikinci grup; ayarlar/çıkış sakin alt grup. Owner-draw yerine mevcut erişilebilir kontroller korunmalı. |

Yerel PWA gözleminde otomatik odaklanan başlığın çevresinde tarayıcı odak
çerçevesi de görüldü. Başlık odağı ekran okuyucu için korunurken görsel odak
tasarımı, etkileşimli düğmelerin odak göstergesinden ayrı ele alınmalı.

## Tasarım yönleri — seçim için öneri

**A / Sakin araç (önerilen):** mevcut lacivert/turkuaz kimlik ve ekran akışlarını
koru. Kontrast/odak, kısa başlık, tek bağlantı kartı ve eylem hiyerarşisini
iyileştir. Native QR kabuğu ve DPI yerleşimi ayrı kontrollü adımlarda yapılır.
Kullanıcının alışkanlığı ve mevcut güvenlik davranışları daha az etkilenir.

**B / Tek çalışma yüzeyi:** masaüstünde yeniden boyutlanabilir tek pencere,
içinde gezinme; telefonda aynı tasarım dili. Daha kapsamlı tutarlılık sağlar,
ancak pencere yaşam döngüsü, odak geri dönüşü ve gezinme değişir; ayrı görsel
prototip ve daha geniş kabul testi gerekir.

Önerilen A yaklaşımında hedef telefon düzeni: kısa başlık → kayıtlı PC ve gerçek
erişim durumu → QR oku (birincil) → görselden oku (ikincil) → açılır yardım ve
gizlilik. Kayıtlı eşleşme hiçbir zaman tek başına çevrimiçi kanıtı değildir.

Uygulama öncesi tasarım yönü seçilmeli. Kabul: TR/EN, 375/390px ve geniş ekran,
200% metin/Windows ölçeği, görünür klavye odağı, yerel kontrol adları, kayıtlı ama
çevrimdışı PC ve teslimatın belirsiz/alındı durumlarının korunması.
