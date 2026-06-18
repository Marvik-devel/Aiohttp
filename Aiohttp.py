import jwt
import bcrypt
import aiosqlite
from datetime import datetime, timedelta
from aiohttp import web

JWT_SECRET = "super-secret-key-123"  # В реале берут из env
JWT_ALGORITHM = "HS256"
DB_NAME = "db.sqlite"


# ПРОВЕРКИ JWT
@web.middleware
async def auth_middleware(request, handler):
    # По умолчанию юзер не залогинен
    request['user'] = None

    auth_header = request.headers.get('Authorization')
    if auth_header and auth_header.startswith('Bearer '):
        token = auth_header.split(' ')[1]
        try:
            payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
            request['user'] = payload  # кладем инфу о юзере прямо в запрос
        except (jwt.ExpiredSignatureError, jwt.InvalidTokenError):
            pass  # Токен битый или просрочен, оставляем user = None

    return await handler(request)


# хендлеры авторизации

async def register_user(request):
    try:
        data = await request.json()
    except:
        return web.json_response({'error': 'invalid json'}, status=400)

    email = data.get('email')
    password = data.get('password')

    if not email or not password:
        return web.json_response({'error': 'email and password required'}, status=400)

    # Хэшируем пароль через bcrypt
    salt = bcrypt.gensalt()
    pwd_hash = bcrypt.hashpw(password.encode('utf-8'), salt).decode('utf-8')

    async with aiosqlite.connect(DB_NAME) as db:
        try:
            await db.execute(
                "INSERT INTO users (email, password_hash) VALUES (?, ?)",
                (email, pwd_hash)
            )
            await db.commit()
        except aiosqlite.IntegrityError:
            return web.json_response({'error': 'email already registered'}, status=400)

    return web.json_response({'status': 'registered'}, status=201)


async def login_user(request):
    try:
        data = await request.json()
    except:
        return web.json_response({'error': 'invalid json'}, status=400)

    email = data.get('email')
    password = data.get('password')

    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM users WHERE email = ?", (email,)) as cursor:
            user = await cursor.fetchone()

    if not user or not bcrypt.checkpw(password.encode('utf-8'), user['password_hash'].encode('utf-8')):
        return web.json_response({'error': 'bad credentials'}, status=401)

    # Выдаем токен на 1 час
    token = jwt.encode({
        'user_id': user['id'],
        'email': user['email'],
        'exp': datetime.utcnow() + timedelta(hours=1)
    }, JWT_SECRET, algorithm=JWT_ALGORITHM)

    return web.json_response({'token': token})


# хендлеры объявлений

async def create_ad(request):
    if not request['user']:
        return web.json_response({'error': 'unauthorized'}, status=401)

    try:
        data = await request.json()
    except:
        return web.json_response({'error': 'invalid json'}, status=400)

    title = data.get('title')
    description = data.get('description')

    if not title or not description:
        return web.json_response({'error': 'missing title or description'}, status=400)

    owner_id = request['user']['user_id']
    created_at = datetime.utcnow().isoformat()

    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute(
            "INSERT INTO ads (title, description, created_at, owner_id) VALUES (?, ?, ?, ?)",
            (title, description, created_at, owner_id)
        )
        await db.commit()
        ad_id = cursor.lastrowid

    return web.json_response({'id': ad_id, 'title': title, 'owner_id': owner_id}, status=201)


async def get_ad(request):
    ad_id = int(request.match_info['ad_id'])

    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM ads WHERE id = ?", (ad_id,)) as cursor:
            ad = await cursor.fetchone()

    if not ad:
        return web.json_response({'error': 'not found'}, status=404)

    return web.json_response(dict(ad))


async def update_ad(request):
    if not request['user']:
        return web.json_response({'error': 'unauthorized'}, status=401)

    ad_id = int(request.match_info['ad_id'])
    try:
        data = await request.json()
    except:
        return web.json_response({'error': 'invalid json'}, status=400)

    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM ads WHERE id = ?", (ad_id,)) as cursor:
            ad = await cursor.fetchone()

        if not ad:
            return web.json_response({'error': 'not found'}, status=404)

        # Проверка прав
        if ad['owner_id'] != request['user']['user_id']:
            return web.json_response({'error': 'forbidden, not your ad'}, status=403)

        # Обновляем поля динамически
        title = data.get('title', ad['title'])
        description = data.get('description', ad['description'])

        await db.execute(
            "UPDATE ads SET title = ?, description = ? WHERE id = ?",
            (title, description, ad_id)
        )
        await db.commit()

    return web.json_response({'id': ad_id, 'title': title, 'description': description})


async def delete_ad(request):
    if not request['user']:
        return web.json_response({'error': 'unauthorized'}, status=401)

    ad_id = int(request.match_info['ad_id'])

    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM ads WHERE id = ?", (ad_id,)) as cursor:
            ad = await cursor.fetchone()

        if not ad:
            return web.json_response({'error': 'not found'}, status=404)

        # Проверка прав на удаление
        if ad['owner_id'] != request['user']['user_id']:
            return web.json_response({'error': 'forbidden'}, status=403)

        await db.execute("DELETE FROM ads WHERE id = ?", (ad_id,))
        await db.commit()

    return web.json_response({'status': 'deleted'})


# приложения и таблицы

async def init_db(app):
    # Создаем таблицы асинхронно при запуске
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT UNIQUE,
                password_hash TEXT
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS ads (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT,
                description TEXT,
                created_at TEXT,
                owner_id INTEGER,
                FOREIGN KEY(owner_id) REFERENCES users(id)
            )
        """)
        await db.commit()


app = web.Application(middlewares=[auth_middleware])
app.on_startup.append(init_db)

app.add_routes([
    web.post('/register', register_user),
    web.post('/login', login_user),
    web.post('/advertisements', create_ad),
    web.get('/advertisements/{ad_id:\d+}', get_ad),
    web.patch('/advertisements/{ad_id:\d+}', update_ad),
    web.delete('/advertisements/{ad_id:\d+}', delete_ad)
])

if __name__ == '__main__':
    web.run_app(app, host='0.0.0.0', port=5000)