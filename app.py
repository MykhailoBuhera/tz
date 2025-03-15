from aiogram import Bot, Dispatcher, types
from aiogram.types import Message, FSInputFile
from aiogram.filters import Command
from aiohttp import web
import asyncio
import sqlite3
import requests
import hashlib
import base64
import json
from datetime import datetime
import logging

TOKEN = '7525781184:AAFlX9nYaBEGV99Qgl_4EK8D9rSnQNM-_iE'
PUBLIC_KEY = 'sandbox_i83440521978'
PRIVATE_KEY = 'sandbox_49HITjjAU12BMtzM7J10szX72313T2WBo9FGNRwD'

bot = Bot(token=TOKEN)
dp = Dispatcher()

# Products list
products = [
    {'name': 'Product 1', 'description': 'Short description 1', 'price': 10.0, 'photo': 'images/product1.jpg'},
    {'name': 'Product 2', 'description': 'Short description 2', 'price': 20.0, 'photo': 'images/product2.jpg'},
    {'name': 'Product 3', 'description': 'Short description 3', 'price': 30.0, 'photo': 'images/product3.jpg'}
]

# LiqPay payment link generator
def generate_payment_link(amount, description, order_id):
    data = {
        'version': 3,
        'public_key': PUBLIC_KEY,
        'action': 'pay',
        'amount': amount,
        'currency': 'UAH',
        'description': description,
        'order_id': order_id,
        'result_url': 'https://t.me/tzrobota_bot',
        'server_url': 'https://07a5-95-46-140-42.ngrok-free.app/webhook'  # replace with your webhook URL
    }
    data_str = base64.b64encode(json.dumps(data).encode()).decode()
    signature = base64.b64encode(hashlib.sha1((PRIVATE_KEY + data_str + PRIVATE_KEY).encode()).digest()).decode()
    return f'https://www.liqpay.ua/api/3/checkout?data={data_str}&signature={signature}'

# Create a function to manage the user's cart
def get_cart(user_id):
    with sqlite3.connect('shop.db') as conn:
        c = conn.cursor()
        c.execute('SELECT product, quantity FROM cart WHERE user_id = ?', (user_id,))
        return c.fetchall()

def add_to_cart(user_id, product_name):
    with sqlite3.connect('shop.db') as conn:
        c = conn.cursor()
        # Перевіряємо, чи є товар у кошику
        c.execute('SELECT quantity FROM cart WHERE user_id = ? AND product = ?', (user_id, product_name))
        row = c.fetchone()
        
        if row:
            # Якщо товар вже є, збільшуємо кількість
            new_quantity = row[0] + 1
            c.execute('UPDATE cart SET quantity = ? WHERE user_id = ? AND product = ?', (new_quantity, user_id, product_name))
        else:
            # Якщо товару немає, додаємо новий запис
            c.execute('INSERT INTO cart (user_id, product, quantity) VALUES (?, ?, ?)', (user_id, product_name, 1))
        
        conn.commit()


def clear_cart(user_id):
    with sqlite3.connect('shop.db') as conn:
        c = conn.cursor()
        c.execute('DELETE FROM cart WHERE user_id = ?', (user_id,))
        conn.commit()

# Start command
@dp.message(Command('start'))
async def start(message: Message):
    args = message.text.split()
    if len(args) > 1 and args[1] == "success":
        await message.reply("✅ Ваш платіж підтверджено! Дякуємо за покупку.")
    else:
        await message.reply("Вітаю! Ось список доступних команд:\n/products — переглянути товари")

# Products command
@dp.message(Command('products'))
async def show_products(message: Message):
    for product in products:
        photo = FSInputFile(product['photo'])
        text = (f"{product['name']}: {product['description']} — {product['price']} грн\n"
                f"/add_to_cart_{product['name'].replace(' ', '_')}")
        await message.answer_photo(photo=photo, caption=text)

# Add to cart command
for product in products:
    async def add_to_cart_command(message: Message, product_name=product["name"]):
        await asyncio.sleep(0)  # Гарантує правильне виконання асинхронних викликів
        add_to_cart(message.from_user.id, product_name)  # Виклик функції роботи з БД
        await message.reply(f"✅ {product_name} додано до кошика!")

    dp.message.register(add_to_cart_command, Command(f'add_to_cart_{product["name"].replace(" ", "_")}'))


