"""
Abid Shoes - Web API
Hosting pe deploy hoga (cPanel/Hostinger)
"""
from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS
import sqlite3, os, datetime, json, uuid

app = Flask(__name__)
CORS(app, origins="*")

@app.after_request
def add_cors(r):
    r.headers["Access-Control-Allow-Origin"] = "*"
    r.headers["Access-Control-Allow-Headers"] = "Content-Type, X-API-Key"
    r.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS"
    return r

DB  = os.path.join(os.path.dirname(__file__), "abidshoes_web.db")
API_KEY = os.environ.get("API_KEY", "abidshoes2024secret")
UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), "uploads")
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

ALLOWED = {'png','jpg','jpeg','gif','webp'}

def get_db():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db(); c = conn.cursor()
    c.executescript("""
        CREATE TABLE IF NOT EXISTS products(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            barcode TEXT UNIQUE, name TEXT, brand TEXT,
            category TEXT, price REAL, stock INTEGER DEFAULT 0,
            image_url TEXT, description TEXT,
            is_active INTEGER DEFAULT 1, updated_at TEXT);
        CREATE TABLE IF NOT EXISTS orders(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_no TEXT UNIQUE, customer_name TEXT,
            customer_phone TEXT, customer_address TEXT, city TEXT,
            items TEXT, subtotal REAL, delivery REAL DEFAULT 200,
            total REAL, payment_method TEXT,
            status TEXT DEFAULT 'Pending',
            notes TEXT, created_at TEXT);
        CREATE TABLE IF NOT EXISTS shop_info(key TEXT PRIMARY KEY, value TEXT);
    """)
    defaults = [
        ("shop_name","Abid Shoes"),
        ("shop_address","Main Bazar Jhumra Road, Khurrianwala, Faisalabad"),
        ("shop_phone","0323-866-6676"),
        ("jazzcash_no","0323-866-6676"),
        ("easypaisa_no","0323-866-6676"),
        ("delivery_charges","200"),
        ("free_delivery_above","3000"),
        ("banner_text","Quality Footwear at Best Prices!"),
    ]
    for k,v in defaults:
        c.execute("INSERT OR IGNORE INTO shop_info(key,value) VALUES (?,?)",(k,v))
    conn.commit(); conn.close()

init_db()

def check_key():
    return (request.headers.get("X-API-Key") or request.args.get("key")) == API_KEY

# ── PUBLIC ──
@app.route("/")
def home():
    return jsonify({"status":"Abid Shoes API running","version":"2.0"})

@app.route("/api/products")
def get_products():
    conn=get_db(); c=conn.cursor()
    brand=request.args.get("brand","")
    category=request.args.get("category","")
    search=request.args.get("search","")
    q="SELECT * FROM products WHERE is_active=1"
    p=[]
    if brand: q+=" AND brand=?"; p.append(brand)
    if category: q+=" AND category=?"; p.append(category)
    if search: q+=" AND (name LIKE ? OR brand LIKE ?)"; p.extend(['%'+search+'%']*2)
    q+=" ORDER BY brand,name"
    rows=c.execute(q,p).fetchall(); conn.close()
    return jsonify([dict(r) for r in rows])

@app.route("/api/shop")
def get_shop():
    conn=get_db()
    rows=conn.execute("SELECT key,value FROM shop_info").fetchall()
    conn.close()
    return jsonify({r[0]:r[1] for r in rows})

