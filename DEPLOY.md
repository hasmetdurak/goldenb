# GoldenBet AI — Dokploy Deployment Rehberi

## Mimari
- **App:** Tek konteyner (Streamlit)
- **Veritabanı:** YOK
- **Redis:** YOK (MVP stateless; oturum ve eğitim `st.session_state`'te)
- **Kalıcılık:** YOK (sayfa yenileyince sıfırlanır — bilinçli tasarım)

## Dokploy Ayarları

### 1) Yeni Servis Oluştur
- **Type:** `App`
- **Source:** `GitHub` → `hasmetdurak/goldenb`
- **Branch:** `main`
- **Build Method:** `Dockerfile`
- **Dockerfile Path:** `./Dockerfile` (repo kökü)

### 2) Port
- Container Port: `8501`
- Dokploy otomatik eşler; gerekirse public portu kendin seç.

### 3) Domain
- Custom domain ekle (örn. `bet.goldenb.app`) → Dokploy otomatik SSL verir.

### 4) Environment Variables
- Şu an **hiçbir ortam değişkeni gerekmez**.
- İleride API anahtarı eklemek gerekirse buraya PAT'leri koy.

### 5) Resource Limits (Önerilen)
- **Memory:** 512 MB (10.000 MC iterasyonu için yeterli)
- **CPU:** 0.5 – 1.0 vCPU
- **Replicas:** 1 (state paylaşımı yok)

### 6) Healthcheck
Dockerfile'da tanımlı: `/_stcore/health` endpoint'ine 30s aralıkla ping atar.
Dokploy bunu otomatik okur.

### 7) Deploy
`Deploy` butonuna bas. İlk build ~60-90s (pip install + ağır paketler: streamlit, pandas, numpy, nba_api).

## Lokal Test (Opsiyonel)
```bash
docker compose up --build
# → http://localhost:8501
```

## Sorun Giderme

| Sorun | Çözüm |
|---|---|
| Container başlamıyor | Logs'da `streamlit` import hatası → `requirements.txt` kontrol et |
| Healthcheck fail | `/_stcore/health` adresine manuel curl at; port 8501 kapalı mı? |
| NBA veri gelmiyor | stats.nba.com'a outbound HTTPS engellenmiş olabilir (firewall) |
| EuroLeague 403 | `EUROLEAGUE_HEADERS` Referer/User-Agent zaten kodda, dokunma |
| İlk yükleme yavaş | Streamlit + pandas cold start ~5-10s normal; warm cache sonrası hızlanır |

## Ölçeklendirme (Gelecek)
Çok kullanıcı olursa:
- Redis ekle → `bias_weight` ve `learning_history`'i Redis'te tut (multi-user paylaşım)
- Postgres ekle → tarihsel tahminler + backtest sonuçlarını persist et
- Workers ekle → ağır backtest'leri arka planda koştur
- API gateway → /api/predict endpoint'i açarak 3rd party erişim

Şu anki MVP için hiçbiri gerekmez.
