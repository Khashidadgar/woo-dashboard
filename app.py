from flask import Flask, render_template, request, jsonify, redirect, url_for, session
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
import bcrypt
import smtplib
from email.mime.text import MIMEText
import random
import string
from dotenv import load_dotenv
import os
import requests
import traceback
import logging

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

app = Flask(__name__, static_folder='static', static_url_path='/static')
load_dotenv()
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY')
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///users.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'index'

EMAIL_USER = os.getenv('EMAIL_USER')
EMAIL_PASSWORD = os.getenv('EMAIL_PASSWORD')

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password = db.Column(db.String(120), nullable=False)
    is_verified = db.Column(db.Boolean, default=False)
    verification_code = db.Column(db.String(6), nullable=True)
    sites = db.relationship('Site', backref='user', lazy=True)

class Site(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    url = db.Column(db.String(200), nullable=False)
    consumer_key = db.Column(db.String(100), nullable=False)
    consumer_secret = db.Column(db.String(100), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    preferences = db.relationship('SitePreferences', backref='site', uselist=False)

class SitePreferences(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    site_id = db.Column(db.Integer, db.ForeignKey('site.id'), nullable=False)
    visible_columns = db.Column(db.String(500), nullable=False, default='id,title,regular_price,sale_price,manage_stock,stock_quantity,categories,status,short_description,description')

@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))

@app.route('/')
def index():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    return render_template('index.html')

@app.route('/login', methods=['POST'])
def login():
    try:
        email = request.form['email']
        password = request.form['password']
        user = User.query.filter_by(email=email).first()
        if user and bcrypt.checkpw(password.encode('utf-8'), user.password):
            if user.is_verified:
                login_user(user)
                return jsonify({'success': True, 'redirect': url_for('dashboard')})
            else:
                return jsonify({'success': False, 'error': 'حساب شما تأیید نشده است. لطفاً ایمیل خود را بررسی کنید.'})
        return jsonify({'success': False, 'error': 'ایمیل یا رمز عبور اشتباه است'})
    except Exception as e:
        logger.error(f"Login error: {str(e)}")
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)})

@app.route('/register', methods=['POST'])
def register():
    try:
        email = request.form['email']
        password = request.form['password']
        if User.query.filter_by(email=email).first():
            return jsonify({'success': False, 'error': 'این ایمیل قبلاً ثبت شده است'})
        verification_code = ''.join(random.choices(string.digits, k=6))
        hashed_password = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())
        user = User(email=email, password=hashed_password, verification_code=verification_code)
        db.session.add(user)
        db.session.commit()
        msg = MIMEText(f'کد تأیید شما: {verification_code}')
        msg['Subject'] = 'کد تأیید ثبت‌نام'
        msg['From'] = EMAIL_USER
        msg['To'] = email
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
            server.login(EMAIL_USER, EMAIL_PASSWORD)
            server.sendmail(EMAIL_USER, email, msg.as_string())
        return jsonify({'success': True, 'message': 'لطفاً کد تأیید ارسال‌شده به ایمیل خود را وارد کنید'})
    except Exception as e:
        logger.error(f"Register error: {str(e)}")
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)})

@app.route('/verify', methods=['POST'])
def verify():
    try:
        email = request.form['email']
        code = request.form['code']
        user = User.query.filter_by(email=email, verification_code=code).first()
        if user:
            user.is_verified = True
            user.verification_code = None
            db.session.commit()
            login_user(user)
            return jsonify({'success': True, 'redirect': url_for('dashboard')})
        return jsonify({'success': False, 'error': 'کد تأیید اشتباه است'})
    except Exception as e:
        logger.error(f"Verify error: {str(e)}")
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)})

@app.route('/dashboard')
@login_required
def dashboard():
    sites = Site.query.filter_by(user_id=current_user.id).all()
    return render_template('dashboard.html', sites=sites)

