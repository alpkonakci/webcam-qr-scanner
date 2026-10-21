# Üretime hazırlık denetimi — 20 Ekim 2026

> 22 Ekim son durum: `9c48e07` için GitHub push ve PR CI kontrollerinin tamamı,
> ayrıca Vercel dağıtım kontrolü başarılı. Canlı beş dakikalık temizlik kuruldu ve
> ilk otomatik çalışması doğrulandı; 28 kayıtlı eşleşme korundu. Aşağıdaki ilk
> denetim tarihsel bulguları içerir. Kaynakta giderilmiş CI ve temizlik bulguları
> güncel açık engel sayılmamalı. [Canlı kanıt](retention-live-2026-10-22.md).
> PR #3 taslak; yeni HTTPS adayıyla gerçek cihaz ve erişilebilirlik kapsamındaki
> açık kontroller, paket kaynak arşivinin güncellenmesi ve geri dönüş tatbikatı
> tamamlanmadan stabil yayın onayı verilmedi.

> 21 Ekim güncellemesi: aşağıdaki ilk kaynak–paket uyuşmazlığı, ayrı `dist/candidate-20261021` adayı üretilerek bu aday için giderildi. Eski accessibility paketi değiştirilmedi. Gerçek cihaz kabul testi ve diğer işletim/yayın kapıları açık; ayrıntılar belgenin sonundadır.

**Sonuç: 78/100 — koşullarla yayımlanabilir beta; stabil sürüm onayı değil.**

En önemli riskler güncel kaynakla dağıtılacak paketin eşleşmemesi, yeni adayın gerçek cihaz uçtan uca doğrulamasının eksik olması ve bağımlılık arızalarını yeterince görünür kılmayan işletim kontrolleridir. Puan mühendislik önceliklendirmesidir; güvenlik sertifikası veya matematiksel güvenilirlik ölçüsü değildir. Güncel CI ve tam uçtan uca kanıt olmadığı için 84 üstü değerlendirilmedi. İncelenen kapsamda doğrulanmış kritik yetkilendirme açığı bulunmadı; bu, açık bulunmadığının garantisi değildir.

## Kapsam ve sürüm yüzeyi

- Depo: QR Scanner; dal `codex/vercel-supabase`; HEAD `6862394`.
- Yerel uzak dal referansına göre dal üç commit ileride. Bu denetimde fetch yapılmadı; uzak sunucunun anlık durumu ayrıca doğrulanmadı.
- Kaynak sürümü: `0.2.0-beta.8-preview.2`.
- `dist/accessibility-20261014/Webcam-QR-Scanner-v0.2.0-beta.8-preview.2-windows-x64/SOURCE_REVISION.txt`, paketin `c9f8a4f` kaynağından olduğunu bildiriyor. Son refaktör bu pakette yok.
- Canlı `https://qrwebcam.vercel.app/` HTTP 200 döndü ve `v0.2 beta.7` gösterdi. Canlı adres, mevcut HEAD için yayın kanıtı değildir.
- Denetim salt okunur kaynak incelemesi, yerel test/derleme ve kimlik doğrulamasız HTTP GET kontrolleriyle yapıldı. Ürün kodu, bulut verisi ve yayınlar değiştirilmedi. Harici tarayıcı hizmetine kaynak yüklenmedi.

## Yeni aday yayımlanmadan önce kapanacak kapılar

### 1. Kaynak, EXE ve web sürümünü aynı adayda birleştir

**Önem: yüksek — yayın doğruluğu.** Kullanıcının test ettiği EXE, denetlenen son kaynakla aynı değil. Bu nedenle kaynak testleri yeşil olsa bile dağıtılan dosya için aynı sonucu söyleyemeyiz.

Yapılacak: aday commit/sürümü sabitle; o kaynaktan yeni EXE, ZIP, kaynak paketi ve checksum üret; `SOURCE_REVISION.txt` ile eşleştir. Aynı kaynağın HTTPS web önizlemesiyle test et. Eski beta.7 yayınını bu işlem sırasında değiştirme.

