# Beta.8 güvenlik ve ek cihaz kontrolü — 25 Ekim 2026

İncelenen kaynak: `57c17ac44250bbba1631a78aaff88e35f011b950`.
Canlı hedef: https://qrwebcam.vercel.app/ (0.2.0-beta.8).

## Karar

Stabil sürüm için tam onay verilmedi. Bu, mevcut geliştirme ajanının yeniden
incelemesi ve test çalıştırmasıdır; bağımsız dış uzman kriptografi denetimi değildir.
Ürün kodu, eşleşmeler, canlı veritabanı ve yayımlanmış paket değiştirilmedi.

## Bulgular

### P2 — İlk replay veritabanı açılışında yarış (doğrulandı)

`bridge/replay.py:52` dosyanın varlığını SQLite işlemi başlamadan önce kaydediyor.
İlk alıcı dosyayı oluşturup henüz tabloyu kurmamışken ikinci alıcı dosyayı var
görebilir ve ilk `BEGIN IMMEDIATE` kilidini alabilir. Tablo bulunmadığı için
`SecureStorageError: replay ledger schema is missing` oluşur.

338 testlik çalışmada `test_transaction_serializes_concurrent_receivers` bu
hatayla başarısız oldu (337 başarılı). İzole 16 test tekrarında hata oluşmadı;
bu, yarışı geçersiz kılmaz. İki alıcının sıralamasını kontrollü bekleten ayrı
sentetik test aynı hatayı deterministik üretti: ikinci alıcı hata, oluşturucu
kabul sonucu verdi. Kanıt betiği yerel `build/release-beta8-20261025/reproduce_replay_init.py`.

Etki: ilk gönderim/başlatma aksayabilir. Yetkisiz kabul veya replay korumasının
atlandığı gözlenmedi; hata güvenli şekilde işlemi reddediyor. Düzeltme, ilk
oluşturmayı süreçler arasında güvenli koordine etmeli; bozuk/eksik mevcut
veritabanını boş kabul etmek güvenlik gerilemesi olur.

### P2 — CSP sıkılaştırma borcu (önceden bilinen, canlı doğrulandı)

`pwa/next.config.ts:4` ve canlı HTTP başlığı `script-src 'self' 'unsafe-inline'`
içeriyor. Bu tek başına kanıtlanmış XSS değildir; bir enjeksiyon açığı varsa CSP'nin
onu durdurma kabiliyetini azaltır. IndexedDB'deki dışarı aktarılamayan anahtar da
aynı-origin kötü amaçlı JavaScript tarafından kullanılmaya karşı koruma sağlamaz.
Next çıktısıyla uyumlu nonce/hash yaklaşımı ayrı regresyon testleriyle uygulanmalı.

### İnceleme açığı — Hız limiti kapsamı

Vercel handler'da açık uygulama limitleri cihaz kaydı (12/600 saniye) ve mesaj
gönderimi (60/60 saniye) için var. Eşleştirme oluşturma ve durum/poll uçları için
aynı dosyada ek sınır görülmedi. Barındırma katmanının firewall/rate-limit ayarları
bu çalışmada doğrulanmadı. Canlı yük testi yapılmadı; istismar kanıtı iddia edilmiyor.

## Yeni çalıştırılan kontroller

| Kontrol | Sonuç ve sınır |
| --- | --- |
| Web testleri | 145/145 geçti; gerçek loopback/D1 entegrasyonu dahil. İlk sandbox denemesindeki 3 ağ hatası izinli koşuda giderildi. |
| Masaüstü testleri | 337/338 geçti; yukarıdaki ilk-açılış yarışı açık. Pytest kurulu değildi; projenin unittest çalıştırıcısı kullanıldı. |
| npm audit | 0 bilinen uyarı; Python bağımlılıklarının yeni advisory taraması yapılmadı. |
| Yetkilendirme regresyonları | Kaldırılmış göndericiyi reddetme, başka cihazın teslimatını alamama, bozuk metadata ve replay reddi geçti. Vercel testlerinde Supabase taşıması mock; canlı geçerli tokenlarla çapraz cihaz testi değil. |
| Kriptografik regresyonlar | Mevcut Python/WebCrypto vektörleri, değiştirilen ciphertext, süre ve anahtar ayrımı testleri geçti; protokol güvenliğinin bağımsız ispatı değil. |
| Kalıcı depolama | DPAPI ayrı süreç testi ve sentetik IndexedDB yeniden açma/ayrı depo testleri geçti; ikinci Windows kullanıcısı veya gerçek kurulu PWA testi değil. |
| Canlı sağlık | `/healthz` ve `/readyz` HTTP 200. |
| Canlı anonim yetki kontrolü | Sentetik pair kimliğine geçersiz bearer ile GET HTTP 401. Gerçek eşleşme bilgisi kullanılmadı. |
| Canlı başlıklar | HSTS, no-referrer, CSP mevcut; inline script istisnası yukarıda. |
| SQL kaynak incelemesi | Migration'larda relay tablolarında RLS ve dar grant'ler var. Canlı DB ayarları bu çalışmada yeniden sorgulanmadı. |
| Temiz Chromium mobil boyutları | 360×800 ve 393×852: ana sayfa scrollWidth=viewport; yatay taşma yok. Ana düğmelerde adlar ve en az 44px yükseklik var. |
| Erişilebilirlik ağacı | Türkçe kontrol adları, başlıklar ve alert bölgesi göründü. Gerçek TalkBack/VoiceOver dinleme testi değil. |

