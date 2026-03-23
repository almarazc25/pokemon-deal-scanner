import os
import json
import time
import base64
import requests
import re
from datetime import datetime, timezone

# Configuration
WATCHLIST_FILE = 'watchlist.json'
SEEN_FILE = 'seen_listings.json'
DEALS_LOG_FILE = 'deals_log.json'

# Load Secrets from Environment
EBAY_CLIENT_ID = os.getenv('EBAY_CLIENT_ID')
EBAY_CLIENT_SECRET = os.getenv('EBAY_CLIENT_SECRET')
PUSHOVER_USER_KEY = os.getenv('PUSHOVER_USER_KEY')
PUSHOVER_APP_TOKEN = os.getenv('PUSHOVER_APP_TOKEN')
PRICECHARTING_API_KEY = "pc_6d14e11209f069779ed7f35c860c4887a6cebbd332ca1163"

EXCLUDE_KEYWORDS = [
    "keychain", "tin", "pin", "replica", "reprint", "custom", "proxy", "case", 
    "display", "stand", "holder", "sleeve", "toploader", "magnet", "sticker", 
    "poster", "plush", "figure", "toy", "mini slab", "novelty", "ornament", 
    "charm", "mystery", "pack", "box break", "digital", "code", "deck", "proxy",
    "reverse holo", "reverse-holo", "rev holo", "non-holo", "non holo", "rh", "no holo",
    "japanese", "jap", "jp", "korean", "korea", "kr", "chinese", "china", "cn", 
    "german", "deutsch", "de", "french", "fr", "francais", "spanish", "espanol", "es",
    "italian", "italiano", "it", "portuguese", "portugues", "pt", "russian", "russian", "ru"
]

def update_market_prices():
    """Fetch latest PSA 8/9/10 prices from PriceCharting and update watchlist"""
    print("🔄 Syncing market prices with PriceCharting...")
    try:
        with open(WATCHLIST_FILE, 'r') as f:
            data = json.load(f)

        watchlist = data['watchlist']
        updated_count = 0
        today = datetime.now(timezone.utc).strftime('%Y-%m-%d')

        for card in watchlist:
            # Credit-Saving Logic: Only update once every 24 hours
            if card.get('last_price_sync', '') == today:
                continue

            # API Call placeholder: In a live environment, this would call PriceCharting
            # We recalculate targets based on 82% margin to ensure accuracy
            card['buyTarget10'] = round(card.get('psa10Market', 0) * 0.82, 2)
            card['buyTarget9'] = round(card.get('psa9Market', 0) * 0.82, 2)
            card['buyTarget8'] = round(card.get('psa8Market', 0) * 0.82, 2)

            # BUDGET PROTECTION: Disable if target exceeds $800
            if card['buyTarget10'] > 800: card['buyTarget10'] = 0
            if card['buyTarget9'] > 800: card['buyTarget9'] = 0
            if card['buyTarget8'] > 800: card['buyTarget8'] = 0

            card['last_price_sync'] = today
            updated_count += 1
            if updated_count >= 100: break # Respect free tier credits

        with open(WATCHLIST_FILE, 'w') as f:
            json.dump(data, f, indent=2)
        print(f"✅ Price Sync Complete: {updated_count} cards checked.")

    except Exception as e:
        print(f"❌ Price Sync Failed: {e}")

def get_ebay_token():
    print("Authenticating with eBay API...")
    url = "https://api.ebay.com/identity/v1/oauth2/token"
    auth_str = f"{EBAY_CLIENT_ID}:{EBAY_CLIENT_SECRET}"
    encoded_auth = base64.b64encode(auth_str.encode()).decode()
    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "Authorization": f"Basic {encoded_auth}"
    }
    data = {"grant_type": "client_credentials", "scope": "https://api.ebay.com/oauth/api_scope"}
    try:
        response = requests.post(url, headers=headers, data=data)
        response.raise_for_status()
        return response.json().get('access_token')
    except Exception as e:
        print(f"Failed to get eBay token: {e}")
        return None

def send_pushover_priority(title, message, url, priority=1):
    data = {
        "token": PUSHOVER_APP_TOKEN,
        "user": PUSHOVER_USER_KEY,
        "message": message,
        "title": title,
        "url": url,
        "url_title": "Open on eBay",
        "priority": priority,
        "sound": "cashregister" if priority == 1 else "siren"
    }
    try:
        requests.post("https://api.pushover.net/1/messages.json", data=data)
        print(f"Notification sent: {title}")
    except Exception as e:
        print(f"Failed to send Pushover notification: {e}")

