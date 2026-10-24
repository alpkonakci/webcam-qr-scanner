# Sunucu zaman aşımı ve hazır oluş doğrulaması — 21 Ekim 2026

## Durum ve kapsam

Kullanıcı kısa tasarımı onayladıktan sonra yerel kaynakta uygulandı. Baz commit `686239436d8234af5b5f1df0ee5fd3a6f5f8c4b6`; bu rapor henüz commit edilmemiş farkları tanımlar. Canlı Vercel/Supabase değişikliği, migration, push/merge veya GitHub yayını yapılmadı. Windows uygulama kaynakları ve kullanıcının doğruladığı `dist/candidate-20261021` EXE'si değiştirilmedi. O ZIP'in uygulama kaynak arşivi bu yeni sunucu farklarını içermez; ileride birleşik yayın hazırlanırken kaynak paketi yeniden üretilmelidir.

## Uygulananlar

- Supabase auth/REST/RPC çağrılarında varsayılan 5 saniye sınırı var. Süre yalnız HTTP başlıklarını değil, JSON yanıt gövdesinin okunmasını da kapsar. Zaman aşımı outgoing AbortController'ı iptal eder; timer her çıkış yolunda temizlenir.
- Yazma otomatik tekrarlanmaz. İptal, veritabanı işleminin geri alındığı anlamına gelmez; mevcut belirsiz teslimat/status sorgulama akışı korunur.
- Zaman aşımı ve taşıma hataları güvenli `SupabaseAdminError` üretir; istemciye geri kazanılabilir `503 relay_unavailable` döner. Upstream auth servisinin 503 yanıtı artık geçersiz kimlik bilgisi gibi 401'e çevrilmez. Gerçek 401/403 auth yanıtlarının mevcut davranışı korunur.
- `GET /healthz` mevcut JSON sözleşmesini korur ve DB erişimi sınamaz. Yapılandırma doğrulaması sürer; rastgele temizlik çalıştırmaz.
- Yeni `GET /readyz`, 2 saniye sınırıyla `relay_devices?select=device_id&limit=0` okuması yapar. Boş dizi doğrulanmadan hazır demez; kayıt, anahtar, upstream mesajı veya hostname döndürmez. Temizlik ya da başka yazma çalıştırmaz.
- Her iki yanıt `Cache-Control: no-store` kullanır. Yeni Next rotası dinamiktir ve yalnız GET destekler (desteklenmeyen POST 405).
- Beklenmeyen, taşıma dışı iç hatalar hâlâ genel ve güvenli 500 yanıtı üretir.

`limit=0` davranışı [resmî PostgREST sürüm notlarında](https://docs.postgrest.org/en/v11/releases/v10.0.0.html) belgelenmiştir. Buradaki testler gerçek canlı Supabase erişimi kanıtı değildir.

## Doğrulamalar

| Kontrol | Sonuç |
| --- | --- |
| İlk test-öncelikli kırmızı aşama | 16 testin 15'i beklenen eksik davranışlarda başarısız; mevcut auth davranışını koruyan test başarılı |
| Son `npm test` | 142/142 başarılı; Next üretim derlemesi başarılı |
| Runtime boundary | 42 kaynak ve 6 Next trace başarılı |
| `npm run lint` | Çıkış 0 |
| `npm run typecheck` | Çıkış 0 |
| `python -m unittest discover -s tests` | 318/318 başarılı |
| Yerel gerçek HTTP smoke | Sağlıklı, arızalı, takılı dependency senaryolarının üçü başarılı |
| Bağımsız salt okunur kod incelemesi | Kritik/önemli bulgu yok; varsayılan üretim sürelerini sınama önerisi uygulandı |

Gerçek HTTP gövde testleri yalnız `127.0.0.1` üzerinde bir HTTP sunucusu kullanır; başlıklar ulaştıktan sonra 200 veya 503 gövdesi tamamlanmaz. Her iki durumda süre aşımı yakalanır. Ayrı testler override olmadan varsayılan 5 saniye sınırını ve route'un 2 saniye sınırını sınar. Her CRUD/RPC/auth yolu için takılan istek iptali ve otomatik yeniden gönderim olmaması denetlenir.

Tam paket ilk turunda eski `unexpected relay failures never log raw exception data` testi 500 beklediği için tek hata verdi. Gereksinime uygun yeni davranış olan taşıma hatası 503 ile güncellendi; taşıma dışı genel 500 koruması ayrı testle tutuldu. Son tam test paketinde başarısız test yok.

Yerel production smoke yardımcıları `build/relay-readiness-20261021/` altındadır. Gerçek Next derlemesi port 3116'da başlatılır; strict fake-fetch preloader sadece sahte Supabase origin'ine sıfır-satır GET kabul eder ve hiçbir dış ağ çağrısı yapmaz. Next'in gerçek GET yanıtları, durum/önbellek/mahremiyet alanları ve POST 405 kontrol edilir. Başlatılan test süreçleri bitişte kapatılır. Windows'ta preload dosyası `file:` URL'siyle yüklenir; ilk yardımcı çalıştırmadaki yol/erken süreç kapanışı sorunu düzeltildi. Bu yardımcılar runtime'a dahil değildir.

## Sınırlar ve kalan kapılar

- Süreler operasyon başınadır; birden fazla DB işlemi olan tüm relay isteğinin toplam süre garantisi değildir.
- Hazır oluş, veritabanı erişimi/sorgu yolunu sınar; Realtime, uçtan uca teslimat, RLS politikalarının tam doğruluğu veya kriptografik güvenlik onayı değildir.
- Sıfır satır dönse de DB isteği maliyeti vardır. Sık frontend polling yapılmamalı; hosting düzeyi abuse kontrolü ve makul izleme aralığı gerekir.
- Başarılı ama bozuk auth cevabının eski 401 davranışı bu kapsamda değiştirilmedi. Bu, auth servisi kesintisinin yeni 503 eşlemesinden ayrıdır.
- Canlı loglar, canlı DB sorgusu, üretim migration/policy doğrulaması, bağımsız güvenlik incelemesi ve güncel CVE/secret geçmiş taraması yapılmadı.
- CI kapıları ve zamanlanmış saklama temizliği ayrı işlerdir; bu değişiklikle tamamlanmış sayılmaz.
- Sonraki doğrulama: yetkilendirilmiş HTTPS önizleme dağıtımında `/healthz` ve `/readyz` karşılaştırması, ardından aynı önizlemede telefon-PC kabul turu. Bunun için ayrıca dağıtım adımı gerekir; bu çalışmada canlı sistem değiştirilmedi.
