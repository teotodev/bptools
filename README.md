# bptools
## missing_block_checker
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
python missing_block_checker.py YOUR_CONFIG.json
```
### example-config.json
```
{
    "api_url": "https://testnet.telos.net",
    "scheduler_interval": 126,    
    "tg_bot_token": "YOUR_TELEGRAM_BOT_TOKEN",
    "tg_channel_id": "YOUR_TELEGRAM_CHANNEL_ID"
}
```
