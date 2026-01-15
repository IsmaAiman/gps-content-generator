import feedparser
import anthropic
import os
from datetime import datetime
import json
import time

# Your organization's narratives/focus areas
NARRATIVES = """
Gerakan Pengundi Sedar focuses on:
- Electoral transparency and fairness
- Voter education and empowerment
- Government accountability
- Anti-corruption efforts
- Democratic participation
- Youth political engagement
"""

# Malaysian news RSS feeds
NEWS_FEEDS = [
    "https://www.malaysiakini.com/rss/en/news.rss",
    "https://www.thestar.com.my/rss/News/Nation/",
    "https://www.freemalaysiatoday.com/feed/",
]

def fetch_news():
    """Fetch latest news from RSS feeds"""
    articles = []
    
    for feed_url in NEWS_FEEDS:
        try:
            print(f"📡 Fetching from {feed_url}")
            feed = feedparser.parse(feed_url)
            for entry in feed.entries[:10]:  # Get 10 latest from each
                articles.append({
                    'title': entry.title,
                    'link': entry.link,
                    'published': entry.get('published', 'N/A'),
                    'summary': entry.get('summary', entry.get('description', ''))[:500]
                })
            time.sleep(1)  # Be nice to servers
        except Exception as e:
            print(f"❌ Error fetching {feed_url}: {e}")
    
    print(f"✅ Found {len(articles)} total articles")
    return articles

def analyze_with_claude(articles):
    """Use Claude to filter and analyze relevant articles"""
    
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("❌ Error: ANTHROPIC_API_KEY not found in environment variables")
        return None
    
    client = anthropic.Anthropic(api_key=api_key)
    
    # Step 1: Filter relevant articles (using cheap Haiku)
    print("🔍 Filtering relevant articles with Claude Haiku...")
    
    articles_text = "\n\n".join([
        f"[{i}] {a['title']}\n{a['summary']}"
        for i, a in enumerate(articles)
    ])
    
    filter_prompt = f"""Given these Malaysian news articles, identify which ones are relevant to:

{NARRATIVES}

Articles:
{articles_text}

Return ONLY a JSON array of article numbers that are relevant. Example: [0, 3, 7, 12]"""

    try:
        filter_response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=500,
            messages=[{"role": "user", "content": filter_prompt}]
        )
        
        relevant_indices = json.loads(filter_response.content[0].text.strip())
        print(f"✅ Found {len(relevant_indices)} relevant articles")
    except Exception as e:
        print(f"⚠️ Filter error: {e}, using first 5 articles as fallback")
        relevant_indices = [i for i in range(min(5, len(articles)))]
    
    relevant_articles = [articles[i] for i in relevant_indices if i < len(articles)]
    
    if not relevant_articles:
        print("ℹ️ No relevant articles found")
        return None
    
    # Step 2: Generate content for relevant articles (using Sonnet)
    print(f"✍️ Generating content for {len(relevant_articles[:5])} articles with Claude Sonnet...")
    content_results = []
    
    for idx, article in enumerate(relevant_articles[:5], 1):  # Limit to 5 to save costs
        print(f"  Processing {idx}/5: {article['title'][:50]}...")
        
        content_prompt = f"""As Gerakan Pengundi Sedar (a Malaysian voter awareness organization), analyze this news:

Title: {article['title']}
Summary: {article['summary']}
Link: {article['link']}

Our focus areas:
{NARRATIVES}

Provide:
1. Why this matters to Malaysian voters (2-3 sentences)
2. Key talking points (3-4 bullets)
3. Suggested social media post (concise, engaging, under 280 chars)
4. Poster design brief (visual concept, text overlay, color mood)

Be bold, clear, and action-oriented. Write in a tone that empowers citizens."""

        try:
            content_response = client.messages.create(
                model="claude-sonnet-4-5-20250929",
                max_tokens=1500,
                messages=[{"role": "user", "content": content_prompt}]
            )
            
            content_results.append({
                'article': article,
                'content': content_response.content[0].text
            })
        except Exception as e:
            print(f"  ❌ Error generating content: {e}")
    
    print(f"✅ Generated {len(content_results)} content briefs")
    return content_results

def save_results(results):
    """Save results to a markdown file"""
    if not results:
        print("ℹ️ No results to save")
        return
    
    # Create output directory if it doesn't exist
    os.makedirs('output', exist_ok=True)
    
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M")
    filename = f"output/content_{timestamp}.md"
    
    with open(filename, 'w', encoding='utf-8') as f:
        f.write(f"# Gerakan Pengundi Sedar - Content Brief\n")
        f.write(f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M MYT')}\n\n")
        f.write("---\n\n")
        
        for i, result in enumerate(results, 1):
            f.write(f"## Article {i}: {result['article']['title']}\n\n")
            f.write(f"**Source:** {result['article']['link']}\n\n")
            f.write(f"**Published:** {result['article']['published']}\n\n")
            f.write(result['content'])
            f.write("\n\n---\n\n")
    
    print(f"💾 Content brief saved to {filename}")
    
    # Also print to console for Railway logs
    print("\n" + "="*60)
    print("CONTENT PREVIEW:")
    print("="*60)
    with open(filename, 'r', encoding='utf-8') as f:
        print(f.read()[:500] + "...\n(see full file in output directory)")
    
    return filename

def main():
    print("="*60)
    print("🚀 Gerakan Pengundi Sedar - Content Generator")
    print(f"⏰ Run Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S MYT')}")
    print("="*60 + "\n")
    
    print("🔍 Step 1: Fetching latest Malaysian news...")
    articles = fetch_news()
    
    if not articles:
        print("❌ No articles found. Exiting.")
        return
    
    print(f"\n🤖 Step 2: Analyzing with Claude AI...")
    results = analyze_with_claude(articles)
    
    print(f"\n💾 Step 3: Saving results...")
    save_results(results)
    
    print("\n✨ Done! Check the output folder for content briefs.")
    print("="*60)

if __name__ == "__main__":
    main()
