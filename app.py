from aiogram import Bot, Dispatcher, types, Router, F
from aiogram.types import Message, FSInputFile, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram.filters import Command
from aiohttp import web
import asyncio
import aiosqlite
import hashlib
import base64
import json
from datetime import datetime
from aiogram.client.default import DefaultBotProperties
import logging

TOKEN = '7525781184:AAFlX9nYaBEGV99Qgl_4EK8D9rSnQNM-_iE'
PUBLIC_KEY = 'sandbox_i83440521978'
PRIVATE_KEY = 'sandbox_49HITjjAU12BMtzM7J10szX72313T2WBo9FGNRwD'

bot = Bot(token=TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
dp = Dispatcher()
router = Router()
dp.include_router(router)

# Настройка логирования
logging.basicConfig(level=logging.INFO)

# Кнопки меню
main_keyboard = ReplyKeyboardMarkup(resize_keyboard=True, keyboard=[
    [KeyboardButton(text='🛍️ Переглянути товари')],
    [KeyboardButton(text='🛒 Переглянути кошик')],
    [KeyboardButton(text='🗑️ Очистити кошик')],
    [KeyboardButton(text='💳 Оформити замовлення')]
])

# Товары
products = [
    {'name': 'Product 1', 'description': 'Description 1', 'price': 10.0, 'photo': 'images/product1.jpg'},
    {'name': 'Product 2', 'description': 'Description 2', 'price': 20.0, 'photo': 'images/product2.jpg'},
    {'name': 'Product 3', 'description': 'Description 3', 'price': 30.0, 'photo': 'images/product3.jpg'}
]

def generate_payment_link(amount, order_id):
    data = {
        'version': 3,
        'public_key': PUBLIC_KEY,
        'action': 'pay',
        'amount': amount,
        'currency': 'UAH',
        'description': 'Оплата замовлення',
        'order_id': order_id,
        'server_url': 'https://32f2-95-46-140-42.ngrok-free.app/webhook'
    }
    data_str = base64.b64encode(json.dumps(data).encode()).decode()
    signature = base64.b64encode(hashlib.sha1((PRIVATE_KEY + data_str + PRIVATE_KEY).encode()).digest()).decode()
    return f'https://www.liqpay.ua/api/3/checkout?data={data_str}&signature={signature}'

@router.message(Command('start'))
async def start(message: Message):
    await message.answer("Вітаю! Виберіть дію з меню:", reply_markup=main_keyboard)

@router.message(F.text == '🛍️ Переглянути товари')
async def show_products(message: Message):
    for product in products:
        text = f"{product['name']}: {product['description']} — {product['price']} грн"
        button = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🛒 Додати в кошик", callback_data=f"add_{product['name']}")]
        ])
        await message.answer_photo(photo=FSInputFile(product['photo']), caption=text, reply_markup=button)

@router.callback_query(F.data.startswith('add_'))
async def add_to_cart_callback(callback_query: CallbackQuery):
    product_name = callback_query.data[4:]
    await add_to_cart(callback_query.from_user.id, product_name)
    await callback_query.answer(f"✅ {product_name} додано до кошика!")

async def add_to_cart(user_id, product_name):
    async with aiosqlite.connect('shop.db') as conn:
        cursor = await conn.cursor()
        await cursor.execute('INSERT INTO cart (user_id, product_name, quantity) VALUES (?, ?, 1) ON CONFLICT(user_id, product_name) DO UPDATE SET quantity = quantity + 1', (user_id, product_name))
        await conn.commit()

@router.message(F.text == '🛒 Переглянути кошик')
async def view_cart(message: Message):
    async with aiosqlite.connect('shop.db') as conn:
        cursor = await conn.cursor()
        await cursor.execute('SELECT product_name, quantity FROM cart WHERE user_id = ?', (message.from_user.id,))
        cart = await cursor.fetchall()
    if cart:
        items = "\n".join([f"{item[0]} x{item[1]}" for item in cart])
        await message.answer(f"🛒 Ваш кошик:\n{items}")
    else:
        await message.answer("Ваш кошик порожній.")

@router.message(F.text == '💳 Оформити замовлення')
async def checkout(message: Message):
    async with aiosqlite.connect('shop.db') as conn:
        cursor = await conn.cursor()
        await cursor.execute('SELECT product_name, quantity FROM cart WHERE user_id = ?', (message.from_user.id,))
        cart = await cursor.fetchall()
    if not cart:
        await message.answer("Ваш кошик порожній!")
        return
    total_amount = sum(p['price'] * item[1] for p in products for item in cart if p['name'] == item[0])
    order_id = f"order_{message.from_user.id}_{datetime.now().strftime('%Y%m%d%H%M%S')}"
    payment_link = generate_payment_link(total_amount, order_id)
    await message.answer(f"Сума до оплати: {total_amount} грн", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="💳 Оплатити", url=payment_link)]]))

async def handle_webhook(request):
    data = await request.post()
    liqpay_data = data.get('data')
    if not liqpay_data:
        return web.Response(text='Invalid data', status=400)
    payment_info = json.loads(base64.b64decode(liqpay_data).decode('utf-8'))
    order_id = payment_info.get('order_id')
    status = payment_info.get('status')
    if order_id and status == 'success':
        user_id = order_id.split("_")[1]
        async with aiosqlite.connect('shop.db') as conn:
            cursor = await conn.cursor()
            await cursor.execute('UPDATE purchases SET status = ? WHERE order_id = ?', ('paid', order_id))
            await conn.commit()
        await clear_cart(user_id)
        await bot.send_message(chat_id=user_id, text="✅ Ваш платіж успішно отримано!")
    return web.Response(text='OK')

async def clear_cart(user_id):
    async with aiosqlite.connect('shop.db') as conn:
        cursor = await conn.cursor()
        await cursor.execute('DELETE FROM cart WHERE user_id = ?', (user_id,))
        await conn.commit()

async def main():
    app = web.Application()
    app.router.add_post('/webhook', handle_webhook)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, 'localhost', 8080)
    await site.start()
    await dp.start_polling(bot)

if __name__ == '__main__':
    asyncio.run(main())
