from flask import Flask, request, jsonify
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
from flask import send_from_directory
import sqlite3, os, time, logging
from flask_cors import CORS
from dotenv import load_dotenv
from functools import wraps

# Load environment variables
load_dotenv()

basedir = os.path.abspath(os.path.dirname(__file__))
static_folder = os.path.join(basedir, 'static')
app = Flask(__name__, static_folder=static_folder, static_url_path='/static')

# Configuration
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'dev-secret-key')
app.config['DEBUG'] = os.getenv('FLASK_ENV', 'development') == 'development'

CORS(app)
CORS(app, resources={r"/": {"origins": "*"}})

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Simple rate limiting
rate_limit = {}

def rate_limited(max_calls=10, window=60):
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            client_ip = request.remote_addr
            now = time.time()
            if client_ip not in rate_limit:
                rate_limit[client_ip] = []
            rate_limit[client_ip] = [t for t in rate_limit[client_ip] if now - t < window]
            if len(rate_limit[client_ip]) >= max_calls:
                return jsonify({"message": "Too many requests"}), 429
            rate_limit[client_ip].append(now)
            return f(*args, **kwargs)
        return wrapper
    return decorator

def get_db_connection():
    db_path = os.path.join(basedir, 'data.db')
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_connection()
    # Bảng xe: Thêm image_url và is_approved (0: Chờ duyệt, 1: Đã duyệt), status_reason
    conn.execute('''CREATE TABLE IF NOT EXISTS vehicles (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        price TEXT NOT NULL,
        status TEXT NOT NULL,
        type TEXT NOT NULL,
        image_url TEXT,
        is_approved INTEGER DEFAULT 0,
        owner_name TEXT,
        odo INTEGER,
        brand TEXT,
        description TEXT,
        status_reason TEXT         
    )''')
    
    # Bảng người dùng: Thêm cccd và address
    conn.execute('''CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        fullname TEXT,
        username TEXT UNIQUE NOT NULL,
        password TEXT NOT NULL,
        role TEXT DEFAULT 'user',
        cccd TEXT,
        address TEXT
    )''')
    # Bảng đơn hàng
    conn.execute('''CREATE TABLE IF NOT EXISTS orders (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        vehicle_id INTEGER,
        days INTEGER DEFAULT 1,
        total_price INTEGER DEFAULT 0,
        rent_date DATETIME DEFAULT CURRENT_TIMESTAMP,
        status TEXT DEFAULT 'pending',
        payment_status TEXT DEFAULT 'unpaid',
        return_days INTEGER,
        refund_amount INTEGER DEFAULT 0,
        FOREIGN KEY(user_id) REFERENCES users(id),
        FOREIGN KEY(vehicle_id) REFERENCES vehicles(id)
    )''')
    # Bảng đặt lịch hẹn / Giỏ hàng
    conn.execute('''CREATE TABLE IF NOT EXISTS appointments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        vehicle_id INTEGER,
        days INTEGER DEFAULT 1,
        total_price INTEGER,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(user_id) REFERENCES users(id),
        FOREIGN KEY(vehicle_id) REFERENCES vehicles(id)
    )''')
    # Khởi tạo tài khoản Admin mặc định
    admin = conn.execute("SELECT * FROM users WHERE username = 'admin'").fetchone()
    if not admin:
        hashed_password = generate_password_hash('123', method='pbkdf2:sha256')
        conn.execute("INSERT INTO users (fullname, username, password, role) VALUES (?, ?, ?, ?)",
                     ('Quản trị viên', 'admin', hashed_password, 'admin'))
        conn.commit()
    else:
        # Nếu admin đã tồn tại với mật khẩu plaintext cũ, cập nhật lại thành hash
        if admin['password'] == '123':
            hashed_password = generate_password_hash('123', method='pbkdf2:sha256')
            conn.execute("UPDATE users SET password = ? WHERE id = ?", (hashed_password, admin['id']))
            conn.commit()
    conn.close()

init_db()

