from flask import Flask
import threading
import time
import os
import json
import re
import random
import requests
import urllib.parse
import html

app = Flask('')

@app.route('/')
def home():
    return "Bot is running and active!"

def run_web():
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 8080)))

# ================= CONFIGURATION =================
RELAY_BOT_TOKEN = os.getenv("RELAY_BOT_TOKEN", "")
MAIN_BOT_TOKEN = os.getenv("MAIN_BOT_TOKEN", "")

STAGING_CHAT_ID = os.getenv("STAGING_CHAT_ID", "")
MAIN_CHAT_ID = os.getenv("MAIN_CHAT_ID", "")

CHANNEL_HANDLE = "@loot_hacked"
DEFAULT_PRICE_HISTORY_LINK = "https://pricehistoryapp.com/"

DEAL_HEADERS = [
    "🔥 MEGA LOOT DEAL ALERT! 🔥",
    "⚡ LIGHTNING FAST OFFER ⚡",
    "💥 CRAZY PRICE DROP 💥",
    "🌟 SPECIAL HANDPICKED LOOT 🌟",
    "🚀 HURRY! MASSIVE DISCOUNT 🚀",
    "💎 BEST VALUE DEAL FOUND 💎",
    "📉 LOWEST PRICE EVER 📉",
    "🚨 HOT DEAL ALERT 🚨"
]

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
]

def get_random_headers():
    return {"User-Agent": random.choice(USER_AGENTS), "Accept-Language": "en-US,en;q=0.9"}

STATE_FILE = "state.json"

# ================= STATE MANAGEMENT =================
def load_state():
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data.get("processed_ids"), list):
                    return data
        except Exception:
            pass
    return {"processed_ids": [], "last_update_id": 0}

def save_state(state):
    try:
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"Error saving state: {e}")

# ================= LINK & EXTRACTION =================
def extract_all_links(msg):
    text = msg.get("caption") or msg.get("text") or ""
    entities = msg.get("caption_entities") or msg.get("entities") or []
    urls = re.findall(r'https?://[^\s>"]+', text)
    for entity in entities:
        if entity.get("type") == "text_link" and entity.get("url"):
            urls.append(entity["url"])
    clean_urls = []
    for u in urls:
        c = u.rstrip(".,;!)")
        if c not in clean_urls:
            clean_urls.append(c)
    return clean_urls

def unshorten_link(short_url):
    try:
        session = requests.Session()
        resp = session.get(short_url, headers=get_random_headers(), allow_redirects=True, timeout=10)
        final_url = resp.url
        if any(x in final_url for x in ["bitli.in", "linkredirect", "earnkaro", "myntr.it", "fkrt.cc"]):
            meta_match = re.search(r'url=(https?://[^\s"\']+)', resp.text, re.IGNORECASE)
            if meta_match:
                resp2 = session.get(meta_match.group(1), headers=get_random_headers(), allow_redirects=True, timeout=10)
                final_url = resp2.url
        return final_url
    except Exception:
        return short_url

def fetch_product_metadata(url):
    try:
        resp = requests.get(url, headers=get_random_headers(), timeout=12, allow_redirects=True)
        html_content = resp.text
        
        title, image_url, price, discount_text = None, None, None, None

        # Extracting product title from Open Graph or meta tags
        og_title = re.search(r'<meta[^>]*property=["\']og:title["\'][^>]*content=["\']([^"\']+)["\']', html_content, re.IGNORECASE)
        if og_title: 
            title = html.unescape(og_title.group(1))
        else:
            tag_title = re.search(r'<title>(.*?)</title>', html_content, re.IGNORECASE)
            if tag_title:
                title = html.unescape(tag_title.group(1))

        # Extracting product image (ignoring generic brand logos/icons)
        og_image = re.search(r'<meta[^>]*property=["\']og:image["\'][^>]*content=["\']([^"\']+)["\']', html_content, re.IGNORECASE)
        if og_image: 
            img_candidate = og_image.group(1)
            if not any(bad in img_candidate.lower() for cat in ["logo", "icon", "default", "placeholder", "brand"] for bad in [cat]):
                image_url = img_candidate

        # Extracting price
        price_match = re.search(r'₹\s?([\d,]+(?:\.\d+)?)', html_content)
        if price_match:
            try: price = float(price_match.group(1).replace(",", ""))
            except: pass

        # Extracting discount
        disc_match = re.search(r'(\d+%\s*off|\d+\s*%\s*discount)', html_content, re.IGNORECASE)
        if disc_match: discount_text = disc_match.group(1)

        return {"title": title, "image_url": image_url, "price": price, "discount": discount_text, "link": resp.url}
    except:
        return None

def get_canonical_url(expanded_url):
    if not expanded_url: return None
    if "flipkart.com" in expanded_url.lower():
        itm_match = re.search(r'/(?:p|dp)/(itm[a-zA-Z0-9]+)', expanded_url)
        if itm_match: return f"https://www.flipkart.com/p/{itm_match.group(1)}"
    elif "amazon" in expanded_url.lower():
        dp_match = re.search(r'/(?:dp|gp/product)/([A-Z0-9]{10})', expanded_url, re.I)
        if dp_match: return f"https://www.amazon.in/dp/{dp_match.group(1)}"
    return expanded_url

