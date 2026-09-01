import os
import re
import random
from functools import wraps
from datetime import datetime, timedelta, date
from werkzeug.security import generate_password_hash, check_password_hash

from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    session,
    flash,
    jsonify
)

from flask_sqlalchemy import SQLAlchemy
from werkzeug.utils import secure_filename
from sqlalchemy import func, case

# ==========================================================
# MEDICINE INVENTORY MANAGEMENT SYSTEM
# ==========================================================

app = Flask(__name__)

app.secret_key = os.environ.get("SECRET_KEY", "medicine_inventory_secret")

BASE_DIR = os.path.abspath(os.path.dirname(__file__))

# On Vercel only /tmp is writable at runtime, and uploaded files won't
# persist between invocations anyway. Uploads folder is best-effort local
# storage; for a real deployment, use external storage (S3, etc).
IS_SERVERLESS = bool(os.environ.get("VERCEL"))

UPLOAD_FOLDER = (
    "/tmp/uploads" if IS_SERVERLESS
    else os.path.join(BASE_DIR, "static", "uploads")
)

try:
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
except OSError:
    pass

app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER

# ==========================================================
# Database
# ----------------------------------------------------------
# Set DATABASE_URL in your environment (e.g. a Neon Postgres
# connection string) to use Postgres. Falls back to a local
# SQLite file for local development when DATABASE_URL is unset.
# ==========================================================

DATABASE_URL = os.environ.get("DATABASE_URL")

if DATABASE_URL:
    # SQLAlchemy 2.x requires the "postgresql://" scheme; some providers
    # (Neon, Heroku, etc.) hand out "postgres://" URLs.
    if DATABASE_URL.startswith("postgres://"):
        DATABASE_URL = DATABASE_URL.replace(
            "postgres://", "postgresql://", 1
        )
    app.config["SQLALCHEMY_DATABASE_URI"] = DATABASE_URL
else:
    db_path = "/tmp/medicine.db" if IS_SERVERLESS else os.path.join(
        BASE_DIR, "medicine.db"
    )
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///" + db_path

app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)

# ==========================================================
# DATABASE MODELS
# ==========================================================


class User(db.Model):

    id = db.Column(db.Integer, primary_key=True)

    name = db.Column(db.String(100))

    email = db.Column(db.String(100), unique=True)

    password = db.Column(db.String(100))

    role = db.Column(db.String(20))


# ==========================================================
# MEDICINES
# (Backend model name kept as Product so existing routes work)
# ==========================================================

class Product(db.Model):

    id = db.Column(db.Integer, primary_key=True)

    # Medicine Code
    code = db.Column(db.String(30), unique=True)

    # Medicine Name
    name = db.Column(db.String(150), nullable=False)

    # Manufacturer
    brand = db.Column(db.String(100))

    # Category
    category = db.Column(db.String(100))

    # Batch Number
    batch_no = db.Column(db.String(50))

    # Manufacturing Date
    manufacture_date = db.Column(db.Date)

    # Expiry Date
    expiry_date = db.Column(db.Date)

    # MRP
    price = db.Column(db.Float)

    # Available Stock
    stock = db.Column(db.Integer, default=0)

    # Medicine Image
    image = db.Column(db.String(255), default="default.png")

    created_at = db.Column(
        db.DateTime,
        default=datetime.utcnow
    )
    # ==========================================================
# EXPIRY LABEL
# ==========================================================

def expiry_label(product):

    if not product.expiry_date:

        return "No Expiry"

    today = date.today()

    if product.expiry_date < today:

        return "Expired"

    elif product.expiry_date <= today + timedelta(days=30):

        return "Expiring Soon"

    return "Safe"

    # -----------------------------
    # EXPIRY STATUS
    # -----------------------------
    @property
    def expiry_status(self):

        if not self.expiry_date:
            return "No Expiry"

        today = date.today()

        if self.expiry_date < today:
            return "Expired"

        if self.expiry_date <= today + timedelta(days=30):
            return "Expiring Soon"

        return "Safe"

    # -----------------------------
    # DAYS LEFT
    # -----------------------------
    @property
    def days_left(self):

        if not self.expiry_date:
            return None

        return (self.expiry_date - date.today()).days


# ==========================================================
# SUPPLIERS
# ==========================================================

class Supplier(db.Model):

    id = db.Column(db.Integer, primary_key=True)

    name = db.Column(db.String(100))

    phone = db.Column(db.String(20))

    email = db.Column(db.String(100))

    address = db.Column(db.Text)


# ==========================================================
# PATIENTS (Customer)
# ==========================================================

class Customer(db.Model):

    id = db.Column(db.Integer, primary_key=True)

    name = db.Column(db.String(100))

    phone = db.Column(db.String(20))

    email = db.Column(db.String(100))

    address = db.Column(db.String(255))

    # ==========================================================
# INVENTORY BATCHES
# (Every purchase of a medicine creates its own independent batch.
#  Stock is never merged just because the medicine name matches.)
# ==========================================================

class Batch(db.Model):

    id = db.Column(db.Integer, primary_key=True)

    product_id = db.Column(
        db.Integer,
        db.ForeignKey("product.id"),
        nullable=False
    )

    supplier_id = db.Column(
        db.Integer,
        db.ForeignKey("supplier.id")
    )

    # Batch Number (as printed on the strip/box)
    batch_no = db.Column(db.String(50))

    # Unique barcode for this specific batch
    barcode = db.Column(db.String(64), unique=True)

    invoice_no = db.Column(db.String(50))

    manufacture_date = db.Column(db.Date)

    expiry_date = db.Column(db.Date)

    quantity_purchased = db.Column(db.Integer, default=0)

    # Remaining stock in THIS batch only
    quantity_remaining = db.Column(db.Integer, default=0)

    purchase_price = db.Column(db.Float, default=0)

    selling_price = db.Column(db.Float, default=0)

    gst_percent = db.Column(db.Float, default=0)

    location = db.Column(db.String(100))

    created_at = db.Column(
        db.DateTime,
        default=datetime.utcnow
    )

    product = db.relationship(
        "Product",
        backref="batches"
    )

    supplier = db.relationship(
        "Supplier",
        backref="batches"
    )

    @property
    def is_expired(self):

        if not self.expiry_date:
            return False

        return self.expiry_date < date.today()

    @property
    def days_to_expiry(self):

        if not self.expiry_date:
            return None

        return (self.expiry_date - date.today()).days

    @property
    def batch_value(self):

        return (self.purchase_price or 0) * (self.quantity_remaining or 0)


# ==========================================================
# PURCHASES
# ==========================================================

class Purchase(db.Model):

    id = db.Column(db.Integer, primary_key=True)

    supplier_id = db.Column(
        db.Integer,
        db.ForeignKey("supplier.id")
    )

    product_id = db.Column(
        db.Integer,
        db.ForeignKey("product.id")
    )

    batch_id = db.Column(
        db.Integer,
        db.ForeignKey("batch.id")
    )

    quantity = db.Column(db.Integer)

    unit_price = db.Column(db.Float)

    cost = db.Column(db.Float)

    purchase_date = db.Column(
        db.DateTime,
        default=datetime.utcnow
    )

    supplier = db.relationship(
        "Supplier",
        backref="purchases"
    )

    product = db.relationship(
        "Product",
        backref="purchases"
    )

    batch = db.relationship(
        "Batch",
        backref="purchase_record"
    )


