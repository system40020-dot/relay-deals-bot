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
from patchright.sync_api import sync_playwright

app = Flask('')

# ================= SHARED SESSION (cookies persist karta hai, real-browser jaisa lagta hai) =================
_flipkart_session = None
_amazon_session = None

def get_warmed_session(homepage_url, session_holder_key):
    """Ek requests.Session banata hai, homepage pe ek 'warm-up' visit karta hai taaki cookies mil jaayein,
    phir wahi session (cookies ke saath) baar-baar reuse hota hai - bilkul jaisa ek real browser karta hai
    (pehle site khulti hai, cookies set hoti hain, phir andar navigate karte hain)."""
    global _flipkart_session, _amazon_session
    existing = _flipkart_session if session_holder_key == "flipkart" else _amazon_session

    if existing is not None:
        return existing

    sess = requests.Session()
    sess.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Accept-Language": "en-IN,en;q=0.9",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
        "sec-ch-ua": '"Chromium";v="122", "Not(A:Brand";v="24", "Google Chrome";v="122"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"Windows"',
    })
    try:
        time.sleep(random.uniform(1, 2.5))
        warm_resp = sess.get(homepage_url, timeout=12)
        print(f"DEBUG SESSION: Warm-up visit to {homepage_url} -> status {warm_resp.status_code}, cookies = {len(sess.cookies)}")
    except Exception as e:
        print(f"DEBUG SESSION: Warm-up visit failed: {e}")

    if session_holder_key == "flipkart":
        _flipkart_session = sess
    else:
        _amazon_session = sess
    return sess

@app.route('/')
def home():
    return "Playwright Bot is running and active!"

@app.route('/test-category')
def test_category():
    url = "https://fktr.in/BVXQxa3"
    products = fetch_category_products_flipkart(url)
    return {"count": len(products), "products": products}

def fetch_category_products_flipkart(category_url, max_products=10, max_pages=1):
    """Flipkart category/listing page se multiple products nikaalta hai (bina Playwright ke).
    Multiple pages (pagination) automatically cover karta hai jab tak naye products milte rahein.
    Ek persistent session (cookies ke saath) use karta hai taaki real-browser jaisa lage."""
    sess = get_warmed_session("https://www.flipkart.com/", "flipkart")
    products = []
    seen_pids = set()
    try:
        time.sleep(random.uniform(0.5, 1.5))
        resp = sess.get(category_url, timeout=15, allow_redirects=True,
                         headers={"Referer": "https://www.flipkart.com/"})
        html_content = resp.text
        base_url = resp.url

        print(f"DEBUG CATEGORY: Final URL = {base_url}")
        print(f"DEBUG CATEGORY: HTML length = {len(html_content)}")

        # CashKaro/EarnKaro jaise networks kabhi ek "interstitial" page dete hain jo
        # JavaScript se real destination pe redirect karta hai (window.location = cashbackUrl).
        js_redirect = re.search(r'cashbackUrl\s*=\s*["\']([^"\']+)["\']', html_content)
        if js_redirect:
            real_url = js_redirect.group(1).encode().decode('unicode_escape')
            print(f"DEBUG CATEGORY: JS redirect detected, following to = {real_url}")
            time.sleep(random.uniform(0.5, 1.5))
            resp = sess.get(real_url, timeout=15, allow_redirects=True,
                             headers={"Referer": "https://www.flipkart.com/"})
            html_content = resp.text
            base_url = resp.url
            print(f"DEBUG CATEGORY: Final URL (after JS redirect) = {base_url}")
            print(f"DEBUG CATEGORY: HTML length (after JS redirect) = {len(html_content)}")

        print(f"DEBUG CATEGORY: Sample = {html_content[:2000]}")

        for page_num in range(1, max_pages + 1):
            if page_num == 1:
                page_html = html_content
            else:
                parsed = urllib.parse.urlparse(base_url)
                q = urllib.parse.parse_qs(parsed.query)
                q["page"] = [str(page_num)]
                new_query = urllib.parse.urlencode(q, doseq=True)
                page_url = urllib.parse.urlunparse(parsed._replace(query=new_query))
                try:
                    time.sleep(random.uniform(1, 2.5))
                    page_resp = sess.get(page_url, timeout=15, headers={"Referer": base_url})
                    page_html = page_resp.text
                except Exception as e:
                    print(f"DEBUG CATEGORY: Page {page_num} fetch failed: {e}")
                    break
                print(f"DEBUG CATEGORY: Page {page_num} HTML length = {len(page_html)}")
                if len(page_html) < 3000:
                    print(f"DEBUG CATEGORY: Page {page_num} looks empty/blocked, stopping pagination")
                    break

            card_links = re.findall(r'href="(/[^"]*?/p/(itm[a-zA-Z0-9]+)\?pid=([A-Z0-9]+)[^"]*)"', page_html)
            found_this_page = 0

            for relative_url, itm_id, pid in card_links:
                if pid in seen_pids:
                    continue
                seen_pids.add(pid)

                full_url = "https://www.flipkart.com" + html.unescape(relative_url)
                link_pos = page_html.find(relative_url)
                window = page_html[link_pos: link_pos + 4000]

                title = None
                title_match = re.search(r'title="([^"]{10,150})"', window)
                if title_match:
                    title = html.unescape(title_match.group(1)).strip()

                price, mrp = None, None
                mrp_match = re.search(
                    r'class=["\'][^"\']*(?:yRaY8j|_3I9_wc|strike|line-through)[^"\']*["\'][^>]*>\s*₹\s?([\d,]+)',
                    window, re.IGNORECASE
                )
                if not mrp_match:
                    mrp_match = re.search(r'<del[^>]*>\s*₹\s?([\d,]+)', window, re.IGNORECASE)

                all_prices = re.findall(r'₹\s?([\d,]+)', window)
                if all_prices:
                    try:
                        price = float(all_prices[0].replace(",", ""))
                    except:
                        pass

                if mrp_match:
                    try:
                        candidate = float(mrp_match.group(1).replace(",", ""))
                        if price and candidate > price:
                            mrp = candidate
                    except:
                        pass
                elif len(all_prices) >= 2:
                    try:
                        p2 = float(all_prices[1].replace(",", ""))
                        if price and p2 > price:
                            mrp = p2
                    except:
                        pass

                rating = None
                rating_match = re.search(r'(\d\.\d)\s*★', window)
                if rating_match:
                    rating = float(rating_match.group(1))

                image_url = None
                img_match = re.search(r'<img[^>]*src="([^"]+\.(?:jpg|jpeg|png|webp)[^"]*)"', window)
                if img_match:
                    image_url = img_match.group(1)

                if title and price:
                    products.append({
                        "title": title, "price": price, "mrp": mrp,
                        "rating": rating, "image_url": image_url, "link": full_url
                    })
                    found_this_page += 1

                if len(products) >= max_products * 3:
                    break

            print(f"DEBUG CATEGORY: Page {page_num} -> {found_this_page} new products (total so far: {len(products)})")

            if found_this_page == 0 or len(products) >= max_products * 3:
                break

        print(f"DEBUG CATEGORY: Final extracted products = {len(products)}")
        return products
    except Exception as e:
        print(f"Category fetch error: {e}")
        return products