# ================= API PHƯƠNG TIỆN =================
@app.route('/cars', methods=['GET'])
def get_cars():
    conn = get_db_connection()
    query = "SELECT * FROM vehicles WHERE 1=1"
    params = []

    search = request.args.get('search', '').strip().lower()
    name = request.args.get('name', '').strip().lower()
    brand = request.args.get('brand', '').strip().lower()
    vtype = request.args.get('type', '').strip().lower()
    status = request.args.get('status', '').strip().lower()

    if search:
        like = f"%{search}%"
        query += " AND (LOWER(name) LIKE ? OR LOWER(brand) LIKE ? OR LOWER(owner_name) LIKE ? OR LOWER(description) LIKE ?)"
        params.extend([like, like, like, like])

    if name:
        query += " AND LOWER(name) LIKE ?"
        params.append(f"%{name}%")

    if brand:
        query += " AND LOWER(brand) LIKE ?"
        params.append(f"%{brand}%")

    if vtype and vtype != 'all':
        query += " AND LOWER(type)=?"
        params.append(vtype)

    if status in ['available', 'unavailable']:
        query += " AND LOWER(status)=?"
        params.append(status)

    query += " ORDER BY id DESC"
    rows = conn.execute(query, params).fetchall()
    conn.close()
    return jsonify([dict(row) for row in rows])

@app.route('/cars/<int:id>', methods=['PUT'])
def update_car(id):
    data = request.json or {}
    conn = get_db_connection()
    
    # Lấy dữ liệu cũ của xe
    old_data = conn.execute("SELECT * FROM vehicles WHERE id=?", (id,)).fetchone()
    if not old_data:
        conn.close()
        return jsonify({"message": "Xe không tồn tại."}), 404
    
    try:
        # Xử lý từng field với type casting phù hợp
        name = data.get('name')
        if name is None or name == '':
            name = old_data['name']
        else:
            name = str(name).strip()
        
        price = data.get('price')
        if price is None or price == '':
            price = old_data['price']
        else:
            try:
                price = float(price)
                if price <= 0:
                    raise ValueError("Giá phải lớn hơn 0")
            except:
                price = old_data['price']
        
        status = data.get('status')
        if status is None or status == '':
            status = old_data['status']
        else:
            status = str(status).strip()
        
        vtype = data.get('type')
        if vtype is None or vtype == '':
            vtype = old_data['type']
        else:
            vtype = str(vtype).strip()
        
        image_url = data.get('image_url')
        if image_url is None or image_url == '':
            image_url = old_data['image_url'] or ''
        else:
            image_url = str(image_url).strip()
        
        is_approved = data.get('is_approved')
        if is_approved is None:
            is_approved = old_data['is_approved']
        else:
            is_approved = int(is_approved)
        
        owner_name = data.get('owner_name')
        if owner_name is None or owner_name == '':
            owner_name = old_data['owner_name'] or ''
        else:
            owner_name = str(owner_name).strip()
        
        odo = data.get('odo')
        if odo is None or odo == '':
            odo = old_data['odo'] or 0
        else:
            try:
                odo = int(odo)
            except:
                odo = old_data['odo'] or 0
        
        brand = data.get('brand')
        if brand is None or brand == '':
            brand = old_data['brand'] or ''
        else:
            brand = str(brand).strip()
        
        description = data.get('description')
        if description is None or description == '':
            description = old_data['description'] or ''
        else:
            description = str(description).strip()
        
        status_reason = data.get('status_reason')
        if status_reason is None or status_reason == '':
            status_reason = old_data['status_reason'] or ''
        else:
            status_reason = str(status_reason).strip()
        
        # Update database
        conn.execute('''UPDATE vehicles SET name=?, price=?, status=?, type=?, image_url=?, is_approved=?, 
                        owner_name=?, odo=?, brand=?, description=?, status_reason=? WHERE id=?''',
                     (name, price, status, vtype, image_url, is_approved,
                      owner_name, odo, brand, description, status_reason, id))
        conn.commit()
        return jsonify({"message": "Cập nhật thông tin xe thành công."})
    except Exception as e:
        conn.rollback()
        print(f"[ERROR] update_car: {str(e)}")
        return jsonify({"message": f"Lỗi cập nhật: {str(e)}"}), 500
    finally:
        conn.close()

@app.route('/cars/<int:id>', methods=['DELETE'])
def delete_car(id):
    conn = get_db_connection()
    try:
        # Kiểm tra xe tồn tại
        vehicle = conn.execute("SELECT id FROM vehicles WHERE id=?", (id,)).fetchone()
        if not vehicle:
            conn.close()
            return jsonify({"message": "Xe không tồn tại."}), 404
        
        # Xóa xe
        conn.execute("DELETE FROM vehicles WHERE id=?", (id,))
        conn.commit()
        return jsonify({"message": "Xóa xe thành công."})
    except Exception as e:
        conn.rollback()
        print(f"[ERROR] delete_car: {str(e)}")
        return jsonify({"message": f"Lỗi xóa xe: {str(e)}"}), 500
    finally:
        conn.close()

