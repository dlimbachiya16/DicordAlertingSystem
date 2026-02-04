#!/usr/bin/env python3
"""
Insider Sentiment Alert Script
Monitors insider sentiment and sends alerts to Discord
"""

import os
import json
import requests
import time
from datetime import datetime, timedelta

# Configuration
FINNHUB_API_KEY = os.getenv('FINNHUB_API_KEY')
FINNHUB_API_KEY_2 = os.getenv('FINNHUB_API_KEY_2')
FINNHUB_API_KEY_3 = os.getenv('FINNHUB_API_KEY_3')
DISCORD_WEBHOOK = os.getenv('DISCORD_WEBHOOK_INSIDER_SENTIMENT')
HISTORY_FILE = 'data/insider_sentiment_history.json'

# Create list of API keys (filter out None values)
API_KEYS = [key for key in [FINNHUB_API_KEY, FINNHUB_API_KEY_2, FINNHUB_API_KEY_3] if key]
api_key_index = 0

def get_next_api_key():
    """Round-robin through available API keys"""
    global api_key_index
    key = API_KEYS[api_key_index % len(API_KEYS)]
    api_key_index += 1
    return key

# Symbols to monitor
SYMBOLS_TO_MONITOR = [
    'ABBV', 'ABT', 'ADBE', 'AEO', 'ALAB', 'ALGN', 'ALGT', 'AMD',
    'AMZN', 'APP', 'ASTS', 'BA', 'BABA', 'BE', 'BULL',
    'CDNS', 'CFLT', 'CMCL', 'CNC', 'COIN', 'COP', 'CPNG',
    'CRWV', 'CSCO', 'CVNA', 'CVS', 'CVX', 'DUOL',
    'ENPH', 'FIG', 'FLR', 'GE', 'GME', 'GOOGL',
    'HIMS', 'HOOD', 'IBM', 'IBRX', 'INTC', 'IONQ',
    'IREN', 'JNJ', 'JOBY', 'KO', 'LCID',
    'LLY', 'LMND', 'LNTH', 'LYFT', 'MARA',
    'META', 'MRVL', 'MSFT', 'MU', 'NEE',
    'NFLX', 'NKE', 'NRG', 'NVAX', 'NVDA',
    'OKLO', 'ONC', 'OPEN', 'ORCL', 'PANW',
    'PATH', 'PEP', 'PDD', 'PFE', 'PLTR',
    'PYPL', 'QBTS', 'QCOM', 'RGTI', 'RKLB',
    'RR', 'SHOP', 'SMCI', 'SMR', 'SNOW',
    'SOFI', 'SOUN', 'SPOT', 'SYNA', 'TEM',
    'TMC', 'TSLA', 'TSM', 'TTD', 'UBER',
    'UAMY', 'UNH', 'USAR', 'UUUU', 'XOM',
    'XPEV', 'Z', 'ZBRA'
]

# Thresholds for significant sentiment changes
MSPR_THRESHOLD = 5  # Alert if MSPR (monthly share purchase ratio) is >= 5
CHANGE_THRESHOLD = 2  # Alert if change is >= 2


def load_history():
    """Load sentiment history"""
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, 'r') as f:
                content = f.read().strip()
                if content:
                    return json.loads(content)
                else:
                    return {}
        except (json.JSONDecodeError, ValueError) as e:
            print(f"Warning: Could not parse history file, starting fresh: {e}")
            return {}
    return {}


def save_history(history):
    """Save sentiment history"""
    os.makedirs(os.path.dirname(HISTORY_FILE), exist_ok=True)
    with open(HISTORY_FILE, 'w') as f:
        json.dump(history, f, indent=2)


def get_insider_sentiment(symbol, from_date, to_date, max_retries=3):
    """Fetch insider sentiment from Finnhub with retry logic"""
    url = 'https://finnhub.io/api/v1/stock/insider-sentiment'
    
    for attempt in range(max_retries):
        params = {
            'symbol': symbol,
            'from': from_date,
            'to': to_date,
            'token': get_next_api_key()  # Use round-robin API key
        }
        
        try:
            response = requests.get(url, params=params, timeout=10)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 429:  # Rate limit hit
                wait_time = (attempt + 1) * 5  # 5, 10, 15 seconds
                print(f"  Rate limit hit, waiting {wait_time}s...")
                time.sleep(wait_time)
                continue
            else:
                print(f"Error fetching sentiment for {symbol}: {e}")
                return None
        except Exception as e:
            print(f"Error fetching sentiment for {symbol}: {e}")
            return None
    
    print(f"  Failed after {max_retries} retries")
    return None


