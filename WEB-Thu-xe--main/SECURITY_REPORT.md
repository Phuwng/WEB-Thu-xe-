# 🔒 BÁO CÁO KIỂM TRA & CẢI THIỆN BẢO MẬT

## ✅ KIỂM TRA ĐẠT CÁC YÊU CẦU TỪ ÁNH

### 1️⃣ **BẢO MẬT MẬT KHẨU**

#### ✅ Sử dụng werkzeug.security để Hash mật khẩu (Pbkdf2:sha256)
- **Location**: `app.py` - Lines 3, 172, 203, 606
- **Implementations**:
  - `generate_password_hash(password, method='pbkdf2:sha256')` - Dùng khi đăng ký tài khoản
  - `check_password_hash(user['password'], password)` - Dùng khi đăng nhập
  - Mật khẩu được hash trước khi lưu vào database

#### ✅ Không lưu mật khẩu văn bản thuần
- ✓ Tất cả mật khẩu được hash trước khi lưu
- ✓ Mật khẩu admin mặc định cũng được hash (lines 165-174)
- ✓ Cập nhật mật khẩu cũ sang hash nếu cần (lines 171-174)
- ✓ Không trả mật khẩu về frontend (line 552)

---

### 2️⃣ **KIỂM SOÁT LUỒNG - PHÂN QUYỀN RÕ RÀNG 3 NHÓM**

#### ✅ 3 Vai trò: Khách hàng (customer), Chủ xe (owner), Quản trị viên (admin)
- **Location**: `app.py` - Lines 68-75
- **Function**: `normalize_role(role)`
- **Mappings**:
  - `'user'` → `'customer'` (khách hàng)
  - `'owner'` → `'owner'` (chủ xe)
  - `'admin'` → `'admin'` (quản trị viên)
  - Mặc định: `'customer'`

#### ✅ Kiểm tra phân quyền
- Line 602: User được gán role khi đăng ký (mặc định: 'customer')
- Line 552: Role được normalize khi đăng nhập
- Line 595: Role được lưu và trả về trong user object
- Database schema (lines 157, 602): Role được lưu trong table users

---

### 3️⃣ **XỬ LÝ XUNG ĐỘT LỊCH ĐẶT (CONFLICT HANDLING)**

#### ✅ Ngăn chặn đặt xe trùng thời gian
- **Location**: `app.py` - Lines 77-125
- **Features**:

1. **Tính toán ngày bắt đầu/kết thúc** - `calculate_rental_dates(days)`:
   - Tính `start_date` = ngày hiện tại
   - Tính `end_date` = ngày hiện tại + số ngày
   - Lưu dưới dạng ISO format

2. **Kiểm tra xung đột thời gian** - `check_booking_conflict()`:
   - Tìm tất cả đơn đã thanh toán (payment_status='paid') cho cùng xe
   - Loại bỏ các đơn đã hoàn tất (status='completed')
   - Kiểm tra overlapping khoảng thời gian:
     ```
     if new_start < existing_end AND new_end > existing_start: 
         → Có xung đột!
     ```
   - Trả về True/False

3. **Tích hợp vào booking** - `book_car()` (lines 747-800):
   - Tính start_date, end_date từ số ngày
   - Gọi `check_booking_conflict()` để kiểm tra
   - Nếu có xung đột → Từ chối booking
   - Nếu OK → Lưu order với start_date, end_date

4. **Database schema** (lines 169-170):
   - Thêm cột `start_date DATETIME`
   - Thêm cột `end_date DATETIME`
   - Migration: `ensure_column()` thêm cột vào database cũ

#### Ví dụ:
```
Xe A được đặt từ 2026-04-28 đến 2026-04-30
Người khác cố gắng đặt từ 2026-04-29 đến 2026-05-01
→ Có xung đột (overlap) → Từ chối

Người khác cố gắng đặt từ 2026-05-01 đến 2026-05-03
→ Không xung đột → Cho phép
```

---

### 4️⃣ **LỌC DỮ LIỆU - TỰ ĐỘNG LOẠI BỎ KỲ TỰ NGUYỀN HIỂM**

#### ✅ Chặn các ký tự nguyền hiểm khi upload ảnh
- **Location**: `app.py` - Lines 498-514, 538-560
- **Function**: `validate_image_magic_bytes(file_stream)`
- **Features**:
  - Kiểm tra magic bytes (file header) để xác nhận loại file thực tế
  - Không cho phép file fake extension (ví dụ: file.exe đổi tên thành file.jpg)
  - Magic bytes hỗ trợ:
    - `\xFF\xD8\xFF` = JPEG
    - `\x89PNG` = PNG
    - `GIF8` = GIF

#### ✅ Xử lý dữ liệu đầu vào
- **Location**: `app.py` - Lines 55-66
- **Functions**:
  1. `sanitize_text(value, default='')` (Lines 55-58):
     - Loại bỏ tất cả HTML tags: `<[^>]*>`
     - Strip whitespace
     - Dùng cho: username, fullname, cccd, address, reason, v.v.
  
  2. `parse_int(value, default=0)` (Lines 60-66):
     - Xử lý input số an toàn
     - Loại bỏ ký tự không hợp lệ (comma, đ, v.v.)
     - Trả về số hợp lệ hoặc default