@app.route('/cars/<int:id>/status', methods=['PUT'])
def update_vehicle_status(id):
    data = request.json or {}
    new_status = data.get('status', '').strip().lower()
    reason = data.get('reason', '').strip()
    
    # Kiểm tra status hợp lệ
    if not new_status or new_status not in ['available', 'unavailable']:
        return jsonify({"message": "Trạng thái không hợp lệ. Chỉ chấp nhận 'available' hoặc 'unavailable'."}), 400
    
    conn = get_db_connection()
    try:
        # Kiểm tra xe tồn tại
        vehicle = conn.execute("SELECT id, status, status_reason FROM vehicles WHERE id=?", (id,)).fetchone()
        if not vehicle:
            conn.close()
            return jsonify({"message": "Xe không tồn tại."}), 404
        
        # Nếu status không thay đổi thì return
        if vehicle['status'] == new_status:
            conn.close()
            return jsonify({"message": "Trạng thái xe không thay đổi."})
        
        # Log for audit
        print(f"Admin changing vehicle {id} status from '{vehicle['status']}' to '{new_status}'. Reason: '{reason}'")
        
        # Cập nhật trạng thái
        # Nếu chuyển về available, xóa reason; nếu chuyển sang unavailable, cập nhật reason (nếu có)
        final_reason = '' if new_status == 'available' else reason
        
        conn.execute("UPDATE vehicles SET status=?, status_reason=? WHERE id=?", (new_status, final_reason, id))
        conn.commit()
        
        action = "cho thuê lại" if new_status == 'available' else "ngừng cho thuê"
        msg = f"Đã cập nhật trạng thái xe thành công: {action}"
        if final_reason:
            msg += f" (Lý do: {final_reason})"
        
        return jsonify({"message": msg})
    except Exception as e:
        conn.rollback()
        print(f"[ERROR] update_vehicle_status: {str(e)}")
        return jsonify({"message": f"Lỗi cập nhật trạng thái: {str(e)}"}), 500
    finally:
        conn.close()

# Cấu hình thư mục lưu ảnh
# Cấu hình thư mục lưu ảnh (nếu cần config thêm)
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# API để tải file lên
@app.route('/upload', methods=['POST'])
def upload_file():
    try:
        if 'file' not in request.files:
            return jsonify({"message": "Không có file trong yêu cầu."}), 400
        file = request.files['file']
        if file.filename == '':
            return jsonify({"message": "Chưa chọn file."}), 400
        if not allowed_file(file.filename):
            return jsonify({"message": "Định dạng tệp không hợp lệ. Chỉ chấp nhận PNG, JPG, JPEG, GIF."}), 400
        
        # Tạo thư mục uploads nếu chưa tồn tại
        upload_dir = os.path.join(app.static_folder, 'uploads')
        if not os.path.exists(upload_dir):
            os.makedirs(upload_dir, exist_ok=True)
        
        filename = secure_filename(file.filename)
        unique_filename = f"{int(time.time())}_{filename}"
        save_path = os.path.join(upload_dir, unique_filename)
        file.save(save_path)
        
        print(f"File uploaded successfully: {save_path}")
        
        # Trả về đường dẫn để lưu vào database
        image_url = f"http://127.0.0.1:5000/static/uploads/{unique_filename}"
        return jsonify({"url": image_url, "message": "Tải lên thành công."}), 200
    except Exception as e:
        print(f"Lỗi upload: {e}")
        return jsonify({"message": f"Lỗi máy chủ: {str(e)}"}), 500


# ================= API NGƯỜI DÙNG =================
@app.route('/register', methods=['POST'])
@rate_limited(max_calls=5, window=300)  # 5 calls per 5 minutes
def register():
    try:
        data = request.json or {}
        fullname = data.get('fullname', '').strip()
        username = data.get('username', '').strip()
        password = data.get('password', '').strip()
        if not fullname or not username or not password:
            return jsonify({"message": "Vui lòng điền đầy đủ họ tên, tên đăng nhập và mật khẩu."}), 400

        hashed_password = generate_password_hash(password, method='pbkdf2:sha256')
        conn = get_db_connection()
        try:
            conn.execute("INSERT INTO users (fullname, username, password, role, cccd, address) VALUES (?, ?, ?, 'user', ?, ?)",
                         (fullname, username, hashed_password, data.get('cccd', '').strip(), data.get('address', '').strip()))
            conn.commit()
            logger.info(f"User {username} registered successfully.")
            return jsonify({"message": "Success"}), 201
        except sqlite3.IntegrityError:
            return jsonify({"message": "Tên đăng nhập đã tồn tại"}), 400
        finally:
            conn.close()
    except Exception as e:
        logger.error(f"Error in register: {str(e)}")
        return jsonify({"message": "Lỗi server"}), 500

