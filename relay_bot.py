import os
import json
import re
import random
import requests

# ================= CONFIGURATION =================
RELAY_BOT_TOKEN = os.getenv("RELAY_BOT_TOKEN", "YOUR_RELAY_BOT_TOKEN")
MAIN_BOT_TOKEN = os.getenv("MAIN_BOT_TOKEN", "YOUR_MAIN_BOT_TOKEN")

STAGING_CHAT_ID = os.getenv("STAGING_CHAT_ID", "-100xxxxxxxxx")  # Staging Channel ID
MAIN_CHAT_ID = os.getenv("MAIN_CHAT_ID", "-100xxxxxxxxx")        # Target Public Channel ID

# IMPORTANT: Update with your actual channel username/handle
CHANNEL_HANDLE = "@your_actual_channel_username" 

# Default fallback Price History site if no explicit link is provided in the message
DEFAULT_PRICE_HISTORY_LINK = "https://pricehistoryapp.com/"

# Dynamic deal header choices
DEAL_HEADERS = [
    "⚡ LIGHTNING DEAL ⚡",
    "📉 LOWEST PRICE EVER 📉",
    "🔥 LOOT DEAL OF THE DAY 🔥",
    "💥 SUPER SAVER DEAL 💥",
    "🚨 HOT DEAL ALERT 🚨"
]

STATE_FILE = "state.json"
DEBUG_PRINT_UPDATES = False


# ================= STATE MANAGEMENT =================
def load_state():
    """Loads state from file, maintaining an ordered list for processed IDs."""
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
    """Saves current state back to state.json."""
    try:
        with open(STATE_FILE, "w") as f:
            json.dump(state, f, indent=2)
    except Exception as e:
        print(f"Error saving state file: {e}")


# ================= PARSING & FORMATTING =================
def extract_links_and_entities(msg):
    """Extracts plain text URLs and embedded text_link entities."""
    text = msg.get("caption") or msg.get("text") or ""
    entities = msg.get("caption_entities") or msg.get("entities") or []
    
    extracted_urls = []
    
    # 1. Plain text URLs
    urls_in_text = re.findall(r'https?://[^\s]+', text)
    extracted_urls.extend(urls_in_text)
    
    # 2. Embedded text_link entities
    for entity in entities:
        if entity.get("type") == "text_link" and "url" in entity:
            extracted_urls.append(entity["url"])
            
    # Deduplicate while preserving order
    unique_urls = []
    for url in extracted_urls:
        if url not in unique_urls:
            unique_urls.append(url)
            
    return unique_urls


def get_product_emoji(text):
    """Detects product category emoji across major Indian shopping platforms."""
    t = text.lower()
    
    # ⌚ Watches & Smartwatches
    if any(k in t for k in [
        "watch", "clock", "smartwatch", "analog", "digital", "chronograph", 
        "titan", "fastrack", "casio", "noise", "boat", "fire-boltt", "timex", 
        "fossil", "amazfit", "realme watch", "dizo", "crossbeats"
    ]):
        return "⌚"
        
    # 📱 Mobiles, Tablets & Mobile Accessories
    elif any(k in t for k in [
        "phone", "mobile", "iphone", "samsung", "oneplus", "realme", "redmi", 
        "5g", "smartphone", "charger", "powerbank", "adapter", "ipad", "tablet", 
        "poco", "vivo", "oppo", "iqoo", "motorola", "back cover", "case"
    ]):
        return "📱"
        
    # 👟 Footwear & Shoes
    elif any(k in t for k in [
        "shoe", "sneaker", "footwear", "sandal", "boot", "slipper", "heels", 
        "loafers", "crocs", "flats", "flip flop", "woodland", "bata", "campus", "sparx"
    ]):
        return "👟"
        
    # 💻 Laptops & Tech
    elif any(k in t for k in [
        "laptop", "macbook", "computer", "pc", "monitor", "keyboard", "mouse", 
        "asus", "hp", "dell", "lenovo", "acer", "msi", "hard disk", "ssd"
    ]):
        return "💻"
        
    # 🎧 Audio & Headphones
    elif any(k in t for k in [
        "headphone", "earphone", "airpods", "tws", "earbuds", "audio", "speaker", 
        "soundbar", "neckband", "bluetooth", "jbl", "sony", "sennheiser", "boult"
    ]):
        return "🎧"
        
    # 👕 Fashion & Apparel
    elif any(k in t for k in [
        "shirt", "tshirt", "t-shirt", "jeans", "trouser", "dress", "cloth", 
        "apparel", "kurta", "saree", "top", "jacket", "hoodie", "blazer", 
        "allen solly", "van heusen", "louis philippe", "puma", "adidas", "nike", "levis"
    ]):
        return "👕"
        
    # 💄 Beauty & Grooming
    elif any(k in t for k in [
        "trimmer", "shaver", "grooming", "makeup", "lipstick", "perfume", 
        "serum", "shampoo", "lotion", "skincare", "philips", "beardo"
    ]):
        return "💄"
        
    # 🎒 Bags & Luggage
    elif any(k in t for k in [
        "bag", "backpack", "trolley", "suitcase", "luggage", "wallet", "handbag", 
        "american tourister", "skybags", "safari"
    ]):
        return "🎒"
        
    else:
        return "🛍️"