@app.route('/add_site', methods=['GET', 'POST'])
@login_required
def add_site():
    if request.method == 'POST':
        try:
            name = request.form['name']
            url = request.form['url'].rstrip('/')
            consumer_key = request.form['consumer_key']
            consumer_secret = request.form['consumer_secret']
            headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}
            logger.debug(f"Testing API with URL: {url}, Key: {consumer_key[:4]}..., Secret: {consumer_secret[:4]}...")
            response = requests.get(f'{url}/wp-json/wc/v3/products', auth=(consumer_key, consumer_secret), headers=headers)
            logger.debug(f"API response status: {response.status_code}, content: {response.text[:200]}")
            if response.status_code == 200:
                site = Site(name=name, url=url, consumer_key=consumer_key, consumer_secret=consumer_secret, user_id=current_user.id)
                db.session.add(site)
                db.session.commit()
                return jsonify({'success': True, 'redirect': url_for('dashboard')})
            else:
                return jsonify({'success': False, 'error': f'کلیدهای API نامعتبر هستند یا سایت WooCommerce در دسترس نیست. کد: {response.status_code}, پیام: {response.text[:200]}'})
        except Exception as e:
            logger.error(f"Add site error: {str(e)}")
            traceback.print_exc()
            return jsonify({'success': False, 'error': str(e)})
    return render_template('add_site.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('index'))

@app.route('/api/sites/<int:site_id>/products', methods=['GET'])
@login_required
def get_products(site_id):
    try:
        site = Site.query.filter_by(id=site_id, user_id=current_user.id).first()
        if not site:
            return jsonify({'error': 'سایت یافت نشد یا متعلق به شما نیست'}), 404
        preferences = SitePreferences.query.filter_by(site_id=site_id).first()
        fields = preferences.visible_columns.split(',') if preferences else ['id', 'name', 'regular_price', 'sale_price', 'manage_stock', 'stock_quantity', 'categories', 'status', 'short_description', 'description']
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}
        params = {'per_page': 100}  # هر بار 100 محصول می‌گیریم تا همه محصولات لود بشن
        all_products = []
        page = 1
        while True:
            params['page'] = page
            logger.debug(f"Sending request to {site.url}/wp-json/wc/v3/products with params: {params}, headers: {headers}")
            response = requests.get(f'{site.url}/wp-json/wc/v3/products', auth=(site.consumer_key, site.consumer_secret), params=params, headers=headers)
            logger.debug(f"Products response status: {response.status_code}, content: {response.text[:200]}")
            if response.status_code != 200:
                return jsonify({'error': f'خطا در دریافت محصولات: {response.text}'}), response.status_code
            products = response.json()
            if not products:
                break
            all_products.extend(products)
            page += 1
        filtered_products = []
        for product in all_products:
            filtered_product = {}
            for field in fields:
                if field == 'title':
                    filtered_product[field] = product.get('name', '')
                else:
                    filtered_product[field] = product.get(field)
            filtered_products.append(filtered_product)
        return jsonify({'products': filtered_products})
    except Exception as e:
        logger.error(f"Get products error: {str(e)}")
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@app.route('/api/sites/<int:site_id>/products/<int:product_id>', methods=['PUT'])
@login_required
def update_product(site_id, product_id):
    try:
        site = Site.query.filter_by(id=site_id, user_id=current_user.id).first()
        if not site:
            return jsonify({'error': 'سایت یافت نشد یا متعلق به شما نیست'}), 404
        data = request.get_json()
        if 'title' in data:
            data['name'] = data.pop('title')
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}
        logger.debug(f"Updating product {product_id} with data: {data}")
        response = requests.put(f'{site.url}/wp-json/wc/v3/products/{product_id}', auth=(site.consumer_key, site.consumer_secret), json=data, headers=headers)
        logger.debug(f"Update product response status: {response.status_code}, content: {response.text[:200]}")
        if response.status_code == 200:
            return jsonify(response.json())
        return jsonify({'error': f'خطا در به‌روزرسانی محصول: {response.text}'}), response.status_code
    except Exception as e:
        logger.error(f"Update product error: {str(e)}")
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@app.route('/api/sites/<int:site_id>/categories', methods=['GET'])
@login_required
def get_categories(site_id):
    try:
        site = Site.query.filter_by(id=site_id, user_id=current_user.id).first()
        if not site:
            return jsonify({'error': 'سایت یافت نشد یا متعلق به شما نیست'}), 404
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}
        logger.debug(f"Sending request to {site.url}/wp-json/wc/v3/products/categories with headers: {headers}")
        response = requests.get(f'{site.url}/wp-json/wc/v3/products/categories', auth=(site.consumer_key, site.consumer_secret), params={'per_page': 100}, headers=headers)
        logger.debug(f"Categories response status: {response.status_code}, content: {response.text[:200]}")
        if response.status_code == 200:
            return jsonify(response.json())
        return jsonify({'error': f'خطا در دریافت دسته‌بندی‌ها: {response.text}'}), response.status_code
    except Exception as e:
        logger.error(f"Get categories error: {str(e)}")
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@app.route('/api/sites/<int:site_id>/preferences', methods=['GET'])
@login_required
def get_site_preferences(site_id):
    try:
        site = Site.query.filter_by(id=site_id, user_id=current_user.id).first()
        if not site:
            return jsonify({'error': 'سایت یافت نشد یا متعلق به شما نیست'}), 404
        preferences = SitePreferences.query.filter_by(site_id=site_id).first()
        if not preferences:
            preferences = SitePreferences(site_id=site_id, visible_columns='id,title,regular_price,sale_price,manage_stock,stock_quantity,categories,status,short_description,description')
            db.session.add(preferences)
            db.session.commit()
        return jsonify({'visible_columns': preferences.visible_columns.split(',')})
    except Exception as e:
        logger.error(f"Get preferences error: {str(e)}")
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@app.route('/api/sites/<int:site_id>/preferences', methods=['PUT'])
@login_required
def update_site_preferences(site_id):
    try:
        site = Site.query.filter_by(id=site_id, user_id=current_user.id).first()
        if not site:
            return jsonify({'error': 'سایت یافت نشد یا متعلق به شما نیست'}), 404
        data = request.get_json()
        visible_columns = data.get('visible_columns', [])
        preferences = SitePreferences.query.filter_by(site_id=site_id).first()
        if not preferences:
            preferences = SitePreferences(site_id=site_id)
            db.session.add(preferences)
        preferences.visible_columns = ','.join(visible_columns)
        db.session.commit()
        return jsonify({'message': 'تنظیمات با موفقیت ذخیره شد'})
    except Exception as e:
        logger.error(f"Update preferences error: {str(e)}")
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@app.route('/sites/<int:site_id>/products')
@login_required
def products(site_id):
    site = Site.query.filter_by(id=site_id, user_id=current_user.id).first()
    if not site:
        return redirect(url_for('dashboard'))
    return render_template('products.html', site=site)

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True)