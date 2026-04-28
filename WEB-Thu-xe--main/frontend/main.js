let allVehicles = [];

window.onload = () => { load(); };

async function load() {
    try {
        // Try to load from cache first
        const cached = localStorage.getItem('vehicles_cache');
        if (cached) {
            allVehicles = JSON.parse(cached);
            displayData(allVehicles);
            updateUserUI();
            initSearch();
            // Refresh in background
            fetchFreshData();
        } else {
            await fetchFreshData();
        }
    } catch (e) { 
        console.error("Lỗi kết nối", e); 
        // Fallback to cached data if available
        const cached = localStorage.getItem('vehicles_cache');
        if (cached) {
            allVehicles = JSON.parse(cached);
            displayData(allVehicles);
        }
    }
}

async function fetchFreshData() {
    document.getElementById('loading').style.display = 'block';
    try {
        let res = await fetch('http://127.0.0.1:5000/cars');
        allVehicles = await res.json();
        localStorage.setItem('vehicles_cache', JSON.stringify(allVehicles));
        displayData(allVehicles);
        updateUserUI();
        initSearch();
    } finally {
        document.getElementById('loading').style.display = 'none';
    }
}

function initSearch() {
    const input = document.getElementById('search-input');
    const brand = document.getElementById('search-brand');
    const type = document.getElementById('search-type');
    const status = document.getElementById('search-status');
    const minPrice = document.getElementById('search-min-price');
    const maxPrice = document.getElementById('search-max-price');
    if (input) input.addEventListener('input', applySearch);
    if (brand) brand.addEventListener('input', applySearch);
    if (type) type.addEventListener('change', applySearch);
    if (status) status.addEventListener('change', applySearch);
    if (minPrice) minPrice.addEventListener('input', applySearch);
    if (maxPrice) maxPrice.addEventListener('input', applySearch);
}

function getSearchFilters() {
    const query = document.getElementById('search-input')?.value.trim().toLowerCase() || '';
    const brand = document.getElementById('search-brand')?.value.trim().toLowerCase() || '';
    const type = document.getElementById('search-type')?.value || 'all';
    const status = document.getElementById('search-status')?.value || 'all';
    const minPrice = document.getElementById('search-min-price')?.value.trim() || '';
    const maxPrice = document.getElementById('search-max-price')?.value.trim() || '';
    return { query, brand, type, status, minPrice, maxPrice };
}

async function applySearch() {
    try {
        const { query, brand, type, status, minPrice, maxPrice } = getSearchFilters();
        let params = [];
        if (query) params.push(`search=${encodeURIComponent(query)}`);
        if (brand) params.push(`brand=${encodeURIComponent(brand)}`);
        if (type && type !== 'all') params.push(`type=${encodeURIComponent(type)}`);
        if (status && status !== 'all') params.push(`status=${encodeURIComponent(status)}`);
        if (minPrice) params.push(`min_price=${encodeURIComponent(minPrice)}`);
        if (maxPrice) params.push(`max_price=${encodeURIComponent(maxPrice)}`);

        const queryString = params.length ? `?${params.join('&')}` : '';
        const res = await fetch(`http://127.0.0.1:5000/cars${queryString}`);
        const data = await res.json();
        displayData(data);
    } catch (error) {
        console.error('Lỗi tìm kiếm:', error);
        displayData(allVehicles);
    }
}

async function resetSearch() {
    const input = document.getElementById('search-input');
    const brand = document.getElementById('search-brand');
    const type = document.getElementById('search-type');
    const status = document.getElementById('search-status');
    const minPrice = document.getElementById('search-min-price');
    const maxPrice = document.getElementById('search-max-price');
    if (input) input.value = '';
    if (brand) brand.value = '';
    if (type) type.value = 'all';
    if (status) status.value = 'all';
    if (minPrice) minPrice.value = '';
    if (maxPrice) maxPrice.value = '';
    await load();
}

function displayData(data) {
    const approvedData = data.filter(x => x.is_approved === 1);
    const cars = approvedData.filter(x => x.type === 'car' || x.type === 'electric');
    const bikes = approvedData.filter(x => x.type === 'motorbike');
    render(cars, 'car-list');
    render(bikes, 'bike-list');
}

function render(list, id) {
    let html = '';
    list.forEach(x => {
        const isAvailable = x.status === 'available';
        const statusLabel = isAvailable ? 
            '<span style="color: #2ecc71; font-weight:bold;">Sẵn sàng</span>' : 
            '<span style="color: #e74c3c; font-weight:bold;">Đã thuê</span>';

        html += `
            <div class="card" style="border: ${isAvailable ? '1px solid #ddd' : '2px solid #e74c3c'}">
                <img src="${x.image_url}" onclick="showDetail(${x.id})" style="width:100%; height:180px; object-fit:cover; cursor:pointer;">
                <div style="padding:15px;">
                    <h3>${x.name}</h3>
                    <p>Trạng thái: ${statusLabel}</p>
                    <p>Giá: <b style="color:red;">${Number(x.price).toLocaleString()}đ</b></p>
                    <button class="btn-book" onclick="showDetail(${x.id})">
                        ${isAvailable ? 'Xem chi tiết' : 'Xem lịch đặt'}
                    </button>
                </div>
            </div>
        `;
    });
    document.getElementById(id).innerHTML = html;
}

