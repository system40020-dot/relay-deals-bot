import os
import json
import re
import requests

# ================= CONFIGURATION =================
RELAY_BOT_TOKEN = os.getenv("RELAY_BOT_TOKEN", "YOUR_RELAY_BOT_TOKEN")
MAIN_BOT_TOKEN = os.getenv("MAIN_BOT_TOKEN", "YOUR_MAIN_BOT_TOKEN")

STAGING_CHAT_ID = os.getenv("STAGING_CHAT_ID", "-100xxxxxxxxx")  # Staging Channel ID
MAIN_CHAT_ID = os.getenv("MAIN_CHAT_ID", "-100xxxxxxxxx")        # Target Public Channel ID

# Replace with your target public channel handle/link
CHANNEL_HANDLE = "@your_channel_username" 

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


def extract_clean_title(text):
    """Extracts a clean title line from message text."""
    if not text:
        return "Hot Deal"
        
    lines = [line.strip() for line in text.split("\n") if line.strip()]
    for line in lines:
        if not line.startswith("http") and "TODAY'S DEAL" not in line and "Verify" not in line:
            return line
            
    return "Hot Deal"


def format_caption(title, deal_link, price_history_link=None):
    """Formats HTML caption without duplicate links or broken footer placeholders."""
    caption_lines = [
        "🔥💥 <b>TODAY'S DEAL</b> 💥🔥\n",
        f"👀 <b>{title}</b>\n",
        f"🛒 <b>Buy Now:</b> {deal_link}"
    ]
    
    if price_history_link:
        caption_lines.append(f"📈 <b>Price Trends:</b> {price_history_link}")
        
    caption_lines.append(f"\n📢 Join for more deals: {CHANNEL_HANDLE}")
    
    full_caption = "\n".join(caption_lines)
    
    # Fallback if over Telegram 1024-character caption limit
    if len(full_caption) > 1000:
        short_title = title[:150] + "..." if len(title) > 150 else title
        return (
            f"🔥💥 <b>TODAY'S DEAL</b> 💥🔥\n\n"
            f"👀 <b>{short_title}</b>\n\n"
            f"🛒 <b>Buy Now:</b> {deal_link}\n\n"
            f"📢 Join: {CHANNEL_HANDLE}"
        )
        
    return full_caption


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


def post_photo(image_url, caption):
    """Downloads image bytes locally first to bypass HTTP 400 cross-bot errors."""
    url = f"https://api.telegram.org/bot{MAIN_BOT_TOKEN}/sendPhoto"
    try:
        img_resp = requests.get(image_url, timeout=15)
        img_resp.raise_for_status()
        
        payload = {
            "chat_id": MAIN_CHAT_ID,
            "caption": caption,
            "parse_mode": "HTML"
        }
        files = {"photo": ("image.jpg", img_resp.content)}
        
        resp = requests.post(url, data=payload, files=files, timeout=20)
        resp.raise_for_status()
        print("  [✓] Posted photo deal successfully.")
        return True
    except Exception as e:
        print(f"  [!] Photo post failed ({e}); falling back to text-only.")
        return False


def post_text(caption):
    """Posts text-only message to Main Channel."""
    url = f"https://api.telegram.org/bot{MAIN_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": MAIN_CHAT_ID,
        "text": caption,
        "parse_mode": "HTML",
        "disable_web_page_preview": False
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
        if "pricehistory" in url.lower():
            price_history_link = url
        elif not deal_link:
            deal_link = url
            
    if not deal_link:
        print("  [-] Skipped: No product link found in message.")
        return

    title = extract_clean_title(raw_text)
    caption = format_caption(title, deal_link, price_history_link)
    
    posted = False
    photos = msg.get("photo")
    
    if photos:
        largest_photo = photos[-1]
        file_url = get_telegram_file_url(largest_photo["file_id"])
        if file_url:
            posted = post_photo(file_url, caption)
            
    if not posted:
        post_text(caption)


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
        
    # Maintain strict chronological sequence when preserving state
    state["processed_ids"] = processed_ids[-200:]
    state["last_update_id"] = last_offset
    save_state(state)
    print("Execution complete.")


if __name__ == "__main__":
    main()
   