#### ✅ SQL Injection Prevention
- Sử dụng parameterized queries (?) ở tất cả nơi:
  ```python
  conn.execute("SELECT * FROM users WHERE id = ?", (id,))
  # KHÔNG dùng: f"SELECT * FROM users WHERE id = {id}"
  ```

#### ✅ Xử lý dữ liệu trong upload
- Line 504: Sử dụng `secure_filename()` từ werkzeug
- Line 505: Thêm timestamp vào filename để tránh collision
- Line 508: Kiểm tra magic bytes trước khi lưu file

---

### 5️⃣ **UPLOAD ẢNH - BẢNG TRẮNG EXTENSIONS**

#### ✅ Whitelist extensions được phép
- **Location**: `app.py` - Line 477
- **Extensions hợp lệ**: `{'png', 'jpg', 'jpeg', 'gif'}`
- **Kiểm tra**: `allowed_file()` function (lines 480-481)
- **Từ chối**: Bất kỳ file không có extension trong danh sách

#### ✅ Bảo mật file upload
- **Function**: `upload_file()` (lines 520-556)
- **Steps**:
  1. Kiểm tra file có trong request
  2. Kiểm tra filename không rỗng
  3. **Kiểm tra extension** (whitelist)
  4. **Kiểm tra magic bytes** (xác nhận loại file thực tế)
  5. Tạo thư mục uploads nếu chưa có
  6. Sử dụng `secure_filename()` để sanitize
  7. Thêm timestamp vào filename
  8. Lưu file vào thư mục an toàn

#### ✅ Từ chối tấn công file upload
- ✓ Không cho phép executable files (.exe, .sh, v.v.)
- ✓ Không cho phép scripts (.php, .jsp, v.v.)
- ✓ Kiểm tra loại file thực tế (magic bytes)
- ✓ Ngăn path traversal attack bằng `secure_filename()`

---

## 📋 DANH SÁCH THAY ĐỔI

### Thêm vào file `app.py`:

1. **Imports** (Line 6):
   ```python
   from datetime import datetime, timedelta
   ```

2. **Helper Functions**:
   - `calculate_rental_dates(days)` - Tính ngày booking
   - `check_booking_conflict(conn, vehicle_id, start_date, end_date)` - Kiểm tra xung đột
   - `validate_image_magic_bytes(file_stream)` - Kiểm tra loại file ảnh

3. **Database Schema**:
   - `start_date DATETIME` (lines 169)
   - `end_date DATETIME` (lines 170)
   - `ensure_column()` migration (auto-add nếu database cũ)

4. **API Updates**:
   - `book_car()` (lines 747-800) - Thêm conflict checking
   - `upload_file()` (lines 520-556) - Thêm magic bytes validation
   - Password handling - Sửa lỗi sanitize password

### Cải thiện bảo mật:
- ✅ Hash mật khẩu: `generate_password_hash()` + `check_password_hash()`
- ✅ Phân quyền: 3 nhóm (customer, owner, admin)
- ✅ Xung đột booking: Kiểm tra overlapping dates
- ✅ Lọc dữ liệu: HTML tag removal, input validation
- ✅ File upload: Extension whitelist + magic bytes check
- ✅ SQL Injection: Parameterized queries

---

## 🔍 KIỂM TRA CÁC YÊUWCẦU TRONG ẢNH

| Yêu cầu | Trạng thái | Chi tiết |
|---------|-----------|---------|
| Bảo mật mật khẩu - Pbkdf2:sha256 | ✅ ĐẠT | `generate_password_hash()` + `check_password_hash()` |
| Không lưu plaintext | ✅ ĐẠT | Tất cả mật khẩu được hash |
| 3 vai trò: Customer, Owner, Admin | ✅ ĐẠT | `normalize_role()` và phân quyền |
| Xử lý xung đột thời gian | ✅ ĐẠT | `check_booking_conflict()` + start/end dates |
| Lọc dữ liệu - HTML tag removal | ✅ ĐẠT | `sanitize_text()` |
| Lọc dữ liệu - Input validation | ✅ ĐẠT | `parse_int()` + parameterized queries |
| Upload ảnh - Whitelist | ✅ ĐẠT | `.png, .jpg, .jpeg, .gif` |
| Upload ảnh - Magic bytes | ✅ ĐẠT | `validate_image_magic_bytes()` |

---

## 🚀 SỬ DỤNG

Database sẽ tự động migrate khi app khởi động:
```python
# app.py sẽ tự động:
# 1. Tạo cơ sở dữ liệu (nếu chưa có)
# 2. Thêm start_date, end_date vào orders table (nếu chưa có)
# 3. Hash lại mật khẩu admin cũ (nếu plaintext)
```

---

**Ngày báo cáo**: 2026-04-28  
**Phiên bản**: 1.0  
**Trạng thái**: ✅ ĐÃ HOÀN THÀNH TẤT CẢ YÊU CẦU BẢO MẬT

