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


def safe_expand_url(url):
    """Safely expands short links and fetches page metadata without raising exceptions."""
    final_url = url
    scraped_title = None
    scraped_image_url = None

    headers = {
        "User-Agent": "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Mobile Safari/537.36"
    }

    try:
        session = requests.Session()
        resp = session.get(url, headers=headers, allow_redirects=True, timeout=8)
        if resp.ok:
            final_url = resp.url
            html = resp.text

            # Extract og:title
            tm = re.search(r'<meta[^>]*property=["\']og:title["\'][^>]*content=["\'](.*?)["\']', html, re.I)
            if not tm:
                tm = re.search(r'<meta[^>]*content=["\'](.*?)["\'][^>]*property=["\']og:title["\']', html, re.I)
            if tm:
                scraped_title = tm.group(1).strip()

            # Extract og:image
            im = re.search(r'<meta[^>]*property=["\']og:image["\'][^>]*content=["\'](.*?)["\']', html, re.I)
            if not im:
                im = re.search(r'<meta[^>]*content=["\'](.*?)["\'][^>]*property=["\']og:image["\']', html, re.I)
            if im:
                scraped_image_url = im.group(1).strip()

            if scraped_title:
                scraped_title = re.sub(r'(?i)(\||\-|\:)\s*(Flipkart|Amazon|Myntra|Ajio).*$', '', scraped_title).strip()
    except Exception as e:
        print(f"  [!] Soft warning on expanding link ({url}): {e}")

    return final_url, scraped_title, scraped_image_url


def build_price_history_url(expanded_url):
    """Converts an expanded store URL into a PriceHistoryApp search link."""
    if expanded_url and expanded_url.startswith("http") and "pricehistory" not in expanded_url:
        encoded_target = urllib.parse.quote(expanded_url, safe='')
        return f"https://pricehistoryapp.com/search?q={encoded_target}"
    return DEFAULT_PRICE_HISTORY_LINK


def get_product_emoji(text):
    t = text.lower()
    if any(k in t for k in ["cashew", "kaju", "dry fruit", "almond", "protein", "fitness", "treadmill", "cycle", "supplement", "whey"]):
        return "🥔" if "cashew" in t or "kaju" in t else "🏋️"
    elif any(k in t for k in ["watch", "clock", "smartwatch", "analog", "digital", "chronograph", "titan", "fastrack", "casio", "noise", "boat"]):
        return "⌚"
    elif any(k in t for k in ["phone", "mobile", "iphone", "samsung", "oneplus", "realme", "redmi", "5g", "smartphone", "charger", "poco", "vivo", "oppo"]):
        return "📱"
    elif any(k in t for k in ["shoe", "sneaker", "footwear", "sandal", "boot", "slipper", "crocs", "bata", "campus", "sparx"]):
        return "👟"
    elif any(k in t for k in ["laptop", "macbook", "computer", "pc", "monitor", "keyboard", "mouse", "asus", "hp", "dell", "lenovo"]):
        return "💻"
    elif any(k in t for k in ["headphone", "earphone", "airpods", "tws", "earbuds", "audio", "speaker", "soundbar", "jbl", "sony"]):
        return "🎧"
    elif any(k in t for k in ["shirt", "tshirt", "t-shirt", "jeans", "trouser", "dress", "cloth", "apparel", "kurta", "saree", "jacket"]):
        return "👕"
    elif any(k in t for k in ["trimmer", "shaver", "grooming", "makeup", "lipstick", "perfume", "serum", "shampoo", "philips"]):
        return "💄"
    elif any(k in t for k in ["bag", "backpack", "trolley", "suitcase", "luggage", "wallet"]):
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
        
        if line_clean and not any(ign in line_clean.lower() for ign in ["buy more save more", "add 5 qty", "use 200 supercoins"]):
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
            deal_link = url # Keeps original short affiliate link
            
    if not deal_link:
        print("  [-] Skipped: No product link found in message.")
        return

    # Safely attempt short link expansion for Price History and photo scraping
    expanded_url, scraped_title, scraped_image_url = safe_expand_url(deal_link)

    # Generate Price History URL using expanded link if available
    if explicit_price_history_link:
        price_history_link = explicit_price_history_link
    else:
        price_history_link = build_price_history_url(expanded_url)

    # Format title & caption using original deal_link
    title, emoji = extract_clean_title(raw_text, deal_link, scraped_title)
    caption = format_caption(title, emoji, deal_link)
    
    posted = False
    photos = msg.get("photo")
    
    # Priority 1: Direct photo from Staging channel message
    if photos:
        largest_photo = photos[-1]
        file_url = get_telegram_file_url(largest_photo["file_id"])
        if file_url:
            posted = post_photo(file_url, caption, price_history_link)
            
    # Priority 2: Scraped product image
    if not posted and scraped_image_url:
        posted = post_photo(scraped_image_url, caption, price_history_link)

    # Priority 3: Text post
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
                continue
                
            chat_id = str(msg.get("chat", {}).get("id"))
            if chat_id != str(STAGING_CHAT_ID):
                continue
                
            msg_id = msg.get("message_id")
            if msg_id in processed_ids:
                print(f"  [-] Skipped already processed message ID: {msg_id}")
                continue
                
            print(f"--> Processing Staging Message ID: {msg_id}")
            
            # Isolated execution per message prevents single-post failures from breaking queue
            try:
                process_message(msg)
            except Exception as pe:
                print(f"  [!] Error processing message {msg_id}: {pe}")
            
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
    
