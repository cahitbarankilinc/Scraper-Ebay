# Scraper-Ebay

Bu depo, eBay Kleinanzeigen üzerindeki ilanları JSON formatında kaydetmek için basit bir komut satırı uygulaması içerir.

## Gereksinimler

- Python 3.9 veya üzeri
- `pip install -r requirements.txt` gerekmez, ancak aşağıdaki kütüphaneler kurulmuş olmalıdır:
  - `requests`
  - `beautifulsoup4`

## Kullanım

1. Gerekli bağımlılıkları yükleyin:
   ```bash
   pip install requests beautifulsoup4
   ```
2. Uygulamayı çalıştırın:
   ```bash
   python scraper.py
   ```
3. Komut satırındaki yönlendirmeyi takip ederek eBay Kleinanzeigen arama sonucu veya kategori sayfasının bağlantısını girin.
4. Uygulama her ilan detayına giderek bilgileri toplayacak ve çalıştığı klasörde `ebay_listings_<timestamp>.json` dosyası oluşturacaktır.

## Notlar

- Site erişim limitlerini aşmamak için istekler arasında kısa bir gecikme bulunur.
- eBay Kleinanzeigen sitesi zaman içinde yapısını değiştirebilir; seçiciler çalışmazsa güncellenmeleri gerekir.
- Program ağ bağlantısı gerektirdiği için çevrimdışı ortamda çalışmayacaktır.