# ==========================================================
# SALES
# ==========================================================

class Sale(db.Model):

    id = db.Column(
        db.Integer,
        primary_key=True
    )

    customer_id = db.Column(
        db.Integer,
        db.ForeignKey("customer.id")
    )

    subtotal = db.Column(db.Float)

    discount = db.Column(db.Float)

    tax = db.Column(db.Float)

    total = db.Column(db.Float)

    payment_method = db.Column(db.String(30))

    date = db.Column(
        db.DateTime,
        default=lambda: datetime.utcnow() + timedelta(hours=5, minutes=30)
    )

    customer = db.relationship(
        "Customer",
        backref="sales"
    )

    items = db.relationship(
        "SaleItem",
        backref="sale",
        lazy=True,
        cascade="all, delete-orphan"
    )


# ==========================================================
# SALE ITEMS
# ==========================================================

class SaleItem(db.Model):

    id = db.Column(
        db.Integer,
        primary_key=True
    )

    sale_id = db.Column(
        db.Integer,
        db.ForeignKey("sale.id")
    )

    product_id = db.Column(
        db.Integer,
        db.ForeignKey("product.id")
    )

    batch_id = db.Column(
        db.Integer,
        db.ForeignKey("batch.id")
    )

    quantity = db.Column(db.Integer)

    price = db.Column(db.Float)

    product = db.relationship(
        "Product",
        backref="sale_items"
    )

    batch = db.relationship(
        "Batch",
        backref="sale_items"
    )


# ==========================================================
# SHOP SETTINGS (UPI / CONTACT / THANK YOU MESSAGE)
# ==========================================================

class Settings(db.Model):

    id = db.Column(db.Integer, primary_key=True)

    shop_name = db.Column(db.String(150), default="JAN SEVA PHARMACY")

    phone_number = db.Column(db.String(20), default="")

    upi_id = db.Column(db.String(100), default="")

    thank_you_message = db.Column(
        db.String(300),
        default="Thank You For Your Purchase! We appreciate your business. Visit Again."
    )


def get_settings():

    settings = Settings.query.first()

    if not settings:

        settings = Settings()

        db.session.add(settings)

        db.session.commit()

    return settings


# ==========================================================
# LIGHTWEIGHT SQLITE MIGRATION
# (Adds new columns to tables that already existed on disk
#  from before batch support was introduced.)
# ==========================================================

def _column_exists(table_name, column_name):

    inspector = db.inspect(db.engine)

    columns = [col["name"] for col in inspector.get_columns(table_name)]

    return column_name in columns


def _migrate_schema():

    migrations = [
        ("purchase", "batch_id", "INTEGER"),
        ("sale_item", "batch_id", "INTEGER"),
    ]

    for table_name, column_name, column_type in migrations:

        try:

            if not _column_exists(table_name, column_name):

                db.session.execute(
                    db.text(
                        f"ALTER TABLE {table_name} "
                        f"ADD COLUMN {column_name} {column_type}"
                    )
                )

                db.session.commit()

        except Exception:

            db.session.rollback()


def _backfill_legacy_batches():
    """
    Older versions of this app stored a single batch_no/expiry_date/stock
    directly on the medicine and merged every purchase into it. The first
    time this app runs after the update, we create one "legacy" batch per
    existing medicine so nothing breaks and existing stock is preserved.
    Every purchase made from now on creates its own independent batch.
    """

    if Batch.query.count() > 0:
        return

    products = Product.query.all()

    for product in products:

        if not product.stock and not product.batch_no:
            continue

        already_sold = db.session.query(
            func.sum(SaleItem.quantity)
        ).filter(
            SaleItem.product_id == product.id
        ).scalar() or 0

        legacy_batch = Batch(
            product_id=product.id,
            batch_no=product.batch_no or "LEGACY",
            barcode=generate_barcode(product.code, product.batch_no or "LEGACY"),
            manufacture_date=product.manufacture_date,
            expiry_date=product.expiry_date,
            quantity_purchased=(product.stock or 0) + already_sold,
            quantity_remaining=product.stock or 0,
            purchase_price=product.price or 0,
            selling_price=product.price or 0,
            gst_percent=0,
            location=None
        )

        db.session.add(legacy_batch)
        db.session.flush()

        # Point existing purchase records and sale items for this
        # medicine at the legacy batch so reports/invoices never crash.
        Purchase.query.filter_by(
            product_id=product.id,
            batch_id=None
        ).update({"batch_id": legacy_batch.id})

        SaleItem.query.filter_by(
            product_id=product.id,
            batch_id=None
        ).update({"batch_id": legacy_batch.id})

    db.session.commit()


def generate_barcode(product_code, batch_no):

    base = re.sub(
        r"[^A-Za-z0-9]", "",
        f"{product_code or 'MED'}{batch_no or ''}"
    ).upper()

    candidate = f"{base}{int(datetime.utcnow().timestamp())}"[:20]

    # Guarantee uniqueness even on rapid repeated calls
    while Batch.query.filter_by(barcode=candidate).first():

        candidate = f"{base}{random.randint(1000, 9999)}"[:20]

    return candidate


def generate_product_code(name):
    """Auto-generate a unique medicine code when a new medicine is
    created straight from the Add Purchase screen (no code entered)."""

    base = re.sub(r"[^A-Za-z0-9]", "", name or "MED").upper()[:6] or "MED"

    candidate = f"{base}{random.randint(1000, 9999)}"

    while Product.query.filter_by(code=candidate).first():
        candidate = f"{base}{random.randint(1000, 9999)}"

    return candidate


def recompute_product_stock(product):
    """Product.stock is kept as a synced total of all its batches so
    existing templates that read product.stock keep working."""

    total = db.session.query(
        func.sum(Batch.quantity_remaining)
    ).filter(
        Batch.product_id == product.id
    ).scalar()

    product.stock = total or 0


def get_fefo_batch(product_id):
    """Return the batch with the nearest expiry date that still has
    stock -- First Expired, First Out."""

    return Batch.query.filter(
        Batch.product_id == product_id,
        Batch.quantity_remaining > 0
    ).order_by(
        case((Batch.expiry_date.is_(None), 1), else_=0),
        Batch.expiry_date.asc()
    ).first()


def expiring_batches(days_min, days_max):

    today = date.today()

    query = Batch.query.filter(
        Batch.quantity_remaining > 0,
        Batch.expiry_date != None
    )

    if days_min is not None:
        query = query.filter(
            Batch.expiry_date >= today + timedelta(days=days_min)
        )

    if days_max is not None:
        query = query.filter(
            Batch.expiry_date <= today + timedelta(days=days_max)
        )

    return query.order_by(Batch.expiry_date.asc()).all()


def expired_batches():

    return Batch.query.filter(
        Batch.quantity_remaining > 0,
        Batch.expiry_date != None,
        Batch.expiry_date < date.today()
    ).order_by(Batch.expiry_date.asc()).all()


# ==========================================================
# CREATE DATABASE
# ==========================================================