Kanıt: `app_info.py:2`, mevcut paketin `SOURCE_REVISION.txt` dosyası, `package_release.ps1` kaynak arşivleme ve revision yazma akışı.

### 2. Yeni adayın kritik gerçek cihaz akışını doğrula

**Önem: yüksek — eksik kanıt, gözlenmiş yeni bir hata değil.** Önceki beta için kullanıcı tarafından iPhone/Android eşleştirme ve gönderim doğrulaması var. Fakat yeni dil, erişilebilirlik, ayarlar ve ana ekrana ekleme değişikliklerinden sonraki tam kabul turu tamamlanmış sayılmaz.

Gerekli tur: eşleştirme → gönderme/onay → aynı QR'ı yeniden gönderme → kaldırma → eski telefondan erişimin reddi → yeniden eşleştirme → uygulama/Windows yeniden açılışı → çevrimdışı kalma ve geri gelme. Ayrıca Safari/Android tarayıcı ile ana ekrana eklenen web uygulaması arasında eşleşmenin gerçekten korunup korunmadığı ölçülmeli; aktarım varsayılmamalı. Narrator/VoiceOver/TalkBack ile sesli çıktı ve odak sırası fiziksel ortamda kontrol edilmeli.

## Yüksek değerli düzeltmeler

### 3. Sağlık kontrolünü bağımlılık hazır oluşundan ayır

**Önem: orta.** `pwa/server/relay-handler.ts:161` içindeki `/healthz` yapılandırma okunabildikten sonra statik başarı cevabı veriyor. Veritabanı erişimini zorunlu olarak sınamıyor. Bu nedenle HTTP 200, mesaj teslimatının çalıştığını kanıtlamaz. Canlı kontrol de yalnız bu sınırlı kanıtı sağlar.

Öneri: basit liveness kontrolünü koru; kısa zaman aşımı ve düşük maliyetli DB erişimi kullanan ayrı readiness kontrolü ekle. Hata oranı ve gecikme için uyarı eşiği tanımla; yanıtta anahtar veya iç hata ayrıntısı bulunmasın.

### 4. Supabase çağrılarına açık sunucu zaman aşımı koy

**Önem: orta.** `pwa/server/supabase-admin.ts:64` ve `:105` içindeki auth/REST/RPC fetch çağrılarında uygulamaya ait AbortSignal/zaman sınırı yok. İstemci tarafındaki sınırlamalar, sunucunun platform zaman aşımına kadar beklemesini engellemez. Ayrıca istek öncesi temizlik çağrısı da aynı beklemeye takılabilir.

Öneri: sınırlı upstream süre bütçesi ve kararlı hata kodu; salt okunur/idempotent işlemler dışındaki yazmalarda kör tekrar denemesi yapma. Geciken upstream, iptal ve belirsiz yazma sonucu testleri ekle.

### 5. Veri temizliğini yalnız trafik ihtimaline bırakma

**Önem: orta — saklama süresi ve işletim.** `pwa/server/relay-handler.ts:104` civarında temizlik her istekte yaklaşık 1/64 olasılıkla çalıştırılıyor. Depoda bunun dışında zamanlanmış çalıştırıcı bulunmadı. SQL temizlik fonksiyonu süresi dolan kayıtları siliyor; fakat trafik yoksa fiziksel silmenin ne zaman yapılacağını bu mekanizma garanti etmez. TTL nedeniyle erişim reddi ile diskte fiziksel silme farklıdır. Teslim edilmiş/reddedilmiş mesaj gövdeleri ayrıca ACK yolunda temizleniyor.

Öneri: yetkili, zamanlanmış temizlik ve son başarılı çalışma ölçümü; gizlilik metninde erişim süresi ile fiziksel silme hedefini ayır. Canlı projede depo dışı bir zamanlayıcı varsa önce onu doğrula, ikincisini kurma.

