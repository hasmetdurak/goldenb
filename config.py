"""
GoldenBet AI - Yapısal Kural Matrisi (Core Structural Rules)
============================================================

Üç katmandan oluşur:

1) Süre ve Periyot Genetiği
   -----------------------
   NBA:        4 çeyrek × 12 dk = 48 dk
   EuroLeague: 4 çeyrek × 10 dk = 40 dk
   EuroCup:    4 çeyrek × 10 dk = 40 dk
   Hücum süresi 24 sn (NBA'de OR sonrası 14 sn'ye sıfırlanır).
   NBA son 2 dk'da mola ve faul taktikleri nedeniyle oyun sık kesilir
   ve skor aniden ivmelenebilir; EuroLeague'de bu etki daha zayıftır.

2) Taktiksel ve Saha İçi Karakter Katmanı (Pace & Space Modifiers)
   ----------------------------------------------------------------
   EuroLeague: defansif 3 sn yok → boyalı alan kalabalık, yarı saha
   set hücumu, kontrolsüz skor fırlaması NBA'ye göre çok daha düşük.
   NBA: erken hızlı hücum, transition, izolasyon → 12-0'lık seriler,
   standart sapma geniş.

3) Kültürel ve Psikolojik Varyans Filtresi (Contextual Tags)
   ---------------------------------------------------------
   Maçın bağlamına göre tempo ve varyans katsayılarını ayarlayan
   etiketler. predict_remaining_game bunları doğrudan uygular.
"""

from __future__ import annotations

from typing import Dict


# -----------------------------------------------------------------------------
# 1) Süre ve Periyot Genetiği
# -----------------------------------------------------------------------------
LEAGUE_TOTAL_MINUTES: Dict[str, int] = {
    "NBA": 48,
    "EUROLEAGUE": 40,
    "EUROCUP": 40,
}

LEAGUE_PERIOD_MINUTES: Dict[str, int] = {
    "NBA": 12,
    "EUROLEAGUE": 10,
    "EUROCUP": 10,
}

LEAGUE_PERIODS: Dict[str, int] = {
    "NBA": 4,
    "EUROLEAGUE": 4,
    "EUROCUP": 4,
}

# Hücum süresi ve son-2-dk akış karakteri (sadece dokümantasyon; motor
# bu sabitleri doğrudan kullanmaz ama bilgi panelinde gösterilir).
LEAGUE_TIMING_NOTES: Dict[str, str] = {
    "NBA": (
        "Shot clock 24s · OR sonrası 14s reset · Son 2 dk'da mola/faul "
        "taktikleriyle skor hızla ivmelenir · Pace & Space yüksek varyans"
    ),
    "EUROLEAGUE": (
        "Shot clock 24s · Yarı saha set hücumu · Defansif 3 sn yok "
        "(boyalı alan kalabalık) · Son 2 dk'da oyun daha az bölünür"
    ),
    "EUROCUP": (
        "Shot clock 24s · EuroLeague temposuna yakın · Daha az mola "
        "· Varyans EuroLeague ile benzer"
    ),
}


# -----------------------------------------------------------------------------
# 2) Taktiksel Karakter Katmanı — Lig Bazında Varyans Çarpanları
# -----------------------------------------------------------------------------
# EuroLeague savunma duvarı → düşük varyans (skor kontrollü akar)
# NBA transition/early-offense → yüksek varyans (seriler mümkün)
LEAGUE_BASE_VARIANCE: Dict[str, float] = {
    "NBA": 1.20,         # Geniş dağılım — transition ve run-and-gun
    "EUROLEAGUE": 0.85,  # Dar dağılım — savunma duvarı, yarı saha
    "EUROCUP": 0.90,     # EuroLeague'e yakın, hafif daha açık
}

LEAGUE_BASE_PACE: Dict[str, float] = {
    "NBA": 1.00,
    "EUROLEAGUE": 1.00,
    "EUROCUP": 1.00,
}


# -----------------------------------------------------------------------------
# 3) Kültürel / Psikolojik Varyans Filtresi — Bağlam Etiketleri
# -----------------------------------------------------------------------------
CONTEXTUAL_MODIFIERS: Dict[str, Dict[str, object]] = {
    "Normal_Season_Match": {
        "pace_multiplier": 1.00,
        "variance_multiplier": 1.00,
        "label": "Normal Sezon Maçı",
        "emoji": "🏀",
        "description": "Standart lig maçı. İstatistiksel ortalamalar doğrudan geçerli.",
    },
    "Derby_Intense": {
        "pace_multiplier": 0.93,
        "variance_multiplier": 0.80,
        "label": "Yüksek Tansiyonlu Derbi",
        "emoji": "🔥",
        "description": (
            "Partizan-Kızılyıldız, Real-Barça gibi derbi maçları. "
            "Sert savunma, düşük tempo, az oynaklık (ALT odaklı)."
        ),
    },
    "Playoff_Elimination_G7": {
        "pace_multiplier": 0.95,
        "variance_multiplier": 0.85,
        "label": "Playoff Eleme Maçı (G7)",
        "emoji": "⚔️",
        "description": (
            "Tamam mı devam mı maçı. Stres yüksek, şut yüzdeleri "
            "düşebilir, hücum süreleri son saniyeye kadar kullanılır."
        ),
    },
    "Revenge_Matchup": {
        "pace_multiplier": 1.05,
        "variance_multiplier": 1.10,
        "label": "İntikam / Kişisel Çekişme",
        "emoji": "😤",
        "description": (
            "Eski takıma karşı oynama veya kişisel rekabet. Tempo ve "
            "bireysel skor eğilimi yüksek, varyans genişler."
        ),
    },
    "Garbage_Time_Heavy": {
        "pace_multiplier": 1.08,
        "variance_multiplier": 1.15,
        "label": "Fark Yüksek · Garbage Time",
        "emoji": "🗑️",
        "description": (
            "Skor farkı açık, son çeyreklerde yedek oyuncular. "
            "Tempo ve bireysel skor yükselir, varyans genişler."
        ),
    },
    "Defensive_Grind": {
        "pace_multiplier": 0.90,
        "variance_multiplier": 0.78,
        "label": "Savunma Öncelikli Düşük Skor",
        "emoji": "🧱",
        "description": (
            "İki takım da savunma odaklı. Toplam skor baseline'ın altında, "
            "ALT baremleri ön plana çıkar."
        ),
    },
}


def get_context_modifier(tag: str) -> Dict[str, object]:
    """Etikete karşılık gelen modifier'ı döndürür; bilinmiyorsa normal sezon."""
    return CONTEXTUAL_MODIFIERS.get(tag, CONTEXTUAL_MODIFIERS["Normal_Season_Match"])


def get_league_variance(league: str) -> float:
    """Lig için temel varyans çarpanını döndürür."""
    return LEAGUE_BASE_VARIANCE.get(league.upper(), 1.0)


def get_league_pace(league: str) -> float:
    """Lig için temel tempo çarpanını döndürür."""
    return LEAGUE_BASE_PACE.get(league.upper(), 1.0)


def get_total_minutes(league: str) -> int:
    """Lig için toplam dakikayı döndürür."""
    return LEAGUE_TOTAL_MINUTES.get(league.upper(), 40)