def fetch_category_products_amazon(category_url, max_products=10, max_pages=1):
    """Amazon search/category listing page se multiple products nikaalta hai (bina Playwright ke).
    NOTE: Amazon Flipkart se zyaada aggressively bot-block karta hai, isliye is func ka
    success-rate Flipkart wale se kam ho sakta hai - yeh best-effort hai. Pagination bhi try karta hai.
    Ek persistent session (cookies ke saath) use karta hai taaki real-browser jaisa lage."""
    sess = get_warmed_session("https://www.amazon.in/", "amazon")
    products = []
    seen_asins = set()
    try:
        time.sleep(random.uniform(0.5, 1.5))
        resp = sess.get(category_url, timeout=15, allow_redirects=True,
                         headers={"Referer": "https://www.amazon.in/"})
        html_content = resp.text
        base_url = resp.url

        print(f"DEBUG CATEGORY (Amazon): Final URL = {base_url}")
        print(f"DEBUG CATEGORY (Amazon): HTML length = {len(html_content)}")

        js_redirect = re.search(r'cashbackUrl\s*=\s*["\']([^"\']+)["\']', html_content)
        if js_redirect:
            real_url = js_redirect.group(1).encode().decode('unicode_escape')
            print(f"DEBUG CATEGORY (Amazon): JS redirect detected, following to = {real_url}")
            time.sleep(random.uniform(0.5, 1.5))
            resp = sess.get(real_url, timeout=15, allow_redirects=True,
                             headers={"Referer": "https://www.amazon.in/"})
            html_content = resp.text
            base_url = resp.url
            print(f"DEBUG CATEGORY (Amazon): HTML length (after redirect) = {len(html_content)}")

        print(f"DEBUG CATEGORY (Amazon): Sample = {html_content[:2000]}")

        for page_num in range(1, max_pages + 1):
            if page_num == 1:
                page_html = html_content
            else:
                parsed = urllib.parse.urlparse(base_url)
                q = urllib.parse.parse_qs(parsed.query)
                q["page"] = [str(page_num)]
                page_url = urllib.parse.urlunparse(parsed._replace(query=urllib.parse.urlencode(q, doseq=True)))
                try:
                    time.sleep(random.uniform(1, 2.5))
                    page_resp = sess.get(page_url, timeout=15, headers={"Referer": base_url})
                    page_html = page_resp.text
                except Exception as e:
                    print(f"DEBUG CATEGORY (Amazon): Page {page_num} fetch failed: {e}")
                    break
                if len(page_html) < 3000:
                    print(f"DEBUG CATEGORY (Amazon): Page {page_num} looks empty/blocked, stopping")
                    break

            card_blocks = re.findall(r'data-component-type="s-search-result"[^>]*data-asin="([A-Z0-9]{10})"', page_html)
            found_this_page = 0

            for asin in card_blocks:
                if asin in seen_asins:
                    continue
                seen_asins.add(asin)

                asin_pos = page_html.find(f'data-asin="{asin}"')
                window = page_html[asin_pos: asin_pos + 5000]

                title = None
                title_match = re.search(r'<h2[^>]*>.*?<span[^>]*>([^<]{10,150})</span>', window, re.DOTALL)
                if not title_match:
                    title_match = re.search(r'<img[^>]*alt="([^"]{10,150})"', window)
                if title_match:
                    title = html.unescape(title_match.group(1)).strip()

                price = None
                price_match = re.search(r'class="a-price-whole"[^>]*>([\d,]+)', window)
                if price_match:
                    try:
                        price = float(price_match.group(1).replace(",", ""))
                    except:
                        pass

                mrp = None
                mrp_match = re.search(r'class="a-price a-text-price"[^>]*>.*?<span[^>]*class="a-offscreen">₹([\d,]+(?:\.\d+)?)', window, re.DOTALL)
                if mrp_match:
                    try:
                        candidate = float(mrp_match.group(1).replace(",", ""))
                        if price and candidate > price:
                            mrp = candidate
                    except:
                        pass

                rating = None
                rating_match = re.search(r'([\d.]+)\s*out of 5 stars', window)
                if rating_match:
                    try:
                        rating = float(rating_match.group(1))
                    except:
                        pass

                image_url = None
                img_match = re.search(r'<img[^>]*class="s-image"[^>]*src="([^"]+)"', window)
                if img_match:
                    image_url = img_match.group(1)

                if title and price:
                    products.append({
                        "title": title, "price": price, "mrp": mrp,
                        "rating": rating, "image_url": image_url,
                        "link": f"https://www.amazon.in/dp/{asin}"
                    })
                    found_this_page += 1

                if len(products) >= max_products * 3:
                    break

            print(f"DEBUG CATEGORY (Amazon): Page {page_num} -> {found_this_page} new (total: {len(products)})")
            if found_this_page == 0 or len(products) >= max_products * 3:
                break

        print(f"DEBUG CATEGORY (Amazon): Final extracted products = {len(products)}")
        return products
    except Exception as e:
        print(f"Category fetch error (Amazon): {e}")
        return []

