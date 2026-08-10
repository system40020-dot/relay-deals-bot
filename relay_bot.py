import os
import json
import re
import random
import requests
import urllib.parse

# ================= CONFIGURATION =================
RELAY_BOT_TOKEN = os.getenv("RELAY_BOT_TOKEN", "YOUR_RELAY_BOT_TOKEN")
MAIN_BOT_TOKEN = os.getenv("MAIN_BOT_TOKEN", "YOUR_MAIN_BOT_TOKEN")

STAGING_CHAT_ID = os.getenv("STAGING_CHAT_ID", "-100xxxxxxxxx")
MAIN_CHAT_ID = os.getenv("MAIN_CHAT_ID", "-100xxxxxxxxx")

CHANNEL_HANDLE = "@loot_hacked" 

DEFAULT_PRICE_HISTORY_LINK = "https://pricehistoryapp.com/"

DEAL_HEADERS = [
    "⚡ LIGHTNING DEAL ⚡",
    "📉 LOWEST PRICE EVER 📉",
    "🔥 LOOT DEAL OF THE DAY 🔥",
    "💥 SUPER SAVER DEAL 💥",
    "🚨 HOT DEAL ALERT 🚨"
]

STATE_FILE = "state.json"


# ================= STATE MANAGEMENT =================
def load_state():
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r") as f:
                data = json.load(f)
                if isinstance(data.get("processed_ids"), list):
                    return data
        except Exception as e:
            print(f"Error loading state file: {e}")
            
    return {"processed_ids": [], "last_update_id": 0}


def save_state(state):
    try:
        with open(STATE_FILE, "w") as f:
            json.dump(state, f, indent=2)
    except Exception as e:
        print(f"Error saving state file: {e}")


# ================= LINK & SCRAPING UTILITIES =================
def extract_links_and_entities(msg):
    text = msg.get("caption") or msg.get("text") or ""
    entities = msg.get("caption_entities") or msg.get("entities") or []
    
    extracted_urls = []
    urls_in_text = re.findall(r'https?://[^\s>"]+', text)
    extracted_urls.extend(urls_in_text)
    
    for entity in entities:
        if entity.get("type") == "text_link" and "url" in entity:
            extracted_urls.append(entity["url"])
            
    unique_urls = []
    for url in extracted_urls:
        clean_url = url.rstrip(".,;!)")
        if clean_url not in unique_urls:
            unique_urls.append(clean_url)
            
    return unique_urls


def parse_title_from_url_slug(url):
    """Extracts product title directly from Flipkart/Amazon URL slugs."""
    try:
        fk_match = re.search(r'flipkart\.com/(?:dl/)?([^/]+)/(?:p|dp)/', url, re.IGNORECASE)
        if fk_match:
            slug = fk_match.group(1)
            title = slug.replace('-', ' ').strip()
            if len(title) > 3:
                return title.title()

        amz_match = re.search(r'amazon\.[a-z.]+/(?:[^/]+/)?dp/([^/]+)', url, re.IGNORECASE)
        if amz_match:
            slug = amz_match.group(1)
            if not slug.startswith('B0') and len(slug) > 3:
                return slug.replace('-', ' ').strip().title()
    except Exception as e:
        print(f"  [!] URL slug parsing error: {e}")
        
    return None


def expand_and_scrape_url(url):
    """Expands short URLs (fkrt.cc, amzn.to) and fetches page metadata & og:image."""
    scraped_title = None
    scraped_image_url = None
    final_url = url

    headers = {
        "User-Agent": "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Mobile Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5"
    }

    try:
        session = requests.Session()
        resp = session.get(url, headers=headers, allow_redirects=True, timeout=12)
        final_url = resp.url
        html = resp.text

        # 1. Extract og:title
        title_match = re.search(r'<meta[^>]*property=["\']og:title["\'][^>]*content=["\'](.*?)["\']', html, re.IGNORECASE)
        if not title_match:
            title_match = re.search(r'<meta[^>]*content=["\'](.*?)["\'][^>]*property=["\']og:title["\']', html, re.IGNORECASE)
        if title_match:
            scraped_title = title_match.group(1).strip()

        # 2. Extract og:image
        img_match = re.search(r'<meta[^>]*property=["\']og:image["\'][^>]*content=["\'](.*?)["\']', html, re.IGNORECASE)
        if not img_match:
            img_match = re.search(r'<meta[^>]*content=["\'](.*?)["\'][^>]*property=["\']og:image["\']', html, re.IGNORECASE)
        if img_match:
            scraped_image_url = img_match.group(1).strip()

        if scraped_title:
            scraped_title = re.sub(r'(?i)(\||\-|\:)\s*(Flipkart|Amazon|Myntra|Ajio).*$', '', scraped_title).strip()

        if not scraped_title or scraped_title.lower() in ["flipkart", "amazon"]:
            scraped_title = parse_title_from_url_slug(final_url)

    except Exception as e:
        print(f"  [!] Web expansion/scraping warning ({e}); using direct URL parsing.")
        scraped_title = parse_title_from_url_slug(url)

    return final_url, scraped_title, scraped_image_url


