# Scraper-Ebay

Bu depo, eBay Kleinanzeigen üzerindeki ilanları JSON formatında kaydetmek için geliştirilmiş bir Python scraper içerir.

## Özellikler

Scraper, verilen arama sayfasındaki her bir ilan linkini açar ve aşağıdaki bilgileri toplar:

### Fahrzeug (Araç Bilgileri)
- Marka, model, fiyat (değer, para birimi, pazarlık durumu)
- Kilometre, ilk kayıt tarihi, motor gücü
- Yakıt türü, şanzıman tipi, araç tipi
- Kapı sayısı, dış renk, iç döşeme malzemesi
- HU/TÜV tarihi, çevre plakası, emisyon sınıfı
- Araç durumu (hasarlı/hasarsız)
- Donanım listesi (klimatemp, navigasyon, vb.)
- Açıklama metni
- Tüm ürün görselleri

### Anzeige (İlan Bilgileri)
- Platform adı (Kleinanzeigen)
- Kategori (breadcrumb)
- İlan ID'si
- Görüntülenme sayısı
- Resim sayısı

### Verkaeufer (Satıcı Bilgileri)
- İsim
- Kullanıcı tipi (Özel/Ticari)
- Üyelik tarihi
- Kullanıcı ID'si
- Şehir ve tam konum bilgisi

## Gereksinimler

- Python 3.9 veya üzeri
- beautifulsoup4>=4.12
- requests>=2.31

## Kurulum

```bash
pip install -r requirements.txt
```

## Kullanım

1. Uygulamayı çalıştırın:
   ```bash
   python scraper.py
   ```

2. İstendiğinde eBay Kleinanzeigen arama sonucu sayfasının URL'sini girin.

3. Scraper, sayfadaki tüm ilanları tek tek ziyaret eder ve bilgileri toplar.

4. Toplanan veriler `ebay_listings_<timestamp>.json` dosyasına JSON formatında kaydedilir.

## Çıktı Formatı

Çıktı JSON dosyası, her ilan için üç ana bölüm içerir:
- `fahrzeug`: Araç detayları
- `anzeige`: İlan bilgileri  
- `verkaeufer`: Satıcı bilgileri

Örnek çıktı formatı için `JSON_Beispiel.json` dosyasına bakınız.

## Notlar

- Scraper, site yapısındaki değişikliklere karşı dayanıklı olacak şekilde tasarlanmıştır
- İstekler arasında kısa gecikmeler bulunur (1 saniye) 
- Tüm veriler mevcut olduğu gibi toplanır, değiştirilmez