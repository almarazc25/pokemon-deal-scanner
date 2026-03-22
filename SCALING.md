# Scaling & Resource Optimization Strategy

## Current Capacity: 500 Cards
The scanner has been optimized to monitor **500 high-value cards** simultaneously across **1,500 grade-specific price points** (PSA 10, 9, 8).

### 📊 API Usage Breakdown (The "Batcher" Engine)
By utilizing eBay's OR logic and grouping cards by set, we have achieved maximum throughput while staying within the 5,000 daily call limit.

- **Batch Size**: 5 cards per API call.
- **Total Batches**: 100 batches (500 cards total).
- **Rotation**: 4 groups of 25 batches.
- **Scan Frequency**: Every 15 minutes (96 scans per day).
- **Calls per Scan**: 25 batches × 2 (Fixed Price + Auction) = 50 calls.
- **Daily Usage**: 50 calls × 96 scans = **4,800 calls**.
- **Utilization**: **96% of 5,000 limit** (Optimized for maximum coverage).

---

## Technical Edge Features

### 1. The Batcher Engine 🚀
Uses optimized queries like `(189,192,180,194,215) "Evolving Skies" PSA` to retrieve data for 5 cards in a single request. This reduced API overhead by 80%, allowing the watchlist to grow from 92 to 500 cards without increasing latency.

### 2. Profit Margin Calculator 💵
Automatically calculates **Net Profit** for every deal by subtracting:
- **Total Cost**: Price + Actual Shipping.
- **eBay Fees**: Estimated at 13% of Market Value.
- **Logistics**: $5.00 estimated outgoing shipping/handling.
*Ensures you only get notifications for deals that leave room for a healthy profit.*

### 3. Dynamic Strategy Labels 📊
Labels deals based on market demand and set age:
- **Quick Flip**: Modern hot sets (151, Prismatic Evolutions) where demand is at all-time highs.
- **Long-term Hold**: Investment-grade modern (Evolving Skies) or Vintage.
- **Legacy Hold**: Ultra-rare vintage grails.

### 4. Likelihood & Confidence Score 🎯
- **Likelihood**: HIGH (10-15% off), MEDIUM (15-25% off), LOW (25%+ off - RARE STEAL).
- **Score (1-10)**: Weighted based on grade, discount depth, and iconic status of the Pokemon.

---

## Future Growth
To scale beyond 500 cards, the rotation interval can be increased (e.g., 30-minute scans would allow for 1,000 cards) or additional eBay developer accounts can be linked.