def build_price_history_url(expanded_url):
    """Converts an expanded store URL into a direct PriceHistoryApp search link."""
    if not expanded_url or not expanded_url.startswith("http"):
        return DEFAULT_PRICE_HISTORY_LINK
    
    encoded_target = urllib.parse.quote(expanded_url, safe='')
    return f"https://pricehistoryapp.com/search?q={encoded_target}"


def get_product_emoji(text):
    t = text.lower()
    if any(k in t for k in ["protein", "yeast", "fitness", "treadmill", "walkpad", "cycle", "gym", "supplement", "creatine", "whey"]):
        return "🏋️" if "cycle" not in t else "🚲"
    elif any(k in t for k in ["watch", "clock", "smartwatch", "analog", "digital", "chronograph", "titan", "fastrack", "casio", "noise", "boat", "fire-boltt", "timex", "fossil"]):
        return "⌚"
    elif any(k in t for k in ["phone", "mobile", "iphone", "samsung", "oneplus", "realme", "redmi", "5g", "smartphone", "charger", "powerbank", "poco", "vivo", "oppo"]):
        return "📱"
    elif any(k in t for k in ["shoe", "sneaker", "footwear", "sandal", "boot", "slipper", "heels", "crocs", "bata", "campus", "sparx"]):
        return "👟"
    elif any(k in t for k in ["laptop", "macbook", "computer", "pc", "monitor", "keyboard", "mouse", "asus", "hp", "dell", "lenovo"]):
        return "💻"
    elif any(k in t for k in ["headphone", "earphone", "airpods", "tws", "earbuds", "audio", "speaker", "soundbar", "jbl", "sony", "boult"]):
        return "🎧"
    elif any(k in t for k in ["shirt", "tshirt", "t-shirt", "jeans", "trouser", "dress", "cloth", "apparel", "kurta", "saree", "jacket", "allen solly", "puma", "adidas", "nike"]):
        return "👕"
    elif any(k in t for k in ["trimmer", "shaver", "grooming", "makeup", "lipstick", "perfume", "serum", "shampoo", "skincare", "philips", "beardo"]):
        return "💄"
    elif any(k in t for k in ["bag", "backpack", "trolley", "suitcase", "luggage", "wallet", "american tourister", "skybags", "safari"]):
        return "🎒"
    else:
        return "🛍️"


def extract_clean_title(raw_text, deal_link, scraped_title):
    lines = [line.strip() for line in raw_text.split("\n") if line.strip()]
    valid_text_lines = []

    for line in lines:
        if re.match(r'^https?://[^\s]+$', line.strip()):
            continue
            
        if any(hdr in line.lower() for hdr in ["earnkaro", "grab deals", "loot deals", "join for more"]):
            continue

        line_no_url = re.sub(r'https?://[^\s]+', '', line).strip()
        line_clean = re.sub(r'^(GRAB|LOOT|DEAL|OFFER|HOT|SPECIAL)\s*:\s*', '', line_no_url, flags=re.IGNORECASE).strip()
        line_clean = re.sub(r'^[^\w\s]+', '', line_clean).strip()
        
        if line_clean:
            valid_text_lines.append(line_clean)

    if valid_text_lines:
        title = " ".join(valid_text_lines)
    elif scraped_title:
        title = scraped_title
    else:
        title = "SPECIAL OFFER DEAL"

    emoji = get_product_emoji(raw_text + " " + title)
    return title.upper(), emoji


def format_caption(title, emoji, deal_link):
    header = random.choice(DEAL_HEADERS)
    
    caption_lines = [
        f"<b>{header}</b>\n",
        f"👀 {emoji} <b>{title}</b>\n",
        f"🛒 <b>BUY NOW:</b> {deal_link}\n",
        f"📢 <b>JOIN FOR MORE DEALS:</b> {CHANNEL_HANDLE}"
    ]
    
    full_caption = "\n".join(caption_lines)
    
    if len(full_caption) > 1000:
        short_title = title[:120] + "..." if len(title) > 120 else title
        return (
            f"<b>{header}</b>\n\n"
            f"👀 {emoji} <b>{short_title}</b>\n\n"
            f"🛒 <b>BUY NOW:</b> {deal_link}\n\n"
            f"📢 <b>JOIN:</b> {CHANNEL_HANDLE}"
        )
        
    return full_caption


def create_price_history_button(price_history_link):
    return json.dumps({
        "inline_keyboard": [
            [
                {
                    "text": "📉 Price History 📉",
                    "url": price_history_link
                }
            ]
        ]
    })


# ================= TELEGRAM API ACTIONS =================
def get_telegram_file_url(file_id):
    url = f"https://api.telegram.org/bot{RELAY_BOT_TOKEN}/getFile"
    try:
        resp = requests.get(url, params={"file_id": file_id}, timeout=10)
        if resp.ok:
            file_path = resp.json().get("result", {}).get("file_path")
            if file_path:
                return f"https://api.telegram.org/file/bot{RELAY_BOT_TOKEN}/{file_path}"
    except Exception as e:
        print(f"Failed to fetch file URL: {e}")
    return None


