from flask import Flask, jsonify, request
from flask_mail import Mail, Message
from flask_bcrypt import Bcrypt
from flask_jwt_extended import JWTManager, create_access_token, jwt_required, get_jwt_identity
from flask_mysqldb import MySQL
import time
from flask_cors import CORS
import os
import re
from datetime import datetime, timedelta
from dotenv import load_dotenv
from contextlib import contextmanager
import logging
from flask_jwt_extended import jwt_required, get_jwt_identity
from competitor_scraper import CompetitorScraper

# Initialize scraper
scraper = CompetitorScraper()

# Initialize Flask app
app = Flask(__name__)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

bcrypt = Bcrypt(app)
jwt = JWTManager(app)
load_dotenv()

CORS(app, origins=["http://localhost:3000"])

# Flask-Mail Configuration (keep for price alerts)
app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USERNAME'] = os.getenv('MAIL_USERNAME')
app.config['MAIL_PASSWORD'] = os.getenv('MAIL_PASSWORD')
app.config['MAIL_DEFAULT_SENDER'] = os.getenv('MAIL_USERNAME')

mail = Mail(app)

# MySQL configuration
app.config['MYSQL_HOST'] = os.getenv('MYSQL_HOST', 'localhost')
app.config['MYSQL_USER'] = os.getenv('MYSQL_USER', 'tracker_user')
app.config['MYSQL_PASSWORD'] = os.getenv('MYSQL_PASSWORD', 'password')
app.config['MYSQL_DB'] = os.getenv('MYSQL_DB', 'price_tracker')

mysql = MySQL(app)

# JWT secret key
app.config['JWT_SECRET_KEY'] = os.getenv('JWT_SECRET_KEY', 'fallback_default_key')

# Database connection context manager
@contextmanager
def get_db_cursor():
    cursor = None
    try:
        cursor = mysql.connection.cursor()
        yield cursor
        mysql.connection.commit()
    except Exception as e:
        mysql.connection.rollback()
        logger.error(f"Database error: {e}")
        raise e
    finally:
        if cursor:
            cursor.close()

# Simplified validation functions
def validate_password_strength(password):
    """Basic password validation"""
    errors = []
    
    if not password:
        errors.append("Password is required")
        return False, errors
    
    if len(password) < 6:
        errors.append("Password must be at least 6 characters long")
    
    return len(errors) == 0, errors

def validate_email(email):
    """Basic email validation"""
    if not email:
        return False
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return re.match(pattern, email) is not None

def validate_username(username):
    """Username validation"""
    if not username:
        return False, "Username is required"
    if len(username) < 3:
        return False, "Username must be at least 3 characters long"
    if len(username) > 50:
        return False, "Username must be less than 50 characters"
    return True, ""

# Simplified Register Route (No Email Verification)
@app.route('/register', methods=['POST'])
def register():
    try:
        data = request.get_json()
        if not data:
            return jsonify(message="No data provided"), 400
            
        username = data.get('username', '').strip()
        email = data.get('email', '').strip().lower()
        password = data.get('password', '')

        # Basic validation
        username_valid, username_error = validate_username(username)
        if not username_valid:
            return jsonify(message=username_error), 400

        if not email or not validate_email(email):
            return jsonify(message="Please provide a valid email address"), 400

        # Password validation
        is_valid, password_errors = validate_password_strength(password)
        if not is_valid:
            return jsonify(message="Password requirements not met", errors=password_errors), 400

        with get_db_cursor() as cursor:
            # Check if user already exists
            cursor.execute('SELECT id FROM users WHERE username = %s OR email = %s', (username, email))
            existing_user = cursor.fetchone()

            if existing_user:
                return jsonify(message="Username or email already exists"), 409

            # Hash password and create user (no email verification needed)
            hashed_password = bcrypt.generate_password_hash(password).decode('utf-8')

            cursor.execute('''
                INSERT INTO users (username, email, password, created_at, is_active) 
                VALUES (%s, %s, %s, NOW(), TRUE)
            ''', (username, email, hashed_password))

        logger.info(f"New user registered: {username}")
        return jsonify(message="Registration successful! You can now log in."), 201

    except Exception as e:
        logger.error(f"Registration error: {e}")
        return jsonify(message="Registration failed. Please try again."), 500

