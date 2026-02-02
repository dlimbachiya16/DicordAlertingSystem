#!/usr/bin/env python3
"""
Insider Sentiment Alert Script
Monitors insider sentiment changes and sends alerts to Discord
"""

import os
import json
import requests
from datetime import datetime, timedelta

# Configuration
FINNHUB_API_KEY = os.getenv('FINNHUB_API_KEY')
DISCORD_WEBHOOK = os.getenv('DISCORD_WEBHOOK_INSIDER_SENTIMENT')
HISTORY_FILE = 'data/insider_sentiment_history.json'

# Symbols to monitor (customize this list)
SYMBOLS_TO_MONITOR = [
    'AAPL', 'MSFT', 'GOOGL', 'AMZN', 'NVDA', 'META', 'TSLA', 'BRK.B',
    'JPM', 'V', 'JNJ', 'WMT', 'PG', 'MA', 'XOM', 'HD', 'CVX', 'MRK',
    'KO', 'ABBV', 'PEP', 'COST', 'AVGO', 'TMO', 'LLY', 'MCD', 'CSCO',
    'ACN', 'DHR', 'NKE', 'VZ', 'ADBE', 'TXN', 'NEE', 'CRM', 'ABT'
]

# Threshold for significant MSPR changes
MSPR_THRESHOLD = 20  # Alert if MSPR moves significantly


def load_history():
    """Load sentiment history"""
    if os.path.exists(HISTORY_FILE):
        with open(HISTORY_FILE, 'r') as f:
            return json.load(f)
    return {}


def save_history(history):
    """Save sentiment history"""
    os.makedirs(os.path.dirname(HISTORY_FILE), exist_ok=True)
    with open(HISTORY_FILE, 'w') as f:
        json.dump(history, f, indent=2)


def get_insider_sentiment(symbol, from_date, to_date):
    """Fetch insider sentiment from Finnhub"""
    url = 'https://finnhub.io/api/v1/stock/insider-sentiment'
    params = {
        'symbol': symbol,
        'from': from_date,
        'to': to_date,
        'token': FINNHUB_API_KEY
    }
    
    try:
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        print(f"Error fetching sentiment for {symbol}: {e}")
        return None


def interpret_mspr(mspr):
    """Interpret MSPR value"""
    if mspr >= 50:
        return "🟢 Very Bullish", 3066993  # Green
    elif mspr >= 20:
        return "🟢 Bullish", 5763719  # Light green
    elif mspr >= -20:
        return "🟡 Neutral", 16776960  # Yellow
    elif mspr >= -50:
        return "🔴 Bearish", 15105570  # Light red
    else:
        return "🔴 Very Bearish", 15158332  # Red


def format_discord_embed(symbol, sentiment_data, previous_mspr=None):
    """Format sentiment data as Discord embed"""
    mspr = sentiment_data.get('mspr', 0)
    change = sentiment_data.get('change', 0)
    year = sentiment_data.get('year', 'N/A')
    month = sentiment_data.get('month', 'N/A')
    
    sentiment_label, color = interpret_mspr(mspr)
    
    # Calculate change from previous
    change_text = ""
    if previous_mspr is not None:
        mspr_change = mspr - previous_mspr
        if mspr_change > 0:
            change_text = f"\n📈 +{mspr_change:.1f} from previous"
        elif mspr_change < 0:
            change_text = f"\n📉 {mspr_change:.1f} from previous"
    
    embed = {
        "title": f"Insider Sentiment: {symbol}",
        "description": f"**{sentiment_label}**{change_text}",
        "color": color,
        "fields": [
            {
                "name": "MSPR Score",
                "value": f"{mspr:.2f}",
                "inline": True
            },
            {
                "name": "Net Change",
                "value": f"{change:,}",
                "inline": True
            },
            {
                "name": "Period",
                "value": f"{year}-{month:02d}" if month != 'N/A' else year,
                "inline": True
            }
        ],
        "footer": {
            "text": "MSPR: -100 (Very Bearish) to +100 (Very Bullish)"
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
    
    # Calculate date range (last 3 months)
    to_date = datetime.now().strftime('%Y-%m-%d')
    from_date = (datetime.now() - timedelta(days=90)).strftime('%Y-%m-%d')
    
    print(f"Checking insider sentiment from {from_date} to {to_date}")
    
    significant_changes = []
    
    # Check each symbol
    for symbol in SYMBOLS_TO_MONITOR:
        print(f"Checking {symbol}...")
        data = get_insider_sentiment(symbol, from_date, to_date)
        
        if data and 'data' in data and len(data['data']) > 0:
            # Get most recent sentiment
            latest = data['data'][0]
            mspr = latest.get('mspr', 0)
            period_key = f"{latest.get('year')}-{latest.get('month'):02d}"
            
            # Check if this is a new period or significant change
            previous_data = history.get(symbol)
            
            should_alert = False
            previous_mspr = None
            
            if previous_data is None:
                # First time seeing this symbol
                should_alert = True
            elif previous_data.get('period') != period_key:
                # New period
                previous_mspr = previous_data.get('mspr')
                mspr_change = abs(mspr - previous_mspr)
                
                # Alert if significant change or extreme values
                if mspr_change >= MSPR_THRESHOLD or abs(mspr) >= 50:
                    should_alert = True
            
            if should_alert:
                significant_changes.append((symbol, latest, previous_mspr))
                print(f"  Significant change: MSPR = {mspr:.2f}")
            
            # Update history
            history[symbol] = {
                'period': period_key,
                'mspr': mspr,
                'last_updated': datetime.utcnow().isoformat()
            }
    
    # Send alerts for significant changes
    if significant_changes:
        print(f"\nFound {len(significant_changes)} significant sentiment changes")
        embeds = [
            format_discord_embed(symbol, sentiment, prev_mspr)
            for symbol, sentiment, prev_mspr in significant_changes
        ]
        send_discord_alert(embeds)
    else:
        print("No significant sentiment changes found")
    
    # Save updated history
    save_history(history)
    print(f"History contains {len(history)} symbols")


if __name__ == '__main__':
    main()