def post_photo(image_url, caption, price_history_link):
    url = f"https://api.telegram.org/bot{MAIN_BOT_TOKEN}/sendPhoto"
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }
        img_resp = requests.get(image_url, headers=headers, timeout=15)
        img_resp.raise_for_status()
        
        payload = {
            "chat_id": MAIN_CHAT_ID,
            "caption": caption,
            "parse_mode": "HTML",
            "reply_markup": create_price_history_button(price_history_link)
        }
        files = {"photo": ("image.jpg", img_resp.content)}
        
        resp = requests.post(url, data=payload, files=files, timeout=20)
        resp.raise_for_status()
        print("  [✓] Posted photo deal with Price History button successfully.")
        return True
    except Exception as e:
        print(f"  [!] Photo post failed ({e}); falling back to text-only.")
        return False


def post_text(caption, price_history_link):
    url = f"https://api.telegram.org/bot{MAIN_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": MAIN_CHAT_ID,
        "text": caption,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
        "reply_markup": create_price_history_button(price_history_link)
    }
    try:
        resp = requests.post(url, json=payload, timeout=15)
        resp.raise_for_status()
        print("  [✓] Posted text deal successfully.")
        return True
    except Exception as e:
        print(f"  [✗] Failed to post message: {e}")
        return False


# ================= CORE WORKFLOW =================
def process_message(msg):
    raw_text = msg.get("caption") or msg.get("text") or ""
    urls = extract_links_and_entities(msg)
    
    deal_link = None
    explicit_price_history_link = None
    
    for url in urls:
        if any(domain in url.lower() for domain in ["pricehistory", "pricetracker"]):
            explicit_price_history_link = url
        elif not deal_link:
            deal_link = url
            
    if not deal_link:
        print("  [-] Skipped: No product link found in message.")
        return

    # 1. Expand short URL (fkrt.cc) -> returns full expanded store link
    final_url, scraped_title, scraped_image_url = expand_and_scrape_url(deal_link)

    # 2. Build Price History URL from expanded store link (hidden in button)
    if explicit_price_history_link:
        price_history_link = explicit_price_history_link
    else:
        price_history_link = build_price_history_url(final_url)

    # 3. Clean title & caption (BUY NOW uses short deal_link)
    title, emoji = extract_clean_title(raw_text, final_url, scraped_title)
    caption = format_caption(title, emoji, deal_link)
    
    posted = False
    photos = msg.get("photo")
    
    # Priority 1: Direct photo from Staging message
    if photos:
        largest_photo = photos[-1]
        file_url = get_telegram_file_url(largest_photo["file_id"])
        if file_url:
            posted = post_photo(file_url, caption, price_history_link)
            
    # Priority 2: Scraped product image from expanded page
    if not posted and scraped_image_url:
        posted = post_photo(scraped_image_url, caption, price_history_link)

    # Priority 3: Clean text-only post
    if not posted:
        post_text(caption, price_history_link)


def main():
    state = load_state()
    processed_ids = list(state.get("processed_ids", []))
    last_offset = state.get("last_update_id", 0)
    
    print(f"Checking staging channel updates (Starting Offset: {last_offset})...")
    
    url = f"https://api.telegram.org/bot{RELAY_BOT_TOKEN}/getUpdates"
    params = {"offset": last_offset + 1, "timeout": 20}
    
    try:
        resp = requests.get(url, params=params, timeout=25)
        if not resp.ok:
            print(f"Telegram API Error: {resp.text}")
            return
            
        updates = resp.json().get("result", [])
        print(f"--> Received {len(updates)} raw update(s) from Telegram.")
        
        for update in updates:
            last_offset = max(last_offset, update["update_id"])
            
            msg = update.get("channel_post") or update.get("message")
            if not msg:
                print("  [-] Skipped: Update is not a message/post.")
                continue
                
            chat_id = str(msg.get("chat", {}).get("id"))
            if chat_id != str(STAGING_CHAT_ID):
                print(f"  [-] Skipped: Message chat ID ({chat_id}) does not match STAGING_CHAT_ID ({STAGING_CHAT_ID}).")
                continue
                
            msg_id = msg.get("message_id")
            if msg_id in processed_ids:
                print(f"  [-] Skipped: Message ID {msg_id} was already processed.")
                continue
                
            print(f"--> Processing Staging Message ID: {msg_id}")
            process_message(msg)
            
            if msg_id not in processed_ids:
                processed_ids.append(msg_id)
                
    except Exception as e:
        print(f"Error during execution: {e}")
        
    state["processed_ids"] = processed_ids[-200:]
    state["last_update_id"] = last_offset
    save_state(state)
    print("Execution complete.")


if __name__ == "__main__":
    main()
      
