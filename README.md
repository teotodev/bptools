# bptools
## monitor
### requirements
```
pip install aiogram
```
  * DO NOT use active permission. Add a permission for eosio::regproducer and eosio::unregprod.
  * Adjust unlock-timeout of keosd config.
  * Unlock cleos wallet.  
### run
```
python3 monitor.py YOUR_CONFIG.json
```
### example-config.json
```
{
    "bot_token": "YOUR_TELEGRAM_BOT_TOKEN",
    "tg_group_id": "YOUR_TELEGRAM_GROUP_ID",
    "interval": 126,
    "manage_bp": {
        "account": "YOUR_ACCOUNT",
        "failover": {
            "enable": true,
            "producer_key": "YOUR_SIGNING_PUBLIC_KEY",
            "url": "YOUR_WEBSITE",
            "location": 0,
            "permission": "YOUR_ACCOUNT@PERMISSION",
                "count": 240
        },
        "unregproducer": {
            "enable": true,
            "permission": "YOUR_ACCOUNT@PERMISSION",
                "count": 360
        }
    },
    "api": "API_NODE_URL",
    "check_list": ["ACCOUNT1", "ACCOUNT2"]
}
```