with app.app_context():

    db.create_all()

    _migrate_schema()

    _backfill_legacy_batches()

    # ----------------------------------
    # Default Administrator
    # ----------------------------------

    if not User.query.filter_by(
        email="admin@inventory.com"
    ).first():

        admin = User(
            name="Administrator",
            email="admin@inventory.com",
            password=generate_password_hash("admin123"),
            role="Admin"
        )

        db.session.add(admin)

    # ----------------------------------
    # Default Cashier
    # ----------------------------------

    if not User.query.filter_by(
        email="cashier@inventory.com"
    ).first():

        cashier = User(
            name="Cashier",
            email="cashier@inventory.com",
            password=generate_password_hash("cashier123"),
            role="Cashier"
        )

        db.session.add(cashier)

    # ----------------------------------
    # Default Shop Settings
    # ----------------------------------

    if not Settings.query.first():

        db.session.add(Settings())

    db.session.commit()


# ==========================================================
# MEDICINE EXPIRY HELPER FUNCTIONS
# ==========================================================

def expired_medicines():

    return Product.query.filter(
        Product.expiry_date < date.today()
    ).all()


def expiring_soon_medicines():

    return Product.query.filter(
        Product.expiry_date >= date.today(),
        Product.expiry_date <= date.today() + timedelta(days=30)
    ).all()


def safe_medicines():

    return Product.query.filter(
        Product.expiry_date > date.today() + timedelta(days=30)
    ).all()


def low_stock_medicines():

    return Product.query.filter(
        Product.stock <= 5
    ).all()


def inventory_value():

    value = db.session.query(
        func.sum(Product.price * Product.stock)
    ).scalar()

    return value or 0
# ==========================================================
# DAYS LEFT
# ==========================================================

def days_remaining(expiry_date):

    if expiry_date is None:

        return None

    return (
        expiry_date - date.today()
    ).days
# ==========================================================
# LOGIN REQUIRED DECORATOR
# ==========================================================

def login_required(f):

    @wraps(f)
    def decorated(*args, **kwargs):

        if "user_id" not in session:

            flash("Please login first.", "warning")
            return redirect(url_for("login"))

        return f(*args, **kwargs)

    return decorated


# ==========================================================
# HOME
# ==========================================================

@app.route("/")
def home():

    return redirect(url_for("login"))


@app.route("/login", methods=["GET", "POST"])
def login():

    if request.method == "POST":

        email = request.form["email"].strip()
        password = request.form["password"]

        user = User.query.filter_by(email=email).first()

        if user and check_password_hash(user.password, password):

            session["user_id"] = user.id
            session["name"] = user.name
            session["role"] = user.role
            session["email"] = user.email

            flash("Welcome", "success")
            return redirect(url_for("dashboard"))

        flash("Invalid Email or Password", "danger")

    return render_template("login.html")

# ==========================================================
# LOGOUT
# ==========================================================

@app.route("/logout")
@login_required
def logout():

    session.clear()

    flash(
        "Logged Out Successfully",
        "success"
    )

    return redirect(url_for("login"))


# ==========================================================
# DASHBOARD
# ==========================================================

@app.route("/dashboard")
@login_required
def dashboard():

    total_products = Product.query.count()

    total_patients = Customer.query.count()

    total_suppliers = Supplier.query.count()

    low_stock = Product.query.filter(
        Product.stock <= 5
    ).count()

    inventory = db.session.query(
        func.sum(Product.price * Product.stock)
    ).scalar() or 0

    today = date.today()

    # -----------------------------
    # Expiry Statistics (batch-level, real-time)
    # -----------------------------

    expired_batch_list = expired_batches()

    expiring_180_list = expiring_batches(None, 180)

    expired_count = len(expired_batch_list)

    expiring_soon = len(expiring_batches(None, 30))

    safe_medicines = Batch.query.filter(
        Batch.quantity_remaining > 0,
        Batch.expiry_date != None,
        Batch.expiry_date > today + timedelta(days=180)
    ).count()

    expired_products = expired_batch_list[:10]

    # "expiring soon" widget: nearest-expiry batches within 180 days
    expiry_products = expiring_180_list[:10]

    expiring_products = expiring_batches(None, 30)[:10]

    # -----------------------------
    # Today's Sales
    # -----------------------------

    today_sales = db.session.query(
        func.sum(Sale.total)
    ).filter(
        func.date(Sale.date) == today
    ).scalar() or 0

    # -----------------------------
    # Monthly Sales
    # -----------------------------

    first_day = today.replace(day=1)

    monthly_sales = db.session.query(
        func.sum(Sale.total)
    ).filter(
        Sale.date >= first_day
    ).scalar() or 0

    recent_sales = Sale.query.order_by(
        Sale.date.desc()
    ).limit(10).all()

    # -----------------------------
    # Sales trend for chart (last 6 months, real data)
    # -----------------------------

    chart_labels = []
    chart_values = []

    def _shift_month_start(base_start, offset):
        # offset is negative to go back in time, 0 = base month
        year = base_start.year
        month = base_start.month + offset
        while month < 1:
            month += 12
            year -= 1
        while month > 12:
            month -= 12
            year += 1
        return base_start.replace(year=year, month=month, day=1)

    for i in range(5, -1, -1):
        month_start = _shift_month_start(first_day, -i)
        next_month_start = _shift_month_start(first_day, -i + 1)

        month_total = db.session.query(
            func.sum(Sale.total)
        ).filter(
            Sale.date >= month_start,
            Sale.date < next_month_start
        ).scalar() or 0

        chart_labels.append(month_start.strftime("%b"))
        chart_values.append(round(float(month_total), 2))

    # Total inventory status breakdown (for the inventory overview bars)
    out_of_stock = Product.query.filter(Product.stock <= 0).count()
    low_stock_only = Product.query.filter(Product.stock > 0, Product.stock <= 5).count()
    in_stock = max(total_products - low_stock_only - out_of_stock, 0)

    return render_template(

        "dashboard.html",

        total_products=total_products,

        total_patients=total_patients,

        total_suppliers=total_suppliers,

        inventory_value=inventory,

        low_stock=low_stock,

        today_sales=today_sales,

        monthly_sales=monthly_sales,

        recent_sales=recent_sales,

        expired_count=expired_count,

        expiring_soon=expiring_soon,

        safe_medicines=safe_medicines,

        expired_products=expired_products,

        expiring_products=expiring_products,

        expiry_products=expiry_products,

        chart_labels=chart_labels,

        chart_values=chart_values,

        in_stock=in_stock,

        low_stock_only=low_stock_only,

        out_of_stock=out_of_stock

    )
# ==========================================================
# SIDEBAR ROUTES
# ==========================================================

# Dashboard -> uses dashboard()

# Products -> uses product_list()

# Sales -> uses pos()

# Purchases -> uses purchases()

# Customers -> uses customers()

# Suppliers -> uses suppliers()

# Reports -> uses reports()

# ==========================================================
# MEDICINES LIST
# ==========================================================

@app.route("/product_list")
@login_required
def product_list():

    search = request.args.get("search", "").strip()

    query = Product.query

    if search:

        query = query.filter(

            db.or_(

                Product.name.contains(search),

                Product.code.contains(search),

                Product.brand.contains(search),

                Product.category.contains(search),

                Product.batch_no.contains(search)

            )

        )

    medicines = query.order_by(
        Product.id.desc()
    ).all()

    today = date.today()

    warning_date = today + timedelta(days=30)

    return render_template(

        "medicines.html",

        products=medicines,

        search=search,

        today=today,

        warning_date=warning_date

    )
# ==========================================================
# ADD MEDICINE
# ==========================================================

