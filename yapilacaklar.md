# GCP CD kurulumu: manuel yapılacaklar

Bu rehber, repodaki CI ve CD pipeline'larını bir **2. nesil Cloud Run function** (eski adıyla Cloud Functions 2nd gen) ile çalıştırmak için bir kez yapılması gerekenleri anlatır.

Pipeline'lar şu sırayla çalışır:

1. `.github/workflows/ci.yml`, her pull request ve `main` push'unda geçici PostgreSQL üzerinde Django kontrollerini, testleri ve production static build'i çalıştırır.
2. `main` dalındaki CI başarılı olursa `.github/workflows/cd.yml` otomatik başlar.
3. CD, statik dosyaları üretir ve GCP'ye parolasız, kısa ömürlü GitHub OIDC kimliğiyle bağlanır.
4. Neon'un direct URL'si ile migration'ları uygular.
5. Neon'un pooled URL'sini Secret Manager'dan alan function'ı deploy eder.

> Önemli: Bu kurulum bitmeden değişiklikleri `main` dalına push etme. Aksi halde workflow, henüz tanımlanmamış GCP değişkenleri yüzünden başarısız olur.

## 1. Maliyet yaklaşımı

Bu yapı küçük ve düşük trafikli kişisel bir uygulama için mümkün olduğunca düşük maliyetlidir:

- Function minimum instance sayısı `0`, maksimum instance sayısı `2` olarak ayarlı.
- GCP faturalandırma hesabı zorunludur; ücretsiz kullanım limitini aşarsan ücret oluşabilir.
- Cloud Run request-based ücretsiz kotasında aylık 2 milyon istek bulunur.
- Cloud Build aylık 2.500 `e2-standard-2` build dakikasına, Artifact Registry 0,5 GB depolamaya kadar ücretsiz kota sunar.
- Secret Manager aylık 6 aktif secret sürümü ve 10.000 erişim işlemine kadar ücretsiz kota sunar. Bu proje ilk kurulumda 3 aktif secret sürümü kullanır.
- GitHub Actions public repolarda ücretsizdir; private repolarda hesabının aylık dahilî dakika kotasını kullanır.
- GCP ile Neon farklı bulutlarda olduğu için ağ çıkış ücreti oluşabilir. Trafiği ve gecikmeyi azaltmak için function bölgesini Neon bölgesine yakın seç.

Ücretsiz kota bir harcama kilidi değildir. İlk iş olarak Google Cloud Console'da **Billing > Budgets & alerts** bölümünden örneğin `1 EUR` bütçe uyarısı oluştur. Uyarı harcamayı otomatik durdurmaz, sadece haber verir.

Resmî fiyat/kota sayfaları:

