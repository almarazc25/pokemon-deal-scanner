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
DEALS_LOG_FILE = 'deals_log.json'  # Track deals for weekly summary

# Load Secrets from Environment
EBAY_CLIENT_ID = os.getenv('EBAY_CLIENT_ID')
EBAY_CLIENT_SECRET = os.getenv('EBAY_CLIENT_SECRET')
PUSHOVER_USER_KEY = os.getenv('PUSHOVER_USER_KEY')
PUSHOVER_APP_TOKEN = os.getenv('PUSHOVER_APP_TOKEN')

# Keywords to filter out novelty items, cases, and non-cards
EXCLUDE_KEYWORDS =[
    "keychain", "key chain", "tin", "pin", "replica", "reprint", "custom", "proxy", 
    "lot of", "lot ", "bundle", "case", "display", "stand", "holder", "sleeve", 
    "toploader", "magnet", "sticker", "poster", "plush", "figure", "toy", 
    "mini slab", "mini ", "slabby", "novelty", "ornament", "charm", 
    "graded card case", "slab case", "card stand", "psa slab", "mystery", "pack", "box break"
]

def get_ebay_token():
    """Get OAuth Application Token from eBay"""
    print("Authenticating with eBay API...")
    url = "https://api.ebay.com/identity/v1/oauth2/token"
    auth_str = f"{EBAY_CLIENT_ID}:{EBAY_CLIENT_SECRET}"
    encoded_auth = base64.b64encode(auth_str.encode()).decode()
    
    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "Authorization": f"Basic {encoded_auth}"
    }
    data = {
        "grant_type": "client_credentials",
        "scope": "https://api.ebay.com/oauth/api_scope"
    }
    
    try:
        response = requests.post(url, headers=headers, data=data)
        response.raise_for_status()
        return response.json().get('access_token')
    except Exception as e:
        print(f"Failed to get eBay token: {e}")
        return None

def send_pushover(title, message, url):
    """Send notification to phone via Pushover"""
    send_pushover_priority(title, message, url, priority=1)

def send_pushover_priority(title, message, url, priority=1):
    """Send notification to phone via Pushover with custom priority"""
    data = {
        "token": PUSHOVER_APP_TOKEN,
        "user": PUSHOVER_USER_KEY,
        "message": message,
        "title": title,
        "url": url,
        "url_title": "Open on eBay",
        "priority": priority,
        "sound": "cashregister" if priority == 1 else "siren"  # Siren for urgent snipes!
    }
    try:
        requests.post("https://api.pushover.net/1/messages.json", data=data)
        print(f"Notification sent: {title}")
    except Exception as e:
        print(f"Failed to send Pushover notification: {e}")

def log_deal(card_name, grade, price, market, discount_pct, desirability, link):
    """Log deal to JSON file for weekly summary tracking"""
    deal_entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "card": card_name,
        "grade": grade,
        "price": price,
        "market": market,
        "discount": discount_pct,
        "desirability": desirability,
        "link": link
    }
    
    try:
        if os.path.exists(DEALS_LOG_FILE):
            with open(DEALS_LOG_FILE, 'r') as f:
                deals = json.load(f)
        else:
            deals = []
        
        deals.append(deal_entry)
        
        with open(DEALS_LOG_FILE, 'w') as f:
            json.dump(deals, f, indent=2)
    except Exception as e:
        print(f"Failed to log deal: {e}")

def generate_misspellings(query):
    """Generate common misspellings to catch underpriced listings others miss"""
    misspelling_map = {
        'umbreon': ['umbreon', 'umbreoon', 'umbrion'],
        'espeon': ['espion', 'espon'],
        'glaceon': ['glacoen', 'glacion'],
        'leafeon': ['leafon', 'leafion'],
        'sylveon': ['sylvion', 'sylvon'],
        'vaporeon': ['vapereon', 'vaporion'],
        'flareon': ['flarion', 'flaroen'],
        'jolteon': ['joltion', 'joltoen'],
        'charizard': ['charizad', 'charizrd', 'charzard'],
        'pikachu': ['pikchu', 'pikacu'],
        'rayquaza': ['rayquza', 'raquaza'],
        'mewtwo': ['mewto', 'mewtoo'],
        'giratina': ['giritina', 'garatina'],
        'dragonite': ['dragonight', 'dragonit'],
        'gengar': ['genger', 'gangar'],
        'lucario': ['lucario', 'lucarion'],
        'gardevoir': ['gardevior', 'gardvoir']
    }
    
    query_lower = query.lower()
    for correct, mistakes in misspelling_map.items():
        if correct in query_lower:
            # Return one common misspelling variant
            return query.lower().replace(correct, mistakes[0])
    
    return None

