import feedparser
import anthropic
import os
from datetime import datetime
import json
import time
import requests

# Load configuration from external file
def load_config():
    """Load configuration from config.json"""
    try:
        with open('config.json', 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        print(f"❌ Error loading config.json: {e}")
        return None

CONFIG = load_config()

def fetch_news():
    """Fetch latest news from RSS feeds"""
    articles = []
    news_feeds = CONFIG.get('news_sources', [])
    
    for feed_url in news_feeds:
        try:
            print(f"📡 Mengambil dari {feed_url}")
            feed = feedparser.parse(feed_url)
            for entry in feed.entries[:10]:  # Get 10 latest from each
                articles.append({
                    'title': entry.title,
                    'link': entry.link,
                    'published': entry.get('published', 'N/A'),
                    'summary': entry.get('summary', entry.get('description', ''))[:500]
                })
            time.sleep(1)
        except Exception as e:
            print(f"❌ Ralat mengambil {feed_url}: {e}")
    
    print(f"✅ Jumpa {len(articles)} artikel")
    return articles

def analyze_with_claude(articles):
    """Use Claude Haiku to filter and analyze relevant articles"""
    
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("❌ Ralat: ANTHROPIC_API_KEY tidak dijumpai")
        return None
    
    client = anthropic.Anthropic(api_key=api_key)
    
    # Build narratives from config
    focus_areas = CONFIG['narratives']['focus_areas']
    narratives_text = "\n".join([f"- {area}" for area in focus_areas])
    
    # Step 1: Filter relevant articles (using Haiku)
    print("🔍 Menapis artikel yang berkaitan dengan Claude Haiku...")
    
    articles_text = "\n\n".join([
        f"[{i}] {a['title']}\n{a['summary']}"
        for i, a in enumerate(articles)
    ])
    
    filter_prompt = f"""Berdasarkan berita-berita Malaysia ini, kenalpasti yang mana berkaitan dengan:

{narratives_text}

Artikel:
{articles_text}

Kembalikan HANYA array JSON nombor artikel yang berkaitan. Contoh: [0, 3, 7, 12]"""

    try:
        filter_response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=500,
            messages=[{"role": "user", "content": filter_prompt}]
        )
        
        relevant_indices = json.loads(filter_response.content[0].text.strip())
        print(f"✅ Jumpa {len(relevant_indices)} artikel yang berkaitan")
    except Exception as e:
        print(f"⚠️ Ralat penapisan: {e}, menggunakan 3 artikel pertama")
        relevant_indices = [i for i in range(min(3, len(articles)))]
    
    relevant_articles = [articles[i] for i in relevant_indices if i < len(articles)]
    
    if not relevant_articles:
        print("ℹ️ Tiada artikel berkaitan dijumpai")
        return None
    
    # Step 2: Generate content (ALSO using Haiku to save cost!)
    max_articles = CONFIG['output_format']['max_articles']
    print(f"✍️ Menjana kandungan untuk {min(len(relevant_articles), max_articles)} artikel dengan Claude Haiku...")
    
    content_results = []
    
    # Build structured prompt from config
    sections = CONFIG['output_format']['sections']
    section_instructions = []
    for section in sections:
        if section.get('format') == 'bullet':
            section_instructions.append(
                f"{section['name']}: {section['instruction']}"
            )
        else:
            section_instructions.append(
                f"{section['name']}: {section['instruction']}"
            )
    
    instructions = "\n".join(section_instructions)
    tone = CONFIG['tone_guidelines']
    
    for idx, article in enumerate(relevant_articles[:max_articles], 1):
        print(f"  Memproses {idx}/{min(len(relevant_articles), max_articles)}: {article['title'][:50]}...")
        
        content_prompt = f"""Sebagai Gerakan Pengundi Sedar, analisa berita ini:

Tajuk: {article['title']}
Ringkasan: {article['summary']}

Fokus kami:
{narratives_text}

PENTING: Ikut format ini DENGAN KETAT. Jangan lebih panjang!

{instructions}

Gaya: {tone['style']}
Nada: {tone['voice']}
Elakkan: {', '.join(tone['avoid'])}

JAWAB DALAM FORMAT INI:

**KEPENTINGAN:**
[2 ayat sahaja]

**ISI UTAMA:**
• [Perkara 1 - maksimum 10 perkataan]
• [Perkara 2 - maksimum 10 perkataan]
• [Perkara 3 - maksimum 10 perkataan]

**POST MEDIA SOSIAL:**
[1 ayat menarik - maksimum 200 aksara]

**KONSEP POSTER:**
[Visual + teks - 1 ayat pendek sahaja]

**PAUTAN:**
{article['link']}"""

        try:
            content_response = client.messages.create(
                model="claude-haiku-4-5-20251001",  # Using Haiku instead of Sonnet!
                max_tokens=800,  # Reduced since we want shorter output
                messages=[{"role": "user", "content": content_prompt}]
            )
            
            content_results.append({
                'article': article,
                'content': content_response.content[0].text
            })
        except Exception as e:
            print(f"  ❌ Ralat menjana kandungan: {e}")
    
    print(f"✅ Berjaya jana {len(content_results)} ringkasan kandungan")
    return content_results