@app.route('/login-user', methods=['POST'])
def login_user():
    try:
        data = request.json
        username = data.get('username', '').strip()
        password = data.get('password', '').strip()
        if not username or not password:
            return jsonify({"status": "fail", "message": "Vui lòng nhập tên đăng nhập và mật khẩu"}), 400

        conn = get_db_connection()
        user = conn.execute("SELECT id, fullname, username, password, role, cccd, address FROM users WHERE username = ?", (username,)).fetchone()
        conn.close()
        if user and check_password_hash(user['password'], password):
            user_dict = dict(user)
            del user_dict['password']  # Không trả mật khẩu
            logger.info(f"User {username} logged in successfully.")
            return jsonify({"status": "success", "user": user_dict})
        logger.warning(f"Failed login attempt for username: {username}")
        return jsonify({"status": "fail", "message": "Sai tài khoản hoặc mật khẩu"}), 401
    except Exception as e:
        logger.error(f"Error in login: {str(e)}")
        return jsonify({"status": "fail", "message": "Lỗi server"}), 500

@app.route('/users', methods=['GET'])
def get_users():
    conn = get_db_connection()
    users = conn.execute("SELECT id, fullname, username, role, cccd, address FROM users WHERE role = 'user'").fetchall()
    conn.close()
    return jsonify([dict(user) for user in users])

@app.route('/users/<int:id>', methods=['GET'])
def get_user(id):
    conn = get_db_connection()
    user = conn.execute("SELECT id, fullname, username, role, cccd, address FROM users WHERE id = ?", (id,)).fetchone()
    conn.close()
    if not user:
        return jsonify({"message": "Người dùng không tồn tại."}), 404
    return jsonify(dict(user))

@app.route('/users/<int:id>', methods=['PUT'])
def update_user(id):
    data = request.json or {}
    conn = get_db_connection()
    user = conn.execute("SELECT * FROM users WHERE id = ?", (id,)).fetchone()
    if not user:
        conn.close()
        return jsonify({"message": "Người dùng không tồn tại."}), 404

    fullname = data.get('fullname', user['fullname']).strip()
    cccd = data.get('cccd', user['cccd'] or '').strip()
    address = data.get('address', user['address'] or '').strip()
    password = data.get('password', '').strip()
    if password:
        password = generate_password_hash(password, method='pbkdf2:sha256')
    else:
        password = user['password']

    conn.execute("UPDATE users SET fullname = ?, cccd = ?, address = ?, password = ? WHERE id = ?",
                 (fullname, cccd, address, password, id))
    conn.commit()
    conn.close()
    return jsonify({"message": "Cập nhật thông tin thành công."})

@app.route('/users/<int:id>', methods=['DELETE'])
def delete_user(id):
    conn = get_db_connection()
    conn.execute("DELETE FROM users WHERE id=?", (id,))
    conn.commit()
    conn.close()
    return jsonify({"message": "Deleted"})

# ================= API ĐẶT LỊCH / GIỎ HÀNG =================
@app.route('/appointments', methods=['POST'])
def create_appointment():
    data = request.json or {}
    user_id = data.get('user_id')
    vehicle_id = data.get('vehicle_id')
    days = max(1, int(data.get('days', 1)))
    total_price = int(data.get('total_price', 0))

    if not user_id or not vehicle_id:
        return jsonify({"message": "Thiếu thông tin người dùng hoặc phương tiện."}), 400

    conn = get_db_connection()
    try:
        # Kiểm tra xe có tồn tại và được duyệt
        existing_vehicle = conn.execute("SELECT status, is_approved FROM vehicles WHERE id = ?", (vehicle_id,)).fetchone()
        if not existing_vehicle:
            return jsonify({"message": "Xe không tồn tại."}), 404
        if existing_vehicle['is_approved'] != 1:
            return jsonify({"message": "Xe chưa được duyệt."}), 400

        status = (existing_vehicle['status'] or '').lower()
        if status == 'available':
            return jsonify({"message": "Xe đang sẵn sàng, bạn có thể thuê ngay."}), 400

        # Kiểm tra người dùng đã có appointment cho xe này chưa
        existing_appointment = conn.execute("SELECT id FROM appointments WHERE user_id=? AND vehicle_id=?", (user_id, vehicle_id)).fetchone()
        if existing_appointment:
            return jsonify({"message": "Bạn đã đặt lịch hẹn cho xe này rồi."}), 400

        # Tạo đặt lịch hẹn (không ảnh hưởng đến trạng thái xe)
        conn.execute('''INSERT INTO appointments (user_id, vehicle_id, days, total_price) 
                        VALUES (?, ?, ?, ?)''',
                     (user_id, vehicle_id, days, total_price))
        conn.commit()
        return jsonify({"message": "Đặt lịch hẹn thành công!"}), 201
    except Exception as e:
        conn.rollback()
        return jsonify({"message": f"Lỗi đặt lịch: {str(e)}"}), 500
    finally:
        conn.close()