@app.route("/add_product", methods=["GET", "POST"])
@login_required
def add_product():

    if request.method == "POST":

        code = request.form["code"]

        name = request.form["name"]

        brand = request.form["brand"]

        category = request.form["category"]

        batch_no = request.form["batch_no"]

        manufacture_date = request.form.get(
            "manufacture_date"
        )

        expiry_date = request.form.get(
            "expiry_date"
        )

        price = float(
            request.form["price"]
        )

        stock = int(
            request.form["stock"]
        )

        filename = "default.png"

        if "image" in request.files:

            file = request.files["image"]

            if file.filename != "":

                filename = secure_filename(
                    file.filename
                )

                file.save(

                    os.path.join(

                        app.config["UPLOAD_FOLDER"],

                        filename

                    )

                )

        medicine = Product(

            code=code,

            name=name,

            brand=brand,

            category=category,

            batch_no=batch_no,

            manufacture_date=datetime.strptime(
                manufacture_date,
                "%Y-%m-%d"
            ).date() if manufacture_date else None,

            expiry_date=datetime.strptime(
                expiry_date,
                "%Y-%m-%d"
            ).date() if expiry_date else None,

            price=price,

            stock=stock,

            image=filename

        )

        db.session.add(medicine)

        db.session.commit()

        flash(
            "Medicine Added Successfully",
            "success"
        )

        return redirect(
            url_for("product_list")
        )

    return render_template(
        "add_medicine.html"
    )
# ==========================================================
# EDIT MEDICINE
# ==========================================================

@app.route("/edit_product/<int:id>", methods=["GET", "POST"])
@login_required
def edit_product(id):

    medicine = Product.query.get_or_404(id)

    if request.method == "POST":

        medicine.code = request.form["code"]

        medicine.name = request.form["name"]

        medicine.brand = request.form["brand"]

        medicine.category = request.form["category"]

        medicine.batch_no = request.form["batch_no"]

        medicine.manufacture_date = datetime.strptime(
            request.form["manufacture_date"],
            "%Y-%m-%d"
        ).date() if request.form["manufacture_date"] else None

        medicine.expiry_date = datetime.strptime(
            request.form["expiry_date"],
            "%Y-%m-%d"
        ).date() if request.form["expiry_date"] else None

        medicine.price = float(
            request.form["price"]
        )

        medicine.stock = int(
            request.form["stock"]
        )

        if "image" in request.files:

            file = request.files["image"]

            if file.filename != "":

                filename = secure_filename(
                    file.filename
                )

                file.save(
                    os.path.join(
                        app.config["UPLOAD_FOLDER"],
                        filename
                    )
                )

                medicine.image = filename

        db.session.commit()

        flash(
            "Medicine Updated Successfully",
            "success"
        )

        return redirect(
            url_for("product_list")
        )

    return render_template(
        "edit_medicine.html",
        product=medicine
    )


# ==========================================================
# DELETE MEDICINE
# ==========================================================

@app.route("/delete_product/<int:id>")
@login_required
def delete_product(id):

    medicine = Product.query.get_or_404(id)

    if medicine.image != "default.png":

        image_path = os.path.join(
            app.config["UPLOAD_FOLDER"],
            medicine.image
        )

        if os.path.exists(image_path):

            os.remove(image_path)

    db.session.delete(medicine)

    db.session.commit()

    flash(
        "Medicine Deleted Successfully",
        "success"
    )

    return redirect(
        url_for("product_list")
    )


# ==========================================================
# SEARCH MEDICINES
# ==========================================================

@app.route("/search_products")
@login_required
def search_products():

    keyword = request.args.get(
        "q",
        ""
    ).strip()

    medicines = Product.query.filter(

        db.or_(

            Product.name.contains(keyword),

            Product.code.contains(keyword),

            Product.brand.contains(keyword),

            Product.category.contains(keyword),

            Product.batch_no.contains(keyword)

        )

    ).order_by(
        Product.name.asc()
    ).all()

    return render_template(

        "medicines.html",

        products=medicines,

        search=keyword,

        today=date.today(),

        warning_date=date.today() + timedelta(days=30)

    )

# ==========================================================
# MEDICINE STATUS
# ==========================================================

def medicine_status(product):

    if product.expiry_date is None:

        return "No Expiry"

    today = date.today()

    if product.expiry_date < today:

        return "Expired"

    elif product.expiry_date <= today + timedelta(days=30):

        return "Expiring Soon"

    else:

        return "Safe"


def medicine_color(product):

    status = medicine_status(product)

    if status == "Expired":

        return "danger"

    elif status == "Expiring Soon":

        return "warning"

    return "success"
# ==========================================================
# MEDICINE PURCHASES
# ==========================================================

@app.route("/purchases")
@login_required
def purchases():

    search = request.args.get("q", "").strip()

    query = Purchase.query.join(Product)

    if search:

        query = query.filter(

            db.or_(

                Product.name.contains(search),

                Product.code.contains(search),

                Product.brand.contains(search),

                Product.batch_no.contains(search)

            )

        )

    purchase_list = query.order_by(
        Purchase.purchase_date.desc()
    ).all()

    suppliers = Supplier.query.order_by(
        Supplier.name.asc()
    ).all()

    medicines = Product.query.order_by(
        Product.name.asc()
    ).all()

    return render_template(

        "purchases.html",

        purchases=purchase_list,

        suppliers=suppliers,

        products=medicines,

        search=search,

        today=date.today(),

        warning_date=date.today() + timedelta(days=30)

    )
# ==========================================================
# ADD MEDICINE PURCHASE
# ==========================================================

@app.route("/add_purchase", methods=["GET", "POST"])
@login_required
def add_purchase():

    suppliers = Supplier.query.order_by(
        Supplier.name
    ).all()

    if request.method == "POST":

        supplier_name = request.form["supplier_name"].strip()

        supplier = Supplier.query.filter_by(
            name=supplier_name
        ).first()

        if not supplier:

            supplier = Supplier(
                name=supplier_name
            )

            db.session.add(supplier)

            db.session.commit()

        product_name = request.form["product_name"].strip()

        brand = request.form.get("brand", "").strip()

        category = request.form.get("category", "").strip()

        product = Product.query.filter(
            db.func.lower(Product.name) == product_name.lower()
        ).first()

        is_new_product = product is None

        if not product:

            product = Product(
                name=product_name,
                code=generate_product_code(product_name)
            )

            db.session.add(product)

            db.session.flush()

        quantity = int(
            request.form["quantity"]
        )

        unit_price = float(
            request.form["unit_price"]
        )

        batch_no = request.form["batch_no"].strip()

        expiry_date = request.form["expiry_date"]

        manufacture_date = request.form.get("manufacture_date")

        selling_price = request.form.get("selling_price")

        gst_percent = request.form.get("gst_percent")

        # Keep the Medicine Inventory record in sync with what was just
        # purchased -- a brand-new medicine gets its full profile filled
        # in from this purchase, and an existing one is only updated
        # where the purchase actually supplied a (non-blank) value, so a
        # quick re-purchase never blanks out details entered earlier.
        if brand and (is_new_product or not product.brand):
            product.brand = brand
        elif is_new_product:
            product.brand = brand or None

        if category and (is_new_product or not product.category):
            product.category = category
        elif is_new_product:
            product.category = category or None

        if selling_price:
            product.price = float(selling_price)
        elif is_new_product:
            product.price = unit_price

        invoice_no = request.form.get("invoice_no", "").strip()

        location = request.form.get("location", "").strip()

        barcode = request.form.get("barcode", "").strip()

        if not barcode:
            barcode = generate_barcode(product.code, batch_no)

        # Every purchase creates its OWN independent batch --
        # stock is never merged just because the medicine matches.

        batch = Batch(

            product_id=product.id,

            supplier_id=supplier.id,

            batch_no=batch_no,

            barcode=barcode,

            invoice_no=invoice_no or None,

            manufacture_date=datetime.strptime(
                manufacture_date, "%Y-%m-%d"
            ).date() if manufacture_date else None,

            expiry_date=datetime.strptime(
                expiry_date, "%Y-%m-%d"
            ).date() if expiry_date else None,

            quantity_purchased=quantity,

            quantity_remaining=quantity,

            purchase_price=unit_price,

            selling_price=float(selling_price) if selling_price else product.price,

            gst_percent=float(gst_percent) if gst_percent else 0,

            location=location or None

        )

        db.session.add(batch)
        db.session.flush()

        total_cost = quantity * unit_price

        purchase = Purchase(

            supplier_id=supplier.id,

            product_id=product.id,

            batch_id=batch.id,

            quantity=quantity,

            unit_price=unit_price,

            cost=total_cost

        )

        db.session.add(purchase)

        # Keep the medicine's own batch_no/expiry_date fields showing the
        # most recently purchased batch, purely for any legacy screens
        # that still read those fields directly.
        product.batch_no = batch_no

        if batch.expiry_date:
            product.expiry_date = batch.expiry_date

        recompute_product_stock(product)

        db.session.commit()

        flash(
            f"Medicine Purchase Added Successfully (Batch: {batch_no}, Barcode: {barcode})",
            "success"
        )

        return redirect(
            url_for("purchases")
        )

    medicines = Product.query.order_by(Product.name).all()

    return render_template(

        "add_purchase.html",

        suppliers=suppliers,

        medicines=medicines

    )
