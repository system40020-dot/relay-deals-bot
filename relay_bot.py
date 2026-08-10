from flask import Flask
import threading
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
    return "Bot is running!"

def run_web():
    app.run(host='0.0.0.0', port=8080)

# Running the dummy web server in a separate thread
threading.Thread(target=run_web).start()

# ================= CONFIGURATION =================
RELAY_BOT_TOKEN = os.getenv("RELAY_BOT_TOKEN", "")
MAIN_BOT_TOKEN = os.getenv("MAIN_BOT_TOKEN", "")

STAGING_CHAT_ID = os.getenv("STAGING_CHAT_ID", "")
MAIN_CHAT_ID = os.getenv("MAIN_CHAT_ID", "")

CHANNEL_HANDLE = "@loot_hacked"
DEFAULT_PRICE_HISTORY_LINK = "https://pricehistoryapp.com/"

# Dynamic Title Rotation Pool (Category-wise multiple options)
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


# ================= LINK & SCRAPING UTILS =================
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
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    }
    try:
        session = requests.Session()
        resp = session.get(short_url, headers=headers, allow_redirects=True, timeout=10)
        final_url = resp.url

        if "bitli.in" in final_url or "linkredirect" in final_url or "earnkaro" in final_url:
            meta_match = re.search(r'url=(https?://[^\s"\']+)', resp.text, re.IGNORECASE)
            if meta_match:
                second_url = meta_match.group(1)
                resp2 = session.get(second_url, headers=headers, allow_redirects=True, timeout=10)
                final_url = resp2.url

        return final_url
    except Exception as e:
        print(f"  [!] Unshorten log ({short_url}): {e}")
        return short_url


def fetch_product_metadata(url):
    """
    Scrapes real title, price, original price, discount, and image from the product page.
    """
    try:
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        resp = requests.get(url, headers=headers, timeout=10, allow_redirects=True)
        html_content = resp.text
        final_url = resp.url

        title = None
        image_url = None
        price = None
        original_price = None
        discount_text = None

        # OpenGraph Meta Tags
        og_title = re.search(r'<meta[^>]*property=["\']og:title["\'][^>]*content=["\']([^"\']+)["\']', html_content, re.IGNORECASE)
        if og_title:
            title = html.unescape(og_title.group(1))

        og_image = re.search(r'<meta[^>]*property=["\']og:image["\'][^>]*content=["\']([^"\']+)["\']', html_content, re.IGNORECASE)
        if og_image:
            image_url = og_image.group(1)

        # Price extraction heuristics
        price_match = re.search(r'₹\s?([\d,]+(?:\.\d+)?)', html_content)
        if price_match:
            try:
                price = float(price_match.group(1).replace(",", ""))
            except ValueError:
                pass

        # Discount extraction heuristics
        disc_match = re.search(r'(\d+%\s*off|\d+\s*%\s*discount)', html_content, re.IGNORECASE)
        if disc_match:
            discount_text = disc_match.group(1)

        return {
            "title": title,
            "image_url": image_url,
            "price": price,
            "original_price": original_price,
            "discount": discount_text,
            "link": final_url
        }
    except Exception as e:
        print(f"  [!] Metadata fetch error: {e}")
        return None


def get_canonical_url_for_price_history(expanded_url):
    if not expanded_url or not expanded_url.startswith("http"):
        return None
        
    if any(s in expanded_url.lower() for s in ["bitli.in", "fkrt.cc", "bit.ly", "/s/!"]):
        return None

    if "flipkart.com" in expanded_url.lower():
        itm_match = re.search(r'/(?:p|dp)/(itm[a-zA-Z0-9]+)', expanded_url)
        pid_match = re.search(r'(pid=[A-Za-z0-9]+)', expanded_url)
        pid_str = f"?{pid_match.group(1)}" if pid_match else ""
        if itm_match:
            return f"https://www.flipkart.com/p/{itm_match.group(1)}{pid_str}"
        clean = re.sub(r'https?://dl\.flipkart\.com/(?:dl/)?', 'https://www.flipkart.com/', expanded_url)
        clean = re.sub(r'(&|\?)(cmpid|hl_lid|ctx|store|fm|_refId|_appId)=[^&]+', '', clean)
        return clean

    elif "amazon" in expanded_url.lower():
        dp_match = re.search(r'/(?:dp|gp/product)/([A-Z0-9]{10})', expanded_url, re.I)
        if dp_match:
            return f"https://www.amazon.in/dp/{dp_match.group(1)}"

    return expanded_url


