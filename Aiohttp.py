import time
from aiohttp import web

# Хранилище
AD_STORAGE = {}


async def add_new_ad(request):
    try:
        body = await request.json()
    except:
        return web.json_response({'msg': 'bad json'}, status=400)

    if not body.get('title') or not body.get('owner'):
        return web.json_response({'error': 'no title or owner'}, status=400)

    # Генерим id на основе времени, чтобы не юзать глобальный счетчик
    new_id = int(time.time() * 1000)

    AD_STORAGE[new_id] = {
        'id': new_id,
        'title': body['title'],
        'description': body.get('description', ''),
        'created_at': time.strftime('%Y-%m-%d %H:%M:%S'),  # другой формат даты
        'owner': body['owner']
    }
    return web.json_response(AD_STORAGE[new_id], status=201)


async def get_ad_by_id(request):
    uid = int(request.match_info['uid'])
    item = AD_STORAGE.get(uid)
    if not item:
        return web.json_response({'err': 'not found'}, status=404)
    return web.json_response(item)


async def remove_ad(request):
    uid = int(request.match_info['uid'])
    if uid not in AD_STORAGE:
        return web.json_response({'err': 'not found'}, status=404)
    del AD_STORAGE[uid]
    return web.json_response({'result': 'ok'})


app = web.Application()
app.add_routes([
    web.post('/advertisements', add_new_ad),
    web.get('/advertisements/{uid:\d+}', get_ad_by_id),
    web.delete('/advertisements/{uid:\d+}', remove_ad)
])

if __name__ == '__main__':
    web.run_app(app, host='0.0.0.0', port=5000)