@app.route('/appointments/<int:user_id>', methods=['GET'])
def get_appointments(user_id):
    conn = get_db_connection()
    query = '''SELECT a.id, a.days, a.total_price, a.created_at,
                      v.name, v.price as price_per_day, v.image_url 
               FROM appointments a JOIN vehicles v ON a.vehicle_id = v.id WHERE a.user_id = ? ORDER BY a.created_at DESC'''
    appointments = conn.execute(query, (user_id,)).fetchall()
    conn.close()
    return jsonify([dict(row) for row in appointments])

@app.route('/appointments/<int:id>', methods=['PUT'])
def update_appointment(id):
    data = request.json or {}
    days = max(1, int(data.get('days', 1)))
    total_price = int(data.get('total_price', 0))

    conn = get_db_connection()
    conn.execute("UPDATE appointments SET days=?, total_price=? WHERE id=?", (days, total_price, id))
    conn.commit()
    conn.close()
    return jsonify({"message": "Cập nhật đặt lịch thành công."})

@app.route('/appointments/<int:id>', methods=['DELETE'])
def delete_appointment(id):
    conn = get_db_connection()
    conn.execute("DELETE FROM appointments WHERE id=?", (id,))
    conn.commit()
    conn.close()
    return jsonify({"message": "Hủy đặt lịch thành công."})

@app.route('/appointments/<int:id>/convert-to-order', methods=['POST'])
def convert_appointment_to_order(id):
    conn = get_db_connection()
    try:
        # Lấy thông tin appointment
        appointment = conn.execute("SELECT user_id, vehicle_id, days, total_price FROM appointments WHERE id=?", (id,)).fetchone()
        if not appointment:
            return jsonify({"message": "Đặt lịch không tồn tại."}), 404

        # Kiểm tra xe có sẵn không
        vehicle = conn.execute("SELECT status FROM vehicles WHERE id=?", (appointment['vehicle_id'],)).fetchone()
        if vehicle['status'] != 'available':
            return jsonify({"message": "Xe hiện không khả dụng."}), 400

        # Tạo order
        conn.execute('''INSERT INTO orders (user_id, vehicle_id, days, total_price, payment_status) 
                        VALUES (?, ?, ?, ?, 'pending')''',
                     (appointment['user_id'], appointment['vehicle_id'], appointment['days'], appointment['total_price']))
        
        # Đánh dấu xe là đã thuê
        conn.execute("UPDATE vehicles SET status='unavailable' WHERE id=?", (appointment['vehicle_id'],))
        
        # Xóa appointment
        conn.execute("DELETE FROM appointments WHERE id=?", (id,))
        
        conn.commit()
        return jsonify({"message": "Chuyển thành đơn hàng thành công!"}), 200
    except Exception as e:
        conn.rollback()
        return jsonify({"message": f"Lỗi chuyển đổi: {str(e)}"}), 500
    finally:
        conn.close()