let currentPrice = 0;
let currentVehicleId = 0;

function showDetail(id) {
    const v = allVehicles.find(x => x.id === id);
    currentVehicleId = id;
    currentPrice = Number(v.price);

    document.getElementById('dt-img').src = v.image_url;
    document.getElementById('dt-name').innerText = v.name;
    document.getElementById('dt-owner').innerText = v.owner_name || "Chưa cập nhật";
    document.getElementById('dt-odo').innerText = v.odo || 0;
    document.getElementById('dt-brand').innerText = v.brand || "Chưa rõ";
    document.getElementById('dt-price').innerText = currentPrice.toLocaleString();
    document.getElementById('dt-desc').innerText = v.description || "Không có mô tả.";
    
    const btn = document.getElementById('dt-btn-book');
    if(v.status === 'available') {
        btn.innerText = "Cho vào giỏ hàng (Thuê ngay)";
        btn.style.background = "linear-gradient(135deg, #2ecc71, #27ae60)";
    } else {
        btn.innerText = "Đặt lịch hẹn trước (Ưu tiên)";
        btn.style.background = "linear-gradient(135deg, #3498db, #2980b9)";
    }
    btn.onclick = () => addToCart();

    updateTotalPreview();
    document.getElementById('detail-modal').style.display = 'block';
}

function updateTotalPreview() {
    const days = document.getElementById('dt-days').value;
    document.getElementById('dt-total').innerText = (days * currentPrice).toLocaleString();
}

function closeModal(modalId) {
    document.getElementById(modalId).style.display = 'none';
}

async function addToCart() {
    const user = JSON.parse(localStorage.getItem('user_logged'));
    if(!user) {
        alert("Vui lòng đăng nhập!");
        return location.href = 'login.html';
    }

    const days = parseInt(document.getElementById('dt-days').value, 10) || 1;
    const payload = {
        user_id: user.id,
        vehicle_id: currentVehicleId,
        days,
        total_price: days * currentPrice
    };

    const v = allVehicles.find(x => x.id === currentVehicleId);
    if (!v) {
        return alert('Xe không hợp lệ. Vui lòng thử lại.');
    }

    const status = (v.status || '').toLowerCase();
    let endpoint = '/orders';
    let message = "Thành công! Bạn có thể kiểm tra trong Giỏ hàng.";

    if (status !== 'available') {
        endpoint = '/appointments';
        message = "Đặt lịch hẹn thành công! Xe sẽ ưu tiên cho bạn khi có sẵn.";
    }

    const res = await fetch(`http://127.0.0.1:5000${endpoint}`, {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(payload)
    });

    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
        alert(data.message || 'Lỗi khi thêm vào giỏ hàng. Vui lòng thử lại.');
        return;
    }

    alert(message);
    closeModal('detail-modal');
    load();
}

function updateUserUI() {
    const user = JSON.parse(localStorage.getItem('user_logged'));
    const navMenu = document.getElementById('nav-menu');
    
    if (user && navMenu) {
        const role = (user.role || 'customer').toLowerCase();
        let extraTools = role === 'admin'
            ? `<a href="admin.html" style="color: #f1c40f;">⚙️ Quản trị</a>`
            : (role === 'owner' ? `<a href="#" onclick="showUploadModal()" style="color: #2ecc71;">+ Đăng tin</a>` : '');

        navMenu.innerHTML = `
            <a href="index.html">Trang chủ</a>
            <a href="profile.html" style="color: #fff;">Tài khoản</a>
            ${extraTools}
            <a href="cart.html" onclick="renderCart()" style="color: #f39c12; font-weight:bold;">🛒 Giỏ hàng / Lịch hẹn</a>
            <span style="display:flex; align-items:center; gap: 15px; margin-left:20px;">
                <span style="color:#eee;">Chào, ${user.fullname}</span>
                <a href="#" onclick="logout()" style="background: #e74c3c; padding: 5px 10px; border-radius: 4px;">Thoát</a>
            </span>
        `;
    }
}

function showUploadModal() { document.getElementById('upload-modal').style.display = 'block'; }