# Simplified Login Route (No Email Verification Check)
@app.route('/login', methods=['POST'])
def login():
    try:
        data = request.get_json()
        username = data.get('username', '').strip()
        password = data.get('password', '')

        if not username or not password:
            return jsonify(message="Username and password are required"), 400

        with get_db_cursor() as cursor:
            cursor.execute('''
                SELECT id, username, email, password, is_active 
                FROM users WHERE username = %s OR email = %s
            ''', (username, username))
            user = cursor.fetchone()

            if not user:
                return jsonify(message="Invalid credentials"), 401

            user_id, db_username, email, db_password, is_active = user

            # Check if account is active
            if not is_active:
                return jsonify(message="Account has been deactivated"), 403

            # Verify password
            if bcrypt.check_password_hash(db_password, password):
                # Update last login
                cursor.execute('UPDATE users SET last_login = NOW() WHERE id = %s', (user_id,))

                # Create JWT token
                access_token = create_access_token(
                    identity=str(user_id),
                    additional_claims={
                        'username': db_username,
                        'email': email
                    }
                )

                logger.info(f"User logged in: {db_username}")
                return jsonify(
                    access_token=access_token,
                    user={
                        'id': user_id,
                        'username': db_username,
                        'email': email
                    }
                ), 200
            else:
                return jsonify(message="Invalid credentials"), 401

    except Exception as e:
        logger.error(f"Login error: {e}")
        return jsonify(message="Login failed"), 500

# Profile Route
@app.route('/profile', methods=['GET'])
@jwt_required()
def profile():
    try:
        user_id = get_jwt_identity()

        with get_db_cursor() as cursor:
            cursor.execute('''
                SELECT username, email, created_at, last_login 
                FROM users WHERE id = %s
            ''', (user_id,))
            user = cursor.fetchone()

            if user:
                return jsonify({
                    'id': user_id,
                    'username': user[0],
                    'email': user[1],
                    'created_at': user[2].isoformat() if user[2] else None,
                    'last_login': user[3].isoformat() if user[3] else None
                }), 200
            else:
                return jsonify(message="User not found"), 404
    except Exception as e:
        logger.error(f"Error fetching profile: {e}")
        return jsonify(message="Error fetching profile"), 500

# Update profile route
@app.route('/profile', methods=['PUT'])
@jwt_required()
def update_profile():
    try:
        user_id = get_jwt_identity()
        data = request.get_json()
        
        username = data.get('username', '').strip()
        email = data.get('email', '').strip().lower()
        
        username_valid, username_error = validate_username(username)
        if not username_valid:
            return jsonify(message=username_error), 400
        
        if not email or not validate_email(email):
            return jsonify(message="Please provide a valid email address"), 400
        
        with get_db_cursor() as cursor:
            # Check if username/email already exists for other users
            cursor.execute('''
                SELECT id FROM users 
                WHERE (username = %s OR email = %s) AND id != %s
            ''', (username, email, user_id))
            
            if cursor.fetchone():
                return jsonify(message="Username or email already exists"), 409
            
            # Update user profile
            cursor.execute('''
                UPDATE users 
                SET username = %s, email = %s 
                WHERE id = %s
            ''', (username, email, user_id))
        
        return jsonify(message="Profile updated successfully"), 200
        
    except Exception as e:
        logger.error(f"Profile update error: {e}")
        return jsonify(message="Profile update failed"), 500

# Change password route
@app.route('/change-password', methods=['POST'])
@jwt_required()
def change_password():
    try:
        user_id = get_jwt_identity()
        data = request.get_json()
        
        current_password = data.get('currentPassword')
        new_password = data.get('newPassword')
        
        if not current_password or not new_password:
            return jsonify(message="Current and new passwords are required"), 400
        
        # Validate new password
        is_valid, password_errors = validate_password_strength(new_password)
        if not is_valid:
            return jsonify(message="Password requirements not met", errors=password_errors), 400
        
        with get_db_cursor() as cursor:
            cursor.execute('SELECT password FROM users WHERE id = %s', (user_id,))
            user = cursor.fetchone()
            
            if not user or not bcrypt.check_password_hash(user[0], current_password):
                return jsonify(message="Current password is incorrect"), 401
            
            # Update password
            hashed_password = bcrypt.generate_password_hash(new_password).decode('utf-8')
            cursor.execute('UPDATE users SET password = %s WHERE id = %s', (hashed_password, user_id))
        
        return jsonify(message="Password changed successfully"), 200
        
    except Exception as e:
        logger.error(f"Change password error: {e}")
        return jsonify(message="Password change failed"), 500