def build_price_history_link(canonical_url, product_title):
    if canonical_url and ("flipkart.com/p/" in canonical_url or "amazon.in/dp/" in canonical_url):
        encoded = urllib.parse.quote(canonical_url, safe='')
        return f"https://pricehistoryapp.com/search?q={encoded}"
    elif product_title and product_title != "SPECIAL OFFER DEAL":
        encoded_title = urllib.parse.quote(product_title, safe='')
        return f"https://pricehistoryapp.com/search?q={encoded_title}"
    return DEFAULT_PRICE_HISTORY_LINK


# ================= FORMATTING & CAPTION =================
def get_product_emoji(text):
    t = text.lower()
    if any(k in t for k in ["beauty", "decor", "home", "cosmetic", "cream", "lotion", "makeup"]):
        return "💄" if "beauty" in t or "cosmetic" in t else "🏠"
    elif any(k in t for k in ["headphone", "earphone", "audio", "speaker", "boat"]):
        return "🎧"
    elif any(k in t for k in ["phone", "mobile", "iphone", "samsung", "realme", "5g"]):
        return "📱"
    elif any(k in t for k in ["shoe", "sneaker", "footwear"]):
        return "👟"
    elif any(k in t for k in ["watch", "smartwatch"]):
        return "⌚"
    return "🛍️"


def format_caption(title, coupon_str, emoji, affiliate_short_link, scraped_data):
    # Dynamic random title rotation from category pool
    header = random.choice(DEAL_HEADERS)
    
    lines = [
        f"<b>{header}</b>\n",
        f"👀 {emoji} <b>{html.escape(title)}</b>\n"
    ]

    # Real price and discount handling
    if scraped_data and scraped_data.get("price"):
        price_val = f"₹{scraped_data['price']:,.0f}"
        disc_val = f" ({scraped_data['discount']})" if scraped_data.get("discount") else ""
        lines.append(f"💰 Price: <b>{price_val}</b>{disc_val}\n")
    else:
        lines.append("💰 Price: <b>Check Live Platform Price</b>\n")

    if coupon_str:
        lines.append(f"🏷️ <b>{coupon_str.upper()}</b>\n")

    lines.extend([
        f"🛒 <b>BUY NOW:</b> {affiliate_short_link}\n",
        f"📢 <b>JOIN FOR MORE DEALS:</b> {CHANNEL_HANDLE}"
    ])
    return "\n".join(lines)


def create_price_history_button(ph_link):
    return json.dumps({
        "inline_keyboard": [[{"text": "📉 Price History 📉", "url": ph_link}]]
    })


# ================= TELEGRAM ACTIONS =================
def get_telegram_file_url(file_id):
    try:
        r = requests.get(f"https://api.telegram.org/bot{RELAY_BOT_TOKEN}/getFile", params={"file_id": file_id}, timeout=8)
        if r.ok:
            path = r.json().get("result", {}).get("file_path")
            if path:
                return f"https://api.telegram.org/file/bot{RELAY_BOT_TOKEN}/{path}"
    except Exception:
        pass
    return None


def post_deal(image_url, caption, ph_link):
    if image_url:
        try:
            img_bytes = requests.get(image_url, headers={"User-Agent": "Mozilla/5.0"}, timeout=12).content
            payload = {
                "chat_id": MAIN_CHAT_ID,
                "caption": caption,
                "parse_mode": "HTML",
                "reply_markup": create_price_history_button(ph_link)
            }
            r = requests.post(f"https://api.telegram.org/bot{MAIN_BOT_TOKEN}/sendPhoto", data=payload, files={"photo": ("i.jpg", img_bytes)}, timeout=15)
            if r.ok:
                print("  [✓] Photo deal posted successfully.")
                return True
        except Exception as e:
            print(f"  [!] Photo post error ({e}), sending text instead.")

    payload = {
        "chat_id": MAIN_CHAT_ID,
        "text": caption,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
        "reply_markup": create_price_history_button(ph_link)
    }
    r = requests.post(f"https://api.telegram.org/bot{MAIN_BOT_TOKEN}/sendMessage", json=payload, timeout=15)
    if r.ok:
        print("  [✓] Text deal posted successfully.")
        return True
    return False