def fetch_category_products(category_url, max_products=10):
    """Platform ko URL se khud detect karke sahi scraper call karta hai."""
    url_lower = category_url.lower()
    if "amazon" in url_lower or "amzn" in url_lower:
        return fetch_category_products_amazon(category_url, max_products)
    # Default Flipkart (fktr.cc, fktr.in, flipkart.com, aur unknown short-links bhi
    # zyaadatar Flipkart affiliate hote hain is bot ke context mein)
    return fetch_category_products_flipkart(category_url, max_products)

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
    "🔥 MEGA LOOT DEAL ALERT! 🔥", "⚡ LIGHTNING FAST OFFER ⚡", "💥 CRAZY PRICE DROP 💥",
    "🌟 SPECIAL HANDPICKED LOOT 🌟", "🚀 HURRY! MASSIVE DISCOUNT 🚀", "💎 BEST VALUE DEAL FOUND 💎",
    "📉 LOWEST PRICE EVER 📉", "🚨 HOT DEAL ALERT 🚨", "🎯 TODAY'S TOP LOOT 🎯",
    "🛍️ SHOPPING SPREE DEAL 🛍️", "🔊 DEAL OF THE DAY 🔊", "🏷️ UNBEATABLE PRICE TAG 🏷️",
    "⏰ LIMITED TIME LOOT ⏰", "💰 SAVE BIG TODAY 💰", "🎉 EXCLUSIVE DEAL FOR YOU 🎉",
    "🔻 PRICE SLASHED 🔻", "✨ FRESH LOOT ALERT ✨", "🏃‍♂️ GRAB IT BEFORE IT'S GONE 🏃‍♂️",
    "📢 BIG SAVINGS INSIDE 📢", "🎁 STEAL DEAL ALERT 🎁", "🧨 EXPLOSIVE OFFER 🧨",
    "🛒 CART-WORTHY DEAL 🛒", "🔑 UNLOCK THIS OFFER 🔑", "🏆 TOP PICK OF THE DAY 🏆",
    "📦 FRESH ARRIVAL DEAL 📦", "🌈 RAINBOW DISCOUNT 🌈", "🎈 FESTIVE PRICE DROP 🎈",
    "🧲 MAGNET DEAL: TOO GOOD 🧲", "🥇 GOLD STANDARD OFFER 🥇", "🎊 CELEBRATION SALE 🎊",
    "⚙️ SMART BUY ALERT ⚙️", "🌟 TRENDING DEAL NOW 🌟", "🔔 DON'T MISS THIS ONE 🔔",
    "💫 PRICE MAGIC HAPPENING 💫", "🧊 COOL DEAL ALERT 🧊"
]
CATEGORY_CATALOG = {
    "Electronics, Computers & Smart Tech": {
        "Smartphones & Mobile Devices": ["smartphone", "android phone", "iphone", "feature phone", "foldable phone", "refurbished mobile", "unboxed mobile", "wi-fi tablet", "tablet", "ipad", "e-reader"],
        "Mobile & Tech Accessories": ["tempered glass", "back cover", "silicone case", "power bank", "gan charger", "fast charger", "data cable", "type-c cable", "lightning cable", "otg cable", "mobile holder", "ring light", "selfie stick", "vr headset", "smartwatch strap"],
        "Computers & Laptops": ["laptop", "gaming laptop", "2-in-1 convertible", "macbook", "desktop pc", "all-in-one pc", "gpu", "ram", "motherboard"],
        "Computer Peripherals & Storage": ["keyboard", "wireless mouse", "gaming mouse", "external hdd", "external ssd", "pen drive", "monitor", "webcam", "printer", "ink cartridge", "router"],
        "Audio, Wearables & Optics": ["earbuds", "tws", "anc headphone", "headphone", "bluetooth speaker", "soundbar", "home theatre", "smartwatch", "fitness band", "dslr", "mirrorless camera", "action camera", "gopro", "drone", "lens", "tripod", "binocular"],
        "Smart Home & Automation": ["smart bulb", "led strip light", "smart plug", "video doorbell", "smart door lock", "alexa", "google nest", "voice assistant"],
    },
    "Large Appliances & Climate Control": {
        "Cooling & Heating": ["split ac", "window ac", "inverter ac", "tower fan", "air cooler", "room heater", "geyser", "water heater"],
        "Home Appliances": ["refrigerator", "fridge", "washing machine", "dishwasher", "vacuum cleaner", "robotic cleaner", "garment steamer", "water purifier", "ro purifier"],
    },
    "Kitchen & Dining": {
        "Kitchen Appliances": ["microwave", "otg oven", "air fryer", "induction cooktop", "mixer grinder", "food processor", "electric kettle", "coffee maker", "sandwich maker", "toaster"],
        "Cookware & Bakeware": ["pressure cooker", "frying pan", "non-stick pan", "cast iron cookware", "tawa", "dosa pan", "baking tray", "casserole"],
        "Tableware & Storage": ["dinner set", "cutlery", "insulated flask", "water bottle", "container", "glass jar", "spice box", "masala dabba", "kitchen rack", "lunch box", "chopper", "vegetable peeler"],
    },
    "Fashion & Apparel": {
        "Women's Western & Contemporary Wear": ["wrap dress", "shift dress", "slip dress", "bodycon dress", "a-line dress", "jumpsuit", "crop top", "peplum top", "tunic", "t-shirt", "mom jeans", "jeggings", "wide-leg trouser", "skirt", "culottes", "shrug", "co-ord set", "maternity wear"],
        "Women's Ethnic & Festive Wear": ["cotton saree", "silk saree", "georgette saree", "chiffon saree", "bandhani saree", "kanjeevaram saree", "kurti", "anarkali", "chikankari", "kurta palazzo", "sharara set", "lehenga", "salwar suit", "dress material", "dupatta", "ethnic skirt", "gown", "blouse"],
        "Men's Casual & Formal Wear": ["graphic t-shirt", "oversized t-shirt", "henley shirt", "polo shirt", "oxford shirt", "linen shirt", "formal shirt", "slim-fit jeans", "chinos", "cargo pants", "track pants", "joggers", "suit", "blazer", "bomber jacket", "denim jacket", "trench coat", "parka", "hoodie"],
        "Men's Ethnic Wear": ["silk kurta", "asymmetric kurta", "sherwani", "nehru jacket", "dhoti", "mojri"],
        "Kids & Baby Apparel": ["romper", "bodysuit", "booties", "mittens", "frock", "party dress", "kurta set", "dungaree", "school uniform", "kids sweater", "kids hoodie"],
        "Lingerie, Innerwear & Sleepwear": ["padded bra", "t-shirt bra", "bralette", "minimizer bra", "bikini panty", "boy-short panty", "seamless panty", "camisole", "shapewear", "nighty", "night suit", "bathrobe", "vest", "briefs", "trunks"],
        "Indie, Artisanal & Handloom": ["handloom saree", "chanderi saree", "ajrakh print", "block-print dress", "kantha quilt", "kantha jacket", "mangalgiri fabric", "potli bag", "silver jhumka"],
    },
    "Footwear & Accessories": {
        "Footwear": ["running shoes", "walking shoes", "sneakers", "chunky sneakers", "high-top sneakers", "oxford shoes", "brogues", "monk strap", "block heels", "stilettos", "kitten heels", "flat sandals", "ballerinas", "platform sneakers", "crocs", "slippers", "flip-flops", "loafers"],
        "Fashion Jewellery & Watches": ["analog watch", "chronograph watch", "smartwatch", "mangalsutra", "kundan earring", "oxidized silver earring", "bangles", "choker", "finger ring", "nose pin", "anklet", "jewellery set"],
        "Bags, Luggage & Travel": ["trolley bag", "laptop backpack", "canvas backpack", "crossbody bag", "school bag", "duffle bag", "handbag", "wallet", "cardholder", "belt", "travel pouch"],
        "General Accessories": ["sunglasses", "wayfarer", "polarized sunglasses", "silk tie", "cufflinks", "bucket hat", "cap", "scarf"],
    },
    "Beauty, Grooming, Health & Personal Care": {
        "Makeup & Cosmetics": ["foundation", "bb cream", "compact powder", "highlighter", "kajal", "eyeliner", "lipstick", "eyeshadow palette", "makeup brush", "nail polish"],
        "Skincare & Haircare": ["face serum", "sunscreen", "moisturizer", "sheet mask", "hair fall shampoo", "conditioner", "hair oil", "beard oil", "hair serum"],
        "Bath, Body & Fragrances": ["perfume", "edp", "body mist", "deodorant", "shower gel", "body lotion", "loofah", "soap"],
        "Health, Wellness & Pharmacy": ["whey protein", "multivitamin", "bp monitor", "oximeter", "first aid kit", "diaper"],
    },
    "Home Furnishing, Decor & Living": {
        "Bed Linen & Textiles": ["bedsheet", "fitted bedsheet", "comforter", "pillow cover", "memory foam pillow", "blanket", "kantha quilt"],
        "Bath & Window Furnishing": ["bath towel", "hand towel", "face towel", "bath mat", "curtain", "blackout curtain", "sofa cover", "cushion cover", "floor cushion"],
        "Home Decor & Lighting": ["vase", "wall clock", "painting", "wall sticker", "showpiece", "aroma diffuser", "candle", "table lamp", "floor lamp", "artificial flower", "led strip light"],
        "Home Maintenance & Utilities": ["floor wiper", "magic mop", "dustpan", "toilet brush", "mosquito net", "gardening tool", "plant pot", "seeds", "watering can"],
    },
    "Sports, Toys, Books & Automotive": {
        "Sports & Fitness Equipment": ["dumbbell", "resistance band", "exercise bench", "cross trainer", "skipping rope", "yoga mat", "cricket bat", "tennis ball", "leather ball", "badminton racket", "football", "shin guard", "shaker", "gym equipment", "fitness equipment"],
        "Toys, Games & School Supplies": ["soft toy", "remote control car", "puzzle", "board game", "action figure", "doll", "baby walker", "notebook", "fountain pen", "calculator", "desk organizer"],
        "Books & Media": ["exam book", "novel", "textbook", "story book"],
        "Automotive & Industrial": ["helmet", "riding gear", "phone mount", "microfiber cloth", "car care product", "industrial supply"],
        "Grocery & Gourmet Foods": ["atta", "basmati rice", "dal", "pulses", "dry fruit", "honey", "cold-pressed oil", "cereal", "chocolate", "green tea", "health drink", "packaged snack"],
    },
}


def match_category(text):
    """Finds best matching (parent_category, catalogue_name) for given text using keyword search."""
    if not text:
        return None
    text_lower = text.lower()
    best_match = None
    best_score = 0
    for main_cat, subcats in CATEGORY_CATALOG.items():
        for catalogue_name, keywords in subcats.items():
            score = sum(1 for kw in keywords if kw in text_lower)
            if catalogue_name.lower() in text_lower:
                score += 3
            if score > best_score:
                best_score = score
                best_match = (main_cat, catalogue_name)
    return best_match if best_score > 0 else None
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
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        resp = session.get(short_url, headers=headers, allow_redirects=True, timeout=10)
        final_url = resp.url
        if any(x in final_url for x in ["bitli.in", "linkredirect", "earnkaro", "myntr.it", "fkrt.cc", "bit.ly"]):
            meta_match = re.search(r'url=(https?://[^\s"\']+)', resp.text, re.IGNORECASE)
            if meta_match:
                resp2 = session.get(meta_match.group(1), headers=headers, allow_redirects=True, timeout=10)
                final_url = resp2.url
        return final_url
    except Exception:
        return short_url

