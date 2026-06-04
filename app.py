"""
Abid Shoes - Web API - Railway (5 Branch)
"""
from flask import Flask, jsonify, request
from flask_cors import CORS
import sqlite3, os, datetime, json

app = Flask(__name__)
CORS(app)

DB = "abidshoes_web.db"
API_KEY = os.environ.get("API_KEY", "abidshoes2024secret")
SHOP_SOURCE = "railway"

def get_db():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db(); c = conn.cursor()
    c.executescript("""
        CREATE TABLE IF NOT EXISTS products(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            barcode TEXT UNIQUE,
            name TEXT, brand TEXT, category TEXT,
            price REAL, stock INTEGER DEFAULT 0,
            image_url TEXT, sizes TEXT, gender TEXT DEFAULT 'Unisex',
            description TEXT, is_active INTEGER DEFAULT 1,
            updated_at TEXT, shop_source TEXT DEFAULT 'railway'
        );
        CREATE TABLE IF NOT EXISTS orders(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_no TEXT UNIQUE,
            customer_name TEXT, customer_phone TEXT,
            customer_address TEXT, city TEXT,
            items TEXT, subtotal REAL, delivery REAL DEFAULT 200,
            total REAL, payment_method TEXT,
            status TEXT DEFAULT 'Pending',
            notes TEXT, created_at TEXT,
            shop_source TEXT DEFAULT 'railway'
        );
        CREATE TABLE IF NOT EXISTS shop_info(
            key TEXT PRIMARY KEY, value TEXT
        );
    """)
    for col in ["image_url","sizes","gender","shop_source"]:
        try: c.execute(f"ALTER TABLE products ADD COLUMN {col} TEXT")
        except: pass
    try: c.execute("ALTER TABLE orders ADD COLUMN shop_source TEXT DEFAULT 'railway'")
    except: pass
    defaults = [
        ("shop_name","Abid Shoes"),("shop_address","Main Bazar Jhumra Road, Khurrianwala, Faisalabad"),
        ("shop_phone","0323-866-6676"),("jazzcash_no","0323-866-6676"),
        ("easypaisa_no","0323-866-6676"),("delivery_charges","200"),
        ("free_delivery_above","3000"),("banner_text","Quality Footwear at Best Prices!"),
    ]
    for k,v in defaults:
        c.execute("INSERT OR IGNORE INTO shop_info(key,value) VALUES (?,?)",(k,v))
    conn.commit(); conn.close()

init_db()

def check_key():
    key = request.headers.get("X-API-Key") or request.args.get("key")
    return key == API_KEY

@app.route("/")
def home():
    return jsonify({"status":"Abid Shoes Railway API","version":"3.0","source":SHOP_SOURCE})

@app.route("/api/products")
def get_products():
    conn = get_db(); c = conn.cursor()
    brand = request.args.get("brand","")
    category = request.args.get("category","")
    search = request.args.get("search","")
    q = "SELECT * FROM products WHERE is_active=1"
    p = []
    if brand: q += " AND brand=?"; p.append(brand)
    if category: q += " AND category=?"; p.append(category)
    if search: q += " AND (name LIKE ? OR brand LIKE ?)"; p.extend(['%'+search+'%']*2)
    q += " ORDER BY brand, name"
    rows = c.execute(q,p).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])

@app.route("/api/shop")
def get_shop():
    conn = get_db()
    rows = conn.execute("SELECT key,value FROM shop_info").fetchall()
    conn.close()
    data = {r[0]:r[1] for r in rows}
    return jsonify(data)