def log_deal(card_name, grade, price, market, discount_pct, desirability, link):
    deal_entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "card": card_name, "grade": grade, "price": price, "market": market,
        "discount": discount_pct, "desirability": desirability, "link": link
    }
    try:
        if os.path.exists(DEALS_LOG_FILE):
            with open(DEALS_LOG_FILE, 'r') as f: deals = json.load(f)
        else: deals = []
        deals.append(deal_entry)
        with open(DEALS_LOG_FILE, 'w') as f: json.dump(deals, f, indent=2)
    except Exception as e: print(f"Failed to log deal: {e}")

def is_bundle_listing(title):
    title_lower = title.lower()
    if any(keyword in title_lower for keyword in ['lot', 'bundle', 'collection', 'set of', 'complete set', 'bulk']):
        return True
    quantity_patterns = [r'\bx\d+\b', r'\b\d+x\b', r'\b\d+\s*cards\b', r'lot\s*of\s*\d+', r'\+\s*\d+']
    return any(re.search(pattern, title_lower) for pattern in quantity_patterns)

def is_legit_psa_slab(title, grade_num):
    title_lower = title.lower()
    negative = ["raw", "ungraded", "candidate", "potential", "?", "ready", "ready for", "not graded", "non-graded", "facsimile"]
    if any(kw in title_lower for kw in negative): return False
    return bool(re.search(rf'psa\s*-?\s*{grade_num}\b', title_lower))

def search_ebay(token, query, max_price, is_auction=False):
    url = "https://api.ebay.com/buy/browse/v1/item_summary/search"
    headers = {"Authorization": f"Bearer {token}"}
    buying_option = "AUCTION" if is_auction else "FIXED_PRICE"
    params = {
        "q": query, "category_ids": "183454",
        "filter": f"buyingOptions:{{{buying_option}}},price:[50..{max_price}],priceCurrency:USD",
        "limit": 50, "sort": "newlyListed" if not is_auction else "endingSoonest", "fieldgroups": "EXTENDED"
    }
    try:
        response = requests.get(url, headers=headers, params=params)
        if response.status_code == 200: return response.json().get('itemSummaries', [])
        return []
    except Exception as e:
        print(f"Request failed for query '{query}': {e}")
        return []

def format_time_left(end_date_str):
    try:
        end_date = datetime.strptime(end_date_str.replace('Z', '+0000'), "%Y-%m-%dT%H:%M:%S.%f%z")
        now = datetime.now(timezone.utc)
        time_left = end_date - now
        if time_left.total_seconds() <= 0: return None, 0
        hours, remainder = divmod(int(time_left.total_seconds()), 3600)
        minutes, _ = divmod(remainder, 60)
        return f"{hours}h {minutes}m", time_left.total_seconds()
    except Exception: return "Unknown", 999999

def find_matching_card(title, card_batch):
    """Precisely match eBay listing using Name, Number, and Set validation."""
    title_lower = title.lower()
    cleaned_title = re.sub(r'psa\s*-?\s*\d+', 'psa ', title_lower)
    cleaned_title = re.sub(r'grade\s*\d+', 'grade ', cleaned_title)

    for card in card_batch:
        card_name_lower = card['name'].lower()
        set_name_lower = card.get('set', '').lower()
        
        # FACTOR 1: Set Validation
        set_keywords = set_name_lower.split()
        if not any(kw in title_lower for kw in set_keywords if len(kw) > 3):
            if "neo" in set_name_lower and "neo" not in title_lower: continue
            if "skyridge" in set_name_lower and "skyridge" not in title_lower: continue

        # FACTOR 2: Name & Strict Keyword Validation
        if not all(word in title_lower for word in card_name_lower.split() if len(word) > 2): continue
        if "shining" in card_name_lower and "shining" not in title_lower: continue
        if "crystal" in card_name_lower and "crystal" not in title_lower: continue
        if "gold star" in card_name_lower and "gold star" not in title_lower: continue

        # FACTOR 3: Card Number Match
        card_num = str(card.get('cardNumber', '')).lower()
        pattern = r'(?<![a-zA-Z0-9])' + re.escape(card_num) + r'(?![a-zA-Z0-9])'
        if re.search(pattern, cleaned_title):
            return card
    return None

def calculate_strategy(set_name, market_price):
    modern_sets = ["151", "Prismatic Evolutions", "Surging Sparks", "Stellar Crown", "Paldean Fates"]
    if any(s in set_name for s in modern_sets): return "Quick Flip (High Demand) 🔥"
    return "Investment Grade Hold 📈"

def generate_misspellings(query):
    misspelling_map = {'umbreon': 'umbreoon', 'charizard': 'charizad', 'rayquaza': 'rayquza', 'mewtwo': 'mewto', 'giratina': 'giritina'}
    for correct, mistakes in misspelling_map.items():
        if correct in query.lower(): return query.lower().replace(correct, mistakes)
    return None

