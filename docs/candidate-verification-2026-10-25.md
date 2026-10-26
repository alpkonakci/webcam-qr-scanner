# Aday doğrulaması — 25 Ekim 2026

Kaynak: `2c0e6988ab04ffa6952b5b8715e9639d2105e5cf`.
Bu çalışma doğrulama ve salt-okunur ajan incelemesidir; ürün kodu değiştirilmedi,
main birleştirme veya yayın yapılmadı. Cihaz sonuçları ayrı kabul kaydındadır.

## Yeni çalıştırılan kontroller

- `.venv/Scripts/python.exe -m unittest discover -s tests -q`: 335 test, OK.
- `npm run test`: Next.js 16.4.3 üretim derlemesi ve runtime sınırı geçti;
  sandbox içindeki üç yerel HTTP testi EACCES nedeniyle başarısız oldu.
  Aynı derleme çıktısıyla sandbox dışında
  `node --experimental-strip-types --test tests/*.test.mjs tests/*.test.mts`:
  145/145 geçti. Testler değiştirilmedi.
- `npm run lint`, `npm run typecheck`: çıkış 0.
- `npm audit --omit=dev`: 0 bilinen açık.
- `npm audit`: 6 etkilenen paket (4 orta, 2 yüksek); fast-uri, undici,
  miniflare, @cloudflare/vite-plugin, wrangler ve zod. Bu sonuç tüm araç zincirinin
  temiz olduğu anlamına gelmez. Otomatik `--force` uygulanmadı.
- `git diff --check`: çıkış 0.

## Paket bütünlüğü

Paket ajanının ayrı denetimi: 50 dondurulmuş proje modülü, 319 kaynak dosyası,
ZIP CRC, kaynak revizyonu, bildirimler ve üç upstream kaynak arşivi hash'i geçti.
Ham, ZIP içindeki ve çıkarılmış EXE birbirinin aynısıdır.

- EXE: `1ABCBA95EE9B9F52BD616BFD040286754A850D3D36E3D1F4EA14AA6B08155DC0`
- ZIP: `EE2C9F8B80C0237533ABFB9FBB088686C51AF40E57C1BBDE413D637EE6793EAA`

Orijinal katı doğrulayıcı, HEAD arşivinden oluşturulmuş geçici çalışma alanında
çeviri varlıklarının LF/CRLF farkında durdu. Varlıklar gerçek çalışma ağacıyla
bayt düzeyinde, HEAD ile satır sonları normalize edildiğinde eşleşir. Bu nedenle
orijinal doğrulayıcının eksiksiz geçtiği iddia edilmez. Bağımsız doğrulama komutu:
`.venv/Scripts/python.exe build/package_integrity_audit_20261025.py`.
Dağıtım lisans/kaynak denetimi `scripts/verify_distribution.py` ile ayrıca geçti.

## Yayını durduran güvenilirlik bulgusu

`bridge/receiver.py` içindeki `_poll_once`, `on_url` çağrısından önce teslim ACK
POST yanıtını bekler. `bridge/protocol.py` içindeki `decrypt_url_envelope` ise
bundan önce mesajı replay ledger'a kaydeder. ACK isteği/yanıtı kaybolursa PC onay
arayüzü açılmaz; aynı zarf tekrar geldiğinde replay olarak reddedilir.

İnceleme ajanı geçerli sentetik şifreli zarf ve ACK ReadTimeout ile yeniden üretti:

```text
Initial ACK failed; callback_count=0
Redelivery handled=False callback_count=0
post_events=['delivery_ack', 'delivery_error']
```

Bu senaryo mevcut yeşil testlerle yakalanmıyor. Düzeltme öncesinde ACK'nin sunucuda
işlenmeden başarısız olması, işlendikten sonra yanıtın kaybolması ve kalıcı replay
deposuyla yeniden bağlanma için regresyon testleri gerekir. Replay güvenliği
gevşetilmemelidir. Kullanıcının başarılı internet geri-gelme testi bu dar ACK
kesinti senaryosunun geçtiği anlamına gelmez.

## Sadelik ve sınırlar

İki son masaüstü odak/Ayarlar commit'inde gerekli bir refactor veya gereksiz katman
bulunmadı. Sırf temizlik için davranış değiştiren düzenleme yapılmadı.
Bağımsız canlı API yetkilendirme testi, tüm ekran okuyucu hata duyuruları ve
Chrome/bağımsız kurulu PWA kabulü tamamlanmış sayılmıyor. Tekil eski relay bağlantı
uyarısının kök nedeni henüz belirlenmedi.