@app.route('/orders', methods=['POST'])
def book_car():
    data = request.json or {}
    user_id = data.get('user_id')
    vehicle_id = data.get('vehicle_id')
    days = max(1, int(data.get('days', 1)))
    total_price = int(data.get('total_price', 0))

    if not user_id or not vehicle_id:
        return jsonify({"message": "Thiếu thông tin người dùng hoặc phương tiện."}), 400

    conn = get_db_connection()
    try:
        existing_vehicle = conn.execute("SELECT status, is_approved FROM vehicles WHERE id = ?", (vehicle_id,)).fetchone()
        if not existing_vehicle:
            return jsonify({"message": "Xe không tồn tại."}), 404
        if existing_vehicle['is_approved'] != 1:
            return jsonify({"message": "Xe chưa được duyệt. Vui lòng chọn phương tiện khác."}), 400

        status = (existing_vehicle['status'] or '').lower()
        if status != 'available':
            return jsonify({"message": "Xe hiện không thể đặt vì đã được thuê hoặc không sẵn sàng."}), 400

        # Kiểm tra người dùng đã có đơn pending cho xe này chưa
        existing_order = conn.execute("SELECT id FROM orders WHERE user_id=? AND vehicle_id=? AND payment_status='pending'", (user_id, vehicle_id)).fetchone()
        if existing_order:
            return jsonify({"message": "Bạn đã có đơn đặt lịch cho xe này. Vui lòng kiểm tra giỏ hàng."}), 400

        existing_appointment = conn.execute("SELECT id FROM appointments WHERE user_id=? AND vehicle_id=?", (user_id, vehicle_id)).fetchone()
        if existing_appointment:
            return jsonify({"message": "Bạn đã đặt lịch hẹn cho xe này. Vui lòng kiểm tra giỏ hàng."}), 400

        conn.execute('''INSERT INTO orders (user_id, vehicle_id, days, total_price, payment_status) 
                        VALUES (?, ?, ?, ?, 'pending')''',
                     (user_id, vehicle_id, days, total_price))
        
        conn.execute("UPDATE vehicles SET status='unavailable' WHERE id=?", (vehicle_id,))
        
        conn.commit()
        return jsonify({"message": "Đặt thuê ngay thành công! Chờ xác nhận thanh toán."}), 201
    except Exception as e:
        conn.rollback()
        return jsonify({"message": f"Lỗi đặt xe: {str(e)}"}), 500
    finally:
        conn.close()

@app.route('/orders/<int:user_id>', methods=['GET'])
def get_orders(user_id):
    conn = get_db_connection()
    query = '''SELECT o.id, o.days, o.total_price, o.status, o.payment_status, o.rent_date as created_at,
                      v.name, v.price as price_per_day, v.image_url 
               FROM orders o JOIN vehicles v ON o.vehicle_id = v.id WHERE o.user_id = ? ORDER BY o.rent_date DESC'''
    orders = conn.execute(query, (user_id,)).fetchall()
    conn.close()
    return jsonify([dict(row) for row in orders])

@app.route('/orders/<int:id>', methods=['PUT'])
def update_order(id):
    data = request.json or {}
    days = max(1, int(data.get('days', 1)))
    total_price = int(data.get('total_price', 0))

    conn = get_db_connection()
    order = conn.execute("SELECT payment_status, status FROM orders WHERE id=?", (id,)).fetchone()
    if not order:
        conn.close()
        return jsonify({"message": "Đơn hàng không tồn tại."}), 404
    if order['payment_status'] == 'paid' or order['status'] == 'completed':
        conn.close()
        return jsonify({"message": "Không thể cập nhật đơn hàng đã thanh toán hoặc đã hoàn tất."}), 400

    conn.execute("UPDATE orders SET days=?, total_price=? WHERE id=?", (days, total_price, id))
    conn.commit()
    conn.close()
    return jsonify({"message": "Cập nhật đơn hàng thành công."})

@app.route('/orders/<int:id>', methods=['DELETE'])
def delete_order(id):
    conn = get_db_connection()
    try:
        # Kiểm tra đơn hàng tồn tại
        order = conn.execute("SELECT vehicle_id, payment_status FROM orders WHERE id=?", (id,)).fetchone()
        if not order:
            return jsonify({"message": "Đơn hàng không tồn tại."}), 404
        
        # Nếu đã thanh toán, không cho hủy
        if order['payment_status'] == 'paid':
            return jsonify({"message": "Không thể hủy đơn hàng đã thanh toán."}), 400
        
        # Xóa đơn hàng và cập nhật trạng thái xe
        conn.execute("DELETE FROM orders WHERE id=?", (id,))
        conn.execute("UPDATE vehicles SET status='available' WHERE id=?", (order['vehicle_id'],))
        conn.commit()
        return jsonify({"message": "Hủy đơn hàng thành công."})
    except Exception as e:
        conn.rollback()
        return jsonify({"message": f"Lỗi hủy đơn: {str(e)}"}), 500
    finally:
        conn.close()

