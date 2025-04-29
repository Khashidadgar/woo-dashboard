from flask import Flask, render_template, request, jsonify, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
import requests
import bcrypt

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-secret-key'  # برای امنیت سشن‌ها
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///users.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'index'

# مدل‌های دیتابیس
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password = db.Column(db.String(120), nullable=False)

class Site(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    woocommerce_url = db.Column(db.String(200), nullable=False)
    consumer_key = db.Column(db.String(200), nullable=False)
    consumer_secret = db.Column(db.String(200), nullable=False)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# تنظیمات ووکامرس
woocommerce_url = None
consumer_key = None
consumer_secret = None

def setup_woocommerce(url, key, secret):
    global woocommerce_url, consumer_key, consumer_secret
    woocommerce_url = url.rstrip('/')
    consumer_key = key
    consumer_secret = secret

def get_woocommerce_data(endpoint, params=None):
    if not woocommerce_url or not consumer_key or not consumer_secret:
        return None
    auth = (consumer_key, consumer_secret)
    url = f"{woocommerce_url}/wp-json/wc/v3/{endpoint}"
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }
    try:
        response = requests.get(url, auth=auth, params=params, headers=headers)
        response.raise_for_status()
        return response.json()
    except requests.RequestException as e:
        print(f"Error fetching {endpoint}: {e}")
        print(f"Response status: {response.status_code}")
        print(f"Response text: {response.text}")
        return None

def update_woocommerce_product(product_id, data):
    if not woocommerce_url or not consumer_key or not consumer_secret:
        return None
    auth = (consumer_key, consumer_secret)
    url = f"{woocommerce_url}/wp-json/wc/v3/products/{product_id}"
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }
    try:
        response = requests.put(url, auth=auth, json=data, headers=headers)
        response.raise_for_status()
        return response.json()
    except requests.RequestException as e:
        print(f"Error updating product {product_id}: {e}")
        print(f"Response status: {response.status_code}")
        print(f"Response text: {response.text}")
        return None

@app.route('/')
def index():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    return render_template('index.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        if User.query.filter_by(email=email).first():
            return jsonify({'status': 'error', 'message': 'ایمیل قبلاً ثبت شده است'})
        
        hashed_password = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())
        user = User(email=email, password=hashed_password)
        db.session.add(user)
        db.session.commit()
        login_user(user)
        return jsonify({'status': 'success'})
    return render_template('register.html')

@app.route('/login', methods=['POST'])
def login():
    email = request.form['email']
    password = request.form['password']
    user = User.query.filter_by(email=email).first()
    if user and bcrypt.checkpw(password.encode('utf-8'), user.password):
        login_user(user)
        return jsonify({'status': 'success'})
    return jsonify({'status': 'error', 'message': 'ایمیل یا کلمه عبور اشتباه است'})

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('index'))

@app.route('/dashboard')
@login_required
def dashboard():
    sites = Site.query.filter_by(user_id=current_user.id).all()
    return render_template('dashboard.html', sites=sites)

@app.route('/add_site', methods=['POST'])
@login_required
def add_site():
    woocommerce_url = request.form['woocommerce_url']
    consumer_key = request.form['consumer_key']
    consumer_secret = request.form['consumer_secret']
    site = Site(
        user_id=current_user.id,
        woocommerce_url=woocommerce_url,
        consumer_key=consumer_key,
        consumer_secret=consumer_secret
    )
    db.session.add(site)
    db.session.commit()
    return redirect(url_for('dashboard'))

@app.route('/select_site/<int:site_id>', methods=['POST'])
@login_required
def select_site(site_id):
    site = Site.query.filter_by(id=site_id, user_id=current_user.id).first()
    if site:
        setup_woocommerce(site.woocommerce_url, site.consumer_key, site.consumer_secret)
        return jsonify({'status': 'success'})
    return jsonify({'status': 'error', 'message': 'سایت یافت نشد'})

@app.route('/products', methods=['GET'])
@login_required
def products():
    if not woocommerce_url or not consumer_key or not consumer_secret:
        return redirect(url_for('dashboard'))

    products_data = get_woocommerce_data('products', params={'per_page': 100})
    categories_data = get_woocommerce_data('products/categories', params={'per_page': 100})
    
    if products_data is None or categories_data is None:
        return "Error fetching data from WooCommerce", 500
    
    return render_template('products.html', products=products_data, categories=categories_data)

@app.route('/get_product/<product_id>', methods=['GET'])
@login_required
def get_product(product_id):
    product_data = get_woocommerce_data(f'products/{product_id}')
    if product_data:
        print(f"Product {product_id} data: {product_data.get('images', [])}")
        return jsonify(product_data)
    print(f"Error fetching product {product_id}: Product not found")
    return jsonify({"error": "Product not found"}), 404

@app.route('/update_products', methods=['POST'])
@login_required
def update_products():
    updates = request.get_json()
    updated_products = []
    
    for update in updates:
        product_id = update['product_id']
        data = update['data']
        product_data = {}
        
        if 'regular_price' in data:
            product_data['regular_price'] = data['regular_price']
        if 'sale_price' in data:
            product_data['sale_price'] = data['sale_price']
        if 'manage_stock' in data:
            product_data['manage_stock'] = data['manage_stock'] == 'on'
        if 'stock_quantity' in data:
            product_data['stock_quantity'] = int(data['stock_quantity']) if data['stock_quantity'] else None
        if 'short_description' in data:
            product_data['short_description'] = data['short_description']
        if 'description' in data:
            product_data['description'] = data['description']
        if 'categories' in data:
            product_data['categories'] = [{'id': int(cat_id)} for cat_id in data['categories']]
        if 'status' in data:
            product_data['status'] = data['status']
        
        if product_data:
            result = update_woocommerce_product(product_id, product_data)
            if result:
                updated_products.append(product_id)
    
    print(f"Updated Products: {updated_products}")
    return jsonify({"updated": updated_products})

@app.route('/update_product/<product_id>', methods=['POST'])
@login_required
def update_product(product_id):
    data = request.get_json()
    product_data = {}
    
    if 'regular_price' in data:
        product_data['regular_price'] = data['regular_price']
    if 'sale_price' in data:
        product_data['sale_price'] = data['sale_price']
    if 'manage_stock' in data:
        product_data['manage_stock'] = data['manage_stock'] == 'on'
    if 'stock_quantity' in data:
        product_data['stock_quantity'] = int(data['stock_quantity']) if data['stock_quantity'] else None
    if 'short_description' in data:
        product_data['short_description'] = data['short_description']
    if 'description' in data:
        product_data['description'] = data['description']
    if 'categories' in data:
        product_data['categories'] = [{'id': int(cat_id)} for cat_id in data['categories']]
    if 'status' in data:
        product_data['status'] = data['status']
    
    result = update_woocommerce_product(product_id, product_data)
    if result:
        return jsonify({"status": "success"})
    return jsonify({"error": "Failed to update product"}), 500

if __name__ == '__main__':
    with app.app_context():
        db.create_all()  # ایجاد دیتابیس و جداول
    app.run(debug=True)