# ==========================================================
# EDIT MEDICINE PURCHASE
# ==========================================================

@app.route("/edit_purchase/<int:id>", methods=["GET", "POST"])
@login_required
def edit_purchase(id):

    purchase = Purchase.query.get_or_404(id)

    suppliers = Supplier.query.order_by(
        Supplier.name
    ).all()

    products = Product.query.order_by(
        Product.name
    ).all()

    if request.method == "POST":

        old_product = Product.query.get_or_404(
            purchase.product_id
        )

        batch = purchase.batch

        # How much of the original batch has already been sold --
        # we must preserve that when the batch quantity is edited.
        already_sold = 0

        if batch:
            already_sold = (batch.quantity_purchased or 0) - (batch.quantity_remaining or 0)

        supplier = Supplier.query.filter_by(
            name=request.form["supplier_name"]
        ).first()

        if not supplier:

            supplier = Supplier(
                name=request.form["supplier_name"]
            )

            db.session.add(supplier)

            db.session.commit()

        purchase.supplier_id = supplier.id

        purchase.product_id = int(
            request.form["product_id"]
        )

        quantity = int(
            request.form["quantity"]
        )

        unit_price = float(
            request.form["unit_price"]
        )

        purchase.quantity = quantity

        purchase.unit_price = unit_price

        purchase.cost = quantity * unit_price

        new_product = Product.query.get_or_404(
            purchase.product_id
        )

        expiry = request.form["expiry_date"]

        expiry_date_value = datetime.strptime(
            expiry, "%Y-%m-%d"
        ).date() if expiry else None

        if batch is None:

            batch = Batch(
                barcode=generate_barcode(
                    new_product.code,
                    request.form["batch_no"]
                )
            )

            db.session.add(batch)
            purchase.batch = batch

        batch.product_id = new_product.id

        batch.supplier_id = supplier.id

        batch.batch_no = request.form["batch_no"]

        if expiry_date_value:
            batch.expiry_date = expiry_date_value

        batch.purchase_price = unit_price

        batch.quantity_purchased = quantity

        # Keep whatever was already sold, clamp remaining at zero
        batch.quantity_remaining = max(quantity - already_sold, 0)

        new_product.batch_no = request.form["batch_no"]

        if expiry_date_value:
            new_product.expiry_date = expiry_date_value

        db.session.flush()

        recompute_product_stock(old_product)

        if new_product.id != old_product.id:
            recompute_product_stock(new_product)

        db.session.commit()

        flash(
            "Medicine Purchase Updated Successfully",
            "success"
        )

        return redirect(
            url_for("purchases")
        )

    return render_template(
        "edit_purchase.html",
        purchase=purchase,
        suppliers=suppliers,
        products=products
    )
# ==========================================================
# DELETE PURCHASE
# ==========================================================

@app.route("/delete_purchase/<int:id>")
@login_required
def delete_purchase(id):

    purchase = Purchase.query.get_or_404(id)

    medicine = Product.query.get_or_404(
        purchase.product_id
    )

    batch = purchase.batch

    if batch:

        sold_from_batch = (batch.quantity_purchased or 0) - (batch.quantity_remaining or 0)

        if sold_from_batch <= 0:
            # Nothing has been sold from this batch yet -- safe to remove it
            db.session.delete(batch)
        else:
            # Some units were already sold; keep the batch (sale history
            # still points to it) but it can no longer be sold from.
            batch.quantity_remaining = 0

    db.session.delete(purchase)

    db.session.flush()

    recompute_product_stock(medicine)

    db.session.commit()

    flash(
        "Medicine Purchase Deleted Successfully",
        "success"
    )

    return redirect(
        url_for("purchases")
    )
# ==========================================================
# PURCHASE DETAILS
# ==========================================================

@app.route("/purchase/<int:id>")
@login_required
def purchase_details(id):

    purchase = Purchase.query.get_or_404(id)

    return render_template(
        "purchase_details.html",
        purchase=purchase,
        today=date.today()
    )
# ==========================================================
# SEARCH PURCHASES
# ==========================================================

@app.route("/search_purchases")
@login_required
def search_purchases():

    keyword = request.args.get(
        "q",
        ""
    ).strip()

    purchase_list = Purchase.query.join(Product).filter(

        db.or_(

            Product.name.contains(keyword),

            Product.code.contains(keyword),

            Product.batch_no.contains(keyword),

            Product.brand.contains(keyword)

        )

    ).order_by(
        Purchase.purchase_date.desc()
    ).all()

    return render_template(

        "purchases.html",

        purchases=purchase_list,

        suppliers=Supplier.query.all(),

        products=Product.query.all(),

        search=keyword,

        today=date.today(),

        warning_date=date.today() + timedelta(days=30)

    )
# ==========================================================
# MEDICINE SALES (POS)
# ==========================================================

@app.route("/pos")
@login_required
def pos():

    medicines = Product.query.order_by(
        Product.name.asc()
    ).all()

    today = date.today()

    return render_template(

        "pos.html",

        products=medicines,

        today=today,

        settings=get_settings()

    )


def _batch_json(batch, expiry_warning=False):

    return {

        "success": True,

        "batch_id": batch.id,

        "product_id": batch.product_id,

        "name": batch.product.name if batch.product else "Unknown Medicine",

        "brand": batch.product.brand if batch.product else "",

        "batch_no": batch.batch_no,

        "barcode": batch.barcode,

        "expiry_date": batch.expiry_date.strftime("%Y-%m-%d") if batch.expiry_date else None,

        "expiry_display": batch.expiry_date.strftime("%d-%m-%Y") if batch.expiry_date else "No Expiry",

        "price": batch.selling_price or 0,

        "stock": batch.quantity_remaining,

        "expiry_warning": expiry_warning

    }


