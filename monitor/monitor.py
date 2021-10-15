import sys
import json
import asyncio
import signal
import concurrent.futures
from datetime import datetime

from aiogram import Bot, Dispatcher, executor, types


config = {
    'bot_token': '',
    'tg_group_id': '',
    'interval': 30,
    'manage_bp': {
        'account': '',
        'failover': {
            'enable': False,
            'producer_key': '',
            'url': '',
            'location': 0,
            'permission': '',
            'count': 240,
        },
        'unregproducer': {
            'enable': False,
            'permission': '',
            'count': 240,
        }
     },
    'api': 'http://127.0.0.1:8888',
    'check_list': []  # No entity means to check all.
}

is_state_failover = False
is_state_unregproducer = False

LIMIT_RECURSIVE = 10


class CleosError(Exception):
    pass


def set_config(new_config):
    for k, v in new_config.items():
        if config.get(k) is None:
            continue
        config[k] = v


async def run(cmd):
    proc = await asyncio.create_subprocess_shell(
        cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE)
    stdout, stderr = await proc.communicate()
    if stderr:
        print(stderr)
        raise CleosError(stderr)
    
    return json.loads(stdout)


async def get_schedule():
    cmd = f'cleos -u {config["api"]} get schedule -j'
    data = await run(cmd)
    producers = data['active']['producers']
    return producers


async def is_in_schedule(bp):
    producers = await get_schedule()
    return any(bp == x['producer_name'] for x in producers)


async def get_producer(bp):
    cmd = f'cleos -u {config["api"]} get table eosio eosio producers --lower {bp} --limit 1'
    data = await run(cmd)
    try:
        producer = data['rows'][0]
    except IndexError:
        producer = None

    return producer


async def get_all_producer(rows=[], lower='', limit=1000, recursive=0):
    if lower:
        cmd = f'cleos -u {config["api"]} get table eosio eosio producers --lower {lower} --limit {limit}'
    else:
        cmd = f'cleos -u {config["api"]} get table eosio eosio producers --limit {limit}'
    data = await run(cmd)
    rows.extend(x for x in data['rows'] if x['is_active'])
    if data['more']:
        if recursive < LIMIT_RECURSIVE:
            recursive += 1
            return await get_all_producer(rows=rows, lower=data['next_key'], limit=limit, recursive=recursive)
        else:
            print('more than LIMIT_RECURSIVE')
            return rows
    else:
        return rows


async def do_failover():
    print('do_failover')
    account = config['manage_bp']['account']
    producer_key = config['manage_bp']['failover']['producer_key']
    url = config['manage_bp']['failover']['url']
    location = config['manage_bp']['failover']['location']
    permission = config['manage_bp']['failover']['permission']
    cmd = f'cleos -u {config["api"]} system regproducer {account} {producer_key} {url} {location} -j -p {permission}'
    data = await run(cmd)


async def do_unregproducer():
    print('do_unregproducer')
    account = config['manage_bp']['account']    
    permission = config['manage_bp']['unregproducer']['permission']
    cmd = f'cleos -u {config["api"]} system unregprod {account} -j -p {permission}'
    data = await run(cmd)


async def manage_bp(bp_name, missed_count):
    global is_state_failover, is_state_unregproducer
    manager = config['manage_bp']
    if bp_name != manager['account']:
        return

    failover = manager['failover']
    if missed_count > failover['count']:
        if failover['enable'] and not is_state_failover:
            is_state_failover = True
            await do_failover()

    unreg = manager['unregproducer']
    if missed_count > unreg['count']:
        if unreg['enable'] and not is_state_unregproducer:
            is_state_unregproducer = True
            await do_unregproducer()


async def check_all_missing_block(data_queue, check_list=[]):
    global is_state_failover, is_state_unregproducer
    loop_count = 0
    prev = {}
    
    while True:
        try:
            current = await get_all_producer()
            current = dict((x['owner'], x) for x in current)

            for bp_name, bp_info in current.items():
                if check_list and bp_name not in check_list:
                    continue

                if prev.get(bp_name) is None:
                    #print(f'Not found {bp_name} in prev producer list')
                    continue

                cur_missed_count = bp_info['missed_blocks_per_rotation']
                prev_missed_count = prev[bp_name]['missed_blocks_per_rotation']
                missed_count = cur_missed_count - prev_missed_count
                checked_time = datetime.utcnow()
                if missed_count > 0:
                    data = {
                        'bp_name': bp_name,
                        'missed_blocks_per_rotation': cur_missed_count,
                        'missed_count': missed_count,
                        'checked_time': checked_time.isoformat()
                    }
                    await data_queue.put(data)
                
                await manage_bp(bp_name, cur_missed_count)

            prev = current                
        except CleosError:
            print('cleos error', datetime.utcnow())            
        except Exception as exc:
            print(exc)
        finally:
            if is_state_unregproducer:
                break

            loop_count += 1
            await asyncio.sleep(config['interval'])


async def notify(data_queue, bot):
    while True:
        data = await data_queue.get()
        await bot.send_message(config['tg_group_id'], repr(data))
        data_queue.task_done()


async def main(loop):
    bot = Bot(token=config['bot_token'])
    dp = Dispatcher(bot)

    task_bot = asyncio.create_task(dp.start_polling())
    data_queue = asyncio.Queue()
    task_check = asyncio.create_task(check_all_missing_block(data_queue, config['check_list']))
    task_notify = asyncio.create_task(notify(data_queue, bot))        

    def shutdown(task=None):
        print(f'task={task}\nTry to shutdown.')
        for i, x in enumerate(asyncio.all_tasks()):
            result = x.cancel()
            print(f'Cancel task {i} {result}')

    loop.add_signal_handler(signal.SIGINT, shutdown)
    loop.add_signal_handler(signal.SIGTERM, shutdown)
    task_check.add_done_callback(shutdown)
    gather = asyncio.gather(
        task_bot,
        task_check,
        task_notify)
    await gather


if __name__ == '__main__':
    try:
        with open(sys.argv[1]) as f:
            cfg = json.load(f)
            set_config(cfg)
    except IndexError:
        print('Specify config file name.')
        sys.exit(1)
    except Exception as exc:
        print(exc)
        sys.exit(1)

    loop = asyncio.get_event_loop()
    try:
        loop.run_until_complete(main(loop))
    except concurrent.futures.CancelledError:
        pass

    loop.close()
