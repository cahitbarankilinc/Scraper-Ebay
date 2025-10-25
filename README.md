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

1. Ayrıntıları çekmek istediğiniz ilanların URL'lerini her satıra bir URL gelecek
   şekilde `urls.txt` adında bir dosyaya kaydedin. Farklı bir dosya adı
   kullanacaksanız komut satırında `--input` parametresi ile belirtin.
2. Aşağıdaki komut ile listeyi işleyip sonuçları `output.json` dosyasına yazın:

   ```bash
   python scraper.py --input urls.txt --output output.json
   ```

   Dosya adlarını parametresiz bıraktığınızda komut varsayılan olarak `urls.txt`
   dosyasını okuyup çıktıyı `output.json` olarak kaydeder.

3. Site yapısı değiştiğinde CSS seçicilerini JSON formatında hazırlayarak
   `--selectors` parametresi ile güncelleyebilirsiniz.

Scraper, öncelikle HTML seçicilerini kullanır; bulunamayan alanlar için ise
sayfada yer alan yapılandırılmış JSON verilerini devreye sokar. Böylece ilan
kimliği, fiyat, satıcı bilgileri ve teknik özellikler gibi kritik veriler sitenin
HTML yapısı değişse bile toplanmaya devam eder.

Komut tamamlandığında `output.json` dosyasında her ilan için ayrıntılı kayıtlar
bulunacaktır.