@app.route('/orders/<int:id>/pay', methods=['PUT'])
def confirm_payment(id):
    conn = get_db_connection()
    try:
        # Kiểm tra đơn hàng
        order = conn.execute("SELECT vehicle_id, payment_status FROM orders WHERE id=?", (id,)).fetchone()
        if not order:
            return jsonify({"message": "Đơn hàng không tồn tại."}), 404
        
        if order['payment_status'] == 'paid':
            return jsonify({"message": "Đơn hàng đã được thanh toán."}), 400
        
        # Kiểm tra xe
        vehicle = conn.execute("SELECT status FROM vehicles WHERE id=?", (order['vehicle_id'],)).fetchone()
        if not vehicle:
            return jsonify({"message": "Thông tin xe không hợp lệ."}), 400
        
        if vehicle['status'] == 'unavailable':
            return jsonify({"message": "Xe đã được thuê bởi đơn khác."}), 400
        
        # Cập nhật thanh toán và trạng thái xe
        conn.execute("UPDATE orders SET payment_status='paid' WHERE id=?", (id,))
        conn.execute("UPDATE vehicles SET status='unavailable' WHERE id=?", (order['vehicle_id'],))
        conn.commit()
        
        return jsonify({"message": "Xác nhận thanh toán thành công. Xe đã được đánh dấu là đã thuê."})
    except Exception as e:
        conn.rollback()
        return jsonify({"message": f"Lỗi xác nhận thanh toán: {str(e)}"}), 500
    finally:
        conn.close()

@app.route('/orders/<int:id>/return', methods=['PUT'])
def return_vehicle(id):
    data = request.json or {}
    return_days = data.get('return_days', None)  # Số ngày thực tế sử dụng
    
    conn = get_db_connection()
    try:
        # Kiểm tra đơn hàng tồn tại và chưa hoàn tất
        order = conn.execute("SELECT vehicle_id, status, payment_status, user_id, days, total_price FROM orders WHERE id=?", (id,)).fetchone()
        if not order:
            return jsonify({"message": "Đơn hàng không tồn tại."}), 404
        
        if order['status'] == 'completed':
            return jsonify({"message": "Đơn hàng đã được hoàn tất trước đó."}), 400
        
        if order['payment_status'] != 'paid':
            return jsonify({"message": "Đơn hàng chưa được thanh toán. Không thể trả xe."}), 400
        
        vehicle_id = order['vehicle_id']
        
        # Kiểm tra xe có tồn tại không
        vehicle = conn.execute("SELECT status FROM vehicles WHERE id=?", (vehicle_id,)).fetchone()
        if not vehicle:
            return jsonify({"message": "Thông tin xe không hợp lệ."}), 400
        
        refund_amount = 0
        refund_info = ""
        
        # Tính toán tiền hoàn lại nếu trả trước thời hạn
        if return_days is not None:
            return_days = max(1, int(return_days))
            if return_days < order['days']:
                # Người dùng trả trước thời hạn → hoàn lại tiền được dùng thêm
                days_saved = order['days'] - return_days
                price_per_day = order['total_price'] / order['days']
                refund_amount = int(days_saved * price_per_day)
                refund_info = f" (Hoàn lại {refund_amount:,}đ cho {days_saved} ngày chưa sử dụng)"
        
        # Log the return action
        print(f"User {order['user_id']} returning vehicle {vehicle_id} for order {id}. Return days: {return_days}, Refund: {refund_amount}")
        
        # Cập nhật order status = completed và refund_amount
        conn.execute("UPDATE orders SET status='completed', refund_amount=? WHERE id=?", (refund_amount, id))
        
        # Trả lại xe vào trạng thái available
        conn.execute("UPDATE vehicles SET status='available', status_reason='' WHERE id=?", (vehicle_id,))
        
        conn.commit()
        return jsonify({"message": f"Trả xe thành công. Cảm ơn quý khách!{refund_info}", "refund": refund_amount})
    except Exception as e:
        conn.rollback()
        print(f"Lỗi khi trả xe: {e}")
        return jsonify({"message": f"Lỗi hệ thống: {str(e)}"}), 500
    finally:
        conn.close()