Sonuç: mevcut kullanıcı akışları ve otomatik kontroller başarılı olsa da ACK kaybı
bulgusu giderilmeden aday yayına hazır olarak onaylanmadı.

## Takip: ACK kaybı düzeltmesi (kaynak kod)

`bridge/receiver.py` içinde HTTP ACK taşıma hatası ve WebSocket ACK gönderme
hatasında, önceden doğrulanmış mesaj bir kez yerel onay callback'ine aktarılıyor;
ardından hata mevcut yeniden bağlanma akışına bırakılıyor. Replay deposu,
şifreleme ve protokol değiştirilmedi. Açık HTTP 401/403/404/503 yanıtları callback
açmadan hata vermeye devam ediyor; bilinmeyen taşıma sonucu ile açık red farklıdır.

- Kalıcı replay deposuyla ACK'nin sunucuda işlenmesinden önce/sonra yanıt kaybı:
  düzeltmeden önce iki alt durum da beklenen callback eksikliğiyle başarısız oldu.
- WebSocket gönderme kaybı: düzeltmeden önce aynı callback eksikliğiyle başarısız oldu.
- Düzeltmeden sonra hedefli 20 test geçti.
- Tam masaüstü testi: 338 test, 15.800 saniye, OK.
- Salt-okunur bağımsız ajan diff incelemesinde somut güvenlik/doğruluk sorunu bulmadı.

Sınırlar: süreç replay kaydı ile callback arasında çökerse kalıcı teslim kuyruğu
garantisi yoktur. Taşıma hatası nedeniyle alınamayan yanıtın yetki reddi içerip
içermediği bilinemez; yalnız gözlenen açık HTTP reddi bastırılır. ACK kaybında
telefondaki teslim sonucu hâlâ belirsiz kalabilir. Yerel callback kullanıcı onayını
beklerken yeniden bağlanma da bekler; izlenmeyen arka plan görevleri eklenmedi.

Bu düzeltme henüz yeni EXE'ye paketlenmedi ve yayımlanmadı. Yukarıdaki paket
hash'leri önceki adayı tanımlar; yeni kaynak kodu kapsamaz. Geliştirme araçlarındaki
altı güvenlik uyarısı bu dar düzeltmede değiştirilmedi.

## Takip: geliştirme bağımlılıklarının güvenlik yamaları

Aynı gün sonraki bağımlılık düzeltmesinde altı npm uyarısının kaynakları giderildi:

| Alt bağımlılık | Önce | Sonra |
| --- | --- | --- |
| fast-uri | 3.1.8 | 3.1.9 |
| undici | 7.29.1 | 7.30.1 |
| zod | 4.6.5 | 4.6.7 |

Kilit dosyasında yalnız bu üç paket değişti. fast-uri ve zod üst paketlerin mevcut
uyumlu sürüm aralıklarında güncellendi. Miniflare eski undici sürümünü tam olarak
sabitlediği için yalnız `miniflare -> undici` zincirine 7.30.1 override eklendi;
genel bir undici override, araç silme veya ana sürüm düşürme yapılmadı.
Miniflare'ın 5.20261019.2-beta sürümü de sorgu anında 7.29.1 istediği için araç
zincirini güncellemek tek başına yeterli değildi. Üst paket yamalı undici'ye geçtiğinde
bu dar override kaldırılıp aynı uyumluluk kontrolleri yeniden çalıştırılmalıdır.

Yama referansları:
- [Undici güvenlik duyurusu](https://github.com/nodejs/undici/security/advisories/GHSA-xjj6-f33q-929c)
- [fast-uri güvenlik duyurusu](https://github.com/fastify/fast-uri/security/advisories/GHSA-w74x-v6f9-j3xg)
- [Zod npm audit duyurusu](https://github.com/advisories/GHSA-mrhx-c7xc-m3w5)

Temiz `npm ci --ignore-scripts` kurulumundan sonra yeni kontroller:
- `npm test`: üretim derlemesi ve 145/145 web testi geçti; gerçek Miniflare/D1
  entegrasyon testi dahil. Runtime sınırı 42 kaynak/6 Next izi için geçti.
- `npm run lint` ve `npm run typecheck`: çıkış 0.
- `npm audit` ve `npm audit --omit=dev`: her ikisinde 0 bilinen açık.

Uyarılar bastırılmadı; denetim seviyesi değiştirilmedi. Bu sonuç tarama anındaki
bilinen npm açıkları içindir, tüm sistemin güvenlik sertifikası değildir.
Uygulama koduna bu bağımlılık adımında ekleme yapılmadı. Yeni EXE, uzak CI,
main birleştirme ve canlı yayın bu sonuçla yapılmış sayılmaz.