def build_price_history_link(canonical_url, title):
    if canonical_url and ("flipkart.com/p/" in canonical_url or "amazon.in/dp/" in canonical_url):
        return f"https://pricehistoryapp.com/search?q={urllib.parse.quote(canonical_url, safe='')}"
    elif title and title not in ["SPECIAL OFFER DEAL", "MYNTRA", "AMAZON", "FLIPKART"]:
        return f"https://pricehistoryapp.com/search?q={urllib.parse.quote(title, safe='')}"
    return DEFAULT_PRICE_HISTORY_LINK

# ================= FORMATTING =================
def get_emoji(text):
    t = text.lower()
    if any(k in t for k in ["phone", "mobile", "iphone", "5g"]): return "📱"
    if any(k in t for k in ["shoe", "sneaker", "nike", "puma"]): return "👟"
    if any(k in t for k in ["watch", "smartwatch"]): return "⌚"
    if any(k in t for k in ["headphone", "audio", "boat", "earbud"]): return "🎧"
    return "🛍️"

def format_caption(title, emoji, link, scraped):
    header = random.choice(DEAL_HEADERS)
    lines = [f"<b>{header}</b>\n", f"👀 {emoji} <b>{html.escape(title)}</b>\n"]

    if scraped and scraped.get("price"):
        p_str = f"₹{scraped['price']:,.0f}"
        d_str = f" ({scraped['discount']})" if scraped.get("discount") else ""
        lines.append(f"💰 Price: <b>{p_str}</b>{d_str}\n")
    else:
        lines.append("💰 Price: <b>Check Live Platform Price</b>\n")

    lines.extend([f"🛒 <b>BUY NOW:</b> {link}\n", f"📢 <b>JOIN FOR MORE DEALS:</b> {CHANNEL_HANDLE}"])
    return "\n".join(lines)

def post_deal(image_url, caption, ph_link):
    keyboard = json.dumps({"inline_keyboard": [[{"text": "📉 Price History 📉", "url": ph_link}]]})
    if image_url:
        try:
            img_data = requests.get(image_url, headers=get_random_headers(), timeout=12).content
            payload = {"chat_id": MAIN_CHAT_ID, "caption": caption, "parse_mode": "HTML", "reply_markup": keyboard}
            r = requests.post(f"https://api.telegram.org/bot{MAIN_BOT_TOKEN}/sendPhoto", data=payload, files={"photo": ("img.jpg", img_data)}, timeout=15)
            if r.ok: return True
        except: pass

    payload = {"chat_id": MAIN_CHAT_ID, "text": caption, "parse_mode": "HTML", "disable_web_page_preview": True, "reply_markup": keyboard}
    requests.post(f"https://api.telegram.org/bot{MAIN_BOT_TOKEN}/sendMessage", json=payload, timeout=15)

# ================= WORKFLOW =================
def process_message(msg):
    urls = extract_all_links(msg)
    if not urls: return
    
    aff_link = urls[0] # Focus purely on the extracted link
    expanded = unshorten_link(aff_link)
    scraped = fetch_product_metadata(expanded)
    canonical = get_canonical_url(expanded)

    # Purely rely on scraped title from the link, avoiding staging text completely
    title = scraped.get("title") if scraped and scraped.get("title") else ""
    if not title or title.upper() in ["MYNTRA", "AMAZON", "FLIPKART", "SPECIAL OFFER DEAL"]:
        title = "SPECIAL OFFER DEAL"

    title = re.sub(r'(?i)(\||\-|\:)\s*(Buy|Online|Flipkart|Amazon|Myntra).*$', '', title).strip().upper()

    emoji = get_emoji(title)
    ph_link = build_price_history_link(canonical, title)
    caption = format_caption(title, emoji, aff_link, scraped)

    # Use product image obtained strictly from scraped link metadata
    image_url = scraped.get("image_url") if scraped else None

    post_deal(image_url, caption, ph_link)

def background_bot_loop():
    print("Background bot listener started...")
    while True:
        try:
            state = load_state()
            processed = set(state.get("processed_ids", []))
            last_offset = state.get("last_update_id", 0)

            resp = requests.get(f"https://api.telegram.org/bot{RELAY_BOT_TOKEN}/getUpdates", params={"offset": last_offset + 1, "timeout": 15}, headers=get_random_headers(), timeout=20)
            if resp.ok:
                updates = resp.json().get("result", [])
                for update in updates:
                    last_offset = max(last_offset, update["update_id"])
                    msg = update.get("channel_post") or update.get("message")
                    if not msg: continue

                    if str(msg.get("chat", {}).get("id")) != str(STAGING_CHAT_ID): continue

                    msg_id = msg.get("message_id")
                    if msg_id in processed: continue

                    process_message(msg)
                    processed.add(msg_id)

            state["processed_ids"] = list(processed)[-200:]
            state["last_update_id"] = last_offset
            save_state(state)
        except Exception as e:
            print(f"Loop error: {e}")
        
        time.sleep(3)

if __name__ == "__main__":
    threading.Thread(target=run_web, daemon=True).start()
    background_bot_loop()
      