## Gerçek cihazda tamamlanacaklar

1. S24 FE / Chrome: canlı adresi Chrome içinde aç, yalnız o tarayıcıyı eşleştir,
   gönder; Chrome'u kapat/aç ve yeniden gönder. Samsung Internet kaydını Chrome
   kaydıymış gibi sayma. İşletim sistemi ve tarayıcı sürümünü kaydet.
2. Chrome ana ekran kurulumundan aç: aynı adresi doğrula, eşleşmenin korunup
   korunmadığını kaydet. Ayrı depo varsa açık yeniden eşleştirme akışını dene.
3. iPhone / Safari ve ana ekran simgesi: aynı depolama ve tekrar gönderim kontrolü.
4. İkinci temiz Windows hesabı/makinesi: yayımlanan ZIP'ten açılış, eşleştirme,
   gönderme, kaldırma, yeniden eşleştirme ve çıkış. Mevcut hesap testi yerine geçmez.
5. Geçerli sentetik kimlik bilgileriyle canlı revocation/çapraz cihaz API kontrolü
   için izole test kayıtları ve temizleme planı hazırla; kullanıcı eşleşmelerini kullanma.

Bağımsız dış güvenlik denetimi ve bu gerçek cihaz sonuçları alınmadan tüm kapılar
tamamlandı olarak işaretlenmemeli. Bu inceleme yeni yayın veya main birleşimi yapmadı.

## Öncelikli düzeltme — yerel kaynak, 25 Ekim

İlk-açılış yarışı düzeltildi. Yeni kayıt SQLite şeması ve DPAPI-korumalı boş
içeriğiyle aynı dosya sistemindeki geçici dizinde hazırlanıp kapatılıyor. Hedefe
atomik, üzerine yazmayan hard-link oluşturma ile sunuluyor. Başka süreç kazanırsa
onun kaydı normal doğrulamadan geçiyor; mevcut boş/bozuk dosya sıfırlanmıyor.
Hard-link desteklenmeyen depolamada işlem güvenli şekilde hata verir; sessiz
korumasız geri dönüş yok. Normal kullanıcı profilindeki Windows testleri geçti.

- Kalıcı regresyon testi düzeltmeden önce aynı schema-missing hatasıyla başarısızdı.
- Düzeltme sonrası 343/343 masaüstü testi geçti.
- Üç eşzamanlılık testi 20 turda 60/60 geçti.
- Dört ayrı Windows sürecinde tam bir kabul ve üç replay reddi doğrulandı.
- Mevcut boş/eksik şema, bozuk içerik ve başarısız yayımlama senaryoları test edildi.
- Yeni bağımlılık eklenmedi; telefon sitesi değiştirilmedi.

Bu sonuçlar kaynak düzeltmesidir. Dağıtılmış beta.8 EXE henüz değişmedi;
yeni EXE paketleme/yayın ve CSP sıkılaştırması bu adımda yapılmadı.

### Ayrı EXE doğrulaması

Sonraki doğrulama adımında 343/343 masaüstü testi yeniden geçti. Ayrı yerel aday:
`dist/candidate-replay-init-20261025/QR-Scanner.exe`.
SHA256: `29AE4D148A8673E4A2F426CE1FE15F257621016A097457A82A3D918119FC3058`.

PyInstaller derlemesi tamamlandı; `bridge.replay` dahil 50 gömülü proje modülü
çalışma ağacındaki kaynakla bytecode düzeyinde karşılaştırıldı ve eşleşti.
EXE `--self-test` çıkış kodu 0: bu, yerleşik sentetik QR okuma testidir;
gerçek telefondan gönderim veya EXE içinde eşzamanlı replay testi değildir.
Eşzamanlılık doğrulaması yukarıdaki kaynak testlerine dayanır.

Bu dosya yerel test adayıdır; sürüm etiketi beta.8 olarak kaldı, yayımlanmış
beta.8 ile aynı dosya değildir. Resmî ZIP/yayın, canlı site ve kullanıcı eşleşmeleri
değiştirilmedi. Yeni adayın gerçek telefon akışı henüz kullanıcı tarafından denenmedi.