def fetch_product_metadata_lightweight(url):
    """Bina browser khole, sirf HTML fetch karke JSON-LD/OG tags se data nikalta hai."""
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            "Accept-Language": "en-IN,en;q=0.9",
        }
        resp = requests.get(url, headers=headers, timeout=12, allow_redirects=True)
        html_content = resp.text
        final_url = resp.url

        title, image_url, price = None, None, None

        ld_blocks = re.findall(r'<script[^>]*type=["\']application/ld\+json["\'][^>]*>(.*?)</script>', html_content, re.IGNORECASE | re.DOTALL)
        for block in ld_blocks:
            try:
                data = json.loads(block.strip())
                candidates = data if isinstance(data, list) else [data]
                for item in candidates:
                    if not isinstance(item, dict):
                        continue
                    if item.get("@type") == "Product":
                        if not title and item.get("name"):
                            title = html.unescape(str(item["name"])).strip()
                        if not image_url and item.get("image"):
                            img = item["image"]
                            image_url = img[0] if isinstance(img, list) else (img.get("url") if isinstance(img, dict) else img)
                        offers = item.get("offers")
                        if offers:
                            offers = offers[0] if isinstance(offers, list) else offers
                            if isinstance(offers, dict) and offers.get("price"):
                                try:
                                    price = float(str(offers["price"]).replace(",", ""))
                                except:
                                    pass
            except Exception:
                continue
            if title and price:
                break

        if not title:
            m = re.search(r'<meta[^>]*property=["\']og:title["\'][^>]*content=["\']([^"\']+)["\']', html_content, re.IGNORECASE)
            if m:
                title = html.unescape(m.group(1)).strip()
        if not image_url:
            m = re.search(r'<meta[^>]*property=["\']og:image["\'][^>]*content=["\']([^"\']+)["\']', html_content, re.IGNORECASE)
            if m:
                image_url = m.group(1).strip()

        if title and len(html_content) > 5000:
            return {"title": title, "image_url": image_url, "price": price, "link": final_url}
        return None
    except Exception as e:
        print(f"Lightweight fetch error: {e}")
        return None

