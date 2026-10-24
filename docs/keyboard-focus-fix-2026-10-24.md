# Native klavye odağı düzeltmesi — 24 Ekim 2026

Kullanıcı ana menüde pencereyi seçtikten sonra da Tab/Enter işlemlerinin ve odak
işaretinin çalışmadığını bildirdi. Önceki doğrudan `window.key()` testleri gerçek
Windows aktivasyonu ve odak işaretinin gizlenmesi durumlarını kapsamıyordu.

## Yeniden üretim

- Eski test EXE'sinde UIA ilk okumada seçili düğmeyi, pencere aktivasyonu/Enter
  sonrasında ise ana pencerenin kendisini odakta gösterdi.
- Yeni native regresyon: seçili son düğmeden SetFocus(root) sonrası focused_name
  None oldu; gerçek WM_SETFOCUS sırasında alt kontrole dönüş yoktu.
- Native UIS_HIDEFOCUS etkinleştirildikten sonra Tab ile gezinme bu bayrağı
  kaldırmıyordu; seçim değişse bile odak çerçevesi görünmeyebiliyordu.
- Gerçek GetMessage döngüsüne gönderilen Tab/Enter olayları, reaktivasyon sonrası
  beklenen ikinci düğme yerine ilk düğmeyi çalıştırdı.
- Üç testin de eski kodda beklenen şekilde başarısız olduğu gözlendi.

## Düzeltme ve kanıt

- Son seçili kontrol hatırlanır. Pencere yeniden odak alınca etkin son kontrole,
  bu kontrol yok/kapalı ise ilk etkin kontrole dönüş yapılır.
- Odak taşınırken native klavye/erişim tuşu işaretlerinin gizlenmesi kaldırılır.
- Standart Win32 düğmeleri ve mevcut güvenlik onayları korunur.
- 17 native kontrol testi ve tam 332 masaüstü testi geçti.
- Gerçek Windows klavye girdisiyle bağımsız, aynı home/settings factory'lerini
  kullanan test penceresinde Tab sırası ve noktalı odak çerçevesi görüldü;
  Enter ile Ayarlar açıldı, Esc ile ana menüye dönüldü.
- Bu test penceresi gerçek eşleşme deposuna erişmedi ve Windows başlangıç tercihi
  değiştirmedi. Kullanıcının asıl uygulaması kapatılmadı.
- Görsel kanıt: build/tls-fix-20261024/keyboard-settings-proof.png.

PWA kaynakları değiştirilmedi; telefon testinde aynı ed884af kaynaklı HTTPS
önizlemesi kullanılabilir. Native test EXE'si ayrıca paketlenir. Kullanıcının yeni
EXE'de fiziksel klavye kabulü, %200 ölçek ve ekran okuyucu testi tamamlanmış sayılmaz.
