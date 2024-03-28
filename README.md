# bptools
## monitor
### requirements  
  * Python 3.7
### virtual environment
```
python3 -m venv .venv
source .venv/bin/activate
```  
### install requirements
```
pip install -r requirements.txt
```  
### run
```
python monitor.py YOUR_CONFIG.json
```
### example-config.json
```
{
    "api_url": "https://testnet.telos.net",
    "tg_bot_token": "YOUR_TELEGRAM_BOT_TOKEN",
    "tg_channel_id": "YOUR_TELEGRAM_CHANNEL_ID"
}
```