@app.route("/api/orders", methods=["POST"])
def place_order():
    data = request.json
    if not data: return jsonify({"error":"No data"}),400
    for f in ["customer_name","customer_phone","customer_address","items"]:
        if not data.get(f): return jsonify({"error":f"{f} required"}),400
    conn = get_db(); c = conn.cursor()
    now = datetime.datetime.now()
    order_no = f"WEB-{now.strftime('%Y%m%d%H%M%S')}"
    items = json.dumps(data.get("items",[]))
    subtotal = float(data.get("subtotal",0))
    free_above = float(c.execute("SELECT value FROM shop_info WHERE key='free_delivery_above'").fetchone()[0] or 3000)
    delivery_charges = float(c.execute("SELECT value FROM shop_info WHERE key='delivery_charges'").fetchone()[0] or 200)
    delivery = 0 if subtotal >= free_above else delivery_charges
    total = subtotal + delivery
    c.execute("""INSERT INTO orders(order_no,customer_name,customer_phone,
                 customer_address,city,items,subtotal,delivery,total,
                 payment_method,status,notes,created_at,shop_source)
                 VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
              (order_no,data["customer_name"],data["customer_phone"],
               data["customer_address"],data.get("city",""),
               items,subtotal,delivery,total,
               data.get("payment_method","COD"),"Pending",
               data.get("notes",""),now.strftime("%Y-%m-%d %H:%M"),SHOP_SOURCE))
    conn.commit(); conn.close()
    return jsonify({"success":True,"order_no":order_no,"total":total,"delivery":delivery})

@app.route("/api/orders/<order_no>")
def track_order(order_no):
    conn = get_db()
    r = conn.execute("SELECT * FROM orders WHERE order_no=?",(order_no,)).fetchone()
    conn.close()
    if not r: return jsonify({"error":"Order not found"}),404
    return jsonify(dict(r))

@app.route("/api/sync", methods=["POST"])
def sync_from_pos():
    if not check_key(): return jsonify({"error":"Unauthorized"}),401
    data = request.json
    if not data or "products" not in data: return jsonify({"error":"No products"}),400
    conn = get_db(); c = conn.cursor()
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    updated = 0
    for p in data["products"]:
        c.execute("""INSERT OR REPLACE INTO products
                     (barcode,name,brand,category,price,stock,image_url,sizes,gender,is_active,updated_at,shop_source)
                     VALUES (?,?,?,?,?,?,?,?,?,1,?,?)""",
                  (p.get("barcode",""),p.get("name",""),p.get("brand",""),p.get("category",""),
                   float(p.get("price",0)),int(p.get("stock",0)),
                   p.get("image_url",""),p.get("sizes",""),p.get("gender","Unisex"),now,SHOP_SOURCE))
        updated += 1
    if "shop_info" in data:
        for k,v in data["shop_info"].items():
            c.execute("INSERT OR REPLACE INTO shop_info(key,value) VALUES (?,?)",(k,v))
    conn.commit(); conn.close()
    return jsonify({"success":True,"updated":updated})

@app.route("/api/orders/list")
def list_orders():
    if not check_key(): return jsonify({"error":"Unauthorized"}),401
    conn = get_db()
    status = request.args.get("status","")
    q = "SELECT * FROM orders WHERE 1=1"
    if status: q += f" AND status='{status}'"
    q += " ORDER BY id DESC LIMIT 100"
    rows = conn.execute(q).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])

@app.route("/api/orders/<order_no>/status", methods=["PUT"])
def update_order_status(order_no):
    if not check_key(): return jsonify({"error":"Unauthorized"}),401
    data = request.json
    conn = get_db()
    conn.execute("UPDATE orders SET status=? WHERE order_no=?",(data.get("status","Pending"),order_no))
    conn.commit(); conn.close()
    return jsonify({"success":True})

@app.route("/api/shop/update", methods=["POST"])
def update_shop():
    if not check_key(): return jsonify({"error":"Unauthorized"}),401
    data = request.json
    conn = get_db(); c = conn.cursor()
    for k,v in data.items():
        c.execute("INSERT OR REPLACE INTO shop_info(key,value) VALUES (?,?)",(k,v))
    conn.commit(); conn.close()
    return jsonify({"success":True})

if __name__ == "__main__":
    port = int(os.environ.get("PORT",5000))
    app.run(host="0.0.0.0",port=port,debug=False)

# ── ADMIN TABLES ──────────────────────────────────────────

def init_admin_tables():
    conn = get_db(); c = conn.cursor()
    c.executescript("""
        CREATE TABLE IF NOT EXISTS sales_summary(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            branch_id INTEGER DEFAULT 1,
            branch_name TEXT DEFAULT 'Main Shop',
            date TEXT,
            total_sales REAL DEFAULT 0,
            total_profit REAL DEFAULT 0,
            total_returns REAL DEFAULT 0,
            invoice_count INTEGER DEFAULT 0,
            synced_at TEXT
        );
        CREATE TABLE IF NOT EXISTS stock_summary(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            branch_id INTEGER DEFAULT 1,
            branch_name TEXT DEFAULT 'Main Shop',
            barcode TEXT,
            name TEXT,
            brand TEXT,
            category TEXT,
            stock INTEGER DEFAULT 0,
            price REAL DEFAULT 0,
            synced_at TEXT
        );
    """)
    conn.commit(); conn.close()

init_admin_tables()

# ── ADMIN SYNC ENDPOINTS ──────────────────────────────────

@app.route("/api/admin/sync", methods=["POST"])
def admin_sync():
    if not check_key(): return jsonify({"error":"Unauthorized"}),401
    data = request.json
    if not data: return jsonify({"error":"No data"}),400

    conn = get_db(); c = conn.cursor()
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")

    # Sales summary
    if "sales" in data:
        for s in data["sales"]:
            # Delete existing record for this branch+date
            c.execute("DELETE FROM sales_summary WHERE branch_id=? AND date=?",
                      (s.get("branch_id",1), s.get("date","")))
            c.execute("""INSERT INTO sales_summary
                        (branch_id,branch_name,date,total_sales,total_profit,
                         total_returns,invoice_count,synced_at)
                        VALUES (?,?,?,?,?,?,?,?)""",
                      (s.get("branch_id",1), s.get("branch_name","Main Shop"),
                       s.get("date",""), float(s.get("total_sales",0)),
                       float(s.get("total_profit",0)), float(s.get("total_returns",0)),
                       int(s.get("invoice_count",0)), now))

    # Stock summary
    if "stock" in data:
        branch_id = data["stock"][0].get("branch_id",1) if data["stock"] else 1
        c.execute("DELETE FROM stock_summary WHERE branch_id=?", (branch_id,))
        for st in data["stock"]:
            c.execute("""INSERT INTO stock_summary
                        (branch_id,branch_name,barcode,name,brand,category,stock,price,synced_at)
                        VALUES (?,?,?,?,?,?,?,?,?)""",
                      (st.get("branch_id",1), st.get("branch_name","Main Shop"),
                       st.get("barcode",""), st.get("name",""),
                       st.get("brand",""), st.get("category",""),
                       int(st.get("stock",0)), float(st.get("price",0)), now))

    conn.commit(); conn.close()
    return jsonify({"success":True,"synced_at":now})

# ── ADMIN VIEW ENDPOINTS ──────────────────────────────────

@app.route("/api/admin/dashboard")
def admin_dashboard():
    if not check_key(): return jsonify({"error":"Unauthorized"}),401
    conn = get_db(); c = conn.cursor()

    # Last 30 days sales per branch
    rows = c.execute("""
        SELECT branch_id, branch_name,
               SUM(total_sales) as sales,
               SUM(total_profit) as profit,
               SUM(total_returns) as returns,
               SUM(invoice_count) as invoices,
               MAX(synced_at) as last_sync
        FROM sales_summary
        WHERE date >= date('now','-30 days')
        GROUP BY branch_id, branch_name
        ORDER BY branch_id
    """).fetchall()

    # Today
    today_rows = c.execute("""
        SELECT branch_id, branch_name,
               SUM(total_sales) as sales,
               SUM(total_profit) as profit,
               SUM(invoice_count) as invoices
        FROM sales_summary
        WHERE date = date('now')
        GROUP BY branch_id, branch_name
    """).fetchall()

    # Orders pending
    orders = c.execute("SELECT COUNT(*) FROM orders WHERE status='Pending'").fetchone()[0]

    conn.close()
    return jsonify({
        "monthly": [dict(r) for r in rows],
        "today": [dict(r) for r in today_rows],
        "pending_orders": orders
    })

@app.route("/api/admin/sales")
def admin_sales():
    if not check_key(): return jsonify({"error":"Unauthorized"}),401
    conn = get_db()
    branch_id = request.args.get("branch_id","")
    date_from = request.args.get("from", (datetime.datetime.now()-datetime.timedelta(days=30)).strftime("%Y-%m-%d"))
    date_to = request.args.get("to", datetime.datetime.now().strftime("%Y-%m-%d"))

    q = "SELECT * FROM sales_summary WHERE date>=? AND date<=?"
    params = [date_from, date_to]
    if branch_id:
        q += " AND branch_id=?"
        params.append(branch_id)
    q += " ORDER BY date DESC, branch_id"

    rows = conn.execute(q, params).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])

@app.route("/api/admin/stock")
def admin_stock():
    if not check_key(): return jsonify({"error":"Unauthorized"}),401
    conn = get_db()
    branch_id = request.args.get("branch_id","")
    search = request.args.get("search","")

    q = "SELECT * FROM stock_summary WHERE stock>0"
    params = []
    if branch_id:
        q += " AND branch_id=?"; params.append(branch_id)
    if search:
        q += " AND (name LIKE ? OR brand LIKE ? OR barcode LIKE ?)"
        params.extend([f"%{search}%"]*3)
    q += " ORDER BY branch_id, brand, name"

    rows = conn.execute(q, params).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])

@app.route("/api/admin/branches")
def admin_branches():
    if not check_key(): return jsonify({"error":"Unauthorized"}),401
    conn = get_db()
    rows = conn.execute("""
        SELECT DISTINCT branch_id, branch_name, MAX(synced_at) as last_sync
        FROM sales_summary GROUP BY branch_id, branch_name
    """).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])