def fetch_product_metadata_with_playwright(url):
    """Uses Playwright real headless browser with advanced timeout, JSON-LD extraction, and generic fallback."""
    browser = None
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True, 
                args=[
                    "--no-sandbox", 
                    "--disable-setuid-sandbox", 
                    "--disable-dev-shm-usage",
                    "--disable-gpu", 
                    "--no-zygote",
                    "--disable-extensions", 
                    "--disable-background-networking"
                ]
            )
            context = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
                viewport={"width": 1280, "height": 800},
                device_scale_factor=1,
                locale="en-IN",
                extra_http_headers={
                    "Accept-Language": "en-IN,en;q=0.9",
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
                    "sec-ch-ua": '"Chromium";v="122", "Not(A:Brand";v="24", "Google Chrome";v="122"',
                    "sec-ch-ua-mobile": "?0",
                    "sec-ch-ua-platform": '"Windows"',
                }
            )
            context.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
                Object.defineProperty(navigator, 'languages', {get: () => ['en-IN', 'en']});
                Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3, 4, 5]});
                window.chrome = { runtime: {} };
            """)
            page = context.new_page()

            page.goto(url, timeout=40000, wait_until="domcontentloaded")

            try:
                page.wait_for_load_state("networkidle", timeout=8000)
            except Exception:
                pass

            final_url = page.url

            html_content = None
            for attempt in range(3):
                try:
                    html_content = page.content()
                    break
                except Exception:
                    time.sleep(1)

            if html_content is None:
                raise Exception("Could not retrieve page content after retries")

            print(f"DEBUG: Final URL = {final_url}")
            print(f"DEBUG: HTML length = {len(html_content)}")

            if len(html_content) < 1000:
                print(f"DEBUG: SHORT HTML CONTENT = {html_content}")

            title, image_url, price, discount_text = None, None, None, None
            
            # ===== STEP 1: Try JSON-LD structured data (works across most modern e-commerce sites) =====
            ld_blocks = re.findall(r'<script[^>]*type=["\']application/ld\+json["\'][^>]*>(.*?)</script>', html_content, re.IGNORECASE | re.DOTALL)
            for block in ld_blocks:
                try:
                    data = json.loads(block.strip())
                    candidates = data if isinstance(data, list) else [data]
                    for item in candidates:
                        if not isinstance(item, dict):
                            continue
                        if "@graph" in item and isinstance(item["@graph"], list):
                            candidates.extend([g for g in item["@graph"] if isinstance(g, dict)])
                        item_type = item.get("@type", "")
                        if isinstance(item_type, list):
                            is_product = "Product" in item_type
                        else:
                            is_product = item_type == "Product"
                        if is_product:
                            if not title and item.get("name"):
                                title = html.unescape(str(item["name"])).strip()
                            if not image_url and item.get("image"):
                                img = item["image"]
                                if isinstance(img, list):
                                    image_url = img[0] if img else None
                                elif isinstance(img, dict):
                                    image_url = img.get("url")
                                else:
                                    image_url = img
                            offers = item.get("offers")
                            if offers:
                                if isinstance(offers, list):
                                    offers = offers[0] if offers else {}
                                if isinstance(offers, dict) and offers.get("price"):
                                    try:
                                        price = float(str(offers["price"]).replace(",", ""))
                                    except:
                                        pass
                except Exception:
                    continue
                if title and price:
                    break

# ===== STEP 1b: Fallback to embedded app-state JSON (React/Next.js apps like Meesho) =====
            if not title or not price:
                state_blocks = re.findall(
                    r'<script[^>]*id=["\'](?:NEXT_DATA|INITIAL_STATE|APOLLO_STATE)["\'][^>]*>(.*?)</script>',
                    html_content, re.IGNORECASE | re.DOTALL
                )
                for block in state_blocks:
                    try:
                        state_data = json.loads(block.strip())
                    except Exception:
                        continue

                    def find_product_fields(obj, depth=0):
                        nonlocal title, price, image_url
                        if depth > 8 or (title and price):
                            return
                        if isinstance(obj, dict):
                            keys_lower = {k.lower(): k for k in obj.keys()}
                            if not title:
                                for key in ["name", "productname", "title"]:
                                    if key in keys_lower and isinstance(obj[keys_lower[key]], str) and len(obj[keys_lower[key]]) > 5:
                                        title = html.unescape(obj[keys_lower[key]]).strip()
                                        break
                            if not price:
                                for key in ["price", "finalprice", "sellingprice", "offerprice"]:
                                    if key in keys_lower:
                                        val = obj[keys_lower[key]]
                                        if isinstance(val, dict):
                                            val = val.get("value") or val.get("amount")
                                        try:
                                            if val: price = float(str(val).replace(",", ""))
                                        except Exception:
                                            pass
                                        if price: break
                            if not image_url:
                                for key in ["image", "images", "imageurl", "thumbnail"]:
                                    if key in keys_lower:
                                        val = obj[keys_lower[key]]
                                        if isinstance(val, list) and val:
                                            val = val[0]
                                        if isinstance(val, str) and val.startswith("http"):
                                            image_url = val
                                            break
                            for v in obj.values():
                                if isinstance(v, (dict, list)):
                                    find_product_fields(v, depth + 1)
                        elif isinstance(obj, list):
                            for item in obj:
                                find_product_fields(item, depth + 1)

                    find_product_fields(state_data)
                    if title and price:
                        break
            
            # ===== STEP 2: og:title / og:image fallback =====
            if not title:
                og_title = re.search(r'<meta[^>]*property=["\']og:title["\'][^>]*content=["\']([^"\']+)["\']', html_content, re.IGNORECASE)
                if og_title:
                    title = html.unescape(og_title.group(1)).strip()

            if not image_url:
                og_image = re.search(r'<meta[^>]*property=["\']og:image["\'][^>]*content=["\']([^"\']+)["\']', html_content, re.IGNORECASE)
                if og_image:
                    img_candidate = og_image.group(1).strip()
                    if not any(bad in img_candidate.lower() for bad in ["logo", "icon", "default", "placeholder", "sprite", "smile", "favicon", "app-icon", "generic"]):
                        image_url = img_candidate

            # ===== STEP 3: Generic bad-title detection (pattern-based, not hardcoded per platform) =====
            BAD_TITLE_PATTERNS = [
                
                "access denied", "site maintenance", "under maintenance", "robot check",
                "are you a human", "verify you are human", "captcha", "forbidden",
                "error 403", "error 404", "page not found", "just a moment",
                "attention required", "service unavailable", "bot detection",
                "online shopping", "online store", "e-commerce", "welcome to",
                "oops", "something went wrong", "unexpected error", "please try again",
                "temporarily unavailable", "we're sorry", "we are sorry", "session expired",
                "invalid request", "suspicious activity", "blocked", "not found",
                "try again later", "went wrong", "server error", "internal error",
                "cannot process", "unavailable", "denied", "unauthorized",
                "add to your order", "add to cart", "add to bag", "shop now",
                "buy daily essentials", "bill payments", "download the app"
                "access denied", "site maintenance", "under maintenance", "robot check",
                "are you a human", "verify you are human", "captcha", "forbidden",
                "error 403", "error 404", "page not found", "just a moment",
                "attention required", "service unavailable", "bot detection",
                "online shopping", "online store", "e-commerce", "welcome to",
                "oops", "something went wrong", "unexpected error", "please try again",
                "temporarily unavailable", "we're sorry", "we are sorry", "session expired",
                "invalid request", "suspicious activity", "blocked", "not found",
                "try again later", "went wrong", "server error", "internal error",
                "cannot process", "unavailable", "denied", "unauthorized"
            ]
            def is_bad_title(t):
                if not t or len(t.strip()) < 5:
                    return True
                tl = t.lower()
                if any(pat in tl for pat in BAD_TITLE_PATTERNS):
                    return True
                # Titles that are JUST a brand/domain name (very short, no product details)
                if len(tl.split()) <= 2 and len(tl) < 20:
                    return True
                if re.fullmatch(r'[A-Za-z0-9\s]{3,20}', t) and any(c.isdigit() for c in t) and t.upper() == t.replace(" ", "").upper():
                    letters_upper = sum(1 for c in t if c.isupper())
                    if letters_upper >= 3:
                        return True
                return False

            if is_bad_title(title):
                h1_match = re.search(r'<h1[^>]*>(.*?)</h1>', html_content, re.IGNORECASE | re.DOTALL)
                if h1_match:
                    clean_h1 = re.sub(r'<[^>]+>', '', h1_match.group(1)).strip()
                    if clean_h1 and not is_bad_title(clean_h1):
                        title = html.unescape(clean_h1)

            if is_bad_title(title):
                tag_title = re.search(r'<title>(.*?)</title>', html_content, re.IGNORECASE)
                if tag_title:
                    tt = html.unescape(tag_title.group(1)).strip()
                    if not is_bad_title(tt):
                        title = tt

            if is_bad_title(title):
                title = "SPECIAL OFFER DEAL"

            # ===== STEP 4: Generic image fallback chain =====
            if not image_url:
                dynamic_img = re.search(r'data-a-dynamic-image=["\'](\{[^\'"]+\})["\']', html_content, re.IGNORECASE)
                if dynamic_img:
                    try:
                        img_data = json.loads(html.unescape(dynamic_img.group(1)))
                        if img_data:
                            image_url = list(img_data.keys())[0]
                    except Exception:
                        pass

            if not image_url:
                old_hires = re.search(r'data-old-hires=["\']([^"\']+)["\']', html_content, re.IGNORECASE)
                if old_hires and old_hires.group(1).strip():
                    image_url = old_hires.group(1).strip()

            if not image_url:
                landing_img = re.search(r'id=["\']landingImage["\'][^>]*src=["\']([^"\']+)["\']', html_content, re.IGNORECASE)
                if landing_img:
                    image_url = landing_img.group(1).strip()

            if not image_url:
                item_img = re.search(r'itemprop=["\']image["\'][^>]*(?:content|src)=["\']([^"\']+)["\']', html_content, re.IGNORECASE)
                if item_img:
                    image_url = item_img.group(1).strip()

            if not image_url:
                twitter_img = re.search(r'<meta[^>]*name=["\']twitter:image["\'][^>]*content=["\']([^"\']+)["\']', html_content, re.IGNORECASE)
                if twitter_img:
                    img_candidate = twitter_img.group(1).strip()
                    if not any(bad in img_candidate.lower() for bad in ["logo", "icon", "default", "placeholder"]):
                        image_url = img_candidate

            print(f"DEBUG: image_url resolved = {image_url}")

    
           # ===== STEP 5: Price fallback (Amazon-specific first, then generic regex) =====
            if not price:
                amazon_price = re.search(r'class=["\']a-price-whole["\'][^>]*>([\d,]+)', html_content, re.IGNORECASE)
                if amazon_price:
                    try: price = float(amazon_price.group(1).replace(",", ""))
                    except: pass

            if not price:
                core_price = re.search(r'id=["\']priceblock_(?:ourprice|dealprice|saleprice)["\'][^>]*>[^₹]*₹\s?([\d,]+(?:\.\d+)?)', html_content, re.IGNORECASE)
                if core_price:
                    try: price = float(core_price.group(1).replace(",", ""))
                    except: pass

            # NOTE: Removed the fully-generic "₹ anywhere on page" fallback here.
            # It used to grab ANY rupee amount on the page (coupon boxes, banners,
            # homepage promos) even when there was no real product on the page,
            # which caused wrong prices to be posted. If price is still None here,
            # we simply don't have a reliable price for this page.

            # ===== STEP 5b: MRP extraction (for strikethrough display + fallback calculation) =====
            mrp_value = None
            mrp_patterns = [
                r'"mrp"\s*:\s*"?₹?\s?([\d,]+(?:\.\d+)?)"?',
                r'"listPrice"\s*:\s*\{?\s*"?(?:value|amount)?"?\s*:?\s*"?₹?\s?([\d,]+(?:\.\d+)?)"?',
                r'"strikePrice"\s*:\s*"?₹?\s?([\d,]+(?:\.\d+)?)"?',
                r'"originalPrice"\s*:\s*"?₹?\s?([\d,]+(?:\.\d+)?)"?',
                r'"was_price"\s*:\s*"?₹?\s?([\d,]+(?:\.\d+)?)"?',
                r'"compareAtPrice"\s*:\s*"?₹?\s?([\d,]+(?:\.\d+)?)"?',
                r'"basePrice"\s*:\s*"?₹?\s?([\d,]+(?:\.\d+)?)"?',
                r'"oldPrice"\s*:\s*"?₹?\s?([\d,]+(?:\.\d+)?)"?',
                r'"higherPrice"\s*:\s*"?₹?\s?([\d,]+(?:\.\d+)?)"?',
                r'MRP[:\s₹]*([\d,]+(?:\.\d+)?)',
                r'class=["\'][^"\']*(?:strike|line-through|linethrough|mrp|original-?price|was-?price)[^"\']*["\'][^>]*>\s*₹?\s?([\d,]+(?:\.\d+)?)',
                r'<[^>]*style=["\'][^"\']*text-decoration:\s*line-through[^"\']*["\'][^>]*>\s*₹?\s?([\d,]+(?:\.\d+)?)',
                r'<del[^>]*>\s*₹?\s?([\d,]+(?:\.\d+)?)',
                r'<s[^>]*>\s*₹?\s?([\d,]+(?:\.\d+)?)',
            ]
            for pat in mrp_patterns:
                m = re.search(pat, html_content, re.IGNORECASE)
                if m:
                    try:
                        candidate = float(m.group(1).replace(",", ""))
                        if price and candidate > price:
                            mrp_value = candidate
                            break
                    except:
                        continue

            # ===== STEP 6: Discount — validated against already-extracted price (avoids ads/unrelated products) =====
            discount_text = None
            if price:
                price_variants = set()
                price_variants.add(f"{price:,.0f}")
                price_variants.add(f"{int(price)}")
                for pv in price_variants:
                    pv_esc = re.escape(pv)
                    m = re.search(rf'(\d+)\s*%[\s\S]{{0,80}}?₹\s?{pv_esc}\b', html_content)
                    if m:
                        discount_text = f"{m.group(1)}% off"
                        break
                    m2 = re.search(rf'₹\s?{pv_esc}\b[\s\S]{{0,80}}?(\d+)\s*%', html_content)
                    if m2:
                        discount_text = f"{m2.group(1)}% off"
                        break

            if not discount_text:
                discount_patterns = [
                    r'savingsPercentage[\s\S]{0,100}?(\d+)\s*%',
                    r'\(\s*(\d+)\s*%\s*off\s*\)',
                    r'(\d+)\s*%\s*off',
                    r'(\d+)\s*%\s*discount',
                    r'save\s*(\d+)\s*%',
                    r'-\s?(\d{1,2})\s*%',
                ]
                for pat in discount_patterns:
                    m = re.search(pat, html_content, re.IGNORECASE)
                    if m:
                        discount_text = f"{m.group(1)}% off"
                        break

            # Agar discount mila text se lekin MRP nahi mila, toh reverse-calculate karo
            if not mrp_value and price and discount_text:
                pct_match = re.search(r'(\d+)', discount_text)
                if pct_match:
                    pct = int(pct_match.group(1))
                    if 0 < pct < 95:
                        mrp_value = round(price / (1 - pct / 100))
            return {"title": title, "image_url": image_url, "price": price, "discount": discount_text, "mrp": mrp_value, "link": final_url}
    except Exception as e:
        print(f"Playwright detailed error: {e}")
        return None
    finally:
        if browser is not None:
            try:
                browser.close()
            except Exception:
                pass

     
            

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
    if canonical_url and "amazon.in/dp/" in canonical_url:
        asin = canonical_url.rstrip("/").split("/")[-1]
        return f"https://keepa.com/#!product/10-{asin}"
    return DEFAULT_PRICE_HISTORY_LINK

# ================= FORMATTING =================
def get_emoji(text):
    t = text.lower()
    if any(k in t for k in ["phone", "mobile", "iphone", "5g", "samsung"]): return "📱"
    if any(k in t for k in ["shoe", "sneaker", "nike", "puma", "adidas"]): return "👟"
    if any(k in t for k in ["watch", "smartwatch"]): return "⌚"
    if any(k in t for k in ["headphone", "audio", "boat", "earbud"]): return "🎧"
    return "🛍️"

def extract_fallback_title_from_text(text):
    """Extracts a usable title from the original staging message when scraping fails."""
    if not text:
        return None
    text = re.sub(r'https?://\S+', '', text)
    lines = [l.strip() for l in text.split("\n") if l.strip()]
    noise_patterns = ["buy now", "join for", "join our", "@loot", "price:", "discount"]
    good_lines = [l for l in lines if not any(p in l.lower() for p in noise_patterns)]
    candidate = good_lines[0] if good_lines else (lines[0] if lines else None)
    if candidate:
        candidate = re.sub(r'[^\w\s₹%.,&\-]', '', candidate).strip()
        if len(candidate) > 100:
            candidate = candidate[:100].strip()
        if len(candidate) < 5:
            return None
        return candidate
    return None
def parse_category_deal(text):
    """Detects category/collection-style messages (e.g. 'LOOT: Shakers Starting @ ₹99')
    and extracts (subject, price_phrase). Returns None for normal single-product messages."""
    if not text:
        return None
    clean = re.sub(r'https?://\S+', '', text).strip()
    clean = re.sub(r'^(loot|grab|deal|offer)\s*:\s*', '', clean, flags=re.IGNORECASE).strip()
    m = re.search(
        r'^(.*?)(?:\s*[\|:]\s*|\s+)(starting\s*@?\s*₹\s?[\d,]+(?:\.\d+)?|up\s*to\s*\d+\s*%\s*off|flat\s*\d+\s*%\s*off)',
        clean, re.IGNORECASE
    )
    
    if not m:
        return None
    subject = m.group(1).strip(" |-:").strip()
    phrase = m.group(2).strip()
    phrase = phrase[0].upper() + phrase[1:]
    if len(subject) < 3:
        return None
    return subject, phrase
def format_caption(title, emoji, link, scraped, show_price_line=True):
    header = random.choice(DEAL_HEADERS)
    lines = [f"<b>{header}</b>\n", f"👀 {emoji} <b>{html.escape(title)}</b>\n"]

    if show_price_line:
        if scraped and scraped.get("price"):
            p_str = f"₹{scraped['price']:,.0f}"
            mrp_str = f"<s>₹{scraped['mrp']:,.0f}</s> " if scraped.get("mrp") else ""
            d_str = f" ({scraped['discount']})" if scraped.get("discount") else ""
            lines.append(f"💰 Price: {mrp_str}<b>{p_str}</b>{d_str}\n")
        else:
            lines.append("💰 Price: <b>Check Live Platform Price</b>\n")

    lines.extend([f"🛒 <b>BUY NOW:</b> {link}\n", f"📢 <b>JOIN FOR MORE DEALS:</b> {CHANNEL_HANDLE}"])
    return "\n".join(lines)
def post_deal(image_url, caption, ph_link):
    keyboard = json.dumps({"inline_keyboard": [[{"text": "📉 Price History 📉", "url": ph_link}]]})
    if image_url:
        try:
            img_data = requests.get(image_url, headers={"User-Agent": "Mozilla/5.0"}, timeout=12).content
            payload = {"chat_id": MAIN_CHAT_ID, "caption": caption, "parse_mode": "HTML", "reply_markup": keyboard}
            r = requests.post(f"https://api.telegram.org/bot{MAIN_BOT_TOKEN}/sendPhoto", data=payload, files={"photo": ("img.jpg", img_data)}, timeout=15)
            if r.ok: return True
        except: pass

    payload = {"chat_id": MAIN_CHAT_ID, "text": caption, "parse_mode": "HTML", "disable_web_page_preview": True, "reply_markup": keyboard}
    requests.post(f"https://api.telegram.org/bot{MAIN_BOT_TOKEN}/sendMessage", json=payload, timeout=15)

# ================= CATEGORY SCHEDULER =================
_category_scheduler_state = {"running_urls": set()}
CATEGORY_STATE_FILE = "category_posted.json"
POSTED_EXPIRY_DAYS = 15  # itne din baad wahi product dobara "naya" maan liya jaata hai

def load_posted_pids():
    """Sirf woh PIDs return karta hai jo POSTED_EXPIRY_DAYS ke andar post hue the (purane apne aap expire ho jaate hain)."""
    try:
        with open(CATEGORY_STATE_FILE, "r") as f:
            data = json.load(f).get("posted", {})
        cutoff = time.time() - (POSTED_EXPIRY_DAYS * 86400)
        return set(pid for pid, ts in data.items() if ts > cutoff)
    except:
        return set()

def save_posted_pids(pids):
    """Har PID ke saath uska post-hone-ka timestamp save karta hai."""
    try:
        try:
            with open(CATEGORY_STATE_FILE, "r") as f:
                data = json.load(f).get("posted", {})
        except:
            data = {}

        now = time.time()
        for pid in pids:
            if pid not in data:
                data[pid] = now

        # Bahut purani (expired) entries file se hata do taaki file badhta na jaaye
        cutoff = now - (POSTED_EXPIRY_DAYS * 86400)
        data = {pid: ts for pid, ts in data.items() if ts > cutoff}

        with open(CATEGORY_STATE_FILE, "w") as f:
            json.dump({"posted": data}, f)
    except Exception as e:
        print(f"DEBUG SCHEDULER: Could not save posted_pids: {e}")

def filter_category_products(products, min_discount=0, min_rating=0, price_min=0, price_max=None, exclude_pids=None):
    """Products ko discount %, rating, price range, aur already-posted status ke hisaab se filter karta hai."""
    exclude_pids = exclude_pids or set()
    filtered = []
    for p in products:
        pid_match = re.search(r'pid=([A-Z0-9]+)', p.get("link", ""))
        pid = pid_match.group(1) if pid_match else p.get("link")
        if pid in exclude_pids:
            continue

        if min_rating and p.get("rating") and p["rating"] < min_rating:
            continue
        if price_min and p["price"] < price_min:
            continue
        if price_max and p["price"] > price_max:
            continue

        disc = 0
        if p.get("mrp") and p["mrp"] > p["price"]:
            disc = round((p["mrp"] - p["price"]) / p["mrp"] * 100)
        if min_discount and disc < min_discount:
            continue

        p = dict(p)
        p["discount_pct"] = disc
        p["_pid"] = pid
        filtered.append(p)
    return filtered

# ================= LIVE-EDITABLE SETTINGS (Telegram se control hote hain) =================
BOT_SETTINGS = {
    "paused": False,
    "interval_minutes": 30,
    "min_discount": 0,
    "min_rating": 0.0,
    "price_min": 0.0,
    "price_max": None,
    "muted_categories": set(),   # jo category temporarily band karni ho
}

def start_category_scheduler(category_url, interval_minutes=30, min_discount=0, min_rating=0,
                              price_min=0, price_max=None, max_products=10, start_delay=0):
    """Har interval_minutes (+/- random jitter) mein category page se ek naya (pehle na-posted) deal post karta hai.
    Settings (interval/filters/pause/mute) BOT_SETTINGS se LIVE padhta hai - Telegram se change karo, turant apply hoga."""
    if category_url in _category_scheduler_state["running_urls"]:
        print(f"DEBUG SCHEDULER: Already running for {category_url}, ignoring duplicate start")
        return
    _category_scheduler_state["running_urls"].add(category_url)

    # Initial defaults yahan set karo (pehli baar), baad mein BOT_SETTINGS override karega
    if "interval_minutes" not in BOT_SETTINGS or BOT_SETTINGS["interval_minutes"] == 30:
        BOT_SETTINGS["interval_minutes"] = interval_minutes
    if min_discount:
        BOT_SETTINGS["min_discount"] = min_discount
    if min_rating:
        BOT_SETTINGS["min_rating"] = min_rating
    if price_min:
        BOT_SETTINGS["price_min"] = price_min
    if price_max:
        BOT_SETTINGS["price_max"] = price_max

    def loop():
        if start_delay:
            time.sleep(start_delay)

        queue = []
        while True:
            try:
                if BOT_SETTINGS["paused"] or category_url in BOT_SETTINGS["muted_categories"]:
                    print(f"DEBUG SCHEDULER [{category_url[:40]}]: Paused/muted, skipping this cycle")
                else:
                    posted_pids = load_posted_pids()

                    if not queue:
                        print(f"DEBUG SCHEDULER [{category_url[:40]}]: Queue empty, fetching fresh...")
                        raw = fetch_category_products(category_url, max_products=max_products)
                        filtered = filter_category_products(
                            raw, BOT_SETTINGS["min_discount"], BOT_SETTINGS["min_rating"],
                            BOT_SETTINGS["price_min"], BOT_SETTINGS["price_max"], exclude_pids=posted_pids
                        )
                        print(f"DEBUG SCHEDULER [{category_url[:40]}]: {len(raw)} scraped, {len(filtered)} new after filters")
                        queue = filtered

                    if queue:
                        product = queue.pop(0)
                        title = product["title"]
                        emoji = get_emoji(title)
                        canonical = get_canonical_url(product["link"])
                        ph_link = build_price_history_link(canonical, title)

                        scraped = {
                            "price": product["price"],
                            "mrp": product.get("mrp"),
                            "discount": f"{product['discount_pct']}% off" if product.get("discount_pct") else None,
                        }
                        caption = format_caption(title, emoji, product["link"], scraped)
                        post_deal(product.get("image_url"), caption, ph_link)
                        print(f"DEBUG SCHEDULER [{category_url[:40]}]: Posted -> {title[:50]}")

                        posted_pids.add(product.get("_pid"))
                        save_posted_pids(posted_pids)
                    else:
                        print(f"DEBUG SCHEDULER [{category_url[:40]}]: Nothing new to post this cycle")

            except Exception as e:
                print(f"DEBUG SCHEDULER error [{category_url[:40]}]: {e}")

            jitter = random.randint(-5, 5)
            sleep_min = max(3, BOT_SETTINGS["interval_minutes"] + jitter)
            time.sleep(sleep_min * 60)

    threading.Thread(target=loop, daemon=True).start()
    print(f"DEBUG SCHEDULER: Started for {category_url[:60]} (every ~{interval_minutes} min, staggered by {start_delay}s)")

def start_all_category_schedulers():
    """CATEGORY_URLS env var (comma-separated) se saari categories ek saath, staggered start ke saath, shuru karta hai."""
    urls_raw = os.getenv("CATEGORY_URLS", "")
    urls = [u.strip() for u in urls_raw.split(",") if u.strip()]
    if not urls:
        print("DEBUG SCHEDULER: CATEGORY_URLS env var khaali hai, koi auto-category-schedule start nahi hui")
        return

    interval = int(os.getenv("CATEGORY_INTERVAL_MIN", "30"))
    min_discount = int(os.getenv("CATEGORY_MIN_DISCOUNT", "0"))
    min_rating = float(os.getenv("CATEGORY_MIN_RATING", "0"))
    price_min = float(os.getenv("CATEGORY_PRICE_MIN", "0"))
    price_max_raw = os.getenv("CATEGORY_PRICE_MAX", "")
    price_max = float(price_max_raw) if price_max_raw else None

    for i, url in enumerate(urls):
        # Har category ka pehla fetch stagger karo (60 sec gap) taaki sab ek saath na chalein
        start_category_scheduler(url, interval, min_discount, min_rating, price_min, price_max, start_delay=i * 60)

    print(f"DEBUG SCHEDULER: {len(urls)} categories auto-started from CATEGORY_URLS")

@app.route('/start-category-schedule')
def start_category_schedule_route():
    from flask import request
    url = request.args.get("url", "")
    if not url:
        return {"error": "Provide ?url=<flipkart category link>"}, 400

    interval = int(request.args.get("interval", 30))
    min_discount = int(request.args.get("min_discount", 0))
    min_rating = float(request.args.get("min_rating", 0))
    price_min = float(request.args.get("price_min", 0))
    price_max_raw = request.args.get("price_max", "")
    price_max = float(price_max_raw) if price_max_raw else None

    start_category_scheduler(url, interval, min_discount, min_rating, price_min, price_max)
    return {"status": "started", "interval_minutes": interval, "min_discount": min_discount,
            "min_rating": min_rating, "price_min": price_min, "price_max": price_max}

# ================= WORKFLOW =================
def process_message(msg):
    urls = extract_all_links(msg)
    if not urls: return

    if len(urls) > 1:
        try:
            requests.post(
                f"https://api.telegram.org/bot{RELAY_BOT_TOKEN}/copyMessage",
                json={"chat_id": MAIN_CHAT_ID, "from_chat_id": STAGING_CHAT_ID, "message_id": msg.get("message_id")},
                timeout=15
            )
        except Exception as e:
            print(f"Copy error: {e}")
        return

    original_text = (msg.get("caption") or msg.get("text") or "").strip()
    aff_link = urls[0]

    scraped = fetch_product_metadata_lightweight(aff_link)
    if not scraped or not scraped.get("price") or not scraped.get("image_url"):
        scraped = fetch_product_metadata_with_playwright(aff_link)

    final_link = scraped.get("link") if scraped else None
    canonical = get_canonical_url(final_link) if final_link else get_canonical_url(unshorten_link(aff_link))
    category_deal = parse_category_deal(original_text)

    if category_deal:
        subject, price_phrase = category_deal
        scraped_title = scraped.get("title") if scraped else None

        combined_text = f"{subject} {scraped_title or ''} {original_text}"
        cat_match = match_category(combined_text)
        category_label = cat_match[1] if cat_match else None

        title_lines = []
        if category_label:
            title_lines.append(f"Category: {category_label}")
        title_lines.append(subject.upper())
        title_lines.append(price_phrase)
        title = "\n".join(title_lines)

        emoji = get_emoji(subject)
        ph_link = build_price_history_link(canonical, subject)
        caption = format_caption(title, emoji, aff_link, None, show_price_line=False)
        image_url = scraped.get("image_url") if scraped else None
        post_deal(image_url, caption, ph_link)
        return

    title = scraped.get("title") if scraped and scraped.get("title") else None
    if not title or title == "SPECIAL OFFER DEAL":
        fallback_title = extract_fallback_title_from_text(original_text)
        title = fallback_title if fallback_title else "SPECIAL OFFER DEAL"

    title = re.sub(r'(?i)(\||\-|\:)\s*(Buy|Online|Flipkart|Amazon|Myntra|Boat).*$', '', title).strip().upper()
    emoji = get_emoji(title)
    ph_link = build_price_history_link(canonical, title)
    caption = format_caption(title, emoji, aff_link, scraped)
    image_url = scraped.get("image_url") if scraped else None
    post_deal(image_url, caption, ph_link)
# ================= TELEGRAM CONTROL PANEL (sirf owner ke liye) =================
OWNER_ID = os.getenv("OWNER_ID", "")

def send_owner_message(text, buttons=None):
    payload = {"chat_id": OWNER_ID, "text": text, "parse_mode": "HTML"}
    if buttons:
        payload["reply_markup"] = json.dumps({"inline_keyboard": buttons})
    requests.post(f"https://api.telegram.org/bot{RELAY_BOT_TOKEN}/sendMessage", json=payload, timeout=15)

def answer_callback(callback_id, text=""):
    requests.post(f"https://api.telegram.org/bot{RELAY_BOT_TOKEN}/answerCallbackQuery",
                  json={"callback_query_id": callback_id, "text": text}, timeout=10)

def status_buttons():
    pause_label = "▶️ Resume" if BOT_SETTINGS["paused"] else "⏸️ Pause"
    return [
        [{"text": pause_label, "callback_data": "toggle_pause"}],
        [{"text": "📊 Status", "callback_data": "status"}, {"text": "📋 List Categories", "callback_data": "list_cats"}],
    ]

def handle_owner_command(text, chat_id):
    parts = text.strip().split()
    cmd = parts[0].lower()

    if cmd in ("/start", "/help"):
        send_owner_message(
            "<b>🎛️ Relay Deals Bot — Control Panel</b>\n\n"
            "/status — current settings + running categories\n"
            "/pause — saara category-posting rok do\n"
            "/resume — wapas shuru karo\n"
            "/setinterval <minutes> — jaise /setinterval 20\n"
            "/setfilters <discount> <rating> <price_min> <price_max> — jaise /setfilters 20 3.5 200 2000\n"
            "/addcategory <url> — naya category link live add karo\n"
            "/mute <partial-url> — ek category temporarily band karo\n"
            "/unmute <partial-url> — wapas chalu karo\n"
            "/listcategories — saari active categories dikhao",
            buttons=status_buttons()
        )
    elif cmd == "/status":
        cats = "\n".join(f"• {u[:60]}" for u in _category_scheduler_state["running_urls"]) or "Koi category active nahi"
        muted = ", ".join(u[:40] for u in BOT_SETTINGS["muted_categories"]) or "None"
        send_owner_message(
            f"<b>📊 Current Status</b>\n\n"
            f"Paused: <b>{'Yes' if BOT_SETTINGS['paused'] else 'No'}</b>\n"
            f"Interval: <b>~{BOT_SETTINGS['interval_minutes']} min</b>\n"
            f"Min Discount: <b>{BOT_SETTINGS['min_discount']}%</b>\n"
            f"Min Rating: <b>{BOT_SETTINGS['min_rating']}</b>\n"
            f"Price Range: <b>₹{BOT_SETTINGS['price_min']} - ₹{BOT_SETTINGS['price_max'] or '∞'}</b>\n"
            f"Muted: {muted}\n\n"
            f"<b>Active categories:</b>\n{cats}",
            buttons=status_buttons()
        )
    elif cmd == "/pause":
        BOT_SETTINGS["paused"] = True
        send_owner_message("⏸️ Saara category-posting pause ho gaya.", buttons=status_buttons())
    elif cmd == "/resume":
        BOT_SETTINGS["paused"] = False
        send_owner_message("▶️ Category-posting resume ho gaya.", buttons=status_buttons())
    elif cmd == "/setinterval":
        try:
            BOT_SETTINGS["interval_minutes"] = int(parts[1])
            send_owner_message(f"✅ Interval ab ~{parts[1]} minute set ho gaya.")
        except:
            send_owner_message("❌ Usage: /setinterval 20")
    elif cmd == "/setfilters":
        try:
            BOT_SETTINGS["min_discount"] = int(parts[1])
            BOT_SETTINGS["min_rating"] = float(parts[2])
            BOT_SETTINGS["price_min"] = float(parts[3])
            BOT_SETTINGS["price_max"] = float(parts[4]) if parts[4] != "0" else None
            send_owner_message("✅ Filters update ho gaye.")
        except:
            send_owner_message("❌ Usage: /setfilters 20 3.5 200 2000  (price_max=0 matlab no-limit)")
    elif cmd == "/addcategory":
        if len(parts) < 2:
            send_owner_message("❌ Usage: /addcategory https://fktr.in/xxxxx")
        else:
            url = parts[1]
            start_category_scheduler(url, BOT_SETTINGS["interval_minutes"], BOT_SETTINGS["min_discount"],
                                      BOT_SETTINGS["min_rating"], BOT_SETTINGS["price_min"], BOT_SETTINGS["price_max"])
            send_owner_message(f"✅ Naya category add ho gaya:\n{url[:60]}")
    elif cmd == "/mute":
        if len(parts) < 2:
            send_owner_message("❌ Usage: /mute <partial-url>")
        else:
            match = next((u for u in _category_scheduler_state["running_urls"] if parts[1] in u), None)
            if match:
                BOT_SETTINGS["muted_categories"].add(match)
                send_owner_message(f"🔇 Muted: {match[:60]}")
            else:
                send_owner_message("❌ Yeh URL kisi active category se match nahi hua.")
    elif cmd == "/unmute":
        if len(parts) < 2:
            send_owner_message("❌ Usage: /unmute <partial-url>")
        else:
            match = next((u for u in BOT_SETTINGS["muted_categories"] if parts[1] in u), None)
            if match:
                BOT_SETTINGS["muted_categories"].discard(match)
                send_owner_message(f"🔊 Unmuted: {match[:60]}")
            else:
                send_owner_message("❌ Yeh URL muted list mein nahi mila.")
    elif cmd == "/listcategories":
        cats = "\n".join(f"• {u[:60]}" for u in _category_scheduler_state["running_urls"]) or "Koi category active nahi"
        send_owner_message(f"<b>📋 Active Categories:</b>\n{cats}")
    else:
        send_owner_message("❓ Command samajh nahi aaya. /help bhejo poori list ke liye.")

def handle_callback_query(callback):
    callback_id = callback["id"]
    data = callback.get("data", "")
    if data == "toggle_pause":
        BOT_SETTINGS["paused"] = not BOT_SETTINGS["paused"]
        answer_callback(callback_id, "Toggled")
        handle_owner_command("/status", OWNER_ID)
    elif data == "status":
        answer_callback(callback_id)
        handle_owner_command("/status", OWNER_ID)
    elif data == "list_cats":
        answer_callback(callback_id)
        handle_owner_command("/listcategories", OWNER_ID)
    else:
        answer_callback(callback_id)

def background_bot_loop():
    print("Playwright background bot listener started...")
    while True:
        try:
            state = load_state()
            processed = set(state.get("processed_ids", []))
            last_offset = state.get("last_update_id", 0)

            resp = requests.get(f"https://api.telegram.org/bot{RELAY_BOT_TOKEN}/getUpdates", params={"offset": last_offset + 1, "timeout": 15}, timeout=20)
            if resp.ok:
                updates = resp.json().get("result", [])
                for update in updates:
                    last_offset = max(last_offset, update["update_id"])

                    # --- Owner control-panel buttons (callback queries) ---
                    if "callback_query" in update and OWNER_ID:
                        cq = update["callback_query"]
                        if str(cq.get("from", {}).get("id")) == str(OWNER_ID):
                            handle_callback_query(cq)
                        continue

                    msg = update.get("channel_post") or update.get("message")
                    if not msg: continue

                    # --- Owner control-panel commands (private chat, sirf OWNER_ID se) ---
                    if OWNER_ID and str(msg.get("chat", {}).get("id")) == str(OWNER_ID):
                        text = msg.get("text", "")
                        if text.startswith("/"):
                            handle_owner_command(text, OWNER_ID)
                        continue

                    # --- Staging channel wala normal deal-processing (jaisa ka waisa) ---
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
    start_all_category_schedulers()
    background_bot_loop()
            