Kanıt: `supabase/migrations/202610030001_separate_receipts_from_replay.sql`, `pwa/server/relay-handler.ts`.

### 6. Yayın kapılarını otomatikleştir ve belgeleri güncelle

**Önem: orta.** Depoda `.github` dizini veya takip edilen CI workflow dosyası yok. Yerel testlerin geçmesi, uzak PR/commit için yeşil CI demek değildir. README ve beta yayın kontrol listesinde önceki beta sürümlerine ait bilgiler mevcut.

Öneri: Windows/Python testleri, web test/derleme/lint/tip kontrolleri ve paket-kaynak eşleşmesini zorunlu CI yap. Son iyi beta.7 web dağıtımı ve ZIP'i korunarak yeni sürümden geri dönüş adımlarını belgeleyip dene. Önceki hosting geçişi için geri dönüş notu var; yeni beta adayına özgü geri dönüş tatbikatı bu denetimde yapılmadı.

### 7. Sonraki güvenlik sertleştirmesi

- Üretim CSP'sinde `script-src 'unsafe-inline'` mevcut (`pwa/next.config.ts:4`). Next'in inline çıktısıyla uyumlu nonce/hash yaklaşımı ayrı bir değişiklik olarak ele alınmalı; doğrulamadan direkt kaldırılmamalı.
- Kamera/ekran tarafındaki `links.py` ile telefon tarafındaki daha katı URL politikasını ortak davranışa yaklaştırmak değerlidir. Kamera politikası yalnız HTTP(S) ve hostname kontrol ediyor; telefon politikası ek olarak kimlik bilgisi ve kontrol karakterlerini reddediyor. Bunun incelenmesi, doğrulanmış bir kod çalıştırma açığı iddiası değildir.

## Taze doğrulamalar

| Kontrol | Bu denetimde sonuç |
| --- | --- |
| `.venv\Scripts\python.exe -m unittest discover -s tests` | 318 test başarılı, çıkış 0 |
| `npm test` | 123 test başarılı, çıkış 0; üretim Next derlemesi ve runtime sınırı kontrolü başarılı |
| `npm run lint` | Çıkış 0 |
| `npm run typecheck` | Çıkış 0 |
| `.venv\Scripts\python.exe -m pip check` | Bozuk bağımlılık ilişkisi yok; CVE taraması değildir |
| İzole yerel üretim tarayıcı testi | Tek QR, çoklu QR/klavye seçimi, sentetik yapıştırma ve iptal/yeniden açma başarılı; sayfa hatası, dış ağ aktarımı veya ek sekme yok |
| Canlı `/` ve `/healthz` GET | HTTP 200; ana sayfa beta.7; sağlık yanıtı `wqrs/1`, `supabase-realtime` |

Tarayıcı testi mevcut `pwa/tests/browser-cleanup-smoke.mjs` ile 390×844 görünümde, ayrı profilsiz headless Chrome bağlamında çalıştı. Dış origin istekleri engellendi; işletim sistemi panosuna ve kameraya erişilmedi. Gerçek mobil cihaz testi veya Send to PC uçtan uca testi değildir.

## İncelenen güvenlik sınırları

- Sunucuda cihaz/telefon bearer yetkileri, token hash ile arama, cihaz ve teslimat sahipliği kontrolü; 12 KiB akışlı istek sınırı, süre/nonce/şema doğrulamaları ve hız limitleri.
- RLS/grants, cihaza özel private Realtime politikası ve atomik teslimat lease SQL'i. Bunlar yerel migration dosyaları üzerinden incelendi; canlı DB politikası yeniden sorgulanmadı.
- Windows kullanıcı kapsamlı DPAPI saklama, atomik kayıt; üretim ReceiverService'e bağlanan kalıcı replay guard.
- Doğrulanmış ACK ile teslimat durumu ve kullanıcıdan ayrı bağlantı açma onayı. “PC aldı”, “tarayıcıda açıldı” anlamına gelmiyor.
- İstemciye yalnız public Supabase config yansıtılması; server secret'ın sunucu tarafında kullanılması.
- Canlı CSP, `no-referrer`, `nosniff` ve kamera/mikrofon/konum izin politikaları.
- Paketleme, üçüncü taraf lisans/kaynak ve yeniden derleme belgeleri.
- Takip edilen dosyalarda yüksek güvenli birkaç secret imzasıyla dosya-adı düzeyinde sınırlı arama: eşleşme yok. Bu tam secret/history/bundle taraması değildir.