# NEW: Required for cart.html handlePay() function
@app.route('/checkout-multiple', methods=['POST'])
def checkout_multiple():
    data = request.json or {}
    order_ids = data.get('order_ids', [])
    if not isinstance(order_ids, list) or not order_ids:
        return jsonify({"message": "Không có đơn hàng nào để thanh toán."}), 400

    conn = get_db_connection()
    try:
        for oid in order_ids:
            # Lấy vehicle_id của order
            order = conn.execute("SELECT vehicle_id FROM orders WHERE id=?", (oid,)).fetchone()
            if order:
                # Cập nhật thanh toán và trạng thái xe
                conn.execute("UPDATE orders SET payment_status='paid' WHERE id=?", (oid,))
                conn.execute("UPDATE vehicles SET status='unavailable' WHERE id=?", (order['vehicle_id'],))
        conn.commit()
        return jsonify({"message": "Payment successful"})
    finally:
        conn.close()

@app.route('/admin/orders', methods=['GET'])
def admin_get_orders():
    conn = get_db_connection()
    query = '''SELECT o.id, o.days, o.total_price, o.status, o.payment_status, o.rent_date,
                      u.fullname as user_name, v.name as vehicle_name
               FROM orders o 
               JOIN users u ON o.user_id = u.id 
               JOIN vehicles v ON o.vehicle_id = v.id 
               ORDER BY o.rent_date DESC'''
    orders = conn.execute(query).fetchall()
    conn.close()
    return jsonify([dict(row) for row in orders])

@app.route('/admin/rented-vehicles', methods=['GET'])
def admin_get_rented_vehicles():
    conn = get_db_connection()
    query = '''SELECT v.id, v.name, v.image_url, v.price, v.owner_name,
                      o.id as order_id, o.days, o.total_price, o.rent_date, o.return_days,
                      u.fullname as user_name, u.username
               FROM vehicles v 
               JOIN orders o ON v.id = o.vehicle_id 
               JOIN users u ON o.user_id = u.id 
               WHERE v.status = 'unavailable' AND o.payment_status = 'paid' AND o.status != 'completed'
               ORDER BY o.rent_date DESC'''
    rented = conn.execute(query).fetchall()
    conn.close()
    return jsonify([dict(row) for row in rented])

@app.route('/admin/appointments', methods=['GET'])
def admin_get_appointments():
    conn = get_db_connection()
    query = '''SELECT a.id, a.days, a.total_price, a.created_at,
                      v.name as vehicle_name, v.image_url, v.status as vehicle_status,
                      u.fullname as user_name, u.username
               FROM appointments a 
               JOIN vehicles v ON a.vehicle_id = v.id 
               JOIN users u ON a.user_id = u.id 
               ORDER BY a.created_at DESC'''
    appointments = conn.execute(query).fetchall()
    conn.close()
    return jsonify([dict(row) for row in appointments])

@app.route('/admin/stats', methods=['GET'])
def admin_stats():
    conn = get_db_connection()
    # Tính doanh thu thực tế: tổng tiền đã thanh toán trừ tiền hoàn lại
    total_revenue = conn.execute("SELECT SUM(total_price - refund_amount) FROM orders WHERE payment_status='paid' AND status='completed'").fetchone()[0] or 0
    total_orders = conn.execute("SELECT COUNT(*) FROM orders").fetchone()[0] or 0
    total_vehicles = conn.execute("SELECT COUNT(*) FROM vehicles WHERE is_approved=1").fetchone()[0] or 0
    total_users = conn.execute("SELECT COUNT(*) FROM users WHERE role='user'").fetchone()[0] or 0
    
    query = '''SELECT u.fullname, v.name as vehicle_name, o.rent_date as created_at, o.days, o.total_price, o.refund_amount 
               FROM orders o 
               JOIN users u ON o.user_id = u.id 
               JOIN vehicles v ON o.vehicle_id = v.id 
               WHERE o.payment_status='paid' ORDER BY o.rent_date DESC LIMIT 10'''
    customers = conn.execute(query).fetchall()
    conn.close()
    return jsonify({
        "total_revenue": total_revenue,
        "total_orders": total_orders,
        "total_vehicles": total_vehicles,
        "total_users": total_users,
        "renting_customers": [dict(row) for row in customers]
    })

if __name__ == '__main__':
    # Production: gunicorn backend.app:app
    # Development: python backend/app.py
    host = os.getenv('FLASK_HOST', '127.0.0.1')
    port = int(os.getenv('FLASK_PORT', 5000))
    debug = os.getenv('FLASK_ENV', 'development') == 'development'
    
    print(f">> Starting Flask app on {host}:{port} (debug={debug})")
    app.run(host=host, port=port, debug=debug)