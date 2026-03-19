import os
import json
import time
import base64
import requests

# Configuration
WATCHLIST_FILE = 'watchlist.json'
SEEN_FILE = 'seen_listings.json'

# Load Secrets from Environment
EBAY_CLIENT_ID = os.getenv('EBAY_CLIENT_ID')
EBAY_CLIENT_SECRET = os.getenv('EBAY_CLIENT_SECRET')
PUSHOVER_USER_KEY = os.getenv('PUSHOVER_USER_KEY')
PUSHOVER_APP_TOKEN = os.getenv('PUSHOVER_APP_TOKEN')

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
    data = {
        "token": PUSHOVER_APP_TOKEN,
        "user": PUSHOVER_USER_KEY,
        "message": message,
        "title": title,
        "url": url,
        "url_title": "Open on eBay",
        "priority": 1,
        "sound": "cashregister"
    }
    try:
        requests.post("https://api.pushover.net/1/messages.json", data=data)
        print(f"Notification sent: {title}")
    except Exception as e:
        print(f"Failed to send Pushover notification: {e}")

def search_ebay(token, query, max_price):
    """Search eBay Browse API for Buy It Now deals"""
    url = "https://api.ebay.com/buy/browse/v1/item_summary/search"
    headers = {"Authorization": f"Bearer {token}"}
    
    # Category 183454 = CCG Individual Cards
    # filter: buyingOptions:{FIXED_PRICE} = Buy It Now
    # filter: price:[..X] = Price up to X
    params = {
        "q": query,
        "category_ids": "183454",
        "filter": f"buyingOptions:{{FIXED_PRICE}},price:[..{max_price}],priceCurrency:USD",
        "limit": 10,
        "sort": "newlyListed"
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

def main():
    # 1. Load Watchlist
    try:
        with open(WATCHLIST_FILE, 'r') as f:
            watchlist = json.load(f)['watchlist']
    except Exception as e:
        print(f"Error loading watchlist: {e}")
        return
    
    # 2. Load Seen Listings
    if os.path.exists(SEEN_FILE):
        try:
            with open(SEEN_FILE, 'r') as f:
                seen_ids = set(json.load(f))
        except:
            seen_ids = set()
    else:
        seen_ids = set()

    # 3. Authenticate
    token = get_ebay_token()
    if not token:
        return

    new_deals_found = False

    # 4. Scan
    for card in watchlist:
        # Check both PSA 9 and PSA 10 targets
        targets = [
            ("PSA 9", card['searchQuery9'], card['buyTarget9']),
            ("PSA 10", card['searchQuery10'], card['buyTarget10'])
        ]
        
        for grade, query, target_price in targets:
            print(f"Scanning: {card['name']} | {grade} (Target: ${target_price})")
            results = search_ebay(token, query, target_price)
            
            for item in results:
                item_id = item.get('itemId')
                
                # Skip if we already notified about this listing
                if item_id in seen_ids:
                    continue
                
                # Extract listing details
                price = float(item.get('price', {}).get('value', 0))
                seller = item.get('seller', {}).get('username', 'Unknown Seller')
                feedback = item.get('seller', {}).get('feedbackPercentage', 'N/A')
                condition = item.get('condition', 'Unknown Condition')
                link = item.get('itemWebUrl')
                
                # Double check price just in case API filter was loose
                if price > 0 and price <= target_price:
                    savings = target_price - price
                    
                    title = f"🚨 DEAL: {card['name']}"
                    msg = (f"{grade} listed at ${price:.2f} (your target: ${target_price})\n"
                           f"Savings: ${savings:.2f} below target\n"
                           f"Seller: {seller} ({feedback}% feedback)\n"
                           f"Condition: {condition}")
                    
                    send_pushover(title, msg, link)
                    seen_ids.add(item_id)
                    new_deals_found = True
            
            # Sleep briefly to respect eBay API rate limits
            time.sleep(1)

    # 5. Save updated seen listings back to file
    if new_deals_found:
        with open(SEEN_FILE, 'w') as f:
            json.dump(list(seen_ids), f, indent=2)
        print("Scan complete. New deals found and saved.")
    else:
        print("Scan complete. No new deals found.")

if __name__ == "__main__":
    main()