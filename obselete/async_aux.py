import asyncio
import threading


def back_loop_body(loop):
    asyncio.set_event_loop(loop)
    loop.run_forever()
    # >>> loop.call_soon_threadsafe(loop.stop)
    # >>> current_thread.join()
    loop.run_until_complete(asyncio.gather(*asyncio.all_tasks(loop)))
    loop.close()


def back_loop_exit(loop, current_thread):
    current_thread.join()
    loop.call_soon_threadsafe(loop.stop)


back_loop = threading.local()


def run_back_coro(coro):
    if not getattr(back_loop, 'loop', None) or back_loop.loop.is_closed():
        back_loop.loop = asyncio.new_event_loop()
        threading.Thread(target=back_loop_body, args=(back_loop.loop, )).start()
        threading.Thread(target=back_loop_exit, args=(back_loop.loop, threading.current_thread())).start()
    return asyncio.run_coroutine_threadsafe(coro, back_loop.loop)


async def set_timeout_body(coro, delay, loop):
    await asyncio.sleep(delay, loop=loop)
    return await coro


def set_timeout(coro, delay, loop=None):
    loop = loop or asyncio.get_event_loop()
    return asyncio.run_coroutine_threadsafe(set_timeout_body(coro, delay, loop), loop=loop)

def run_gracefully(coro):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(coro)
    while len(all_tasks := asyncio.all_tasks(loop)) > 0:
        loop.run_until_complete(asyncio.gather(*all_tasks))
    loop.run_until_complete(loop.shutdown_asyncgens())
    loop.run_until_complete(loop.shutdown_default_executor())
    asyncio.set_event_loop(None)
    loop.close()