Ödeme/webhook ve AI/agent çalıştırma yüzeyi uygulamada bulunmadığından bu başlıklar kapsam dışıdır.

## Eksik kanıtlar ve sınırlamalar

- Güncel bağımlılık güvenlik veritabanı taraması çalıştırılmadı. Önceki sıfır bulgu raporu bugünün sonucu sayılamaz; önceki “8 uyarı” için de bu denetim güncel sayı iddia etmiyor.
- Tam Git geçmişi, üretilmiş paketler ve istemci bundle'ları için kapsamlı secret taraması yapılmadı; gitleaks PATH'te bulunmadı.
- Canlı Supabase migration/policy durumu, loglar, yedekten dönüş ve olası depo dışı cron/alarmlar kontrol edilmedi.
- Güncel adayın paketlenmiş EXE testi, gerçek mobil/Windows kullanıcı oturumu testleri ve zorlanmış Realtime kesintisi/fallback turu yapılmadı.
- Bağımsız protokol/kriptografi değerlendirmesi yok. Testlerin geçmesi bağımsız güvenlik incelemesinin yerine geçmez.

## Tek sonraki adım

Önce sabitlenmiş güncel commit'ten **ayrı bir aday EXE/ZIP üret ve kaynak revision eşleşmesini doğrula**. Aynı adayın HTTPS web önizlemesiyle gerçek cihaz kabul turu tamamlanmadan yeni genel yayına veya stabil sürüm ilanına geçme. Ardından readiness, upstream zaman aşımı ve zamanlanmış temizliği önceliklendir.

## Yeniden doğrulama — 21 Ekim 2026

- HEAD değişmedi: `686239436d8234af5b5f1df0ee5fd3a6f5f8c4b6`.
- Yeniden çalıştırılan masaüstü testleri: 318/318 başarılı.
- Yeniden çalıştırılan `npm test`: 123/123 başarılı; üretim derlemesi ve runtime sınırı kontrolü başarılı.
- Yeniden çalıştırılan `npm run lint`: çıkış 0.
- Mevcut accessibility adayının `QR-Scanner.exe --self-test` çalıştırması: çıkış 0. Bu sentetik QR çözme testidir; eşleştirme/teslimat veya gerçek kamera testi değildir.
- ZIP SHA-256: `34B9DC90FA28F9DA6D0083D32F20FEC02C7A145436FD86CB493218CDBEB11CAF`.
- Çıkarılmış EXE SHA-256: `AF04C1DC9E8615D233C99F63D75FB28172B91B4B21DF135CC9E8D7D04710EFF3`.
- İki değer de mevcut `dist/accessibility-20261014/SHA256SUMS.txt` kaydıyla aynı. Bu bütünlük karşılaştırmasıdır; bağımsız yayıncı imzası doğrulaması değildir.
- Paket kaynak kaydı hâlâ `c9f8a4f84493fef3c848b396963850ee08fa43ee`; güncel HEAD ile eşleşmiyor. Dolayısıyla yeni kaynak için paket doğrulama kapısı açık kalıyor.
- Bu turda yeni EXE/ZIP üretilmedi, ürün kaynakları değiştirilmedi ve yayın yapılmadı. Gerçek cihaz kabul turu ve önceki işletim bulguları kapanmış sayılmadı.

## Güncel adayın hazırlanması — 21 Ekim 2026