# View cart command
@dp.message(Command('view_cart'))
async def view_cart(message: Message):
    cart = get_cart(message.from_user.id)
    if cart:
        cart_items = "\n".join([f"{item[0]} x{item[1]}" for item in cart])
        await message.reply(f"🛒 Ваш кошик:\n{cart_items}")
    else:
        await message.reply("Ваш кошик порожній.")

# Clear cart command
@dp.message(Command('clear_cart'))
async def clear_cart_command(message: Message):
    clear_cart(message.from_user.id)
    await message.reply("🗑️ Ваш кошик очищено.")

# LiqPay payment link generation for the cart
@dp.message(Command('checkout'))
async def checkout(message: Message):
    cart = get_cart(message.from_user.id)
    if not cart:
        await message.reply("Ваш кошик порожній!")
        return
    
    total_amount = sum(
    p['price'] * item[1]  # Ціна товару * його кількість у кошику
    for item in cart
    for p in products
    if p['name'] == item[0]
    )
    order_id = f"order_{message.from_user.id}_{datetime.now().strftime('%Y%m%d%H%M%S')}"
    payment_link = generate_payment_link(total_amount, "Ваше замовлення", order_id)

    await message.reply(f"Сума до оплати: {total_amount} грн. Оплатіть за посиланням: {payment_link}")

    with sqlite3.connect('shop.db') as conn:
        c = conn.cursor()
        c.execute('INSERT INTO purchases (user_id, product, price, date, status, order_id) VALUES (?, ?, ?, datetime("now"), ?, ?)', 
                  (message.from_user.id, ', '.join(cart), total_amount, 'pending', order_id))
        conn.commit()

# LiqPay webhook handler
logging.basicConfig(level=logging.INFO)

async def handle_webhook(request):
    data = await request.post()
    logging.info(f"Received webhook data: {data}")

    liqpay_data = data.get('data')
    liqpay_signature = data.get('signature')

    if not liqpay_data or not liqpay_signature:
        logging.error("Invalid data received")
        return web.Response(text='Invalid data', status=400)

    calculated_signature = base64.b64encode(hashlib.sha1((PRIVATE_KEY + liqpay_data + PRIVATE_KEY).encode()).digest()).decode()
    if liqpay_signature != calculated_signature:
        logging.error("Invalid signature")
        return web.Response(text='Invalid signature', status=400)

    try:
        payment_info = json.loads(base64.b64decode(liqpay_data).decode('utf-8'))
        logging.info(f"Parsed payment info: {payment_info}")
    except json.JSONDecodeError:
        logging.error("Invalid JSON")
        return web.Response(text='Invalid JSON', status=400)

    order_id = payment_info.get('order_id')
    status = payment_info.get('status')
    
    if not order_id:
        logging.error("Missing order_id")
        return web.Response(text='Missing order_id', status=400)

    user_id = order_id.split("_")[1]  # Отримуємо user_id з order_id
    logging.info(f"Order ID: {order_id}, Status: {status}")

    if status == 'success':
        with sqlite3.connect('shop.db') as conn:
            c = conn.cursor()
            c.execute('UPDATE purchases SET status = ? WHERE order_id = ?', ('paid', order_id))
            conn.commit()

        # Очищаємо кошик після успішної оплати
        clear_cart(user_id)

        logging.info(f"Order {order_id} marked as paid and cart cleared for user {user_id}")

        async with Bot(token=TOKEN) as bot:
            await bot.send_message(chat_id=user_id, text="✅ Дякуємо за покупку! Ваш платіж успішно отримано. Кошик очищено.")

    return web.Response(text='OK')


# Check payment command
@dp.message(Command('check_payment'))
async def check_payment(message: Message):
    with sqlite3.connect('shop.db') as conn:
        c = conn.cursor()
        c.execute('SELECT status FROM purchases WHERE user_id = ? ORDER BY date DESC LIMIT 1', (message.from_user.id,))
        row = c.fetchone()

        if row and row[0] == 'paid':
            await message.reply("✅ Ваш платіж успішно отримано!")
        else:
            await message.reply("❌ Оплата ще не підтверджена.")

# Run bot and webhook server
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
