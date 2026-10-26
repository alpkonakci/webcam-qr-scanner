# Ana menü → Ayarlar geçişi — 24 Ekim 2026

Klavye düzeltmeli adayda kullanıcı Tab/Enter'ın çalıştığını doğruladı; Ayarlar'a
geçince uygulamanın arkaya düştüğünü bildirdi. Bu ayrı kabul sorunu açık kaldı.

Eski akış ana menü UI sürecini kapatıyor, dönüş kodunu arka plandaki tepsi
kontrolcüsüne iletiyor ve Ayarlar'ı yeni bir süreçte başlatıyordu. Windows'un
[ön plan kuralları](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-setforegroundwindow)
bu tür süreçler arası geçişte aktivasyon isteğinin reddedilmesine izin verir.
Bu mekanizma bildirilen davranışla uyumludur; eski EXE'nin reddedilen Win32
dönüş kodu ayrıca kaydedilmediği için tek başına doğrudan API kanıtı sayılmaz.

## Değişiklik

- Ana menüden Ayarlar aynı UI sürecinde açılır; Geri/Esc sonrasında aynı süreç
  ana menüyü tekrar gösterir. Kamera, tarama, çıkış ve diğer kontrol kodları korunur.
- UI süreci kontrolü tepsiye döndürdüğünde dil ve menü yenilenir; arka plana
  gizleme tercihi uygulamadan tamamen çıkıştan ayrı kalır.
- Pencereyi sürekli üstte tutma, genel foreground izni, sahte tuş, zamanlayıcıyla
  tekrar tekrar odak çalma veya Windows ayarı değiştirme eklenmedi.
- Tepsi menüsünden doğrudan açılan bağımsız Ayarlar yolu bu değişiklikte yeniden
  tasarlanmadı; düzeltmenin cihaz kabulü ana menü → Ayarlar → Geri kapsamındadır.

## Doğrulama

- Yeni launcher testleri eski akışın Ayarlar'dan dönmeden 29 koduyla çıkmasını
  yakaladı; tercih yenileme regresyonu da eski kodda başarısız oldu.
- Düzeltme sonrası tam 335 masaüstü testi başarılı.
- Gerçek `launcher.py --home-process` akışında Windows klavyesiyle Ayarlar'a
  geçildi. Yeni pencereye ayrıca activate komutu verilmeden Settings and about
  görünür/odakta ve Language kontrolü seçili görüldü. Esc ile ana menü geri geldi.
- Ekran kanıtı: build/keyboard-fix-20261024/settings-foreground-proof.png.
- Yeniden derlenen ham EXE'nin TLS + QR `--self-test` sonucu çıkış 0.
- Telefon sitesi ve eşleşme protokolü değiştirilmedi; mevcut HTTPS preview kalır.

Yeni paketlenmiş EXE'de kullanıcının Ayarlar/Geri geçişini tekrar doğrulaması
gereklidir. %200 ölçek ve fiziksel ekran okuyucu kabulü henüz tamamlanmadı.