Kullanıcının devam onayıyla aynı gün yeni bir aday üretildi. Önceki bölümdeki eski paket kontrolünden ayrı işlemdir.

- Kaynak commit: `686239436d8234af5b5f1df0ee5fd3a6f5f8c4b6`.
- Sürüm: `0.2.0-beta.8-preview.2`; genel yayın değil, yerel test adayı.
- ZIP: `dist/candidate-20261021/Webcam-QR-Scanner-v0.2.0-beta.8-preview.2-windows-x64.zip`.
- Kullanılacak EXE: `dist/candidate-20261021/Webcam-QR-Scanner-v0.2.0-beta.8-preview.2-windows-x64/QR-Scanner.exe`.
- Yeni SHA-256 ZIP: `68A1785CD00B80603055213243ADFA481F361EB73F92B11BB03A42CE761AE75D`.
- Yeni SHA-256 EXE: `94931AECEC683766302AA547040BFD5430E9C7D0078C2F58388E741125DF0E85`.

Yeni doğrulamalar:

1. Ayrı dist/work klasörleriyle PyInstaller derlemesi başarılı; eski sürümler değiştirilmedi. Test/modified-library build override'ları kullanılmadı.
2. 318 masaüstü testi ve 123 web testi yeniden başarılı. Web üretim derlemesi/runtime sınırı kontrolü başarılı; canlı web sitesi yayımlanmadı.
3. Hem ilk üretilen hem ZIP'ten çıkarılmış EXE için `--self-test`: çıkış 0.
4. EXE içindeki 50 proje modülünün kod nesneleri, yalnız derleme dosya yolları normalize edilerek güncel temiz kaynakla eşleşti. İki çeviri dosyası ve simge baytları da eşleşti.
5. Dağıtım doğrulayıcısı 1135 donmuş arşiv girdisini kontrol etti; kullanılmayan FFmpeg eklentisi yok, gerekli modüller mevcut.
6. Paketlenen üçüncü taraf envanter/lisans/kaynak kontrolü başarılı; upstream pystray için 13, certifi için 6 dosya kurulu kaynaklarla eşleşti.
7. ZIP CRC kontrolü, kayıtlı/hesaplanan SHA-256 değerleri, ZIP içindeki ve çıkarılan EXE baytları, zorunlu lisans/kaynak dosyaları ve SOURCE_REVISION başarılı.
8. APPLICATION_SOURCE.zip içindeki 294 dosya aynı commit'in yeni üretilen `git archive HEAD` çıktısıyla bayt düzeyinde eşleşti. İlk yardımcı kontrolde ham Git blob'u ile Windows CRLF arşiv çıktısı karşılaştırılmıştı; `.gitattributes` farkının yalnız satır sonu dönüşümü olduğu gösterildi ve doğrulayıcı kanonik Git arşivini karşılaştıracak şekilde düzeltildi. Ürün kaynakları veya paket bu sebeple değiştirilmedi.

Yerel tekrar doğrulama yardımcıları: `build/candidate-20261021/check_frozen_source.py` ve `check_package.py`. Bunlar aday kontrol araçlarıdır, uygulamanın runtime parçası değildir.

**Kapanan kapı:** bu adayda kaynak/EXE/ZIP eşleşmesi. **Açık kalanlar:** gerçek cihazda tam kabul, güncel aday için HTTPS web önizlemesiyle eşleşen uçtan uca test, CI, readiness/upstream zaman aşımı/zamanlanmış temizlik ve önceki raporda belirtilen eksik güvenlik kanıtları. GitHub/Vercel yayını, push/merge, veritabanı değişikliği veya eski paket temizliği yapılmadı.

## Kullanıcı kabul sonucu — 21 Ekim 2026

Kullanıcı, yukarıdaki yeni aday için **eşleştirme → gönderme → kaldırma → yeniden eşleştirme → çıkış** akışının sorunsuz çalıştığını bildirdi. Bu temel masaüstü/telefon akışı kullanıcı doğrulaması olarak başarılı kaydedildi.