@app.route('/logout', methods=['POST'])
@jwt_required()
def logout():
    return jsonify(message="Logged out successfully"), 200

# Price Alert Routes
@app.route('/price-alert', methods=['POST'])
@jwt_required()
def set_price_alert():
    try:
        user_id = get_jwt_identity()
        data = request.get_json()
        product_id = data['productId']
        alert_price = data['alertPrice']

        with get_db_cursor() as cursor:
            cursor.execute('SELECT * FROM price_alerts WHERE user_id = %s AND product_id = %s', (user_id, product_id))
            existing_alert = cursor.fetchone()

            if existing_alert:
                cursor.execute('UPDATE price_alerts SET alert_price = %s WHERE user_id = %s AND product_id = %s',
                             (alert_price, user_id, product_id))
            else:
                cursor.execute('INSERT INTO price_alerts (user_id, product_id, alert_price) VALUES (%s, %s, %s)',
                             (user_id, product_id, alert_price))

        return jsonify(message="Price alert set successfully"), 200
    except Exception as e:
        logger.error(f"Price alert error: {e}")
        return jsonify(message="Failed to set price alert"), 500

@app.route('/price-alerts', methods=['GET'])
@jwt_required()
def get_price_alerts():
    try:
        user_id = get_jwt_identity()

        with get_db_cursor() as cursor:
            cursor.execute('''
                SELECT p.name, pa.alert_price
                FROM price_alerts pa
                JOIN product_details p ON pa.product_id = p.id
                WHERE pa.user_id = %s
            ''', (user_id,))
            alerts = cursor.fetchall()

        alert_list = [{'product_name': alert[0], 'alert_price': alert[1]} for alert in alerts]
        return jsonify(alerts=alert_list), 200
    except Exception as e:
        logger.error(f"Get price alerts error: {e}")
        return jsonify(message="Failed to fetch price alerts"), 500

@app.route('/check-price-alerts', methods=['GET'])
@jwt_required()
def check_price_alerts():
    try:
        user_id = get_jwt_identity()

        with get_db_cursor() as cursor:
            cursor.execute('''
                SELECT pa.id, p.name, pa.alert_price, p.price, u.email
                FROM price_alerts pa
                JOIN product_details p ON pa.product_id = p.id
                JOIN users u ON pa.user_id = u.id
                WHERE pa.user_id = %s
            ''', (user_id,))
            
            alerts = cursor.fetchall()

        triggered_alerts = []

        for alert in alerts:
            alert_id, product_name, alert_price, current_price, user_email = alert

            if current_price <= alert_price:
                triggered_alerts.append({
                    'product_name': product_name,
                    'alert_price': alert_price,
                    'current_price': current_price
                })

                send_price_drop_email(user_email, product_name, current_price, alert_price)

                with get_db_cursor() as cursor:
                    cursor.execute('UPDATE price_alerts SET triggered = TRUE WHERE id = %s', (alert_id,))

        return jsonify({'triggered_alerts': triggered_alerts}), 200
    except Exception as e:
        logger.error(f"Check price alerts error: {e}")
        return jsonify(message="Failed to check price alerts"), 500

def send_price_drop_email(user_email, product_name, current_price, alert_price):
    """Send price drop notification email"""
    try:
        subject = f"Price Alert: {product_name} price has dropped!"
        body = f"""
        Dear User,

        The price of {product_name} has dropped to Rs. {current_price}!

        You had set an alert for this product at Rs. {alert_price}, and the current price has now reached that threshold.

        Hurry, grab your deal now!

        Regards,
        PriceTracker Team
        """

        msg = Message(subject, recipients=[user_email], body=body)
        mail.send(msg)
        logger.info(f"Price drop email sent to {user_email}")
    except Exception as e:
        logger.error(f"Failed to send price drop email to {user_email}: {e}")

