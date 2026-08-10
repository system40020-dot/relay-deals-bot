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


# ================= LINK & METADATA UTILITIES =================
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


def get_canonical_flipkart_url(url):
    """Converts raw expanded store links to clean canonical URLs for Price History."""
    if not url or not url.startswith("http"):
        return None
    if any(short in url.lower() for short in ["/s/", "fkrt.cc", "bitli.in", "bit.ly"]):
        return None

    itm_match = re.search(r'/(?:p|dp)/(itm[a-zA-Z0-9]+)', url)
    pid_match = re.search(r'(pid=[A-Za-z0-9]+)', url)
    
    pid_str = f"?{pid_match.group(1)}" if pid_match else ""
    
    if itm_match:
        return f"https://www.flipkart.com/p/{itm_match.group(1)}{pid_str}"
        
    clean = re.sub(r'https?://dl\.flipkart\.com/(?:dl/)?', 'https://www.flipkart.com/', url)
    clean = re.sub(r'(&|\?)(cmpid|hl_lid|ctx|store|fm|_refId|_appId)=[^&]+', '', clean)
    return clean


def build_price_history_link(canonical_url, title):
    """Builds Price History link. Never returns a 404 page."""
    if canonical_url and ("flipkart.com/p/" in canonical_url or "amazon.in/dp/" in canonical_url):
        encoded = urllib.parse.quote(canonical_url, safe='')
        return f"https://pricehistoryapp.com/search?q={encoded}"
    elif title and title != "SPECIAL OFFER DEAL":
        encoded_title = urllib.parse.quote(title, safe='')
        return f"https://pricehistoryapp.com/search?q={encoded_title}"
    else:
        return DEFAULT_PRICE_HISTORY_LINK


def get_product_emoji(text):
    t = text.lower()
    if any(k in t for k in ["beauty", "decor", "home", "cosmetic", "skin", "cream", "lotion", "makeup"]):
        return "💄" if "beauty" in t or "cosmetic" in t else "🏠"
    elif any(k in t for k in ["headphone", "earphone", "airpods", "tws", "earbuds", "audio", "speaker", "zebronics", "boat", "sony"]):
        return "🎧"
    elif any(k in t for k in ["cashew", "kaju", "dry fruit", "almond", "protein", "fitness", "treadmill", "cycle"]):
        return "🥔" if "cashew" in t or "kaju" in t else "🏋️"
    elif any(k in t for k in ["watch", "clock", "smartwatch", "analog", "titan", "fastrack", "casio"]):
        return "⌚"
    elif any(k in t for k in ["phone", "mobile", "iphone", "samsung", "oneplus", "realme", "redmi", "5g", "poco"]):
        return "📱"
    elif any(k in t for k in ["shoe", "sneaker", "footwear", "sandal", "crocs", "bata"]):
        return "👟"
    elif any(k in t for k in ["laptop", "macbook", "computer", "pc", "monitor", "keyboard"]):
        return "💻"
    elif any(k in t for k in ["shirt", "tshirt", "jeans", "trouser", "dress", "cloth"]):
        return "👕"
    else:
        return "🛍️"


def parse_message_components(raw_text, web_page, deal_link):
    lines = [l.strip() for l in raw_text.split('\n') if l.strip()]
    title_lines = []
    coupon_line = None

    for line in lines:
        if re.match(r'^https?://[^\s]+$', line):
            continue
            
        # Detect Promo / Coupon Code
        if re.search(r'(?i)(use|apply)\s*code\s*:', line) or re.search(r'(?i)^code\s*:', line):
            coupon_line = line.strip()
            continue

        if any(hdr in line.lower() for hdr in ["earnkaro", "grab deals", "loot deals", "join for more"]):
            continue

        line_no_url = re.sub(r'https?://[^\s]+', '', line).strip()
        line_clean = re.sub(r'^(GRAB|LOOT|DEAL|OFFER|HOT|SPECIAL)\s*:\s*', '', line_no_url, flags=re.IGNORECASE).strip()
        line_clean = re.sub(r'^[^\w\s]+', '', line_clean).strip()
        
        if line_clean and not any(ign in line_clean.lower() for ign in ["lighting deal", "lowest price"]):
            title_lines.append(line_clean)

    if title_lines:
        title = " ".join(title_lines).upper()
    elif web_page.get("title"):
        clean_wp = re.sub(r'(?i)(\||\-|\:)\s*(Buy|Online|Flipkart|Amazon|At Best).*$', '', web_page.get("title")).strip()
        title = clean_wp.upper() if len(clean_wp) > 3 else "SPECIAL OFFER DEAL"
    else:
        title = "SPECIAL OFFER DEAL"

    emoji = get_product_emoji(raw_text + " " + title)
    return title, coupon_line, emoji


def format_caption(title, coupon_line, emoji, deal_link):
    header = random.choice(DEAL_HEADERS)
    
    caption_lines = [
        f"<b>{header}</b>\n",
        f"👀 {emoji} <b>{title}</b>\n"
    ]

    if coupon_line:
        caption_lines.append(f"🏷️ <b>{coupon_line.upper()}</b>\n")

    caption_lines.extend([
        f"🛒 <b>BUY NOW:</b> {deal_link}\n",
        f"📢 <b>JOIN FOR MORE DEALS:</b> {CHANNEL_HANDLE}"
    ])
    
    return "\n".join(caption_lines)


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
    web_page = msg.get("web_page") or {}
    
    deal_link = None
    explicit_price_history_link = None
    
    for url in urls:
        if any(domain in url.lower() for domain in ["pricehistory", "pricetracker"]):
            explicit_price_history_link = url
        elif not deal_link:
            deal_link = url # Keeps short link (bitli.in / fkrt.cc)
            
    if not deal_link:
        print("  [-] Skipped: No product link found in message.")
        return

    # Extract expanded URL from Telegram web preview
    telegram_expanded_url = web_page.get("url")
    canonical_url = get_canonical_flipkart_url(telegram_expanded_url or deal_link)

    # Parse Title, Coupon Code, and Emoji
    title, coupon_line, emoji = parse_message_components(raw_text, web_page, deal_link)

    # Build Price History Link
    if explicit_price_history_link:
        price_history_link = explicit_price_history_link
    else:
        price_history_link = build_price_history_link(canonical_url, title)

    # Format Caption with Coupon & short deal link
    caption = format_caption(title, coupon_line, emoji, deal_link)
    
    posted = False
    
    # Priority 1: Direct photo in Staging Channel
    photos = msg.get("photo")
    if photos:
        file_url = get_telegram_file_url(photos[-1]["file_id"])
        if file_url:
            posted = post_photo(file_url, caption, price_history_link)

    # Priority 2: Photo from Telegram cached web_page preview
    if not posted and web_page.get("photo"):
        wp_photos = web_page.get("photo")
        if wp_photos:
            file_url = get_telegram_file_url(wp_photos[-1]["file_id"])
            if file_url:
                posted = post_photo(file_url, caption, price_history_link)

    # Priority 3: Text Post
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
    
    