Bu mesajda telefon modeli, tarayıcı ve Windows hesabı belirtilmedi; sonuç hem iPhone hem Android için ayrı ayrı test yapıldığı şeklinde genişletilmedi. Ana ekrana eklenen web uygulamasının depolama davranışı, ekran okuyucu, zorlanmış bağlantı kesintisi ve güncel HTTPS web önizlemesiyle tam kabul turu ayrıca açık kalıyor. Canlı web sitesi değiştirilmedi.

Sonraki sınırlı değişiklik için önerilen kapsam: mevcut `/healthz` sözleşmesini koruyarak salt okunur DB erişimini doğrulayan ayrı hazır oluş kontrolü; Supabase auth/REST/RPC işlemlerinde yanıt gövdesini de kapsayan zaman sınırı; güvenli hata eşleme ve otomatik yazma tekrarı yapılmaması. Kullanıcı ardından tasarımı onayladı; uygulama sonucu aşağıdadır.

## Sunucu düzeltmeleri — 21 Ekim 2026

Zaman aşımı ve ayrı hazır oluş kontrolü **yerel kaynakta** uygulandı. Son doğrulama: 142 web testi, 318 masaüstü testi, üretim derlemesi, lint, tip kontrolü ve üç senaryolu yerel HTTP smoke başarılı. Bağımsız incelemede kritik/önemli bulgu yok; süre varsayımlarının test kapsamı güçlendirildi.

Bu iki bulgu yerel uygulama/test düzeyinde giderildi; canlı sisteme yayımlanmadığından üretim doğrulaması hâlâ bekliyor. CI ve zamanlanmış fiziksel temizlik dahil diğer kapılar açık. Ayrıntılar: [sunucu güvenilirliği doğrulaması](relay-reliability-2026-10-21.md). Yeni EXE oluşturulmadı, mevcut aday ve eski sürümler değiştirilmedi.

## CI ve zamanlanmış temizlik hazırlığı — 21 Ekim 2026

Push/PR için Windows masaüstü, web derleme/test/lint/tip kontrolü ve geçici PostgreSQL üzerinde SQL doğrulaması içeren CI dosyası hazırlandı. Canlı anahtar, dağıtım adımı veya yazma yetkili GitHub token kullanılmıyor. Henüz push yapılmadı; uzaktaki CI sonucu ve zorunlu dal kontrolleri doğrulanmış sayılmıyor.

Beş dakikalık temizleme için ayrı, isteğe bağlı kurulum/durum/kaldırma SQL betikleri hazırlandı. Kayıtlı eşleşmeler korunuyor; çakışan görev tanımı, yinelenen temizlik ve istemci rolü izinleri kontrol ediliyor. Supabase Cron etkinleştirilmedi. Yerel test gerçek PostgreSQL çekirdeği kullanan PGlite üzerinde sentetik Cron API'siyle çalıştı; gerçek zamanlayıcı/worker ve hosted PostgreSQL yolu ayrıca doğrulanmalı.

Son yerel doğrulama: **143 web testi, 318 masaüstü testi**, üretim derlemesi, lint, tip kontrolü, SQL kurulum/tekrar kurulum/temizleme/durum/kaldırma senaryoları ve `git diff --check` başarılı. Kurulum hemen veri temizlemiyor; eski ACK ve tekrar-gönderim koruması regresyonu da başarılı.

[CI ve temizlik işletim rehberi](ci-retention-operations-2026-10-21.md), etkinleştirme öncesi kontrolleri, ilk çalışmanın doğrulanmasını ve yalnız ilgili görevin kaldırılmasını açıklıyor. Mevcut EXE/ZIP değiştirilmedi; gelecekteki birleşik yayında kaynak paketi yenilenmeli. Önceki rapordaki diğer üretim kapıları bu hazırlıkla kapanmış sayılmıyor.