# Product Routes
@app.route('/products', methods=['GET'])
def get_products():
    try:
        search_query = request.args.get('search', '')
        category = request.args.get('category', 'All')
        min_price = request.args.get('minPrice', 0)
        max_price = request.args.get('maxPrice', 1000000)
        
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('limit', 10, type=int)

        offset = (page - 1) * per_page

        with get_db_cursor() as cursor:
            query = "SELECT * FROM product_details WHERE 1=1"
            params = []

            if search_query:
                query += " AND name LIKE %s"
                params.append(f"%{search_query}%")

            if category != 'All':
                query += " AND category = %s"
                params.append(category)

            if min_price and max_price:
                query += " AND price BETWEEN %s AND %s"
                params.append(min_price)
                params.append(max_price)

            query += " LIMIT %s OFFSET %s"
            params.extend([per_page, offset])

            cursor.execute(query, tuple(params))
            products = cursor.fetchall()

            cursor.execute("SELECT COUNT(*) FROM product_details")
            total_products = cursor.fetchone()[0]
            total_pages = (total_products // per_page) + (1 if total_products % per_page > 0 else 0)

        product_list = []
        for product in products:
            product_data = {
                'id': product[0],
                'name': product[1],
                'price': product[2],
                'old_price': product[3],
                'availability': product[4],
                'images': product[5],
                'company': product[6],
                'ProductURL': product[7],
                'category': product[8],
                'created_at': product[9]
            }
            product_list.append(product_data)

        return jsonify({
            'products': product_list,
            'total_pages': total_pages,
            'current_page': page
        }), 200

    except Exception as e:
        logger.error(f"Get products error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/product/<int:id>/price-history', methods=['GET'])
def get_price_history(id):
    try:
        with get_db_cursor() as cursor:
            cursor.execute('''
                SELECT price, timestamp
                FROM price_history
                WHERE product_id = %s
                ORDER BY timestamp DESC
            ''', (id,))
            price_history = cursor.fetchall()

        price_history_list = [{'price': record[0], 'timestamp': record[1]} for record in price_history]
        return jsonify(price_history=price_history_list), 200

    except Exception as e:
        logger.error(f"Get price history error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/products/<int:id>', methods=['GET'])
def get_product(id):
    try:
        with get_db_cursor() as cursor:
            cursor.execute('SELECT * FROM product_details WHERE id = %s', (id,))
            product = cursor.fetchone()

        if product:
            product_data = {
                'id': product[0],
                'name': product[1],
                'price': product[2],
                'old_price': product[3],
                'availability': product[4],
                'images': product[5],
                'company': product[6],
                'ProductURL': product[7],
                'category': product[8],
            }
            return jsonify(product_data)
        else:
            return jsonify({'message': 'Product not found'}), 404

    except Exception as e:
        logger.error(f"Get product error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/products/category/<string:category>', methods=['GET'])
def get_products_by_category(category):
    try:
        with get_db_cursor() as cursor:
            cursor.execute('SELECT * FROM product_details WHERE category = %s', (category,))
            products = cursor.fetchall()

        product_list = []
        for product in products:
            product_data = {
                'id': product[0],
                'name': product[1],
                'price': product[2],
                'old_price': product[3],
                'availability': product[4],
                'images': product[5],
                'company': product[6],
                'ProductURL': product[7],
                'category': product[8],
            }
            product_list.append(product_data)

        return jsonify(product_list)

    except Exception as e:
        logger.error(f"Get products by category error: {e}")
        return jsonify({'error': str(e)}), 500
    
@app.route('/products/similar-tvs', methods=['GET'])
def get_similar_tvs():
    try:
        size = request.args.get('size')
        exclude_id = request.args.get('excludeId')
        category = request.args.get('category', 'TV')
        
        print(f"Finding similar products - Size: {size}, Exclude: {exclude_id}, Category: {category}")
        
        with get_db_cursor() as cursor:
            if size and category == 'TV':
                # Size-based TV matching
                cursor.execute('''
                    SELECT DISTINCT id, name, price, old_price, availability, images, company, ProductURL, category
                    FROM product_details 
                    WHERE category = %s 
                    AND id != %s 
                    AND (
                        name LIKE %s OR name LIKE %s OR name LIKE %s OR
                        name LIKE %s OR name LIKE %s OR name LIKE %s
                    )
                    ORDER BY 
                        CASE WHEN company != (SELECT company FROM product_details WHERE id = %s) THEN 0 ELSE 1 END,
                        ABS(price - (SELECT price FROM product_details WHERE id = %s)) ASC
                    LIMIT 8
                ''', (
                    category, exclude_id,
                    f'{size}" %', f'%{size} inch%', f'%{size}"%',
                    f'%{size}-inch%', f'%{size}inch%', f'%{size} in%',
                    exclude_id, exclude_id
                ))
            else:
                # Category-based matching for non-TVs
                cursor.execute('''
                    SELECT DISTINCT id, name, price, old_price, availability, images, company, ProductURL, category
                    FROM product_details 
                    WHERE category = %s 
                    AND id != %s
                    ORDER BY 
                        CASE WHEN company != (SELECT company FROM product_details WHERE id = %s) THEN 0 ELSE 1 END,
                        ABS(price - (SELECT price FROM product_details WHERE id = %s)) ASC
                    LIMIT 8
                ''', (category, exclude_id, exclude_id, exclude_id))
            
            products = cursor.fetchall()
            print(f"Found {len(products)} similar products")
            
        # Format response with explicit column mapping
        product_list = []
        for product in products:
            product_data = {
                'id': product[0],
                'name': product[1],
                'price': float(product[2]) if product[2] else 0,
                'old_price': float(product[3]) if product[3] else None,
                'availability': product[4],
                'images': product[5],
                'company': product[6],
                'ProductURL': product[7],
                'category': product[8]
            }
            product_list.append(product_data)
        
        return jsonify({
            'products': product_list,
            'count': len(product_list),
            'search_criteria': {
                'size': size,
                'category': category,
                'excluded_id': exclude_id
            }
        }), 200
        
    except Exception as e:
        print(f"Similar products error: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/products/similar', methods=['GET'])
def get_similar_products():
    try:
        product_id = request.args.get('productId')
        limit = request.args.get('limit', 8, type=int)
        
        if not product_id:
            return jsonify({'error': 'Product ID required'}), 400

        with get_db_cursor() as cursor:
            # Get the reference product details
            cursor.execute('''
                SELECT id, name, price, old_price, availability, images, company, ProductURL, category, created_at
                FROM product_details
                WHERE id = %s
            ''', (product_id,))
            
            ref_product = cursor.fetchone()
            if not ref_product:
                return jsonify({'error': 'Product not found'}), 404

            ref_price = float(ref_product[2])
            ref_category = ref_product[8]
            ref_company = ref_product[6]

            # First try: Different companies, same category, similar price range
            cursor.execute('''
                SELECT id, name, price, old_price, availability, images, company, ProductURL, category, created_at
                FROM product_details
                WHERE category = %s
                AND id != %s
                AND company != %s
                AND price IS NOT NULL
                AND price > 0
                AND price BETWEEN %s AND %s
                ORDER BY ABS(price - %s) ASC
                LIMIT %s
            ''', (
                ref_category,
                product_id,
                ref_company,
                ref_price * 0.5,  # 50% lower
                ref_price * 2.0,  # 100% higher
                ref_price,
                limit
            ))

            products = cursor.fetchall()
            
            # If we don't have enough products, expand the search
            if len(products) < limit:
                remaining_limit = limit - len(products)
                existing_ids = [str(p[0]) for p in products] + [str(product_id)]
                
                cursor.execute('''
                    SELECT id, name, price, old_price, availability, images, company, ProductURL, category, created_at
                    FROM product_details
                    WHERE category = %s
                    AND id NOT IN ({})
                    AND company != %s
                    AND price IS NOT NULL
                    AND price > 0
                    ORDER BY ABS(price - %s) ASC
                    LIMIT %s
                '''.format(','.join(['%s'] * len(existing_ids))), 
                (ref_category, *existing_ids, ref_company, ref_price, remaining_limit))
                
                additional_products = cursor.fetchall()
                products.extend(additional_products)

            # Format response
            product_list = []
            for product in products:
                product_data = {
                    'id': product[0],
                    'name': product[1],
                    'price': float(product[2]),
                    'old_price': float(product[3]) if product[3] else None,
                    'availability': product[4],
                    'images': product[5],
                    'company': product[6],
                    'ProductURL': product[7],
                    'category': product[8],
                    'created_at': product[9]
                }
                product_list.append(product_data)

            return jsonify({
                'products': product_list,
                'count': len(product_list),
                'reference_product': {
                    'id': ref_product[0],
                    'price': ref_price,
                    'category': ref_category,
                    'company': ref_company
                }
            }), 200

    except Exception as e:
        logger.error(f"Similar products fetch error: {e}")
        return jsonify({'error': str(e)}), 500








@app.route('/products', methods=['POST'])
def add_product():
    try:
        data = request.get_json()
        name = data['name']
        price = data['price']
        old_price = data['old_price']
        availability = data['availability']
        images = data['images']
        company = data['company']
        ProductURL = data['ProductURL']
        category = data['category']

        with get_db_cursor() as cursor:
            cursor.execute(''' 
                INSERT INTO product_details (name, price, old_price, availability, images, company, ProductURL, category) 
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            ''', (name, price, old_price, availability, images, company, ProductURL, category))

        return jsonify({'message': 'Product added successfully'}), 201

    except Exception as e:
        logger.error(f"Add product error: {e}")
        return jsonify({'error': str(e)}), 500
    


@app.route('/api/competitors', methods=['GET'])
@jwt_required()
def get_competitors():
    """Get all competitors with statistics"""
    try:
        with get_db_cursor() as cursor:
            cursor.execute('''
                SELECT c.*, 
                       COUNT(cp.id) as tracked_products,
                       AVG(cph.price) as avg_competitor_price,
                       MAX(cph.scraped_at) as last_price_update
                FROM competitors c
                LEFT JOIN competitor_products cp ON c.id = cp.competitor_id AND cp.is_active = TRUE
                LEFT JOIN competitor_price_history cph ON cp.id = cph.competitor_product_id 
                    AND cph.scraped_at >= DATE_SUB(NOW(), INTERVAL 7 DAY)
                WHERE c.status = 'active'
                GROUP BY c.id
                ORDER BY c.name
            ''')
            
            competitors = cursor.fetchall()
            
        competitor_list = []
        for comp in competitors:
            competitor_list.append({
                'id': comp[0],
                'name': comp[1],
                'website_url': comp[2],
                'logo_url': comp[3],
                'status': comp[4],
                'scrape_frequency_hours': comp[5],
                'last_scraped': comp[6].isoformat() if comp[6] else None,
                'tracked_products': comp[9] or 0,
                'avg_competitor_price': float(comp[10]) if comp[10] else 0,
                'last_price_update': comp[11].isoformat() if comp[11] else None
            })
        
        return jsonify({
            'competitors': competitor_list,
            'total': len(competitor_list)
        }), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/competitors', methods=['POST'])
@jwt_required()
def add_competitor():
    """Add a new competitor"""
    try:
        data = request.get_json()
        
        required_fields = ['name', 'website_url']
        for field in required_fields:
            if not data.get(field):
                return jsonify({'error': f'{field} is required'}), 400
        
        with get_db_cursor() as cursor:
            cursor.execute('''
                INSERT INTO competitors (name, website_url, logo_url, scrape_frequency_hours)
                VALUES (%s, %s, %s, %s)
            ''', (
                data['name'],
                data['website_url'],
                data.get('logo_url'),
                data.get('scrape_frequency_hours', 24)
            ))
            
            competitor_id = cursor.lastrowid
        
        return jsonify({
            'message': 'Competitor added successfully',
            'competitor_id': competitor_id
        }), 201
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/products/<int:product_id>/competitors', methods=['GET'])
@jwt_required()
def get_product_competitors(product_id):
    """Get competitor prices for a specific product"""
    try:
        with get_db_cursor() as cursor:
            # Get our product details
            cursor.execute('''
                SELECT id, name, price, company, category
                FROM product_details 
                WHERE id = %s
            ''', (product_id,))
            
            product = cursor.fetchone()
            if not product:
                return jsonify({'error': 'Product not found'}), 404
            
            # Get competitor data with latest prices
            cursor.execute('''
                SELECT c.id, c.name, c.website_url,
                       cp.competitor_sku, cp.competitor_url, cp.product_name,
                       cph.price, cph.old_price, cph.availability, cph.scraped_at
                FROM competitors c
                JOIN competitor_products cp ON c.id = cp.competitor_id
                LEFT JOIN competitor_price_history cph ON cp.id = cph.competitor_product_id
                WHERE cp.product_id = %s AND cp.is_active = TRUE
                AND (cph.id IS NULL OR cph.id = (
                    SELECT MAX(id) FROM competitor_price_history 
                    WHERE competitor_product_id = cp.id
                ))
                ORDER BY c.name
            ''', (product_id,))
            
            competitors = cursor.fetchall()
        
        # Format response
        our_product = {
            'id': product[0],
            'name': product[1],
            'price': float(product[2]),
            'company': product[3],
            'category': product[4]
        }
        
        competitor_data = []
        for comp in competitors:
            competitor_data.append({
                'competitor_id': comp[0],
                'competitor_name': comp[1],
                'website_url': comp[2],
                'competitor_sku': comp[3],
                'competitor_url': comp[4],
                'product_name': comp[5],
                'current_price': float(comp[6]) if comp[6] else None,
                'old_price': float(comp[7]) if comp[7] else None,
                'availability': comp[8],
                'last_updated': comp[9].isoformat() if comp[9] else None,
                'price_difference': float(comp[6] - product[2]) if comp[6] else None,
                'price_difference_percentage': round(((comp[6] - product[2]) / product[2]) * 100, 2) if comp[6] else None
            })
        
        # Calculate market analysis
        competitor_prices = [c['current_price'] for c in competitor_data if c['current_price']]
        market_analysis = {
            'total_competitors': len(competitor_data),
            'cheaper_options': len([c for c in competitor_data if c['current_price'] and c['current_price'] < our_product['price']]),
            'more_expensive': len([c for c in competitor_data if c['current_price'] and c['current_price'] > our_product['price']]),
            'lowest_competitor_price': min(competitor_prices) if competitor_prices else None,
            'highest_competitor_price': max(competitor_prices) if competitor_prices else None,
            'average_competitor_price': sum(competitor_prices) / len(competitor_prices) if competitor_prices else None
        }
        
        return jsonify({
            'our_product': our_product,
            'competitors': competitor_data,
            'market_analysis': market_analysis
        }), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/products/<int:product_id>/competitors', methods=['POST'])
@jwt_required()
def add_product_competitor(product_id):
    """Add competitor tracking for a product"""
    try:
        data = request.get_json()
        
        required_fields = ['competitor_id', 'competitor_url']
        for field in required_fields:
            if not data.get(field):
                return jsonify({'error': f'{field} is required'}), 400
        
        with get_db_cursor() as cursor:
            # Check if mapping already exists
            cursor.execute('''
                SELECT id FROM competitor_products 
                WHERE product_id = %s AND competitor_id = %s
            ''', (product_id, data['competitor_id']))
            
            if cursor.fetchone():
                return jsonify({'error': 'Competitor already tracked for this product'}), 400
            
            # Add new mapping
            cursor.execute('''
                INSERT INTO competitor_products 
                (product_id, competitor_id, competitor_sku, competitor_url, product_name)
                VALUES (%s, %s, %s, %s, %s)
            ''', (
                product_id,
                data['competitor_id'],
                data.get('competitor_sku'),
                data['competitor_url'],
                data.get('product_name')
            ))
            
            mapping_id = cursor.lastrowid
        
        # Trigger immediate price scraping
        scrape_competitor_price_sync(mapping_id)
        
        return jsonify({
            'message': 'Competitor tracking added successfully',
            'mapping_id': mapping_id
        }), 201
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

def scrape_competitor_price_sync(competitor_product_id):
    """Synchronously scrape price for a competitor product"""
    try:
        with get_db_cursor() as cursor:
            # Get competitor product details
            cursor.execute('''
                SELECT cp.id, cp.competitor_url, c.name
                FROM competitor_products cp
                JOIN competitors c ON cp.competitor_id = c.id
                WHERE cp.id = %s AND cp.is_active = TRUE
            ''', (competitor_product_id,))
            
            result = cursor.fetchone()
            if not result:
                return False
            
            _, competitor_url, competitor_name = result
            
            # Scrape the price
            price_data = scraper.scrape_competitor_price(competitor_url, competitor_name)
            
            if price_data:
                # Store the price data
                cursor.execute('''
                    INSERT INTO competitor_price_history 
                    (competitor_product_id, price, old_price, availability, scraped_at)
                    VALUES (%s, %s, %s, %s, %s)
                ''', (
                    competitor_product_id,
                    price_data['price'],
                    price_data['old_price'],
                    price_data['availability'],
                    price_data['scraped_at']
                ))
                
                print(f"Price scraped successfully for competitor product {competitor_product_id}: Rs. {price_data['price']}")
                return True
            
            return False
            
    except Exception as e:
        print(f"Error scraping competitor price: {e}")
        return False

@app.route('/api/scrape/competitor/<int:competitor_product_id>', methods=['POST'])
@jwt_required()
def manual_scrape_competitor(competitor_product_id):
    """Manually trigger price scraping for a competitor product"""
    try:
        success = scrape_competitor_price_sync(competitor_product_id)
        
        if success:
            return jsonify({'message': 'Price scraped successfully'}), 200
        else:
            return jsonify({'error': 'Failed to scrape price'}), 500
            
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True)