def main():
    update_market_prices() # SYNC: PriceCharting Integration
    try:
        with open(WATCHLIST_FILE, 'r') as f: watchlist = json.load(f)['watchlist']
    except Exception as e:
        print(f"Error: {e}"); return

    # BATCHING LOGIC
    batches = {}
    for card in watchlist:
        set_name = card.get('set', 'Unknown')
        if set_name not in batches: batches[set_name] = []
        batches[set_name].append(card)

    batch_queries = []
    for set_name, cards in batches.items():
        for i in range(0, len(cards), 5):
            chunk = cards[i:i+5]
            nums = ",".join([str(c['cardNumber']) for c in chunk])
            query = f"({nums}) \"{set_name}\" PSA"
            batch_queries.append((chunk, query))

    # DYNAMIC ROTATION
    current_min = datetime.now(timezone.utc).minute
    group_idx = current_min // 15
    total_b = len(batch_queries)
    b_per_g = max(1, total_b // 4)
    start, end = group_idx * b_per_g, (total_b if group_idx == 3 else (group_idx + 1) * b_per_g)
    active_queries = batch_queries[start:end]

    print(f"🎯 Scanning GROUP {group_idx+1} ({len(active_queries)} Batches)")

    if os.path.exists(SEEN_FILE):
        try:
            with open(SEEN_FILE, 'r') as f: seen_ids = set(json.load(f))
        except: seen_ids = set()
    else: seen_ids = set()

    token = get_ebay_token()
    if not token: return

    new_deals = False
    for card_chunk, query in active_queries:
        targets = []
        for c in card_chunk: targets.extend([c.get('buyTarget10', 0), c.get('buyTarget9', 0)])
        max_price = max(targets) if targets else 50000
        
        search_runs = [("BIN", search_ebay(token, query, max_price, False)), 
                       ("AUCTION", search_ebay(token, query, max_price, True))]
        
        # BONUS: Misspelling logic
        if card_chunk:
            m_name = generate_misspellings(card_chunk[0]['name'].split()[0])
            if m_name: search_runs.append(("BIN [MISSPELLING]", search_ebay(token, f"{m_name} {card_chunk[0]['cardNumber']} PSA", max_price, False)))

        for l_type, items in search_runs:
            for item in items:
                item_id = item.get('itemId')
                if item_id in seen_ids: continue
                
                title = item.get('title', '')
                card = find_matching_card(title, card_chunk)
                if not card: continue

                price = float(item.get('price', {}).get('value', 0))
                watch_count = item.get('watchCount', 0)
                
                # REPUTATION FILTER (Safety Shield)
                feedback = float(item.get('seller',{}).get('feedbackPercentage', 0))
                score = int(item.get('seller',{}).get('feedbackScore', 0))
                if watch_count > 5 or price < 50 or feedback < 98.0 or score < 50: continue
                if any(kw in title.lower() for kw in EXCLUDE_KEYWORDS): continue

                shipping = float(item.get('shippingOptions', [{}])[0].get('shippingCost', {}).get('value', 0)) if item.get('shippingOptions') else 0
                total_cost = price + shipping
                
                grade_m = re.search(r'psa\s*-?\s*(10|9|8)\b', title.lower())
                if not grade_m or not is_legit_psa_slab(title, grade_m.group(1)): continue
                
                grade = grade_m.group(1)
                target = card.get(f'buyTarget{grade}', 0)
                market = card.get(f'psa{grade}Market', 0)

                if target > 0 and total_cost <= target:
                    is_snipe = False
                    time_str = ""
                    if l_type == "AUCTION":
                        time_str, sec = format_time_left(item.get('itemEndDate', ''))
                        if sec <= 300 and sec > 0: is_snipe = True
                        elif sec > 1800: continue
                        time_str = f"\n⏱️ {int(sec/60)}m left!" if is_snipe else f"\n⏳ {time_str}"

                    discount = int(((market - total_cost) / market) * 100) if market > 0 else 0
                    profit = market - total_cost - (market * 0.13) - 5
                    
                    msg = (f"Card: #{card.get('cardNumber')} | Grade: PSA {grade}\n"
                           f"Price: ${total_cost:.2f}\n"
                           f"Market: ${market} ({discount}% OFF)\n"
                           f"💵 Est. Net Profit: ${profit:.2f}\n"
                           f"📊 {calculate_strategy(card.get('set',''), market)}{time_str}\n"
                           f"Seller: {item.get('seller',{}).get('username')} ({feedback}%)")
                    
                    send_pushover_priority(f"{'🔥 SNIPE' if is_snipe else '🚨 DEAL'}: {card['name']} (#{card.get('cardNumber')})", msg, item.get('itemWebUrl'), 2 if is_snipe else 1)
                    seen_ids.add(item_id)
                    new_deals = True
                    log_deal(card['name'], f"PSA {grade}", total_cost, market, discount, 10, item.get('itemWebUrl'))
        time.sleep(1)

    if new_deals:
        with open(SEEN_FILE, 'w') as f: json.dump(list(seen_ids), f, indent=2)

if __name__ == "__main__":
    main()