# ================= MAIN WORKFLOW =================
def process_message(msg):
    raw_text = msg.get("caption") or msg.get("text") or ""
    urls = extract_all_links(msg)
    web_page = msg.get("web_page") or {}
    
    affiliate_short_link = None
    explicit_ph = None
    
    for u in urls:
        if "pricehistory" in u.lower():
            explicit_ph = u
        elif not affiliate_short_link:
            affiliate_short_link = u
            
    if not affiliate_short_link:
        print("  [-] No product link found in post.")
        return

    print(f"  [+] Found affiliate link: {affiliate_short_link}")
    
    expanded_url = unshorten_link(affiliate_short_link)
    print(f"  [+] Expanded target: {expanded_url}")
    
    # Fetch real platform metadata (Price, Discount, Image, Title)
    scraped_data = fetch_product_metadata(expanded_url)
    
    canonical_url = get_canonical_url_for_price_history(expanded_url)

    # Title extraction fallback logic
    title = None
    if scraped_data and scraped_data.get("title"):
        clean_wp = re.sub(r'(?i)(\||\-|\:)\s*(Buy|Online|Flipkart|Amazon|At Best).*$', '', scraped_data["title"]).strip()
        title = clean_wp.upper()
    else:
        title = "SPECIAL OFFER DEAL"

    coupon_str = None
    for line in raw_text.split('\n'):
        if re.search(r'(?i)(use|apply)\s*code', line) or re.search(r'(?i)^code\s*:', line):
            coupon_str = line.strip()
            break

    emoji = get_product_emoji(raw_text + " " + title)
    ph_link = explicit_ph or build_price_history_link(canonical_url, title)
    
    caption = format_caption(title, coupon_str, emoji, affiliate_short_link, scraped_data)

    # Image priority: Telegram photo attachment -> Scraped OG image -> Webpage preview photo
    image_url = None
    photos = msg.get("photo")
    if photos:
        image_url = get_telegram_file_url(photos[-1]["file_id"])
    elif scraped_data and scraped_data.get("image_url"):
        image_url = scraped_data["image_url"]
    elif web_page.get("photo"):
        wp_p = web_page["photo"]
        if wp_p:
            image_url = get_telegram_file_url(wp_p[-1]["file_id"])

    post_deal(image_url, caption, ph_link)


def main():
    state = load_state()
    processed_ids = list(state.get("processed_ids", []))
    last_offset = state.get("last_update_id", 0)

    url = f"https://api.telegram.org/bot{RELAY_BOT_TOKEN}/getUpdates"
    params = {
        "offset": last_offset + 1,
        "timeout": 15,
        "allowed_updates": ["channel_post", "message"]
    }

    try:
        resp = requests.get(url, params=params, timeout=20)
        if not resp.ok:
            return
            
        updates = resp.json().get("result", [])
        for update in updates:
            last_offset = max(last_offset, update["update_id"])
            msg = update.get("channel_post") or update.get("message")
            if not msg:
                continue

            chat_id = str(msg.get("chat", {}).get("id")).strip()
            if chat_id != str(STAGING_CHAT_ID).strip():
                continue

            msg_id = msg.get("message_id")
            if msg_id in processed_ids:
                continue

            try:
                process_message(msg)
            except Exception as pe:
                print(f"  [!] Error processing {msg_id}: {pe}")

            processed_ids.append(msg_id)

    except Exception as e:
        print(f"Error during main loop: {e}")

    state["processed_ids"] = processed_ids[-200:]
    state["last_update_id"] = last_offset
    save_state(state)

if __name__ == "__main__":
    main()
    
