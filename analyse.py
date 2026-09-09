"""
analyse.py
==========
Modul statistik & analisis sentimen/naratif harian untuk GPS Content Generator.

Apa yang dibuat:
1. Baca fail master CSV (format sama seperti "2026 Grid view": Tarikh, Link Berita,
   Tajuk Berita, Tag, Siapa 1?, Parti 1, Siapa 2?, Parti 2, Tags).
2. Kira statistik: bilangan berita ikut kategori (Tag), jumlah sebutan setiap
   pemimpin, jumlah sebutan setiap parti - keseluruhan & 7 hari terkini.
3. Kesan naratif "trending" (kategori yang tiba-tiba naik berbanding purata biasa).
4. Guna Claude (Haiku - murah) SEKALI SAHAJA setiap hari untuk:
   - beri skor/label sentimen keseluruhan hari itu
   - kaitkan naratif yang trending dengan sentimen & cadangkan insight ringkas
5. Simpan output sebagai JSON (untuk dashboard/Drive) + Markdown (untuk dibaca
   content creator/CEO terus).

Kos: 1 panggilan Claude Haiku sehari sahaja untuk bahagian sentimen/naratif -
bukan sekali per-artikel, supaya kos kekal rendah walaupun data makin banyak.
"""

import os
import json
from datetime import datetime, timedelta
from collections import Counter

import pandas as pd

MALAY_MONTHS = {
    'jan': 1, 'feb': 2, 'mac': 3, 'apr': 4, 'mei': 5, 'jun': 6,
    'jul': 7, 'ogo': 8, 'ogos': 8, 'sep': 9, 'okt': 10, 'nov': 11, 'dis': 12
}


def parse_malay_date(value):
    """Parse tarikh dalam format '8 Jun 2026' (Bahasa Melayu) -> pandas Timestamp."""
    if pd.isna(value):
        return pd.NaT
    try:
        day, month, year = str(value).strip().split()
        key = month.lower()[:4] if month.lower()[:4] in MALAY_MONTHS else month.lower()[:3]
        return pd.Timestamp(year=int(year), month=MALAY_MONTHS[key], day=int(day))
    except Exception:
        return pd.NaT


def load_master_csv(path):
    """Load & bersihkan CSV master (grid-view style, tarikh hanya diisi sekali per hari)."""
    df = pd.read_csv(path, encoding='utf-8-sig')
    df['Tarikh'] = df['Tarikh'].ffill()
    df['Tarikh_parsed'] = df['Tarikh'].apply(parse_malay_date)

    n_failed = df['Tarikh_parsed'].isna().sum()
    if n_failed:
        print(f"⚠️ {n_failed} baris gagal parse tarikh - sila semak format dalam CSV master")

    return df


def compute_stats(df, days_window=7):
    """Kira statistik kategori, pemimpin & parti - keseluruhan dan 'trending' (window terkini)."""
    latest_date = df['Tarikh_parsed'].max()
    window_start = latest_date - timedelta(days=days_window)

    df_recent = df[df['Tarikh_parsed'] >= window_start]
    df_baseline = df[df['Tarikh_parsed'] < window_start]

    def top_counts(frame, col_a, col_b=None, top_n=15, is_party=False):
        series = frame[col_a].dropna()
        if col_b:
            series = pd.concat([series, frame[col_b].dropna()])
        series = series.astype(str).str.strip()
        series = series[series != ""]
        if is_party:
            series = series.str.upper()
        return Counter(series).most_common(top_n)

    stats = {
        "generated_at": datetime.now().isoformat(),
        "data_range": {
            "min_date": str(df['Tarikh_parsed'].min().date()) if df['Tarikh_parsed'].notna().any() else None,
            "max_date": str(latest_date.date()) if pd.notna(latest_date) else None,
            "total_articles": int(len(df)),
        },
        "kategori_keseluruhan": top_counts(df, 'Tag', top_n=20),
        "pemimpin_keseluruhan": top_counts(df, 'Siapa 1?', 'Siapa 2?', top_n=20),
        "parti_keseluruhan": top_counts(df, 'Parti 1', 'Parti 2', top_n=20, is_party=True),
        f"kategori_{days_window}hari_terkini": top_counts(df_recent, 'Tag', top_n=15),
        f"pemimpin_{days_window}hari_terkini": top_counts(df_recent, 'Siapa 1?', 'Siapa 2?', top_n=15),
        f"parti_{days_window}hari_terkini": top_counts(df_recent, 'Parti 1', 'Parti 2', top_n=15, is_party=True),
    }

    # Kesan trending: kategori yang kadar sebutan/hari naik ketara berbanding baseline
    trending = detect_trending_tags(df_recent, df_baseline, days_window)
    stats["naratif_trending"] = trending

    return stats