- [Google Cloud Free Tier](https://cloud.google.com/free/docs/free-cloud-features)
- [Cloud Run pricing](https://cloud.google.com/run/pricing)
- [Secret Manager pricing](https://cloud.google.com/secret-manager/pricing)

## 2. GCP projesini ve faturalandırmayı hazırla

1. [Google Cloud Console](https://console.cloud.google.com/) içinde yeni bir proje oluştur veya bu uygulamaya ayıracağın projeyi seç.
2. Projeye bir billing account bağla.
3. Sağ üstten **Activate Cloud Shell** seçeneğini aç.
4. Aşağıdaki değerlerde yalnızca `PROJECT_ID` gerekirse değişsin. `europe-west1` Belçika bölgesidir; Neon veritabanın başka bir coğrafyadaysa ona yakın bir [GCP bölgesi](https://cloud.google.com/functions/docs/locations) seç.

```bash
export PROJECT_ID="GCP_PROJECT_ID_BURAYA"
export REGION="europe-west1"
export FUNCTION_NAME="home-sweet-home"
export GITHUB_REPOSITORY="bahadircolak44/home-sweet-home"

gcloud config set project "$PROJECT_ID"
export PROJECT_NUMBER="$(gcloud projects describe "$PROJECT_ID" --format='value(projectNumber)')"
```

Değerleri kontrol et:

```bash
printf 'Project ID: %s\nProject number: %s\nRegion: %s\n' "$PROJECT_ID" "$PROJECT_NUMBER" "$REGION"
```

## 3. Gerekli API'leri aç

Cloud Shell'de çalıştır:

```bash
gcloud services enable \
  artifactregistry.googleapis.com \
  cloudbuild.googleapis.com \
  cloudfunctions.googleapis.com \
  iamcredentials.googleapis.com \
  logging.googleapis.com \
  run.googleapis.com \
  secretmanager.googleapis.com \
  sts.googleapis.com
```

API'lerin hazırlanması birkaç dakika sürebilir.

## 4. Üç ayrı service account oluştur

Deployment, build ve çalışan uygulama için farklı kimlikler kullanıyoruz. Böylece uygulamanın deployment yetkisi olmaz.

```bash
gcloud iam service-accounts create hsh-github-deployer \
  --display-name="Home Sweet Home GitHub deployer"

gcloud iam service-accounts create hsh-function-runtime \
  --display-name="Home Sweet Home function runtime"

gcloud iam service-accounts create hsh-function-builder \
  --display-name="Home Sweet Home function builder"

export DEPLOY_SA="hsh-github-deployer@${PROJECT_ID}.iam.gserviceaccount.com"
export RUNTIME_SA="hsh-function-runtime@${PROJECT_ID}.iam.gserviceaccount.com"
export BUILD_SA="hsh-function-builder@${PROJECT_ID}.iam.gserviceaccount.com"
```

Deployment kimliğine yalnızca gereken proje rollerini ver:

```bash
gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="serviceAccount:${DEPLOY_SA}" \
  --role="roles/cloudfunctions.developer"

gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="serviceAccount:${DEPLOY_SA}" \
  --role="roles/serviceusage.serviceUsageConsumer"
```

Build kimliğine resmî dokümanda istenen üç rolü ver:

```bash
gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="serviceAccount:${BUILD_SA}" \
  --role="roles/logging.logWriter"

gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="serviceAccount:${BUILD_SA}" \
  --role="roles/artifactregistry.writer"

gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="serviceAccount:${BUILD_SA}" \
  --role="roles/storage.objectViewer"
```

Deployment kimliğinin yalnızca runtime ve build kimlikleri gibi davranabilmesine izin ver:

```bash
gcloud iam service-accounts add-iam-policy-binding "$RUNTIME_SA" \
  --member="serviceAccount:${DEPLOY_SA}" \
  --role="roles/iam.serviceAccountUser"

gcloud iam service-accounts add-iam-policy-binding "$BUILD_SA" \
  --member="serviceAccount:${DEPLOY_SA}" \
  --role="roles/iam.serviceAccountUser"
```

## 5. Neon URL'lerini Secret Manager'a ekle

### Önce Secret Manager'ı etkinleştir

`Secret Manager API has not been used ... or it is disabled` hatası alırsan URL ile ilgili adıma henüz gelmedin. Önce doğru proje ve hesabı doğrula:

```bash
gcloud auth list
gcloud config set project "home-sweet-home-503219"
gcloud config get-value project
gcloud projects describe "home-sweet-home-503219"
```

Aktif hesap doğru ve proje erişilebiliyorsa API'yi aç:

```bash
gcloud services enable secretmanager.googleapis.com \
  --project="home-sweet-home-503219"

gcloud services list --enabled \
  --project="home-sweet-home-503219" \
  --filter="name:secretmanager.googleapis.com"
```

İkinci komut `secretmanager.googleapis.com` göstermelidir. API'yi yeni açtıysan 2-5 dakika bekleyip secret oluşturma adımını tekrar dene.

İlk komut yine `PERMISSION_DENIED` verirse aktif `bahadircolaknl@gmail.com` hesabında API açmak için gereken yetki yoktur. Projenin sahibi olan hesapla oturum aç veya proje sahibinden bu hesaba **Service Usage Admin** (`roles/serviceusage.serviceUsageAdmin`) rolünü vermesini iste. Secret oluşturmak için ayrıca **Secret Manager Admin** (`roles/secretmanager.admin`) gerekir.

Bunu terminal yerine Console'dan yapmak istersen:

1. [Secret Manager API](https://console.cloud.google.com/apis/library/secretmanager.googleapis.com?project=home-sweet-home-503219) sayfasını aç.
2. Üst çubukta `home-sweet-home-503219` projesinin seçili olduğunu doğrula.
3. **Enable** düğmesine bas ve birkaç dakika bekle.
4. Ardından [Secret Manager](https://console.cloud.google.com/security/secret-manager?project=home-sweet-home-503219) sayfasına git.

### URL'leri Neon'dan al

Neon Console'da projenin **Connect** penceresini aç. İki bağlantı URL'si kopyala:

- **Pooled connection**: function'ın normal isteklerinde kullanılır; host adında genellikle `-pooler` bulunur.
- **Direct connection**: yalnızca Django migration için kullanılır.

Her ikisinde de `sslmode=require` bulunmalı. URL'leri dosyaya, repoya, `.env.example` içine veya GitHub değişkenine yazma.

### URL'yi nereye yapıştıracağım?

En kolay yöntem GCP Console'dur. Secret Manager sayfasında **Create secret** düğmesine basıp aşağıdaki üç kaydı ayrı ayrı oluştur:

| Secret name | Secret value alanına yapıştırılacak değer |
|---|---|
| `home-sweet-home-database-url` | Neon **pooled connection** URL'sinin tamamı |
| `home-sweet-home-database-url-unpooled` | Neon **direct connection** URL'sinin tamamı |
| `home-sweet-home-django-secret-key` | Rastgele Django secret key; aşağıdaki komutla üretilebilir |

Console'a yapıştıracağın Django key'i üretmek için:

```bash
openssl rand -base64 48
```

Replication ayarını **Automatic** bırak. Neon URL'sini tırnak işaretleri olmadan, `postgresql://...` ile başlayan ve parametreleriyle birlikte tek satır olarak **Secret value** alanına yapıştır. Secret oluşturulduktan sonra değer `Version 1` olarak saklanır.

Console kullanırsan aşağıdaki üç `gcloud secrets create` komutunu tekrar çalıştırma; doğrudan **Secret erişimlerini tanımla** kısmına geç.

Terminal kullanmayı tercih edersen `read -rsp` komutundan sonra ekranda yazı görünmez. Neon URL'sini yapıştırıp Enter'a basarsın; komut değeri geçici shell değişkenine alıp Secret Manager'a yollar.

Önce pooled URL'yi güvenli ve görünmez girişle oluştur:

```bash
read -rsp "Neon pooled DATABASE_URL: " HSH_DATABASE_URL
printf '\n'
printf '%s' "$HSH_DATABASE_URL" | gcloud secrets create home-sweet-home-database-url \
  --replication-policy="automatic" \
  --data-file=-
unset HSH_DATABASE_URL
```

Direct URL'yi ekle:

```bash
read -rsp "Neon direct DATABASE_URL: " HSH_DATABASE_URL_UNPOOLED
printf '\n'
printf '%s' "$HSH_DATABASE_URL_UNPOOLED" | gcloud secrets create home-sweet-home-database-url-unpooled \
  --replication-policy="automatic" \
  --data-file=-
unset HSH_DATABASE_URL_UNPOOLED
```

Django `SECRET_KEY` değerini üret ve sakla:

```bash
HSH_DJANGO_SECRET_KEY="$(openssl rand -base64 48)"
printf '%s' "$HSH_DJANGO_SECRET_KEY" | gcloud secrets create home-sweet-home-django-secret-key \
  --replication-policy="automatic" \
  --data-file=-
unset HSH_DJANGO_SECRET_KEY
```

Secret erişimlerini tanımla. Bu komutları GitHub Actions içinde değil, proje sahibi kullanıcı hesabınla açtığın Cloud Shell'de çalıştır. Runtime yalnızca uygulamanın iki secret'ını alır; deployer migration ve deployment doğrulaması için üçünü de okuyabilir:

```bash
gcloud config set project "home-sweet-home-503219"

gcloud secrets add-iam-policy-binding home-sweet-home-database-url \
  --project="home-sweet-home-503219" \
  --member="serviceAccount:hsh-function-runtime@home-sweet-home-503219.iam.gserviceaccount.com" \
  --role="roles/secretmanager.secretAccessor"

gcloud secrets add-iam-policy-binding home-sweet-home-django-secret-key \
  --project="home-sweet-home-503219" \
  --member="serviceAccount:hsh-function-runtime@home-sweet-home-503219.iam.gserviceaccount.com" \
  --role="roles/secretmanager.secretAccessor"

gcloud secrets add-iam-policy-binding home-sweet-home-database-url \
  --project="home-sweet-home-503219" \
  --member="serviceAccount:hsh-github-deployer@home-sweet-home-503219.iam.gserviceaccount.com" \
  --role="roles/secretmanager.secretAccessor"

gcloud secrets add-iam-policy-binding home-sweet-home-database-url-unpooled \
  --project="home-sweet-home-503219" \
  --member="serviceAccount:hsh-github-deployer@home-sweet-home-503219.iam.gserviceaccount.com" \
  --role="roles/secretmanager.secretAccessor"

gcloud secrets add-iam-policy-binding home-sweet-home-django-secret-key \
  --project="home-sweet-home-503219" \
  --member="serviceAccount:hsh-github-deployer@home-sweet-home-503219.iam.gserviceaccount.com" \
  --role="roles/secretmanager.secretAccessor"
```

Özellikle migration secret'ının binding'ini doğrula:

```bash
gcloud secrets get-iam-policy home-sweet-home-database-url-unpooled \
  --project="home-sweet-home-503219" \
  --flatten="bindings[].members" \
  --filter="bindings.role:roles/secretmanager.secretAccessor AND bindings.members:hsh-github-deployer" \
  --format="table(bindings.role,bindings.members)"
```

Çıktıda `hsh-github-deployer@home-sweet-home-503219.iam.gserviceaccount.com` görünmelidir. IAM değişikliği sonrası 2-5 dakika bekleyip başarısız GitHub Actions çalışmasında **Re-run failed jobs** seç.

Secret değerlerini değiştirmek gerektiğinde yeni secret yaratma; yeni sürüm ekle. Örnek:

```bash
read -rsp "Yeni Neon pooled DATABASE_URL: " HSH_DATABASE_URL
printf '\n'
printf '%s' "$HSH_DATABASE_URL" | gcloud secrets versions add home-sweet-home-database-url --data-file=-
unset HSH_DATABASE_URL
```

Pipeline `latest` sürümünü kullanır. Eski sürümü Secret Manager ekranından disable veya destroy ederek aktif sürüm sayısını ücretsiz kota içinde tutabilirsin.

Neon'un pooled/direct URL açıklaması: [Neon connection pooling](https://neon.com/docs/connect/connection-pooling).

## 6. GitHub ile anahtarsız GCP bağlantısını kur

Workload Identity Pool ve GitHub OIDC provider oluştur:

```bash
gcloud iam workload-identity-pools create github-actions \
  --location="global" \
  --display-name="GitHub Actions"

gcloud iam workload-identity-pools providers create-oidc home-sweet-home \
  --location="global" \
  --workload-identity-pool="github-actions" \
  --display-name="Home Sweet Home GitHub" \
  --issuer-uri="https://token.actions.githubusercontent.com" \
  --attribute-mapping="google.subject=assertion.sub,attribute.repository=assertion.repository,attribute.ref=assertion.ref" \
  --attribute-condition="attribute.repository=='${GITHUB_REPOSITORY}' && attribute.ref=='refs/heads/main'"
```

Yalnızca bu GitHub reposunun deployment service account'u taklit etmesine izin ver:

```bash
export GITHUB_PRINCIPAL="principalSet://iam.googleapis.com/projects/${PROJECT_NUMBER}/locations/global/workloadIdentityPools/github-actions/attribute.repository/${GITHUB_REPOSITORY}"

gcloud iam service-accounts add-iam-policy-binding "$DEPLOY_SA" \
  --member="$GITHUB_PRINCIPAL" \
  --role="roles/iam.workloadIdentityUser"
```

Provider'ın tam adını al:

```bash
export WIF_PROVIDER="$(gcloud iam workload-identity-pools providers describe home-sweet-home \
  --location="global" \
  --workload-identity-pool="github-actions" \
  --format='value(name)')"

printf '%s\n' "$WIF_PROVIDER"
```

Bu yöntem JSON service-account key üretmez. GitHub her deployment'ta kısa ömürlü bir OIDC kimliği alır. Ayrıntı: [GCP Workload Identity Federation for deployment pipelines](https://cloud.google.com/iam/docs/workload-identity-federation-with-deployment-pipelines).

## 7. GitHub Actions değişkenlerini gir

GitHub reposunda şu sayfayı aç:

**Settings > Secrets and variables > Actions > Variables > New repository variable**

Aşağıdaki 7 repository variable'ı oluştur:

| Variable | Değer |
|---|---|
| `GCP_PROJECT_ID` | `$PROJECT_ID` çıktısı |
| `GCP_REGION` | `europe-west1` veya seçtiğin bölge |
| `GCP_FUNCTION_NAME` | `home-sweet-home` |
| `GCP_WORKLOAD_IDENTITY_PROVIDER` | `$WIF_PROVIDER` çıktısı; `projects/123.../providers/home-sweet-home` biçiminde |
| `GCP_DEPLOY_SERVICE_ACCOUNT` | `$DEPLOY_SA` değeri |
| `GCP_RUNTIME_SERVICE_ACCOUNT` | `$RUNTIME_SA` değeri |
| `GCP_BUILD_SERVICE_ACCOUNT` | `$BUILD_SA` değeri |

Buraya `DATABASE_URL` veya `SECRET_KEY` girme. Bunlar GitHub'da değil, GCP Secret Manager'da kalır.

## 8. İlk pipeline'ı çalıştır

Bu repodaki değişiklikleri gözden geçir, commit et ve `main` dalına push et. Ben commit veya push yapmadım.

GitHub'da önce **Actions > Continuous integration** ekranını aç. CI şu adımlarda yeşil olmalı:

- Check for missing migrations
- Run Django checks
- Run tests
- Verify production static build

`main` CI başarılı olduktan sonra **Actions > Continuous deployment** otomatik başlamalı. CD şu adımlarda yeşil olmalı:

- Collect production static files
- Authenticate to Google Cloud
- Apply database migrations
- Deploy Cloud Run function

İlk WIF/IAM kurulumu henüz yayılmadıysa birkaç dakika bekleyip başarısız workflow'da **Re-run all jobs** seç.

Deployment başarılı olduğunda job summary içinde `run.app` URL'si görünür. İlk deployment varsayılan olarak dış dünyaya kapalıdır; sonraki adımda bir kez public yapacağız.

## 9. Function'ı bir kez public yap

Uygulamanın kendi Django login ekranı olduğu için HTTP function'a anonim erişim açılır; uygulama sayfalarını yine Django kimlik doğrulaması korur.

Cloud Shell'de, 2. adımdaki değişkenler hâlâ yoksa yeniden tanımladıktan sonra çalıştır:

```bash
gcloud functions add-invoker-policy-binding "$FUNCTION_NAME" \
  --region="$REGION" \
  --member="allUsers"
```

`run.app` URL'sini tekrar öğrenmek için:

```bash
export APP_URL="$(gcloud functions describe "$FUNCTION_NAME" \
  --v2 \
  --region="$REGION" \
  --format='value(serviceConfig.uri)')"

printf '%s\n' "$APP_URL"
```

Tarayıcıda bu `run.app` URL'sini aç. Giriş ekranına yönlenmelisin. Uygulama statik dosyaları Functions Framework'ün ayırdığı `/static/` yolu yerine `/assets/` altında yayınlar. Ana adres olarak path prefix içermeyen `run.app` URL'sini kullan.

Public erişim ayrıntısı: [Cloud Run functions IAM access](https://cloud.google.com/functions/docs/securing/managing-access-iam).

## 10. İlk Django kullanıcısını oluştur

Bilgisayarında Google Cloud CLI kurulu ve GCP hesabınla giriş yapılmış olmalı. Repo klasöründe virtual environment hazırlandıktan sonra çalıştır:

```bash
export PROJECT_ID="GCP_PROJECT_ID_BURAYA"

source .venv/bin/activate
pip install -r requirements.txt

export DATABASE_URL="$(gcloud secrets versions access latest --secret=home-sweet-home-database-url-unpooled --project="$PROJECT_ID")"
export DJANGO_SETTINGS_MODULE="home_sweet_home.settings.production"
export SECRET_KEY="temporary-management-command-key"
export ALLOWED_HOSTS=".run.app"
export CSRF_TRUSTED_ORIGINS="https://example.com"

python manage.py createsuperuser

unset DATABASE_URL DJANGO_SETTINGS_MODULE SECRET_KEY ALLOWED_HOSTS CSRF_TRUSTED_ORIGINS
deactivate
```

Sonra `$APP_URL/admin/` adresinden giriş yapıp README'deki **Initial household setup** adımlarını tamamla.

## 11. Normal kullanım

Bundan sonra:

- Her pull request ve `main` push'u CI kontrollerini çalıştırır.
- Pull request'ler deploy edilmez.
- `main` dalına push edilen revision'ın CI'ı başarılı olursa CD otomatik başlar.
- Gerekirse GitHub **Actions > Continuous deployment > Run workflow** ile `main` üzerinde manuel deployment başlatabilirsin.
- Deployment sırasında hata olursa önceki çalışan function revision hizmet vermeye devam eder; fakat migration deployment'tan önce uygulandığı için model değişikliklerini geriye uyumlu tasarlamak gerekir.

Schema değişikliklerinde güvenli sıra:

1. Yeni alanı nullable/default değerli ve eski kodla uyumlu ekle.
2. Deploy et ve veriyi doldur.
3. Gerekli ise daha sonraki ayrı deployment'ta eski alanı kaldır veya constraint'i sıkılaştır.

## 12. Sorun giderme

### Workflow secret erişiminde 403 veriyor

5. adımdaki Secret Manager IAM binding'lerini ve 7. adımdaki service-account değişkenlerini kontrol et. IAM değişikliklerinin yayılması birkaç dakika sürebilir.

### WIF authentication başarısız

Provider condition yalnızca `bahadircolak44/home-sweet-home` reposunun `main` ref'ine izin verir. Workflow'u başka branch'ten manuel başlatma. Repo adı değişirse 6. adımdaki provider condition ve principal binding güncellenmelidir.

### Build service account `ActAs` veya permission hatası

4. adımdaki build rollerini ve deployer → builder `roles/iam.serviceAccountUser` binding'ini tekrar kontrol et.

### Sayfa 403/404 ve login ekranı gelmiyor

9. adımdaki `add-invoker-policy-binding` komutunu uyguladığını kontrol et. Organization Policy, `allUsers` erişimini engelliyorsa GCP organization yöneticisinin bu kısıtı değiştirmesi gerekir.

### `DisallowedHost` hatası

Ana adres olarak job summary'deki `https://...run.app` URL'sini kullan. Workflow runtime ayarları `.run.app` hostlarını kabul eder.

### CSRF hatası

`run.app` URL'sinde aynı-origin istekler doğrudan çalışır. Daha sonra custom domain eklersen `.github/workflows/cd.yml` içindeki `ALLOWED_HOSTS` ve `CSRF_TRUSTED_ORIGINS` değerlerine tam domaini ekleyip yeniden deploy et.

### Static dosyalar görünmüyor

GitHub Actions logunda **Collect production static files** adımının başarılı olduğunu doğrula ve path prefix içermeyen `run.app` adresini kullandığından emin ol. Sayfa kaynağındaki CSS/JS adresleri `/assets/...` ile başlamalıdır. `/static/...` görüyorsan bu düzeltmeyi içeren commit henüz deploy edilmemiştir; değişiklikleri `main` dalına gönder, CI/CD tamamlanınca sayfayı zorla yenile (`Ctrl+Shift+R`).

### Neon bağlantı sayısı artıyor

Runtime secret'ında `-pooler` içeren pooled URL olduğunu doğrula. Pipeline migration için direct URL kullanır. Düşük maliyetli kesirli CPU kullanıldığı için function instance başına concurrency `1`, maksimum instance sayısı `2` olarak ayarlanmıştır. Daha fazla eşzamanlı trafik gerekirse en az `1` vCPU seçip concurrency artırılabilir.

### Maliyet artıyor

Billing ekranından hangi servisin harcama oluşturduğunu kontrol et. Sık deployment yapılıyorsa Artifact Registry'deki eski build image'ları depolama tüketebilir; kullanılan son revision image'larını koruyarak eski, kullanılmayan image'ları temizle. Minimum instance değerini `0` bırak.
