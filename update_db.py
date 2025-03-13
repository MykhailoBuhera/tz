import sqlite3

# Підключення до бази даних
conn = sqlite3.connect('shop.db')
c = conn.cursor()

# Отримуємо список колонок у таблиці purchases
c.execute("PRAGMA table_info(purchases)")
columns = [col[1] for col in c.fetchall()]

# Додаємо колонку status, якщо її немає
if "status" not in columns:
    c.execute("ALTER TABLE purchases ADD COLUMN status TEXT DEFAULT 'pending'")
    print("✅ Колонка 'status' успішно додана!")

# Додаємо колонку order_id, якщо її немає
if "order_id" not in columns:
    c.execute("ALTER TABLE purchases ADD COLUMN order_id TEXT")
    print("✅ Колонка 'order_id' успішно додана!")

# Зберігаємо зміни
conn.commit()
conn.close()
