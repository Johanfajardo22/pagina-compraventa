import os
import sqlite3
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify, abort
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
from flask import Flask






BASE_DIR = os.path.abspath(os.path.dirname(__file__))
DB_PATH = os.path.join(BASE_DIR, "catalog.db")
UPLOAD_FOLDER = os.path.join("static", "uploads")
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "webp"}

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "change-me-leon-secret")
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
app.config["MAX_CONTENT_LENGTH"] = 12 * 1024 * 1024  # 12 MB

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            description TEXT,
            price REAL NOT NULL DEFAULT 0,
            weight REAL,
            category TEXT,
            image_filename TEXT,
            is_active INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL
        );
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS admin_users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
    """)
    conn.commit()

    cur.execute("SELECT COUNT(*) as c FROM admin_users")
    if cur.fetchone()["c"] == 0:
        email = "admin@leon.com"
        pwd_hash = generate_password_hash("admin123")
        cur.execute("INSERT INTO admin_users (email, password_hash, created_at) VALUES (?, ?, ?)",
                    (email, pwd_hash, datetime.utcnow().isoformat()))
        conn.commit()
        print("Default admin created:", email, "/ admin123")

    # Seed sample products if none
    cur.execute("SELECT COUNT(*) as c FROM products")
    if cur.fetchone()["c"] == 0:
        sample = [
            ("Anillo Clásico 18K", "Anillo en oro 18 kilates, diseño clásico pulido.", 450000.0, 3.5, "anillo", None),
            ("Cadena Venezolana 14K", "Cadena de eslabones tipo venezolana, sólida.", 1250000.0, 9.8, "cadena", None),
            ("Arracadas Diseño Sutil 18K", "Arracadas medianas con acabado satinado.", 680000.0, 4.2, "arracadas", None)
        ]
        for name, desc, price, weight, category, img in sample:
            cur.execute("""INSERT INTO products (name, description, price, weight, category, image_filename, created_at)
                           VALUES (?, ?, ?, ?, ?, ?, ?)""",
                        (name, desc, price, weight, category, img, datetime.utcnow().isoformat()))
        conn.commit()
        print("Sample products added.")
    conn.close()

def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS

def save_image(file_storage):
    if not file_storage or file_storage.filename == "":
        return None
    if not allowed_file(file_storage.filename):
        return None
    filename = secure_filename(file_storage.filename)
    name, ext = os.path.splitext(filename)
    ts = datetime.utcnow().strftime("%Y%m%d%H%M%S%f")
    filename = f"{name}_{ts}{ext}"
    save_path = os.path.join(app.config["UPLOAD_FOLDER"], filename)
    os.makedirs(os.path.dirname(save_path), exist_ok=True)
    file_storage.save(save_path)
    return filename

def login_required(f):
    from functools import wraps
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not session.get("admin_id"):
            flash("Debes iniciar sesión.", "warning")
            return redirect(url_for("admin_login"))
        return f(*args, **kwargs)
    return wrapper

@app.route("/")
def home():
    return redirect(url_for("catalog"))

@app.route("/catalog")
def catalog():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT id, name, description, price, weight, category, image_filename FROM products WHERE is_active=1 ORDER BY created_at DESC")
    products = cur.fetchall()
    conn.close()
    return render_template("catalog.html", products=products)

@app.route("/api/products")
def api_products():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT id, name, description, price, weight, category, image_filename FROM products WHERE is_active=1 ORDER BY created_at DESC")
    items = [dict(r) for r in cur.fetchall()]
    conn.close()
    for it in items:
        it["image_url"] = url_for("static", filename="uploads/" + it["image_filename"]) if it.get("image_filename") else None
    return jsonify(items)

@app.route("/display")
def display():
    return render_template("display.html")

@app.route("/admin/login", methods=["GET","POST"])
def admin_login():
    if request.method == "POST":
        email = request.form.get("email","").strip().lower()
        password = request.form.get("password","")
        conn = get_db(); cur = conn.cursor()
        cur.execute("SELECT * FROM admin_users WHERE email = ?", (email,))
        user = cur.fetchone(); conn.close()
        if user and check_password_hash(user["password_hash"], password):
            session["admin_id"] = user["id"]
            session["admin_email"] = user["email"]
            flash("Bienvenido.", "success")
            return redirect(url_for("admin_dashboard"))
        flash("Credenciales inválidas.", "danger")
    return render_template("admin_login.html")

@app.route("/admin/logout")
def admin_logout():
    session.clear()
    flash("Sesión cerrada.", "info")
    return redirect(url_for("admin_login"))

@app.route("/admin")
@login_required
def admin_dashboard():
    conn = get_db(); cur = conn.cursor()
    cur.execute("SELECT id, name, price, weight, category, is_active, image_filename, created_at FROM products ORDER BY created_at DESC")
    products = cur.fetchall(); conn.close()
    return render_template("admin_dashboard.html", products=products)

@app.route("/admin/product/new", methods=["GET","POST"])
@login_required
def product_new():
    if request.method == "POST":
        name = request.form.get("name","").strip()
        description = request.form.get("description","").strip()
        price = float(request.form.get("price") or 0)
        weight = float(request.form.get("weight") or 0)
        category = request.form.get("category","").strip()
        is_active = 1 if request.form.get("is_active") == "on" else 0
        image = request.files.get("image")
        image_filename = save_image(image) if image else None
        conn = get_db(); cur = conn.cursor()
        cur.execute("INSERT INTO products (name, description, price, weight, category, image_filename, is_active, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (name, description, price, weight, category, image_filename, is_active, datetime.utcnow().isoformat()))
        conn.commit(); conn.close()
        flash("Producto creado.", "success")
        return redirect(url_for("admin_dashboard"))
    return render_template("product_form.html", mode="new", product=None)

@app.route("/admin/product/<int:pid>/edit", methods=["GET","POST"])
@login_required
def product_edit(pid):
    conn = get_db(); cur = conn.cursor()
    if request.method == "POST":
        name = request.form.get("name","").strip()
        description = request.form.get("description","").strip()
        price = float(request.form.get("price") or 0)
        weight = float(request.form.get("weight") or 0)
        category = request.form.get("category","").strip()
        is_active = 1 if request.form.get("is_active") == "on" else 0
        image = request.files.get("image")
        cur.execute("SELECT image_filename FROM products WHERE id = ?", (pid,))
        row = cur.fetchone()
        image_filename = row["image_filename"] if row else None
        if image and image.filename:
            new_fn = save_image(image)
            if new_fn:
                if image_filename:
                    try: os.remove(os.path.join(app.config["UPLOAD_FOLDER"], image_filename))
                    except OSError: pass
                image_filename = new_fn
        cur.execute("UPDATE products SET name=?, description=?, price=?, weight=?, category=?, image_filename=?, is_active=? WHERE id = ?",
                    (name, description, price, weight, category, image_filename, is_active, pid))
        conn.commit(); conn.close()
        flash("Producto actualizado.", "success")
        return redirect(url_for("admin_dashboard"))
    else:
        cur.execute("SELECT * FROM products WHERE id = ?", (pid,))
        product = cur.fetchone(); conn.close()
        if not product: abort(404)
        return render_template("product_form.html", mode="edit", product=product)

@app.route("/admin/product/<int:pid>/delete", methods=["POST"])
@login_required
def product_delete(pid):
    conn = get_db(); cur = conn.cursor()
    cur.execute("SELECT image_filename FROM products WHERE id = ?", (pid,))
    row = cur.fetchone()
    if row and row["image_filename"]:
        try: os.remove(os.path.join(app.config["UPLOAD_FOLDER"], row["image_filename"]))
        except OSError: pass
    cur.execute("DELETE FROM products WHERE id = ?", (pid,))
    conn.commit(); conn.close()
    flash("Producto eliminado.", "info")
    return redirect(url_for("admin_dashboard"))

@app.cli.command('init-db')
def cli_init_db():
    init_db()
    print('Base de datos inicializada.')

if __name__ == '__main__':
    os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)
    if not os.path.exists(DB_PATH):
        init_db()
    app.run(host='0.0.0.0', port=5000, debug=True)