@app.route("/api/orders",methods=["POST"])
def place_order():
    data=request.json
    if not data: return jsonify({"error":"No data"}),400
    for f in ["customer_name","customer_phone","customer_address","items"]:
        if not data.get(f): return jsonify({"error":f"{f} zaroori hai"}),400
    conn=get_db(); c=conn.cursor()
    now=datetime.datetime.now()
    order_no=f"WEB-{now.strftime('%Y%m%d%H%M%S')}"
    items=json.dumps(data.get("items",[]))
    subtotal=float(data.get("subtotal",0))
    fa=float(c.execute("SELECT value FROM shop_info WHERE key='free_delivery_above'").fetchone()[0] or 3000)
    dc=float(c.execute("SELECT value FROM shop_info WHERE key='delivery_charges'").fetchone()[0] or 200)
    delivery=0 if subtotal>=fa else dc
    total=subtotal+delivery
    c.execute("""INSERT INTO orders(order_no,customer_name,customer_phone,
                 customer_address,city,items,subtotal,delivery,total,
                 payment_method,status,notes,created_at)
                 VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
              (order_no,data["customer_name"],data["customer_phone"],
               data["customer_address"],data.get("city",""),
               items,subtotal,delivery,total,
               data.get("payment_method","COD"),"Pending",
               data.get("notes",""),now.strftime("%Y-%m-%d %H:%M")))
    conn.commit(); conn.close()
    return jsonify({"success":True,"order_no":order_no,"total":total,"delivery":delivery})

@app.route("/api/orders/<order_no>")
def track_order(order_no):
    conn=get_db()
    r=conn.execute("SELECT * FROM orders WHERE order_no=?",(order_no,)).fetchone()
    conn.close()
    if not r: return jsonify({"error":"Order nahi mila"}),404
    return jsonify(dict(r))

# ── IMAGE UPLOAD ──
@app.route("/api/upload",methods=["POST"])
def upload_image():
    """POS se image upload"""
    if not check_key(): return jsonify({"error":"Unauthorized"}),401
    if 'image' not in request.files:
        return jsonify({"error":"No image"}),400
    file=request.files['image']
    if file.filename=='': return jsonify({"error":"No file"}),400
    ext=file.filename.rsplit('.',1)[-1].lower()
    if ext not in ALLOWED: return jsonify({"error":"Invalid file type"}),400
    # Unique filename
    fname=f"{uuid.uuid4().hex}.{ext}"
    fpath=os.path.join(UPLOAD_FOLDER,fname)
    file.save(fpath)
    # Return public URL
    base_url=request.host_url.rstrip('/')
    url=f"{base_url}/uploads/{fname}"
    return jsonify({"success":True,"url":url,"filename":fname})

@app.route("/uploads/<filename>")
def serve_upload(filename):
    return send_from_directory(UPLOAD_FOLDER,filename)

# ── POS ENDPOINTS ──
@app.route("/api/sync",methods=["POST"])
def sync_from_pos():
    if not check_key(): return jsonify({"error":"Unauthorized"}),401
    data=request.json
    if not data or "products" not in data: return jsonify({"error":"No data"}),400
    conn=get_db(); c=conn.cursor()
    now=datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    updated=0
    for p in data["products"]:
        c.execute("""INSERT OR REPLACE INTO products
                     (barcode,name,brand,category,price,stock,image_url,is_active,updated_at)
                     VALUES (?,?,?,?,?,?,?,1,?)""",
                  (p.get("barcode",""),p.get("name",""),p.get("brand",""),
                   p.get("category",""),float(p.get("price",0)),
                   int(p.get("stock",0)),p.get("image_url",""),now))
        updated+=1
    conn.commit(); conn.close()
    return jsonify({"success":True,"updated":updated,"time":now})

@app.route("/api/orders/list")
def list_orders():
    if not check_key(): return jsonify({"error":"Unauthorized"}),401
    conn=get_db()
    status=request.args.get("status","")
    q="SELECT * FROM orders"
    if status: q+=f" WHERE status='{status}'"
    q+=" ORDER BY id DESC LIMIT 100"
    rows=conn.execute(q).fetchall(); conn.close()
    return jsonify([dict(r) for r in rows])

@app.route("/api/orders/<order_no>/status",methods=["PUT"])
def update_order(order_no):
    if not check_key(): return jsonify({"error":"Unauthorized"}),401
    data=request.json
    conn=get_db()
    conn.execute("UPDATE orders SET status=? WHERE order_no=?",(data.get("status","Pending"),order_no))
    conn.commit(); conn.close()
    return jsonify({"success":True})

@app.route("/api/shop/update",methods=["POST"])
def update_shop():
    if not check_key(): return jsonify({"error":"Unauthorized"}),401
    data=request.json
    conn=get_db(); c=conn.cursor()
    for k,v in data.items():
        c.execute("INSERT OR REPLACE INTO shop_info(key,value) VALUES (?,?)",(k,v))
    conn.commit(); conn.close()
    return jsonify({"success":True})

if __name__=="__main__":
    port=int(os.environ.get("PORT",5000))
    app.run(host="0.0.0.0",port=port,debug=False)
