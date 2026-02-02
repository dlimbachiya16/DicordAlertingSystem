#!/usr/bin/env python3
"""
EPS Surprises Alert Script
Monitors earnings surprises and sends alerts to Discord
"""

import os
import json
import requests
from datetime import datetime, timedelta

# Configuration
FINNHUB_API_KEY = os.getenv('FINNHUB_API_KEY')
DISCORD_WEBHOOK = os.getenv('DISCORD_WEBHOOK_EPS_SURPRISES')
HISTORY_FILE = 'data/eps_surprises_history.json'

# Symbols to monitor (customize this list)
SYMBOLS_TO_MONITOR = [
    'AAPL', 'NVDA', 'AMD', 'META', 'AMZN', 'NFLX', 'NVAX', 'TSLA', 
    'GOOGL', 'HIMS', 'CRWV', 'SMR', 'HOOD', 'UNH', 'CPNG' 
]

# Threshold for significant surprises (%)
SURPRISE_THRESHOLD = 5.0  # Alert if surprise is more than 5%


def load_history():
    """Load earnings history"""
    if os.path.exists(HISTORY_FILE):
        with open(HISTORY_FILE, 'r') as f:
            return json.load(f)
    return {}


def save_history(history):
    """Save earnings history"""
    os.makedirs(os.path.dirname(HISTORY_FILE), exist_ok=True)
    with open(HISTORY_FILE, 'w') as f:
        json.dump(history, f, indent=2)


def get_earnings_surprises(symbol):
    """Fetch earnings surprises from Finnhub"""
    url = 'https://finnhub.io/api/v1/stock/earnings'
    params = {
        'symbol': symbol,
        'token': FINNHUB_API_KEY
    }
    
    try:
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        print(f"Error fetching earnings for {symbol}: {e}")
        return None


def create_earnings_id(symbol, earnings):
    """Create unique ID for earnings report"""
    return f"{symbol}_{earnings.get('period')}"


def calculate_surprise_pct(actual, estimate):
    """Calculate surprise percentage"""
    if estimate == 0:
        return 0
    return ((actual - estimate) / abs(estimate)) * 100


def format_discord_embed(symbol, earnings):
    """Format earnings data as Discord embed"""
    actual = earnings.get('actual', 0)
    estimate = earnings.get('estimate', 0)
    period = earnings.get('period', 'N/A')
    surprise = earnings.get('surprise', 0)
    surprise_pct = earnings.get('surprisePercent', 0)
    
    # If surprise percent not provided, calculate it
    if surprise_pct == 0 and estimate != 0:
        surprise_pct = calculate_surprise_pct(actual, estimate)
    
    # Determine if beat or miss
    if actual > estimate:
        result = "🟢 BEAT"
        color = 3066993  # Green
        emoji = "📈"
    elif actual < estimate:
        result = "🔴 MISS"
        color = 15158332  # Red
        emoji = "📉"
    else:
        result = "🟡 MET"
        color = 16776960  # Yellow
        emoji = "➡️"
    
    # Format the surprise percentage
    surprise_pct_str = f"{surprise_pct:+.2f}%"
    
    embed = {
        "title": f"{emoji} Earnings {result}: {symbol}",
        "description": f"**{period}**",
        "color": color,
        "fields": [
            {
                "name": "Actual EPS",
                "value": f"${actual:.2f}",
                "inline": True
            },
            {
                "name": "Estimated EPS",
                "value": f"${estimate:.2f}",
                "inline": True
            },
            {
                "name": "Surprise",
                "value": f"${surprise:.2f}",
                "inline": True
            },
            {
                "name": "Surprise %",
                "value": surprise_pct_str,
                "inline": True
            }
        ],
        "footer": {
            "text": "Finnhub Earnings Surprises"
        },
        "timestamp": datetime.utcnow().isoformat()
    }
    
    return embed


def send_discord_alert(embeds):
    """Send alert to Discord webhook"""
    if not DISCORD_WEBHOOK:
        print("Discord webhook not configured")
        return False
    
    # Discord allows max 10 embeds per message
    for i in range(0, len(embeds), 10):
        batch = embeds[i:i+10]
        payload = {
            "embeds": batch
        }
        
        try:
            response = requests.post(DISCORD_WEBHOOK, json=payload, timeout=10)
            response.raise_for_status()
            print(f"Sent {len(batch)} alerts to Discord")
        except Exception as e:
            print(f"Error sending Discord alert: {e}")
            return False
    
    return True


def main():
    """Main execution function"""
    if not FINNHUB_API_KEY:
        print("Error: FINNHUB_API_KEY not set")
        return
    
    # Load history
    history = load_history()
    
    print("Checking earnings surprises...")
    
    significant_surprises = []
    
    # Check each symbol
    for symbol in SYMBOLS_TO_MONITOR:
        print(f"Checking {symbol}...")
        data = get_earnings_surprises(symbol)
        
        if data and len(data) > 0:
            # Check the most recent earnings report
            latest = data[0]
            earnings_id = create_earnings_id(symbol, latest)
            
            # Check if we've seen this earnings report before
            if earnings_id not in history:
                actual = latest.get('actual', 0)
                estimate = latest.get('estimate', 0)
                surprise_pct = latest.get('surprisePercent', 0)
                
                # Calculate surprise percent if not provided
                if surprise_pct == 0 and estimate != 0:
                    surprise_pct = calculate_surprise_pct(actual, estimate)
                
                # Check if surprise is significant
                if abs(surprise_pct) >= SURPRISE_THRESHOLD:
                    significant_surprises.append((symbol, latest))
                    print(f"  Significant surprise: {surprise_pct:+.2f}%")
                
                # Store the earnings report
                history[earnings_id] = {
                    'first_seen': datetime.utcnow().isoformat(),
                    'earnings': latest
                }
    
    # Send alerts for significant surprises
    if significant_surprises:
        print(f"\nFound {len(significant_surprises)} significant earnings surprises")
        embeds = [
            format_discord_embed(symbol, earnings)
            for symbol, earnings in significant_surprises
        ]
        send_discord_alert(embeds)
    else:
        print("No significant earnings surprises found")
    
    # Clean up old history (keep last 2 years of data)
    cutoff_date = datetime.utcnow() - timedelta(days=730)
    history = {
        k: v for k, v in history.items()
        if datetime.fromisoformat(v['first_seen']) > cutoff_date
    }
    
    # Save updated history
    save_history(history)
    print(f"History contains {len(history)} earnings reports")


if __name__ == '__main__':
    main()