def is_bundle_listing(title):
    """Detect if listing contains multiple cards or sets"""
    title_lower = title.lower()
    
    # 1. Keywords that almost always mean multiple cards
    bundle_keywords = ['lot', 'bundle', 'collection', 'set of', 'lots', 'complete set', 'bulk']
    if any(keyword in title_lower for keyword in bundle_keywords):
        return True
    
    # 2. Regex for quantities like "x2", "2x", "5 cards", "lot of 3"
    quantity_patterns = [
        r'\bx\d+\b',          # x2, x3, etc.
        r'\b\d+x\b',          # 2x, 3x, etc.
        r'\b\d+\s*cards\b',    # 5 cards
        r'lot\s*of\s*\d+',     # lot of 3
        r'\+\s*\d+'            # + 2
    ]
    for pattern in quantity_patterns:
        if re.search(pattern, title_lower):
            return True
            
    # 3. Specific bundle indicators
    if " + " in title_lower or " and " in title_lower:
        # Only count if it's adding another card or item (not just "mint and centered")
        if re.search(r'\b(and|&)\s+(?!centered|clean|mint|psa)', title_lower):
            return True
            
    return False

def is_legit_psa_slab(title, grade_num):
    """Strictly verify if listing is a graded PSA slab and not a raw card 'candidate'"""
    title_lower = title.lower()
    
    # 1. Negative keywords: things that indicate it's NOT yet a slab
    negative_keywords = [
        "raw", "ungraded", "un-graded", "candidate", "potential", "?", "ready", 
        "ready for", "for psa", "not graded", "non-graded", "proxy", "replica",
        "custom", "reprint", "facsimile"
    ]
    if any(kw in title_lower for kw in negative_keywords):
        return False
        
    # 2. Strict PSA Grade Match
    # Ensures "PSA 10" or "PSA-10" or "PSA10" is present
    pattern = rf'psa\s*-?\s*{grade_num}\b'
    if not re.search(pattern, title_lower):
        return False
        
    return True

def search_ebay(token, query, max_price, is_auction=False):
    """Search eBay Browse API (Combined query for PSA 8/9/10)"""
    url = "https://api.ebay.com/buy/browse/v1/item_summary/search"
    headers = {"Authorization": f"Bearer {token}"}
    
    buying_option = "AUCTION" if is_auction else "FIXED_PRICE"
    
    params = {
        "q": query,
        "category_ids": "183454",
        "filter": f"buyingOptions:{{{buying_option}}},price:[50..{max_price}],priceCurrency:USD",
        "limit": 15,
        "sort": "newlyListed" if not is_auction else "endingSoonest",
        "fieldgroups": "EXTENDED"
    }
    
    try:
        response = requests.get(url, headers=headers, params=params)
        if response.status_code == 200:
            return response.json().get('itemSummaries',[])
        else:
            print(f"API Error ({response.status_code}) for query '{query}'")
            return[]
    except Exception as e:
        print(f"Request failed for query '{query}': {e}")
        return[]

def format_time_left(end_date_str):
    """Calculate time left for auctions"""
    try:
        end_date = datetime.strptime(end_date_str.replace('Z', '+0000'), "%Y-%m-%dT%H:%M:%S.%f%z")
        now = datetime.now(timezone.utc)
        time_left = end_date - now
        
        if time_left.total_seconds() <= 0:
            return None, 0
            
        hours, remainder = divmod(int(time_left.total_seconds()), 3600)
        minutes, _ = divmod(remainder, 60)
        return f"{hours}h {minutes}m", time_left.total_seconds()
    except Exception:
        return "Unknown", 999999

