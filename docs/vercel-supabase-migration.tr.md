# Vercel + Supabase geçiş planı

Bu belge `codex/vercel-supabase` dalındaki kesintisiz geçişi anlatır. Çalışan
Sites/Cloudflare yayını, yeni sistem gerçek cihazla doğrulanana kadar açık
kalır. Kaynak dosyaların bu dalda değişmesi mevcut üretim dağıtımını kapatmaz.

## Hedef mimari

```mermaid
flowchart LR
    Phone["Telefon PWA\nVercel"] -->|"WQRS/1 şifreli zarf"| API["Next.js API\nVercel"]
    API -->|"Yalnızca ciphertext + yönlendirme kimliği"| DB["Postgres\nSupabase"]
    DB -->|"Özel cihaz kanalına wake-up"| RT["Supabase Realtime"]
    RT --> PC["Windows alıcısı"]
    PC -->|"Zarfı al + şifreli ACK"| API
    PC -. "5 sn kurtarma sorgusu" .-> API
```

- Vercel, PWA'yı ve mevcut `/v1` HTTP sözleşmesini barındırır.
- Supabase Postgres yalnızca token özetleri, kısa ömürlü yönlendirme verileri ve
  uçtan uca şifreli zarfları tutar.
- Supabase Realtime birincil bildirim yoludur. Bildirim yalnızca rastgele
  `delivery_id` taşır; URL veya şifreli zarf Realtime mesajına konmaz.
- Masaüstü, Realtime bağlantısı yokken beş saniyede bir bekleyen teslimatı
  kontrol eder. Bağlantı sağlıklıyken yalnızca bildirim geldiğinde ve 60
  saniyelik güvenlik eşitlemesinde sorgu yapılır; polling ana taşıma yolu değildir.
- PC uygulaması dışarıya port açmaz; tüm bağlantılar dışarı doğrudur.

## Bu dalda tamamlanan ilk dilim

- PWA, `vinext` yerine standart `next dev`, `next build` ve `next start`
  komutlarıyla derleniyor.
- Vercel güvenlik başlıkları Next.js yapılandırmasına taşındı.
- Supabase Postgres şeması ve sürümlü migration eklendi.
- Relay tablolarında RLS açık; tarayıcı ve masaüstü tablolara doğrudan erişemez.
- Vercel API, Supabase'in yeni `sb_secret_...` anahtarını yalnızca `apikey`
  başlığında ve sunucu tarafında kullanıyor.
- Masaüstü, e-posta/telefon istemeyen anonim Supabase Auth oturumuyla yalnızca
  kendi özel Realtime cihaz kanalına bağlanıyor.
- Auth erişim ve yenileme token'ları Windows'ta mevcut DPAPI korumalı dosyanın
  içinde saklanıyor ve yenileme sırasında döndürülüyor.
- Eski localhost WebSocket relay'i ve mevcut Sites/D1 HTTP polling yolu geriye
  uyumlu kalıyor.
- Realtime kesilirse beş saniyelik kurtarma sorgusu teslimatı sürdürüyor.

## Gizlilik sınırı

Uygulama GPS/konum, mikrofon, kişi listesi, fotoğraf arşivi veya yerel ağ izni
istemez. QR kareleri cihazda çözülür ve yüklenmez. Açık URL Vercel veya
Supabase'e gönderilmez; yalnızca WQRS/1 ciphertext zarfı gider.

Supabase anonim oturumu bir kullanıcı hesabı ekranı oluşturmaz ve e-posta,
telefon veya profil istemez. Buna rağmen Vercel ve Supabase, kötüye kullanım ve
altyapı güvenliği için bağlantı IP'si gibi standart ağ metadatasını kendi
politikaları kapsamında işleyebilir. Uygulama, hız sınırı için ham IP yerine
sunucu sırrıyla özetlenmiş kısa ömürlü bir anahtar saklar. Uygulama loglarına
Authorization başlığı, token, URL, QR görüntüsü veya ciphertext gövdesi yazılmaz.

## Canlı geçiş sırası

1. Supabase projesi oluşturulur ve anonim giriş etkinleştirilir.
2. `supabase/migrations/202608030001_phone_to_pc_relay.sql` SQL Editor veya CLI
   ile uygulanır.
3. Realtime ayarında private channel kullanımı korunur; public kanal gerekmez.
4. GitHub deposu Vercel'e bağlanır ve Root Directory olarak `pwa` seçilir.
5. Vercel Production ortamına şu değerler girilir:
   `SUPABASE_URL`, `SUPABASE_PUBLISHABLE_KEY`, `SUPABASE_SECRET_KEY` ve en az
   32 karakterlik rastgele `RELAY_RATE_LIMIT_PEPPER`.
6. Önizleme dağıtımında `/healthz`, PWA kamera yaşam döngüsü, eşleştirme,
   Realtime teslimi, ACK, replay reddi ve beş saniyelik kurtarma yolu sınanır.
7. Sabit Production `.vercel.app` adresi seçilir. Preview URL eşleştirme için
   kullanılmaz.
8. Masaüstünün varsayılan public relay adresi bu sabit URL'ye alınır ve yeni EXE
   üretilir. Origin değiştiği için telefon bir kez yeniden eşleştirilir.
9. En az 48 saat iki sistem paralel tutulur. Yeni sistemin gerçek iPhone ve
   Android testleri geçince Sites/Cloudflare yayını kaldırılır ve eski D1
   kaynakları silinir.

## Gerekli sırlar

Gerçek değerler Git'e, README'ye, masaüstü EXE'ye veya PWA JavaScript paketine
konmaz. `SUPABASE_SECRET_KEY` yalnızca Vercel sunucu ortamında bulunur.
`SUPABASE_PUBLISHABLE_KEY` tasarımı gereği halka açıktır; veri erişimini RLS ve
anonim kullanıcı oturumu sınırlar. Yerel geliştirme için `.env.example`
`.env.local` adıyla kopyalanır; `.env.local` Git tarafından yok sayılır.

## Geri dönüş

Canlı test başarısız olursa masaüstünün varsayılan relay adresi eski Sites
origin'inde bırakılır. Bu geçiş dalı `main` ile birleştirilmediği ve eski dağıtım
kaldırılmadığı sürece kullanıcı akışı etkilenmez. Supabase tablolarını silmek
veya Sites yayınını kapatmak, yalnızca yeni Production testi tamamlandıktan
sonra yapılır.