async function submitVehicle() {
    const name = document.getElementById('up-name').value.trim();
    const price = document.getElementById('up-price').value.trim();
    const type = document.getElementById('up-type').value;
    
    const owner = document.getElementById('up-owner').value.trim();
    const odo = document.getElementById('up-odo').value.trim();
    const brand = document.getElementById('up-brand').value.trim();
    const desc = document.getElementById('up-desc').value.trim();

    let imageUrl = document.getElementById('up-image-url').value.trim();
    const fileInput = document.getElementById('up-image-file');
    const user = JSON.parse(localStorage.getItem('user_logged'));

    if(!name || !price) return alert("Vui lòng nhập đủ Tên và Giá!");
    if(isNaN(price) || price <= 0) return alert("Vui lòng nhập giá hợp lệ!");
    if(!imageUrl && fileInput.files.length === 0) return alert("Vui lòng chọn ảnh hoặc dán link ảnh sản phẩm.");
    if (!user || (user.role || 'customer') !== 'owner') return alert('Chỉ tài khoản chủ xe mới được đăng tin.');

    if (fileInput.files.length > 0) {
        const formData = new FormData();
        formData.append('file', fileInput.files[0]);
        try {
            console.log('Uploading file:', fileInput.files[0].name);
            const upRes = await fetch('http://127.0.0.1:5000/upload', { method: 'POST', body: formData });
            const upData = await upRes.json();
            console.log('Upload response:', upRes.status, upData);
            if (!upRes.ok) return alert(upData.message || "Lỗi tải ảnh!");
            imageUrl = upData.url;
            console.log('Image uploaded:', imageUrl);
        } catch (e) { 
            console.error('Upload error:', e);
            return alert("Lỗi tải ảnh: " + e.message); 
        }
    }

    const vehicleData = {
        name, price, type, image_url: imageUrl,
        owner_name: owner, odo: odo, brand: brand, description: desc,
        status: 'available', is_approved: 0,
        submitted_by_role: user.role || 'customer'
    };

    try {
        console.log('Submitting vehicle:', vehicleData);
        const res = await fetch('http://127.0.0.1:5000/cars', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(vehicleData)
        });
        console.log('Vehicle submission response:', res.status);
        if(res.ok) {
            alert("Đã gửi tin! Chờ Admin phê duyệt.");
            // Reset form
            document.getElementById('up-name').value = '';
            document.getElementById('up-price').value = '';
            document.getElementById('up-owner').value = '';
            document.getElementById('up-brand').value = '';
            document.getElementById('up-odo').value = '';
            document.getElementById('up-desc').value = '';
            document.getElementById('up-image-url').value = '';
            document.getElementById('up-image-file').value = '';
            closeModal('upload-modal');
            load();
        } else {
            const errData = await res.json();
            alert(errData.message || "Lỗi gửi tin!");
        }
    } catch (error) { 
        console.error('Submit error:', error);
        alert("Lỗi server: " + error.message); 
    }
}

// ================= CODE GIỎ HÀNG (CART) =================
async function renderCart() {
    const user = JSON.parse(localStorage.getItem('user_logged'));
    if(!user) return;
    
    let res = await fetch(`http://127.0.0.1:5000/orders/${user.id}`);
    let data = await res.json();
    
    let html = data.map(item => {
        const canModify = item.payment_status === 'pending';
        const statusText = item.payment_status === 'paid' ? 'Đã thanh toán - Đang thuê' : 'Chờ thanh toán';
        const statusColor = item.payment_status === 'paid' ? '#27ae60' : '#f39c12';
        
        return `
        <div style="display:flex; align-items:center; border-bottom:1px solid #ddd; padding:15px 0;">
            <img src="${item.image_url || 'https://via.placeholder.com/100'}" style="width:100px; height:70px; object-fit:cover; border-radius:5px;">
            <div style="flex:1; margin-left:20px;">
                <h4 style="margin:0;">${item.name}</h4>
                <p style="margin:5px 0 0 0; font-size:14px; color:${statusColor};">Trạng thái: ${statusText}</p>
            </div>
            <div>
                Số ngày: ${canModify ? `<input type="number" value="${item.days}" min="1" 
                    onchange="updateOrder(${item.id}, this.value, ${item.price_per_day})" style="width:50px; padding:5px;">` : item.days}
            </div>
            <div style="margin-left:20px; font-weight:bold; color:#e74c3c; width:120px;">
                ${Number(item.days * item.price_per_day).toLocaleString()}đ
            </div>
            ${canModify ? `<button onclick="deleteOrder(${item.id})" style="background:#e74c3c; color:white; border:none; padding:5px 10px; cursor:pointer; border-radius:4px;">❌ Hủy</button>` : ''}
        </div>
        `;
    }).join('');
    
    if(!html) html = '<p style="text-align:center; padding:20px;">Chưa có xe nào trong danh sách đặt.</p>';
    
    document.getElementById('cart-container').innerHTML = html;
    document.getElementById('cart-modal').style.display = 'block';
}

async function updateOrder(id, newDays, price) {
    try {
        const res = await fetch(`http://127.0.0.1:5000/orders/${id}`, {
            method: 'PUT',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ days: newDays, total_price: newDays * price })
        });
        if(res.ok) {
            renderCart(); // Reload giỏ hàng
        } else {
            const data = await res.json();
            alert(data.message || "Không thể cập nhật đơn hàng.");
        }
    } catch(e) {
        alert("Lỗi cập nhật: " + e.message);
    }
}

async function deleteOrder(id) {
    if(confirm("Bạn muốn hủy đơn hàng này?")) {
        try {
            const res = await fetch(`http://127.0.0.1:5000/orders/${id}`, { method: 'DELETE' });
            if(res.ok) {
                renderCart();
            } else {
                const data = await res.json();
                alert(data.message || "Không thể hủy đơn hàng.");
            }
        } catch(e) {
            alert("Lỗi hủy đơn: " + e.message);
        }
    }
}

function logout() {
    localStorage.clear();
    location.reload();
}