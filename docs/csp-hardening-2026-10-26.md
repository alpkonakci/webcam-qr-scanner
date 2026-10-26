# Vercel/Next CSP sıkılaştırması — 26 Ekim 2026

## Değişiklik

- Üretim `script-src` politikasından `unsafe-inline` kaldırıldı.
- Sayfa proxy'si her istekte 16 rastgele bayttan yeni nonce üretip gelen nonce/CSP
  başlıklarını değiştiriyor; aynı politika hem Next renderer'a hem yanıta veriliyor.
- Ana sayfa `connection()` ile istek başına render ediliyor. HTML `private,
  no-store`; nonce'li HTML CDN'de ortak önbelleğe alınmamalı.
- Statik varlıklar, relay API ve sağlık uçları proxy dışında. Temel güvenlik
  başlıkları next.config üzerinden korunuyor.
- Yeni bağımlılık yok. IndexedDB ve eşleşmeler değiştirilmedi.
- `style-src 'unsafe-inline'` görsel kırpmanın dinamik React stilleri için kaldı;
  JavaScript izniyle aynı şey değildir. `unsafe-eval` yalnız geliştirme modunda.

## Kanıt

Mevcut politika için yeni test `script-src 'unsafe-inline'` nedeniyle başarısız
oldu. Nonce uygulaması sonrası testler geçti. Üretim Next derlemesi, ESLint ve
TypeScript kontrolleri başarılı. Son web regresyon çalışması: **147/147 geçti**.

Yerel üretim sunucusu: http://127.0.0.1:3114 (Next dev değil).
`tests/browser-csp-smoke.mjs` gerçek Chromium ile:

- Next betiklerinin yanıt nonce'sini taşıdığını ve sayfanın etkileşimli açıldığını;
- nonce'siz/yanlış nonce'li sentetik betiklerin CSP tarafından engellendiğini,
  doğru nonce'linin çalıştığını;
- yenilemede nonce'nin değiştiğini;
- Ayarlar → Geri, aynı görsel QR'ı iki kez okuma ve worker çalışmasını;
- sentetik kamera açma/ESC ile kapatma, sayfa hatası ve mobil taşma olmamasını
  doğruladı.

Bu yerel Chromium testi, gerçek Safari/Samsung cihazı veya canlı PC teslimatı
değildir. Gönderim/kimlik doğrulama regresyonları otomatik web testlerinde kaldı.

## Kapsam ve kalanlar

Değişiklik yerel Next/Vercel dağıtım adayıdır. Canlı site, GitHub yayını ve beta.8
paketi güncellenmedi. Yeni HTTPS önizlemesinde gerçek iPhone/Samsung akışı
doğrulanmadan production'a taşınmamalı. Tarihsel Cloudflare/vinext Worker'ın
ayrı CSP başlıkları bu değişiklikte değiştirilmedi veya sıkılaştırılmış sayılmadı.
Önceki incelemedeki hız limiti kapsamı ve bağımsız dış protokol denetimi açık.
