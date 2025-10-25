# Scraper-Ebay

Bu depo, eBay araç ilanlarının detaylarını çekmek için hazırlanmış örnek bir Python
uygulaması içerir. Uygulama, ilan listesi sayfasından toplanan bağlantıları tek tek
ziyaret ederek hem satıcıya hem de araca ait ayrıntılı bilgileri JSON formatında
kaydetmenizi sağlar.

## Özellikler

- İlan kimliği, başlığı, fiyatı, adresi, yayın tarihi ve görüntülenme sayısı
- Araç markası, modeli, kilometresi, hasar durumu, ilk tescil tarihi, yakıt türü,
  beygir gücü ve şanzıman tipi
- Satıcı adı, aktif olduğu tarih, bireysel/kurumsal bilgisi, telefon numarası ve
  diğer aktif ilan sayısı
- İlan açıklaması ve sayfada yer alan diğer teknik özellikler
- Sayfadaki JSON-LD ve `__NEXT_DATA__` bloklarındaki yapılandırılmış verileri
  okuyarak eksik kalan alanları otomatik tamamlama

## Kurulum

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Kullanım

1. Arama sonuçlarındaki ilanların bağlantılarını toplamak istediğiniz URL'yi
   belirleyin. Varsayılan olarak uygulama, Stockach bölgesindeki otomobil
   sonuçlarını içeren aşağıdaki sabit bağlantıyı kullanır:

   ```text
   https://www.kleinanzeigen.de/s-autos/stockach/c216l8477r100+autos.ez_i:1910%2C+autos.km_i:1%2C+autos.power_i:1%2C
   ```

2. Komutu çalıştırarak arama sonuçlarında listelenen tüm ilanların ayrıntılarını
   `output.json` dosyasına yazdırın:

   ```bash
    python scraper.py --output output.json
   ```

   Farklı bir arama sonuç sayfasını işlemek isterseniz `--search-url` parametresi
   ile yeni bağlantıyı geçebilirsiniz.

3. Site yapısı değiştiğinde CSS seçicilerini JSON formatında hazırlayarak
   `--selectors` parametresi ile güncelleyebilirsiniz.

Scraper, öncelikle HTML seçicilerini kullanır; bulunamayan alanlar için ise
sayfada yer alan yapılandırılmış JSON verilerini devreye sokar. Böylece ilan
kimliği, fiyat, satıcı bilgileri ve teknik özellikler gibi kritik veriler sitenin
HTML yapısı değişse bile toplanmaya devam eder.

Komut tamamlandığında `output.json` dosyasında her ilan için ayrıntılı kayıtlar
bulunacaktır.

## Sorun Giderme

- `SyntaxError: invalid decimal literal` hatası ve satırlarda `<<<<<<<`, `=======`, `>>>>>>>` gibi parçalar görüyorsanız dosyada çözümlenmemiş bir git birleşme çatışması bulunuyor demektir. Çatışmayı giderip bu işaretleri sildikten sonra komutu yeniden çalıştırın.