# ==========================================================
# BARCODE SCANNER SUPPORT
# Scanning (or manually typing) a barcode returns the exact
# purchased batch so it can be added to the billing cart.
# ==========================================================

@app.route("/api/scan_barcode")
@login_required
def api_scan_barcode():

    barcode = request.args.get("barcode", "").strip()

    if not barcode:
        return jsonify({"success": False, "message": "No barcode provided"})

    batch = Batch.query.filter_by(barcode=barcode).first()

    if not batch:
        return jsonify({"success": False, "message": "Barcode not found"})

    if batch.is_expired:
        return jsonify({
            "success": False,
            "message": f"{batch.product.name if batch.product else 'Medicine'} "
                       f"(Batch {batch.batch_no}) is expired and cannot be sold."
        })

    if batch.quantity_remaining <= 0:
        return jsonify({
            "success": False,
            "message": f"{batch.product.name if batch.product else 'Medicine'} "
                       f"(Batch {batch.batch_no}) is out of stock."
        })

    warn = batch.days_to_expiry is not None and batch.days_to_expiry <= 30

    return jsonify(_batch_json(batch, expiry_warning=warn))


# ==========================================================
# FEFO MEDICINE SEARCH (search by name -> nearest-expiry batch)
# ==========================================================

@app.route("/api/search_medicine")
@login_required
def api_search_medicine():

    keyword = request.args.get("q", "").strip()

    if not keyword:
        return jsonify({"success": False, "message": "Enter a search term", "results": []})

    products = Product.query.filter(

        db.or_(
            Product.name.contains(keyword),
            Product.code.contains(keyword),
            Product.brand.contains(keyword),
            Product.category.contains(keyword)
        )

    ).order_by(Product.name.asc()).limit(25).all()

    results = []

    for product in products:

        batch = get_fefo_batch(product.id)

        if not batch:
            continue

        warn = batch.days_to_expiry is not None and batch.days_to_expiry <= 30

        entry = _batch_json(batch, expiry_warning=warn)

        results.append(entry)

    return jsonify({"success": True, "results": results})


@app.route("/api/product_batch/<int:product_id>")
@login_required
def api_product_batch(product_id):

    product = Product.query.get(product_id)

    if not product:
        return jsonify({"success": False, "message": "Medicine not found"})

    batch = get_fefo_batch(product_id)

    if not batch:
        return jsonify({
            "success": False,
            "message": f"No available (in-stock, non-expired) batch found for {product.name}."
        })

    warn = batch.days_to_expiry is not None and batch.days_to_expiry <= 30

    return jsonify(_batch_json(batch, expiry_warning=warn))

# ==========================================================
# ADD SALE
# ==========================================================

@app.route("/create_sale", methods=["POST"])
@login_required
def create_sale():

    customer_name = request.form.get(
        "customer_name"
    )

    customer_phone = request.form.get(
        "customer_phone"
    )

    customer = None

    if customer_phone:

        customer = Customer.query.filter_by(
            phone=customer_phone
        ).first()

    if not customer and customer_name:

        customer = Customer(

            name=customer_name,

            phone=customer_phone,

            email=""

        )

        db.session.add(customer)

        db.session.commit()

    discount = float(
        request.form.get("discount", 0)
    )

    tax_percent = float(
        request.form.get("tax", 0)
    )

    payment_method = request.form.get(
        "payment_method"
    )

    product_ids = request.form.getlist(
        "product_id[]"
    )

    batch_ids = request.form.getlist(
        "batch_id[]"
    )

    quantities = request.form.getlist(
        "quantity[]"
    )

    subtotal = 0

    today = date.today()

    line_items = []

    # ===========================================
    # RESOLVE EACH CART LINE TO AN EXACT BATCH
    # (barcode-scanned lines already carry a batch_id;
    #  if one is missing, fall back to FEFO by product)
    # ===========================================

    for i in range(len(product_ids)):

        qty = int(quantities[i])

        batch = None

        if i < len(batch_ids) and batch_ids[i]:
            batch = Batch.query.get(int(batch_ids[i]))

        if batch is None:
            batch = get_fefo_batch(int(product_ids[i]))

        if batch is None:

            medicine = Product.query.get_or_404(int(product_ids[i]))

            flash(
                f"No available (non-expired, in-stock) batch found for {medicine.name}.",
                "danger"
            )

            return redirect(url_for("pos"))

        medicine = batch.product

        # -------------------------
        # Expired Batch
        # -------------------------

        if batch.is_expired:

            flash(
                f"{medicine.name} (Batch {batch.batch_no}) is expired and cannot be sold.",
                "danger"
            )

            return redirect(url_for("pos"))

        # -------------------------
        # Expiring Soon Warning
        # -------------------------

        elif batch.days_to_expiry is not None and batch.days_to_expiry <= 30:

            flash(
                f"Warning: {medicine.name} (Batch {batch.batch_no}) will expire on {batch.expiry_date}.",
                "warning"
            )

        # -------------------------
        # Stock Checking (this batch only)
        # -------------------------

        if qty > batch.quantity_remaining:

            flash(
                f"Only {batch.quantity_remaining} unit(s) available for {medicine.name} "
                f"(Batch {batch.batch_no}).",
                "danger"
            )

            return redirect(url_for("pos"))

        price = batch.selling_price or medicine.price or 0

        subtotal += price * qty

        line_items.append((batch, qty, price))

    # ===========================================
    # DISCOUNT
    # ===========================================

    subtotal_after_discount = subtotal - discount

    # ===========================================
    # GST
    # ===========================================

    tax_amount = (
        subtotal_after_discount
        * tax_percent
        / 100
    )

    total = (
        subtotal_after_discount
        + tax_amount
    )

    # ===========================================
    # SAVE SALE
    # ===========================================

    sale = Sale(

        customer_id=customer.id
        if customer else None,

        subtotal=subtotal,

        discount=discount,

        tax=tax_amount,

        total=total,

        payment_method=payment_method

    )

    db.session.add(sale)

    db.session.commit()

    # ===========================================
    # SAVE SALE ITEMS -- reduce stock from the
    # EXACT batch sold, never from a merged total
    # ===========================================

    touched_products = {}

    for batch, qty, price in line_items:

        sale_item = SaleItem(

            sale_id=sale.id,

            product_id=batch.product_id,

            batch_id=batch.id,

            quantity=qty,

            price=price

        )

        db.session.add(sale_item)

        batch.quantity_remaining -= qty

        touched_products[batch.product_id] = batch.product

    for product in touched_products.values():
        recompute_product_stock(product)

    db.session.commit()

    flash(

        "Medicine Sale Completed Successfully",

        "success"

    )

    return redirect(

        url_for(

            "invoice",

            sale_id=sale.id

        )

    )
# ==========================================================
# MEDICINE SALES HISTORY
# ==========================================================

@app.route("/sales_history")
@login_required
def sales_history():

    sales = Sale.query.order_by(
        Sale.date.desc()
    ).all()

    return render_template(

        "sales_history.html",

        sales=sales,

        today=date.today()

    )
# ==========================================================
# SALE DETAILS
# ==========================================================

