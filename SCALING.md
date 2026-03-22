# 📈 Scanner Scaling Guide

## How the Rotating Groups Work

Your scanner now uses **rotating card groups** to monitor **~42 cards** while staying under eBay's 5,000 calls/day limit.

### How It Works:
- **Every 15 minutes**, the scanner runs on GitHub Actions
- **Group A** (first half of watchlist): Scans at :00 and :30
- **Group B** (second half of watchlist): Scans at :15 and :45
- Each card is scanned **every 30 minutes** (still very fast!)

### Current Capacity:
- **21 cards** per group × 2 groups = **42 total cards**
- Each card: 2 API calls (Buy It Now + Auction)
- Total: ~4,032 API calls/day (80% of 5,000 limit) ✅

---

## 🎯 How to Add More Cards

### Maximum Capacity:
- **~42 cards total** at current settings
- You currently have **21 cards** (Group A only)
- **You can add ~21 more cards!**

### Steps to Add Cards:

1. **Add new card objects to `watchlist.json`:**
```json
{
  "id": "new-card-id",
  "name": "Card Name #123 (Set Name)",
  "searchQuery": "Card Name 123 Set Name PSA",
  "cardNumber": "123",
  "psa10Market": 500,
  "psa9Market": 300,
  "psa8Market": 240,
  "buyTarget10": 400,
  "buyTarget9": 240,
  "buyTarget8": 180
}
```

2. **Card Requirements:**
   - PSA 9 market price MUST be under $500
   - Must have a valid card number (not "SIR" or placeholders)
   - Buy targets under $450

3. **Recommended Cards to Add:**
   - More Evolving Skies alt arts (Flareon V, Jolteon V, etc.)
   - More Crown Zenith Galarian Gallery (Charizard V, Moltres, Zapdos)
   - Stellar Crown cards (Pikachu ex, etc.)
   - 151 set cards (Mew ex, Charizard ex, etc.)
   - Obsidian Flames (Charizard ex)

4. **Commit and push:**
```bash
git add watchlist.json
git commit -m "Add new cards to watchlist"
git push
```

---

## 📊 API Usage Calculator

**Formula:**
```
Cards per group: X
API calls per card: 2 (Buy It Now + Auction)
Scans per day: 96 (every 15 min × 24 hours)

Daily API calls = X × 2 × 96
```

**Examples:**
- 20 cards/group = 3,840 calls/day (77% usage) ✅
- 21 cards/group = 4,032 calls/day (81% usage) ✅
- 22 cards/group = 4,224 calls/day (84% usage) ✅
- 25 cards/group = 4,800 calls/day (96% usage) ⚠️
- 26 cards/group = 4,992 calls/day (99.8% usage) 🔴

**Safe maximum: 25 cards per group (50 total)**

---

## 🔧 How the Groups Are Split

The scanner automatically splits your watchlist in half:

**Example with 42 cards:**
- **Group A (Cards 1-21):** Umbreon V, Dragonite V, Espeon V... (scans at :00, :30)
- **Group B (Cards 22-42):** Jolteon V, Flareon V, Mew ex... (scans at :15, :45)

**Important:** The split is based on **card order in watchlist.json**, so you can control which cards go in which group by reordering them.

### Strategy Tip:
- Put **high-priority cards** at the **top** (Group A scans first at :00)
- Put **lower-priority cards** at the **bottom** (Group B scans at :15)

---

## ⏱️ Timing Logic

The scanner determines which group to scan based on the current minute:

- **:00-:01** → Group A
- **:15-:16** → Group B
- **:30-:31** → Group A
- **:45-:46** → Group B

This 1-minute buffer ensures the cron job (which might trigger at :00 or :01) always hits the right group.

---

## 🚀 Next Steps

1. **Add ~21 more cards** to your watchlist (currently at 21, can go to 42)
2. **Organize by priority** (top half = most wanted cards)
3. **Push changes** to GitHub
4. **Monitor logs** to confirm both groups are scanning

Your scanner will automatically handle the rotation! 🎯