def detect_trending_tags(df_recent, df_baseline, days_window):
    """Bandingkan kadar sebutan/hari setiap Tag: window terkini vs baseline sebelumnya."""
    baseline_days = df_baseline['Tarikh_parsed'].nunique() or 1
    recent_days = df_recent['Tarikh_parsed'].nunique() or 1

    recent_rate = df_recent['Tag'].value_counts() / recent_days
    baseline_rate = df_baseline['Tag'].value_counts() / baseline_days

    trending = []
    for tag, rate in recent_rate.items():
        base = baseline_rate.get(tag, 0.0)
        if rate >= 1.0 and rate > base * 1.5:
            trending.append({
                "tag": tag,
                "kadar_terkini_per_hari": round(rate, 2),
                "kadar_baseline_per_hari": round(base, 2),
                "peningkatan_x": round(rate / base, 1) if base > 0 else None,
            })

    trending.sort(key=lambda x: x["kadar_terkini_per_hari"], reverse=True)
    return trending[:10]


def generate_ai_insight(df, stats, api_key, model="claude-haiku-4-5-20251001"):
    """Satu panggilan Claude sehari: sentimen + kaitan naratif trending, untuk brief content team."""
    import anthropic

    latest_date = stats["data_range"]["max_date"]
    todays = df[df['Tarikh_parsed'] == pd.Timestamp(latest_date)] if latest_date else df.tail(20)

    headlines = "\n".join(f"- {t}" for t in todays['Tajuk Berita'].dropna().tolist()[:40])
    trending_txt = "\n".join(
        f"- {t['tag']} (naik {t['peningkatan_x']}x)" if t['peningkatan_x'] else f"- {t['tag']} (baru)"
        for t in stats["naratif_trending"]
    ) or "Tiada naratif melonjak ketara hari ini."

    prompt = f"""Anda seorang analis media untuk pasukan kandungan GPS. Berdasarkan tajuk berita
tempatan hari ini dan naratif yang sedang trending, buat ringkasan analisis (BUKAN cadangan
posting - itu langkah lain):

TAJUK BERITA HARI INI:
{headlines}

NARATIF TRENDING (berbanding purata biasa):
{trending_txt}

Berikan dalam format ini, ringkas dan padat:

**SENTIMEN KESELURUHAN HARI INI:** [positif/negatif/bercampur/neutral - 1 ayat sebab]

**KAITAN NARATIF & SENTIMEN:** [2-3 ayat - naratif mana yang mendorong sentimen ini, dan kenapa]

**ISU BERISIKO/PERLU PANTAU:** [1-2 ayat jika ada isu sensitif yang perlu perhatian]
"""

    client = anthropic.Anthropic(api_key=api_key)
    response = client.messages.create(
        model=model,
        max_tokens=500,
        messages=[{"role": "user", "content": prompt}],
    )
    return response.content[0].text


def save_report(stats, ai_insight, out_dir="output"):
    os.makedirs(out_dir, exist_ok=True)
    date_tag = stats["data_range"]["max_date"] or datetime.now().strftime("%Y-%m-%d")

    json_path = os.path.join(out_dir, f"statistik_{date_tag}.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(stats, f, ensure_ascii=False, indent=2, default=str)

    md_path = os.path.join(out_dir, f"laporan_{date_tag}.md")
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(f"# Laporan Statistik & Sentimen - {date_tag}\n\n")
        f.write(f"Jumlah artikel dalam data: {stats['data_range']['total_articles']}\n\n")

        f.write("## Analisis Sentimen & Naratif\n\n")
        f.write((ai_insight or "_(tiada ANTHROPIC_API_KEY - langkau analisis AI)_") + "\n\n")

        f.write("## Naratif Trending (berbanding purata biasa)\n\n")
        for t in stats["naratif_trending"]:
            naik = f"{t['peningkatan_x']}x" if t['peningkatan_x'] else "baru"
            f.write(f"- **{t['tag']}** — naik {naik} ({t['kadar_terkini_per_hari']} berita/hari)\n")

        f.write("\n## Top Pemimpin (7 hari terkini)\n\n")
        for name, count in stats.get("pemimpin_7hari_terkini", []):
            f.write(f"- {name}: {count}\n")

        f.write("\n## Top Parti (7 hari terkini)\n\n")
        for name, count in stats.get("parti_7hari_terkini", []):
            f.write(f"- {name}: {count}\n")

        f.write("\n## Top Kategori Keseluruhan\n\n")
        for name, count in stats.get("kategori_keseluruhan", [])[:15]:
            f.write(f"- {name}: {count}\n")

    print(f"💾 Statistik disimpan: {json_path}")
    print(f"💾 Laporan disimpan: {md_path}")
    return json_path, md_path


def main(csv_path="data/master_berita.csv"):
    print("=" * 60)
    print("📊 GPS Content Generator - Modul Statistik & Sentimen")
    print("=" * 60)

    df = load_master_csv(csv_path)
    stats = compute_stats(df)

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    ai_insight = None
    if api_key:
        print("🤖 Menjana analisis sentimen & naratif...")
        try:
            ai_insight = generate_ai_insight(df, stats, api_key)
        except Exception as e:
            print(f"❌ Ralat AI insight: {e}")
    else:
        print("⚠️ ANTHROPIC_API_KEY tidak dijumpai - langkau analisis AI")

    save_report(stats, ai_insight)
    print("✨ Selesai.")


if __name__ == "__main__":
    import sys
    path = sys.argv[1] if len(sys.argv) > 1 else "data/master_berita.csv"
    main(path)