@app.route("/sale/<int:id>")
@login_required
def sale_details(id):

    sale = Sale.query.get_or_404(id)

    items = SaleItem.query.filter_by(
        sale_id=id
    ).all()

    customer = None

    if sale.customer_id:

        customer = Customer.query.get(
            sale.customer_id
        )

    total_items = sum(
        item.quantity
        for item in items
    )

    return render_template(

        "sale_details.html",

        sale=sale,

        items=items,

        customer=customer,

        total_items=total_items,

        today=date.today()

    )
# ==========================================================
# MEDICINE INVOICE
# ==========================================================

@app.route("/invoice/<int:sale_id>")
@login_required
def invoice(sale_id):

    sale = Sale.query.get_or_404(
        sale_id
    )

    items = SaleItem.query.filter_by(
        sale_id=sale.id
    ).all()

    customer = None

    if sale.customer_id:

        customer = Customer.query.get(
            sale.customer_id
        )

    return render_template(

        "invoice.html",

        sale=sale,

        items=items,

        customer=customer,

        settings=get_settings(),

        today=date.today()

    )
# ==========================================================
# SHOP SETTINGS PAGE
# ==========================================================

@app.route("/settings", methods=["GET", "POST"])
@login_required
def settings():

    shop_settings = get_settings()

    if request.method == "POST":

        shop_settings.shop_name = request.form.get(
            "shop_name", shop_settings.shop_name
        ).strip()

        shop_settings.phone_number = request.form.get(
            "phone_number", ""
        ).strip()

        shop_settings.upi_id = request.form.get(
            "upi_id", ""
        ).strip()

        shop_settings.thank_you_message = request.form.get(
            "thank_you_message", ""
        ).strip() or shop_settings.thank_you_message

        db.session.commit()

        flash(
            "Settings Updated Successfully",
            "success"
        )

        return redirect(
            url_for("settings")
        )

    return render_template(
        "settings.html",
        settings=shop_settings
    )

# ==========================================================
# MEDICINE REPORTS
# ==========================================================

@app.route("/reports")
@login_required
def reports():

    today = date.today()

    # ------------------------------------------
    # Dashboard Statistics
    # ------------------------------------------

    total_products = Product.query.count()

    total_patients = Customer.query.count()

    total_suppliers = Supplier.query.count()

    total_sales = Sale.query.count()

    # ------------------------------------------
    # Revenue
    # ------------------------------------------

    revenue = db.session.query(
        func.sum(Sale.total)
    ).scalar() or 0

    # ------------------------------------------
    # Inventory Value
    # ------------------------------------------

    inventory_value = db.session.query(
        func.sum(Product.price * Product.stock)
    ).scalar() or 0

    # ------------------------------------------
    # Low Stock Medicines
    # ------------------------------------------

    low_stock_products = Product.query.filter(
        Product.stock <= 5
    ).order_by(
        Product.stock.asc()
    ).all()

    # ------------------------------------------
    # Expired Medicines
    # ------------------------------------------

    expired_products = Product.query.filter(
        Product.expiry_date != None,
        Product.expiry_date < today
    ).order_by(
        Product.expiry_date.asc()
    ).all()

    expired_count = len(expired_products)

    # ------------------------------------------
    # Expiring Within 30 Days
    # ------------------------------------------

    expiring_products = Product.query.filter(
        Product.expiry_date != None,
        Product.expiry_date >= today,
        Product.expiry_date <= today + timedelta(days=30)
    ).order_by(
        Product.expiry_date.asc()
    ).all()

    expiring_count = len(expiring_products)

    # ------------------------------------------
    # Safe Medicines
    # ------------------------------------------

    safe_count = Product.query.filter(
        Product.expiry_date != None,
        Product.expiry_date > today + timedelta(days=30)
    ).count()

    # ------------------------------------------
    # Actual Sales Graph
    # ------------------------------------------

    sales_data = (

        db.session.query(

            func.date(Sale.date).label("sale_date"),

            func.sum(Sale.total).label("amount")

        )

        .group_by(
            func.date(Sale.date)
        )

        .order_by(
            func.date(Sale.date)
        )

        .all()

    )

    chart_labels = []

    chart_data = []

    for row in sales_data:

        if isinstance(row.sale_date, str):

            chart_labels.append(
                row.sale_date
            )

        else:

            chart_labels.append(
                row.sale_date.strftime("%d-%m-%Y")
            )

        chart_data.append(
            float(row.amount)
        )

    # ------------------------------------------
    # Monthly Sales Graph (last 6 months, real data)
    # ------------------------------------------

    def _shift_month_start(base_start, offset):
        year = base_start.year
        month = base_start.month + offset
        while month < 1:
            month += 12
            year -= 1
        while month > 12:
            month -= 12
            year += 1
        return base_start.replace(year=year, month=month, day=1)

    current_month_start = today.replace(day=1)

    monthly_labels = []
    monthly_values = []

    for i in range(5, -1, -1):
        month_start = _shift_month_start(current_month_start, -i)
        next_month_start = _shift_month_start(current_month_start, -i + 1)

        month_total = db.session.query(
            func.sum(Sale.total)
        ).filter(
            Sale.date >= month_start,
            Sale.date < next_month_start
        ).scalar() or 0

        monthly_labels.append(month_start.strftime("%b %Y"))
        monthly_values.append(round(float(month_total), 2))

    # ------------------------------------------
    # Top Selling Products
    # ------------------------------------------

    top_products = (

        db.session.query(

            Product.name.label("name"),

            func.sum(SaleItem.quantity).label("quantity_sold")

        )

        .join(
            SaleItem,
            SaleItem.product_id == Product.id
        )

        .group_by(
            Product.id
        )

        .order_by(
            func.sum(SaleItem.quantity).desc()
        )

        .limit(5)

        .all()

    )

    # ------------------------------------------
    # Recent Sales
    # ------------------------------------------

    recent_sales = Sale.query.order_by(
        Sale.date.desc()
    ).limit(10).all()

    return render_template(

        "reports.html",

        revenue=revenue,

        inventory_value=inventory_value,

        total_products=total_products,

        total_patients=total_patients,

        total_suppliers=total_suppliers,

        total_sales=total_sales,

        low_stock_products=low_stock_products,

        expired_products=expired_products,

        expiring_products=expiring_products,

        expired_count=expired_count,

        expiring_count=expiring_count,

        safe_count=safe_count,

        sales_labels=chart_labels,

        sales_values=chart_data,

        monthly_labels=monthly_labels,

        monthly_values=monthly_values,

        top_products=top_products,

        recent_sales=recent_sales

    )
# ==========================================================
# DAILY SALES REPORT
# ==========================================================

@app.route("/reports/daily")
@login_required
def daily_report():

    today = date.today()

    sales = Sale.query.filter(
        func.date(Sale.date) == today
    ).order_by(
        Sale.date.desc()
    ).all()

    total_sales = sum(
        sale.total
        for sale in sales
    )

    total_orders = len(sales)

    return render_template(

        "daily_report.html",

        sales=sales,

        total_sales=total_sales,

        total_orders=total_orders,

        report_date=today

    )
# ==========================================================
# LOW STOCK MEDICINES REPORT
# ==========================================================

@app.route("/reports/low-stock")
@login_required
def low_stock_report():

    medicines = Product.query.filter(
        Product.stock <= 5
    ).order_by(
        Product.stock.asc()
    ).all()

    return render_template(

        "low_stock_report.html",

        products=medicines,

        today=date.today()

    )
# ==========================================================
# MEDICINE EXPIRY REPORT
# ==========================================================