def extract_title_and_emoji(raw_text):
    """Cleans up text, extracts a valid title, and assigns a matching emoji."""
    if not raw_text:
        return "SPECIAL OFFER DEAL", "🛍️"
        
    lines = [line.strip() for line in raw_text.split("\n") if line.strip()]
    clean_lines = []
    
    for line in lines:
        # Strip out HTTP/HTTPS URLs
        line_without_urls = re.sub(r'https?://[^\s]+', '', line).strip()
        # Filter out common header or promo phrases
        line_clean = re.sub(r"(TODAY'S DEAL|Verify|Join|Price trends|Flipkart|Amazon|Myntra|Ajio|LIGHTNING DEAL|LOWEST PRICE EVER)", '', line_without_urls, flags=re.IGNORECASE).strip()
        
        if line_clean:
            clean_lines.append(line_clean)
            
    if clean_lines:
        raw_title = clean_lines[0]
        # Strip extraneous leading icons/emojis from title text
        title = re.sub(r'^[^\w\s]+', '', raw_title).strip()
        if not title:
            title = "SPECIAL OFFER DEAL"
    else:
        title = "SPECIAL OFFER DEAL"

    emoji = get_product_emoji(raw_text + " " + title)
    
    # Capitalize title for bold presentation
    return title.upper(), emoji


def format_caption(title, emoji, deal_link):
    """Formats HTML caption with randomized bold catchy headers and bold title."""
    header = random.choice(DEAL_HEADERS)
    
    caption_lines = [
        f"<b>{header}</b>\n",
        f"👀 {emoji} <b>{title}</b>\n",
        f"🛒 <b>BUY NOW:</b> {deal_link}\n",
        f"📢 <b>JOIN FOR MORE DEALS:</b> {CHANNEL_HANDLE}"
    ]
    
    full_caption = "\n".join(caption_lines)
    
    # Fallback if over Telegram 1024-character caption limit
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
    """Generates Telegram Inline Keyboard Button for Price History."""
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
    """Gets original file URL from Telegram server using Relay Bot token."""
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
    """Downloads image bytes locally and attaches Price History button."""
    url = f"https://api.telegram.org/bot{MAIN_BOT_TOKEN}/sendPhoto"
    try:
        img_resp = requests.get(image_url, timeout=15)
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
    """Posts text-only message with disabled link preview and Price History button."""
    url = f"https://api.telegram.org/bot{MAIN_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": MAIN_CHAT_ID,
        "text": caption,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,  # Disables ugly blurred link preview boxes
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
    """Processes each update received from Staging channel."""
    raw_text = msg.get("caption") or msg.get("text") or ""
    urls = extract_links_and_entities(msg)
    
    deal_link = None
    price_history_link = None
    
    for url in urls:
        if any(domain in url.lower() for domain in ["pricehistory", "pricetracker"]):
            price_history_link = url
        elif not deal_link:
            deal_link = url
            
    if not deal_link:
        print("  [-] Skipped: No product link found in message.")
        return

    # Fallback Price History URL if not provided
    if not price_history_link:
        price_history_link = DEFAULT_PRICE_HISTORY_LINK

    title, emoji = extract_title_and_emoji(raw_text)
    caption = format_caption(title, emoji, deal_link)
    
    posted = False
    photos = msg.get("photo")
    
    if photos:
        largest_photo = photos[-1]
        file_url = get_telegram_file_url(largest_photo["file_id"])
        if file_url:
            posted = post_photo(file_url, caption, price_history_link)
            
    if not posted:
        post_text(caption, price_history_link)


def main():
    state = load_state()
    processed_ids = list(state.get("processed_ids", []))
    last_offset = state.get("last_update_id", 0)
    
    print("Checking for staging channel updates...")
    
    url = f"https://api.telegram.org/bot{RELAY_BOT_TOKEN}/getUpdates"
    params = {"offset": last_offset + 1, "timeout": 20}
    
    try:
        resp = requests.get(url, params=params, timeout=25)
        if not resp.ok:
            print(f"Telegram API Error: {resp.text}")
            return
            
        updates = resp.json().get("result", [])
        
        for update in updates:
            last_offset = max(last_offset, update["update_id"])
            
            if DEBUG_PRINT_UPDATES:
                print(json.dumps(update, indent=2))
                
            msg = update.get("channel_post") or update.get("message")
            if not msg:
                continue
                
            chat_id = str(msg.get("chat", {}).get("id"))
            if chat_id != str(STAGING_CHAT_ID):
                continue
                
            msg_id = msg.get("message_id")
            if msg_id in processed_ids:
                continue
                
            print(f"Processing Staging Message ID: {msg_id}")
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
    