def send_telegram(filename):
    """Send results to multiple Telegram chats"""
    
    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN")
    
    # Get chat IDs from config or environment
    chat_ids = CONFIG.get('telegram', {}).get('chat_ids', [])
    
    # Also check for individual environment variables
    env_chat_ids = []
    for i in range(1, 10):  # Check for TELEGRAM_CHAT_ID_1, _2, _3, etc.
        chat_id = os.environ.get(f"TELEGRAM_CHAT_ID_{i}")
        if chat_id:
            env_chat_ids.append(chat_id)
    
    # Use main TELEGRAM_CHAT_ID if available
    main_chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if main_chat_id:
        env_chat_ids.insert(0, main_chat_id)
    
    # Combine both sources, remove placeholders
    all_chat_ids = [
        cid for cid in (env_chat_ids + chat_ids) 
        if cid and not cid.startswith("CHAT_ID_")
    ]
    
    if not bot_token:
        print("⚠️ TELEGRAM_BOT_TOKEN tidak dijumpai")
        return
    
    if not all_chat_ids:
        print("⚠️ Tiada Chat ID dijumpai")
        return
    
    try:
        print(f"📱 Menghantar ke {len(all_chat_ids)} penerima Telegram...")
        
        # Read the content
        with open(filename, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Send to each chat ID
        for idx, chat_id in enumerate(all_chat_ids, 1):
            # Split if too long (Telegram limit: 4096 chars)
            if len(content) <= 4000:
                messages = [content]
            else:
                messages = [content[i:i+4000] for i in range(0, len(content), 4000)]
            
            # Send each chunk
            for msg_idx, msg in enumerate(messages, 1):
                url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
                data = {
                    "chat_id": chat_id,
                    "text": msg if msg_idx == 1 else f"(Bahagian {msg_idx})\n\n{msg}",
                    "parse_mode": "Markdown"
                }
                response = requests.post(url, json=data)
                
                if response.status_code == 200:
                    print(f"  ✅ Penerima {idx}/{len(all_chat_ids)} - Mesej {msg_idx}/{len(messages)} dihantar")
                else:
                    print(f"  ❌ Ralat untuk chat ID {chat_id}: {response.text}")
                
                time.sleep(0.5)
                
    except Exception as e:
        print(f"❌ Ralat Telegram: {e}")

def save_results(results):
    """Save results to a markdown file"""
    if not results:
        print("ℹ️ Tiada hasil untuk disimpan")
        return
    
    os.makedirs('output', exist_ok=True)
    
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M")
    filename = f"output/kandungan_{timestamp}.md"
    
    with open(filename, 'w', encoding='utf-8') as f:
        f.write(f"# Gerakan Pengundi Sedar - Ringkasan Kandungan\n")
        f.write(f"**Dijana:** {datetime.now().strftime('%d/%m/%Y %H:%M')} MYT\n\n")
        f.write("---\n\n")
        
        for i, result in enumerate(results, 1):
            f.write(f"## 📰 Artikel {i}: {result['article']['title']}\n\n")
            f.write(result['content'])
            f.write("\n\n---\n\n")
    
    print(f"💾 Ringkasan kandungan disimpan ke {filename}")
    
    # Print to Railway logs
    print("\n" + "="*80)
    print("📄 KANDUNGAN PENUH:")
    print("="*80)
    with open(filename, 'r', encoding='utf-8') as f:
        print(f.read())
    print("="*80 + "\n")
    
    # Send via Telegram
    send_telegram(filename)
    
    return filename

def main():
    if not CONFIG:
        print("❌ Tidak dapat memuatkan config.json. Keluar.")
        return
    
    print("="*60)
    print("🚀 Gerakan Pengundi Sedar - Penjana Kandungan")
    print(f"⏰ Masa: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')} MYT")
    print("="*60 + "\n")
    
    print("🔍 Langkah 1: Mengambil berita terkini Malaysia...")
    articles = fetch_news()
    
    if not articles:
        print("❌ Tiada artikel dijumpai. Keluar.")
        return
    
    print(f"\n🤖 Langkah 2: Menganalisa dengan Claude AI...")
    results = analyze_with_claude(articles)
    
    print(f"\n💾 Langkah 3: Menyimpan hasil...")
    save_results(results)
    
    print("\n✨ Selesai! Semak Telegram anda untuk ringkasan kandungan.")
    print("="*60)

if __name__ == "__main__":
    main()