@app.route("/reports/expiry")
@login_required
def expiry_report():

    today = date.today()

    expired = Product.query.filter(

        Product.expiry_date != None,

        Product.expiry_date < today

    ).order_by(

        Product.expiry_date.asc()

    ).all()

    expiring = Product.query.filter(

        Product.expiry_date != None,

        Product.expiry_date >= today,

        Product.expiry_date <= today + timedelta(days=30)

    ).order_by(

        Product.expiry_date.asc()

    ).all()

    safe = Product.query.filter(

        Product.expiry_date != None,

        Product.expiry_date > today + timedelta(days=30)

    ).order_by(

        Product.expiry_date.asc()

    ).all()

    return render_template(

        "expiry_report.html",

        expired=expired,

        expiring=expiring,

        safe=safe,

        today=today

    )
# ==========================================================
# SUPPLIERS
# ==========================================================

@app.route("/suppliers")
@login_required
def suppliers():

    search = request.args.get("q", "").strip()

    query = Supplier.query

    if search:

        query = query.filter(

            db.or_(

                Supplier.name.contains(search),

                Supplier.phone.contains(search),

                Supplier.email.contains(search)

            )

        )

    supplier_list = query.order_by(
        Supplier.name.asc()
    ).all()

    return render_template(

        "suppliers.html",

        suppliers=supplier_list,

        search=search

    )
# ==========================================================
# ADD SUPPLIER
# ==========================================================

@app.route("/add_supplier", methods=["GET", "POST"])
@login_required
def add_supplier():

    if request.method == "POST":

        supplier = Supplier(

            name=request.form["name"],

            phone=request.form["phone"],

            email=request.form["email"],

            address=request.form["address"]

        )

        db.session.add(supplier)

        db.session.commit()

        flash(
            "Supplier Added Successfully",
            "success"
        )

        return redirect(
            url_for("suppliers")
        )

    return render_template(
        "add_supplier.html"
    )
# ==========================================================
# EDIT SUPPLIER
# ==========================================================

@app.route("/edit_supplier/<int:id>", methods=["GET", "POST"])
@login_required
def edit_supplier(id):

    supplier = Supplier.query.get_or_404(id)

    if request.method == "POST":

        supplier.name = request.form["name"]

        supplier.phone = request.form["phone"]

        supplier.email = request.form["email"]

        supplier.address = request.form["address"]

        db.session.commit()

        flash(
            "Supplier Updated Successfully",
            "success"
        )

        return redirect(
            url_for("suppliers")
        )

    return render_template(

        "edit_supplier.html",

        supplier=supplier

    )
# ==========================================================
# DELETE SUPPLIER
# ==========================================================

@app.route("/delete_supplier/<int:id>")
@login_required
def delete_supplier(id):

    supplier = Supplier.query.get_or_404(id)

    db.session.delete(supplier)

    db.session.commit()

    flash(
        "Supplier Deleted Successfully",
        "success"
    )

    return redirect(
        url_for("suppliers")
    )
# ==========================================================
# SUPPLIER DETAILS
# ==========================================================

@app.route("/supplier/<int:id>")
@login_required
def supplier_details(id):

    supplier = Supplier.query.get_or_404(id)

    purchases = Purchase.query.filter_by(
        supplier_id=id
    ).order_by(
        Purchase.purchase_date.desc()
    ).all()

    total_purchase = sum(
        purchase.cost
        for purchase in purchases
    )

    return render_template(

        "supplier_details.html",

        supplier=supplier,

        purchases=purchases,

        total_purchase=total_purchase

    )
# ==========================================================
# SEARCH SUPPLIERS
# ==========================================================

@app.route("/search_suppliers")
@login_required
def search_suppliers():

    keyword = request.args.get("q", "").strip()

    suppliers = Supplier.query.filter(

        db.or_(

            Supplier.name.contains(keyword),

            Supplier.phone.contains(keyword),

            Supplier.email.contains(keyword)

        )

    ).order_by(
        Supplier.name.asc()
    ).all()

    return render_template(

        "suppliers.html",

        suppliers=suppliers,

        search=keyword

    )

# ==========================================================
# CUSTOMERS
# ==========================================================

@app.route("/customers")
@login_required
def customers():

    search = request.args.get("q", "").strip()

    query = Customer.query

    if search:

        query = query.filter(

            db.or_(

                Customer.name.contains(search),

                Customer.phone.contains(search),

                Customer.email.contains(search)

            )

        )

    customer_list = query.order_by(
        Customer.name.asc()
    ).all()

    return render_template(

        "customers.html",

        customers=customer_list,

        search=search

    )
# ==========================================================
# ADD CUSTOMER
# ==========================================================

@app.route("/add_customer", methods=["GET", "POST"])
@login_required
def add_customer():

    if request.method == "POST":

        customer = Customer(

            name=request.form["name"],

            phone=request.form["phone"],

            email=request.form.get("email"),

            address=request.form.get("address")

        )

        db.session.add(customer)

        db.session.commit()

        flash(
            "Customer Added Successfully",
            "success"
        )

        return redirect(
            url_for("customers")
        )

    return render_template(
        "add_customer.html"
    )
# ==========================================================
# EDIT CUSTOMER
# ==========================================================

@app.route("/edit_customer/<int:id>", methods=["GET", "POST"])
@login_required
def edit_customer(id):

    customer = Customer.query.get_or_404(id)

    if request.method == "POST":

        customer.name = request.form["name"]

        customer.phone = request.form["phone"]

        customer.email = request.form.get("email")

        customer.address = request.form.get("address")

        db.session.commit()

        flash(
            "Customer Updated Successfully",
            "success"
        )

        return redirect(
            url_for("customers")
        )

    return render_template(

        "edit_customer.html",

        customer=customer

    )
# ==========================================================
# DELETE CUSTOMER
# ==========================================================

@app.route("/delete_customer/<int:id>")
@login_required
def delete_customer(id):

    customer = Customer.query.get_or_404(id)

    db.session.delete(customer)

    db.session.commit()

    flash(
        "Customer Deleted Successfully",
        "success"
    )

    return redirect(
        url_for("customers")
    )
# ==========================================================
# CUSTOMER DETAILS
# ==========================================================

@app.route("/customer/<int:id>")
@login_required
def customer_details(id):

    customer = Customer.query.get_or_404(id)

    sales = Sale.query.filter_by(
        customer_id=id
    ).order_by(
        Sale.date.desc()
    ).all()

    return render_template(

        "customer_details.html",

        customer=customer,

        sales=sales

    )
# ==========================================================
# EXPIRY ALERTS
# ==========================================================

@app.route("/expiry_alerts")
@login_required
def expiry_alerts():

    return render_template(

        "expiry_alerts.html",

        expired=expired_batches(),

        within_30=expiring_batches(None, 30),

        within_60=expiring_batches(31, 60),

        within_90=expiring_batches(61, 90),

        within_180=expiring_batches(91, 180),

        today=date.today()

    )

# ==========================================================
# JINJA FILTER
# ==========================================================

@app.template_filter("days_left")
def days_left_filter(value):

    if value is None:

        return "-"

    days = (
        value - date.today()
    ).days

    if days < 0:

        return f"{abs(days)} Days Ago"

    elif days == 0:

        return "Today"

    return f"{days} Days Left"


# ==========================================================
# START FLASK SERVER
# ==========================================================

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
       