def create_sentiment_id(symbol, sentiment):
    """Create unique ID for sentiment data"""
    return f"{symbol}_{sentiment.get('year')}_{sentiment.get('month')}"


def format_discord_embed(symbol, sentiment):
    """Format sentiment data as Discord embed"""
    year = sentiment.get('year', 'N/A')
    month = sentiment.get('month', 'N/A')
    mspr = sentiment.get('mspr', 0)
    change = sentiment.get('change', 0)
    
    # Determine sentiment and color
    if mspr > 0 and change > 0:
        sentiment_type = "🟢 BULLISH"
        color = 3066993  # Green
        emoji = "📈"
    elif mspr < 0 and change < 0:
        sentiment_type = "🔴 BEARISH"
        color = 15158332  # Red
        emoji = "📉"
    else:
        sentiment_type = "🟡 NEUTRAL"
        color = 16776960  # Yellow
        emoji = "➡️"
    
    # Format month name
    try:
        month_name = datetime(year, month, 1).strftime('%B')
    except:
        month_name = str(month)
    
    embed = {
        "title": f"{emoji} Insider Sentiment {sentiment_type}: {symbol}",
        "description": f"**{month_name} {year}**",
        "color": color,
        "fields": [
            {
                "name": "MSPR (Monthly Share Purchase Ratio)",
                "value": f"{mspr:.2f}",
                "inline": True
            },
            {
                "name": "Change",
                "value": f"{change:+.2f}",
                "inline": True
            },
            {
                "name": "Period",
                "value": f"{month_name} {year}",
                "inline": True
            }
        ],
        "footer": {
            "text": "Finnhub Insider Sentiment"
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
            time.sleep(0.5)  # Small delay between batches
        except Exception as e:
            print(f"Error sending Discord alert: {e}")
            return False
    
    return True


def main():
    """Main execution function"""
    if not API_KEYS:
        print("Error: No FINNHUB_API_KEY configured")
        return
    
    print(f"Using {len(API_KEYS)} API key(s)")
    
    # Load history
    history = load_history()
    
    # Calculate date range (last 3 months)
    to_date = datetime.now().strftime('%Y-%m-%d')
    from_date = (datetime.now() - timedelta(days=90)).strftime('%Y-%m-%d')
    
    print(f"Checking insider sentiment from {from_date} to {to_date}")
    
    significant_sentiments = []
    
    # Check each symbol
    for symbol in SYMBOLS_TO_MONITOR:
        print(f"Checking {symbol}...")
        data = get_insider_sentiment(symbol, from_date, to_date)
        
        # Rate limit with 3 API keys: 180 API calls per minute = 0.33s per call
        # Using 0.4s for safety buffer
        time.sleep(0.4)
        
        if data and 'data' in data:
            for sentiment in data['data']:
                sentiment_id = create_sentiment_id(symbol, sentiment)
                
                # Check if we've seen this sentiment data before
                if sentiment_id not in history:
                    mspr = sentiment.get('mspr', 0)
                    change = sentiment.get('change', 0)
                    
                    # Check if sentiment is significant
                    if abs(mspr) >= MSPR_THRESHOLD or abs(change) >= CHANGE_THRESHOLD:
                        significant_sentiments.append((symbol, sentiment))
                        print(f"  Significant sentiment: MSPR={mspr:.2f}, Change={change:+.2f}")
                    
                    # Store the sentiment data
                    history[sentiment_id] = {
                        'first_seen': datetime.utcnow().isoformat(),
                        'sentiment': sentiment
                    }
    
    # Send alerts for significant sentiments
    if significant_sentiments:
        print(f"\nFound {len(significant_sentiments)} significant insider sentiments")
        embeds = [
            format_discord_embed(symbol, sentiment)
            for symbol, sentiment in significant_sentiments
        ]
        send_discord_alert(embeds)
    else:
        print("No significant insider sentiments found")
    
    # Clean up old history (keep last 1 year of data)
    cutoff_date = datetime.utcnow() - timedelta(days=365)
    history = {
        k: v for k, v in history.items()
        if datetime.fromisoformat(v['first_seen']) > cutoff_date
    }
    
    # Save updated history
    save_history(history)
    print(f"History contains {len(history)} sentiment records")


if __name__ == '__main__':
    main()
