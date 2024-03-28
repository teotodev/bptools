import sys
import json
import logging
from datetime import datetime
from urllib.parse import urljoin
import argparse

import asyncio
import aiohttp
import signal
import concurrent.futures

from aiogram import Bot, Dispatcher, types


async def get_schedule(api_url):
    url = urljoin(api_url, "/v1/chain/get_table_rows")
    headers = {"Content-Type": "application/json"}
    data = {
        "code": "eosio",
        "scope": "eosio",
        "table": "schedulemetr",
        "key_type": "i64",
        "json": True}

    async with aiohttp.ClientSession() as session:
        async with session.post(url=url, data=json.dumps(data), headers=headers) as response:
            result = await response.json()
            return result
    

async def check_missing_block_count(api_url, bp_name, exporter):
    url = urljoin(api_url, "/v1/chain/get_table_rows")    
    headers = {"Content-Type": "application/json"}
    data = {
        "code": "eosio",
        "scope": "eosio",
        "table": "producers",
        "key_type": "i64",
        "lower_bound": bp_name,
        "upper_bound": bp_name,
        "limit": 1,
        "json": True}

    async with aiohttp.ClientSession() as session:
        async with session.post(url=url, data=json.dumps(data), headers=headers) as response:
            result = await response.json()
            if "error" in result:
                logging.error(f"check_missing_block_count> {bp_name} {str(result)}")
                return
            
            bp_data = result["rows"][0]
            missing_count = bp_data["missed_blocks_per_rotation"]            
            logging.debug(f"check_missing_block_count> {bp_name} {missing_count}")
            await exporter(bp_data)


async def scheduler(api_url, exporter, interval=60):
    while True:
        schedule = await get_schedule(api_url)
        if "error" in schedule:
            logging.error(f"scheduler> {str(schedule)}")
            await asyncio.sleep(interval)
            continue
        else:
            schedule = schedule["rows"][0]["producers_metric"]

        bp_tasks = []    
        for bp in schedule:
            task = asyncio.create_task(check_missing_block_count(api_url, bp["bp_name"], exporter), name=bp["bp_name"])
            bp_tasks.append(task)
        gather = asyncio.gather(*bp_tasks)
        await gather
        await asyncio.sleep(interval)


async def http_post(getter, url, headers={"Content-Type": "application/json"}, interval=0.01):
    while True:
        data = await getter()
        async with aiohttp.ClientSession() as session:
            async with session.post(url=url, data=json.dumps(data), headers=headers) as response:
                pass
                #result = await response.json()
                #if "error" in result:
                #    logging.error(f"http_post> {result}")
        await asyncio.sleep(interval)


async def tg_bot_consumer(getter, bot, tg_channel_id, interval=1):
    await bot.send_message(tg_channel_id, "Started.")
    while True:
        datas = []
        for x in range(21):
            try:
                data = getter()  # get_nowait is not coroutine
                datas.append(data)
            except asyncio.QueueEmpty:
                break
            
        if len(datas) == 0:
            await asyncio.sleep(interval)    
            continue

        message = "\n".join([f"{data['owner']} {data['missed_blocks_per_rotation']} +{data['delta']}"
                              for data in datas])
        #message = f"{data['owner']} {data['missed_blocks_per_rotation']}"
        await bot.send_message(tg_channel_id, message)
        #data_queue.task_done()
        await asyncio.sleep(interval)


async def stream_consumer(getter, interval=0.01):
    while True:
        data = await getter()
        #logging.debug(f"stream_consumer> {data['owner']} {data['missed_blocks_per_rotation']}")
        logging.debug(f"stream_consumer> {data['owner']} {data['delta']}")
        await asyncio.sleep(interval)


async def dummy_consumer(getter, interval=0.01):
    while True:
        data = await getter()
        logging.debug(f"dummy_consumer> {data['owner']} {data['missed_blocks_per_rotation']}")
        await asyncio.sleep(interval)    


async def data_handler(getter, receivers, interval=0.01):
    prev_datas = {}
    while True:
        delta = 0
        data = await getter()
        owner = data['owner']
        quantity = data['missed_blocks_per_rotation']
        if quantity == 0:
            if prev_datas.get(owner) is not None:
                del prev_datas[owner]
            await asyncio.sleep(interval)
            continue            
        elif quantity > 0:
            if prev_datas.get(owner) is None:
                prev_datas[owner] = quantity
                delta = quantity
            else:
                prev_datas[owner] = quantity                
                if prev_datas[owner] < quantity:
                    delta = quantity - prev_datas[owner]
                elif prev_datas[owner] == quantity:  # TODO check round.
                    await asyncio.sleep(interval)
                    continue            
                else:
                    delta = quantity
        else:
            logging.error("quantity < 0")
            await asyncio.sleep(interval)
            continue

        data["delta"] = delta

        for r in receivers:
            await r(data)

        await asyncio.sleep(interval)
        

def shutdown(obj=None):
    logging.debug(f"shutdown> {obj} Trying to cancel all tasks.")
    for i, x in enumerate(asyncio.all_tasks()):
        result = x.cancel()
        logging.debug(f"shutdown> Trying to cancel task {x.get_name()} {result}")
    logging.debug(f"shutdown> Completed.")


async def main(api_url, tg_bot_token, tg_channel_id, scheduler_interval=126):
    data_queue = asyncio.Queue()
    scheduler_task = asyncio.create_task(
        scheduler(api_url=api_url, 
                  exporter=data_queue.put, 
                  interval=scheduler_interval), 
        name="scheduler")
    
    # telegram bot
    bot = Bot(token=tg_bot_token)
    dp = Dispatcher()
    """
    @dp.channel_post()
    async def test_channel_post(message: types.Message):
        logging.debug(message)
        await message.answer("channel test.")    

    @dp.message()
    async def test_message(message):
        logging.debug(message.chat_id)
        await message.answer("message test.")
    """
    bot_task = asyncio.create_task(dp.start_polling(bot), name="telegram bot")        
    # bot_task intercepts signal so loop.add_signal_handler not used.
    bot_task.add_done_callback(shutdown)

    consumer_tasks = []
    receivers = []
    consumers = [
        (stream_consumer, "stream_consumer", [], {}),
        #(dummy_consumer, "dummy_consumer", [], {}),
        #(http_post, "http_post", [url], {})
        (tg_bot_consumer, "tg_bot_consumer", [bot, tg_channel_id], {})
    ]
    for coro, name, args, kwargs in consumers:
        queue = asyncio.Queue()
        receivers.append(queue.put)
        if name == "tg_bot_consumer":
            task = asyncio.create_task(coro(queue.get_nowait, *args, **kwargs), name=name)
        else:
            task = asyncio.create_task(coro(queue.get, *args, **kwargs), name=name)
        consumer_tasks.append(task)
    data_handler_task = asyncio.create_task(data_handler(data_queue.get, receivers), name="data_handler")    

    gather = asyncio.gather(bot_task, scheduler_task, data_handler_task, *consumer_tasks)
    await gather    


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument("config", help="Specify config file.")
    args = parser.parse_args()
    with open(args.config, 'r') as f:
        config = json.load(f)

    console = logging.StreamHandler()    
    console.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    logging.getLogger().addHandler(console)
    logging.getLogger().setLevel(logging.DEBUG)

    loop = asyncio.get_event_loop()

    try:
        main_task = asyncio.Task(main(**config), name="main")
        loop.run_until_complete(main_task)
    except concurrent.futures.CancelledError:
        pass
    except asyncio.exceptions.CancelledError:
        pass

    loop.close()
    logging.info("Exited.")