def main():
    try:
        with open(WATCHLIST_FILE, 'r') as f:
            watchlist = json.load(f)['watchlist']
    except Exception as e:
        print(f"Error loading watchlist: {e}")
        return
    
    current_minute = datetime.now(timezone.utc).minute
    total_cards = len(watchlist)
    cards_per_group = total_cards // 4
    
    if current_minute <= 14:
        group_index = 0
        group_name = "A 🔵"
    elif current_minute <= 29:
        group_index = 1
        group_name = "B 🟢"
    elif current_minute <= 44:
        group_index = 2
        group_name = "C 🟡"
    else:
        group_index = 3
        group_name = "D 🟣"
    
    start_idx = group_index * cards_per_group
    end_idx = total_cards if group_index == 3 else (group_index + 1) * cards_per_group
    
    active_watchlist = watchlist[start_idx:end_idx]
    print(f"🎯 Scanning GROUP {group_name} ({len(active_watchlist)} cards) - Cards {start_idx+1}-{end_idx}")
    
    if os.path.exists(SEEN_FILE):
        try:
            with open(SEEN_FILE, 'r') as f:
                seen_ids = set(json.load(f))
        except:
            seen_ids = set()
    else:
        seen_ids = set()

    token = get_ebay_token()
    if not token:
        return

    new_deals_found = False

    for card in active_watchlist:
        max_api_price = max(card['buyTarget10'], card['buyTarget9'], card['buyTarget8'])
        query = card['searchQuery']
        card_number = str(card.get('cardNumber', '')).lower()
        
        print(f"Scanning: {card['name']} (Max API Price: ${max_api_price})")
        
        all_results = []
        search_types = [
            ("BUY IT NOW", search_ebay(token, query, max_api_price, is_auction=False)),
            ("AUCTION", search_ebay(token, query, max_api_price, is_auction=True))
        ]
        
        for listing_type, results in search_types:
            all_results.extend([(listing_type, item) for item in results])
            time.sleep(1)
        
        card_index = active_watchlist.index(card)
        if card_index < 5:
            if card_index % 2 == 0:
                misspelled = generate_misspellings(query)
                if misspelled:
                    print(f"  + Bonus: Misspelling search '{misspelled}'")
                    bonus_results = search_ebay(token, misspelled, max_api_price, is_auction=False)
                    all_results.extend([("BUY IT NOW [MISSPELLING]", item) for item in bonus_results])
                    time.sleep(1)
            else:
                fresh_query = f"{query} just back PSA fresh grade"
                print(f"  + Bonus: Fresh grade search")
                bonus_results = search_ebay(token, fresh_query, max_api_price, is_auction=False)
                all_results.extend([("BUY IT NOW [FRESH GRADE]", item) for item in bonus_results])
                time.sleep(1)
        
        for listing_type, item in all_results:
            item_id = item.get('itemId')
            if item_id in seen_ids:
                continue
            
            title = item.get('title', '').lower()
            price = float(item.get('price', {}).get('value', 0))
            
            if is_bundle_listing(title):
                continue
            
            watch_count = item.get('watchCount', 0)
            if watch_count > 5:
                print(f"  ⏭️ Skipping - {watch_count} watchers (too much competition)")
                continue
            
            shipping_cost = 0
            shipping_info = item.get('shippingOptions', [])
            if shipping_info:
                shipping_cost = float(shipping_info[0].get('shippingCost', {}).get('value', 0))
            
            total_price = price + shipping_cost
            buying_options = item.get('buyingOptions', [])
            has_best_offer = 'BEST_OFFER' in buying_options
            best_offer_emoji = " 💰" if has_best_offer else ""
            
            if price < 50:
                continue
            if any(kw in title for kw in EXCLUDE_KEYWORDS):
                continue
            
            if card_number:
                pattern = r'(?<![a-zA-Z0-9])' + re.escape(card_number) + r'(?![a-zA-Z0-9])'
                if not re.search(pattern, title):
                    continue

            grade_match = re.search(r'psa\s*-?\s*(10|9|8)\b', title)
            if not grade_match:
                continue
                
            grade_num = grade_match.group(1)
            grade_label = f"PSA {grade_num}"
            
            if not is_legit_psa_slab(title, grade_num):
                print(f"  ⏭️ Skipping - Potential raw card candidate: '{title}'")
                continue
            
            if grade_num == "10":
                target = card['buyTarget10']
                market = card['psa10Market']
            elif grade_num == "9":
                target = card['buyTarget9']
                market = card['psa9Market']
            else:
                target = card['buyTarget8']
                market = card['psa8Market']
            
            if total_price <= target:
                is_snipe_opportunity = False
                time_str = ""
                if "AUCTION" in listing_type:
                    end_date = item.get('itemEndDate', '')
                    time_str, seconds_left = format_time_left(end_date)
                    if seconds_left <= 300 and seconds_left > 0:
                        is_snipe_opportunity = True
                        time_str = f"\n🔥⏱️ ENDING IN {int(seconds_left/60)} MIN - SNIPE NOW!"
                    elif seconds_left <= 1800 and seconds_left > 0:
                        time_str = f"\n⏳ Ends in: {time_str}"
                    else:
                        continue

                pct_market = int((total_price / market) * 100) if market > 0 else 0
                discount_pct = int(((market - total_price) / market) * 100) if market > 0 else 0
                savings = target - total_price
                
                desirability = 0
                if grade_num == "10":
                    desirability += 3
                    grade_emoji = "🏆"
                elif grade_num == "9":
                    desirability += 2
                    grade_emoji = "✨"
                else:
                    desirability += 1
                    grade_emoji = "⚠️"
                
                if discount_pct >= 25: desirability += 3
                elif discount_pct >= 20: desirability += 2
                elif discount_pct >= 10: desirability += 1
                
                iconic_names = ['umbreon', 'charizard', 'pikachu', 'rayquaza', 'lugia', 'mewtwo', 'giratina']
                if any(name in card['name'].lower() for name in iconic_names): desirability += 2
                
                oop_sets = ['evolving skies', 'lost origin', 'silver tempest', 'brilliant stars']
                if any(set_name in card['name'].lower() for set_name in oop_sets): desirability += 1
                
                if any(term in card['name'].lower() for term in ['alt art', 'sir', 'vmax']): desirability += 1
                desirability = min(desirability, 10)
                
                confidence = "HIGH 🔥" if desirability >= 8 and discount_pct >= 15 else ("MEDIUM 👍" if desirability >= 5 and discount_pct >= 10 else "LOW 💡")
                
                if discount_pct >= 20 and ('evolving skies' in card['name'].lower() or 'lost origin' in card['name'].lower()):
                    strategy = "Long-term hold 📈 (Dipped card)"
                elif 'prismatic' in card['name'].lower() or 'surging sparks' in card['name'].lower():
                    strategy = "Quick flip 💰 (Hot card)"
                else:
                    strategy = "Medium hold ⏳"
                
                stars = "⭐" * desirability
                seller = item.get('seller', {}).get('username', 'Unknown')
                feedback = item.get('seller', {}).get('feedbackPercentage', 'N/A')
                condition = item.get('condition', 'Unknown')
                link = item.get('itemWebUrl')
                
                watch_badge = ""
                if watch_count == 0: watch_badge = "\n💎 NO WATCHERS - You found it first!"
                elif watch_count <= 2: watch_badge = f"\n👀 Only {watch_count} watchers - Low competition"
                
                shipping_line = f"\nShipping: ${shipping_cost:.2f}" if shipping_cost > 0 else "\nShipping: FREE ✅"
                
                best_offer_line = ""
                if has_best_offer:
                    optimal_offer = price * 0.87
                    min_offer = target * 1.05
                    if optimal_offer >= min_offer:
                        offer_discount = int(((price - optimal_offer) / price) * 100)
                        best_offer_line = f"\n💰 OPTIMAL OFFER: ${optimal_offer:.0f} ({offer_discount}% below asking)"
                    else:
                        best_offer_line = f"\n💰 ACCEPTS OFFERS - Start at ${min_offer:.0f} (leave room to negotiate)"
                
                special_catch = ""
                if "MISSPELLING" in listing_type: special_catch = "\n🎯 MISSPELLING CATCH - Low competition!"
                elif "FRESH GRADE" in listing_type: special_catch = "\n🆕 FRESH FROM GRADING - Uninformed seller!"
                
                notification_priority = 2 if is_snipe_opportunity else 1
                notif_title = f"🔥 URGENT SNIPE: {card['name']}{best_offer_emoji}" if is_snipe_opportunity else f"🚨 {listing_type.split('[')[0].strip()}: {card['name']}{best_offer_emoji}"
                
                msg = (
                    f"Grade: {grade_label} {grade_emoji}\n"
                    f"Price: ${price:.2f}{shipping_line}\n"
                    f"TOTAL: ${total_price:.2f} ({pct_market}% of market, {discount_pct}% OFF)\n"
                    f"Target: ${target} | Market: ${market}\n"
                    f"Savings: ${savings:.2f} below your max{time_str}{watch_badge}{best_offer_line}{special_catch}\n\n"
                    f"⭐ DESIRABILITY: {desirability}/10 {stars}\n"
                    f"🎯 CONFIDENCE: {confidence}\n"
                    f"📊 STRATEGY: {strategy}\n\n"
                    f"Seller: {seller} ({feedback}%)\n"
                    f"Condition: {condition}"
                )
                
                send_pushover_priority(notif_title, msg, link, notification_priority)
                seen_ids.add(item_id)
                new_deals_found = True
                log_deal(card['name'], grade_label, total_price, market, discount_pct, desirability, link)

    if new_deals_found:
        with open(SEEN_FILE, 'w') as f:
            json.dump(list(seen_ids), f, indent=2)
        print("Scan complete. New deals found and saved.")
    else:
        print("Scan complete. No new deals found.")

if __name__ == "__main__":
    main()
