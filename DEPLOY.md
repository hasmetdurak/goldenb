# GoldenBet AI — Dokploy Deployment Rehberi

## Mimari — İki Profil

| Profil | Servisler | Ne Zaman? |
|---|---|---|
| **default** (MVP) | Sadece Streamlit | Şu an |
| **live** (full stack) | Streamlit + PostgreSQL + Redis | Canlı API gelince |

MVP **stateless** çalışır. `st.session_state` per-user in-memory. Bu yüzden
`goldenb` reposu `default` profilde bağımsız deploy edilebilir.

## Profil Seçimi (Dokploy)

Dokploy compose editöründe servislere bak. `postgres` ve `redis` servisleri
`profiles: ["live"]` ile işaretli → bunlar sadece "live" profili seçildiğinde kalkar.

Eğer Dokploy otomatik profile desteklemiyorsa:
1. Compose dosyasından `profiles: ["live"]` satırlarını kaldır (her zaman kalkar)
2. Veya `docker compose --profile live up` kullan

## Default Profil — Sadece Streamlit

### 1) Yeni Servis Oluştur
- **Type:** `App`
- **Source:** `GitHub` → `hasmetdurak/goldenb`
- **Branch:** `main`
- **Build Method:** `Dockerfile`
- **Dockerfile Path:** `./Dockerfile`

### 2) Port & Domain
- Container Port: `8501`
- Custom domain ekle (örn. `bet.goldenb.app`) → otomatik SSL.

### 3) Environment Variables
Hiçbiri gerekmez. Boş bırak.

### 4) Resource Limits
- **Memory:** 512 MB · **CPU:** 0.5 vCPU · **Replicas:** 1

### 5) Deploy
`Deploy` butonu. İlk build ~60-90s.

## Live Profil — Streamlit + PostgreSQL + Redis

Canlı API entegrasyonu başladığında:

### 1) Compose Moduna Geç
Dokploy'da servis tipini `App` yerine `Compose` seç, `docker-compose.yml` yolunu göster.

### 2) Environment Variables (Dokploy → Service → Env)
```
INSTALL_LIVE_DEPS=true
POSTGRES_DB=goldenb
POSTGRES_USER=goldenb
POSTGRES_PASSWORD=<güçlü-rastgele-şifre>
DATABASE_URL=postgresql://goldenb:<şifre>@postgres:5432/goldenb
REDIS_URL=redis://redis:6379/0
```

### 3) Resource Limits
| Servis | Memory | CPU |
|---|---|---|
| goldenb | 512 MB | 0.5 |
| postgres | 512 MB | 0.5 |
| redis | 256 MB | 0.25 |

### 4) Persistent Volume
- Dokploy otomatik yönetir; compose'daki `postgres-data` ve `redis-data` volume'leri restart sonrası veri kaybını engeller.

### 5) Deploy
Compose olarak deploy et. Üç servis birlikte ayağa kalkar. `goldenb` servisi `postgres` ve `redis` ayakta olana kadar bekler (healthcheck).

## Lokal Test

```bash
# Sadece app
docker compose up --build
# → http://localhost:8501

# Full stack (live)
INSTALL_LIVE_DEPS=true docker compose --profile live up --build
# → app:8501, postgres:5432, redis:6379
```

## Sorun Giderme

| Sorun | Çözüm |
|---|---|
| Container başlamıyor | `requirements.txt` / `requirements-live.txt` versiyon uyumsuzluğu; build logları kontrol et |
| Healthcheck fail | Port 8501 kapalı; container loglarında streamlit startup hatası var mı bak |
| NBA veri gelmiyor | stats.nba.com outbound HTTPS engellenmiş olabilir; container içinden `curl https://stats.nba.com` test et |
| EuroLeague 403 | `EUROLEAGUE_HEADERS` zaten kodda, dokunma; VPN/firewall kontrol et |
| Postgres bağlanmıyor | DATABASE_URL doğru mu? Container adı `postgres` (compose service adı) |
| Redis bağlanmıyor | REDIS_URL doğru mu? Container adı `redis` |
| `db.py` veya `cache.py` NoOp dönüyor | Servisler ayakta mı? `db.is_available()` / `cache.is_available()` ile test et |

## Ölçeklendirme Yol Haritası

### Şu an (MVP)
- Tek Streamlit worker
- Stateless oturum
- Anlık tahmin + backtest

### Aşama 1 — Canlı Skor Feed (yakın gelecek)
- Dış API ile her 10s polling
- `cache.k_live_score(game_id)` ile son skoru Redis'te tut
- `db.save_prediction()` ile her tahmini Postgres'e yaz
- Sayfa yenileyince `db.recent_predictions(50)` ile son 50 tahmini göster

### Aşama 2 — Çok Kullanıcı (uzak gelecek)
- Postgres'te `users` tablosu + auth
- Bias_weight ve öğrenme geçmişi kullanıcıya özel
- Redis pub/sub ile canlı anomali yayını

### Aşama 3 — Yatay Ölçekleme
- Streamlit worker sayısını 3-5'e çıkar
- Redis pub/sub ile worker'lar arası senkronizasyon
- Postgres read replica
- CDN ön yüz
