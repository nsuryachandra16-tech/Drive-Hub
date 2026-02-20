import os
import uuid
import random
from datetime import datetime
from flask import Flask, render_template_string, request, jsonify, session
from werkzeug.utils import secure_filename
import xml.etree.ElementTree as ET

# ==========================================
# 1. CONFIGURATION
# ==========================================
app = Flask(__name__)
app.secret_key = 'TITANIUM_PAYMASTER_KEY_V16'
app.config['UPLOAD_FOLDER'] = 'static/uploads'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024

if not os.path.exists(app.config['UPLOAD_FOLDER']):
    os.makedirs(app.config['UPLOAD_FOLDER'])

DB_FILES = {
    'users': 'users.xml',
    'vehicles': 'vehicles.xml',
    'rentals': 'rentals.xml'
}

# ==========================================
# 2. XML DATABASE ENGINE
# ==========================================

def save_db(key, data):
    root = ET.Element(key)

    for item in data:
        record = ET.SubElement(root, "record")
        for k, v in item.items():
            child = ET.SubElement(record, k)
            child.text = str(v)

    tree = ET.ElementTree(root)
    tree.write(DB_FILES[key], encoding='utf-8', xml_declaration=True)


def load_db(key):
    if not os.path.exists(DB_FILES[key]):
        return []

    tree = ET.parse(DB_FILES[key])
    root = tree.getroot()

    data = []
    for record in root.findall("record"):
        entry = {}
        for child in record:
            value = child.text.strip() if child.text else ""
            entry[child.tag] = value
        data.append(entry)

    return data


def repair_db():
    # USERS
    if not os.path.exists(DB_FILES['users']):
        users = [
            {"id": "1", "name": "Boss Surya", "email": "admin@rental.com", "password": "admin", "role": "admin"},
            {"id": "2", "name": "Client One", "email": "user@gmail.com", "password": "user", "role": "user"}
        ]
        save_db('users', users)

    # VEHICLES
    if not os.path.exists(DB_FILES['vehicles']):
        vehicles = [{
            "id": "101",
            "model": "Tesla Model S",
            "price": "1200",
            "status": "Available",
            "health": "100",
            "kms": "5000",
            "fuel": "Electric",
            "year": "2024",
            "transmission": "Auto",
            "seats": "5",
            "image": ""
        }]
        save_db('vehicles', vehicles)

    # RENTALS
    if not os.path.exists(DB_FILES['rentals']):
        save_db('rentals', [])

repair_db()


# ==========================================
# 3. BACKEND ROUTES (UNCHANGED LOGIC)
# ==========================================

@app.route('/')
def root():
    return render_template_string(UI_CODE)

@app.route('/api/auth/login', methods=['POST'])
def login():
    data = request.json
    users = load_db('users')

    user = next((u for u in users if u['email'] == data['email'] and u['password'] == data['password']), None)

    if user:
        session['user'] = user
        return jsonify({"status": "success", "user": user})

    return jsonify({"status": "error", "message": "Invalid Credentials"})


@app.route('/api/auth/register', methods=['POST'])
def register():
    data = request.json
    users = load_db('users')

    if any(u['email'] == data['email'] for u in users):
        return jsonify({"status": "error", "message": "Email exists"})

    users.append({
        "id": str(len(users) + 1),
        "name": data['name'],
        "email": data['email'],
        "password": data['password'],
        "role": "user"
    })

    save_db('users', users)
    return jsonify({"status": "success"})




@app.route('/api/data/sync')
def sync():
    user = session.get('user')
    if not user:
        return jsonify({"status": "error"}), 401

    vehicles = load_db('vehicles')
    rentals = load_db('rentals')

    # 🔥 AUTO MAINTENANCE CHECK
    now = datetime.now()

    for v in vehicles:
        if v.get('status') == 'Maintenance' and v.get('maintenance_start'):
            try:
                start_time = datetime.strptime(v['maintenance_start'], "%Y-%m-%d %H:%M:%S")

                if now - start_time >= timedelta(hours=1):
                    v['health'] = "100"
                    v['status'] = "Available"
                    v.pop('maintenance_start', None)

            except:
                pass

    save_db('vehicles', vehicles)
    # 🔥 END MAINTENANCE CHECK

    if user['role'] == 'admin':
        revenue = sum(float(r.get('total', 0)) for r in rentals)
        active = len([r for r in rentals if r.get('status') == 'Active'])
        fleet = len(vehicles)
        kms = sum(int(v.get('kms', 0)) for v in vehicles)

        response = {
            "role": "admin",
            "vehicles": vehicles,
            "rentals": rentals,
            "stats": {
                "revenue": revenue,
                "active": active,
                "fleet": fleet,
                "kms": kms
            }
        }
    else:
        my_rentals = [r for r in rentals if r.get('user_email') == user['email']]
        response = {
            "role": "user",
            "vehicles": vehicles,
            "rentals": my_rentals,
            "stats": {}
        }

    return jsonify({"status": "success", "data": response})

@app.route('/api/vehicle/manage', methods=['POST'])
def manage_vehicle():
    if not session.get('user') or session['user']['role'] != 'admin':
        return jsonify({"error": "Unauthorized"}), 403

    v_id = request.form.get('id')
    vehicles = load_db('vehicles')

    v_data = {
        "model": request.form.get('model'),
        "price": str(request.form.get('price')),
        "year": request.form.get('year', '2024'),
        "fuel": request.form.get('fuel', 'Petrol'),
        "transmission": request.form.get('transmission', 'Auto'),
        "seats": request.form.get('seats', '4'),
        "health": request.form.get('health', '100'),
        "kms": request.form.get('kms', '0'),
        "status": request.form.get('status', 'Available'),
        "image": ""
    }

    f = request.files.get('image')
    if f:
        fname = secure_filename(f"{uuid.uuid4()}_{f.filename}")
        f.save(os.path.join(app.config['UPLOAD_FOLDER'], fname))
        v_data['image'] = fname

    if v_id and v_id != 'null':
        for v in vehicles:
            if str(v.get('id')).strip() == str(v_id).strip():
                v.update(v_data)
    else:
        v_data['id'] = str(uuid.uuid4().int)[:6]
        vehicles.append(v_data)

    save_db('vehicles', vehicles)
    return jsonify({"status": "success"})


@app.route('/api/vehicle/delete', methods=['POST'])
def delete_vehicle():
    if not session.get('user') or session['user']['role'] != 'admin':
        return jsonify({"error": "Unauthorized"}), 403

    v_id = request.json.get('id')
    vehicles = load_db('vehicles')

    vehicles = [v for v in vehicles if str(v.get('id')).strip() != str(v_id).strip()]

    save_db('vehicles', vehicles)
    return jsonify({"status": "success"})


@app.route('/api/rent/create', methods=['POST'])
def create_rental():
    data = request.json
    user = session.get('user')

    vehicles = load_db('vehicles')
    rentals = load_db('rentals')

    target = next((v for v in vehicles if str(v.get('id')) == str(data['v_id'])), None)

    if not target or target.get('status') != 'Available':
        return jsonify({"error": "Unavailable"})

    target['status'] = 'Rented'

    tx_id = f"TX-{uuid.uuid4().hex[:8].upper()}"

    rentals.append({
        "tx_id": tx_id,
        "user_email": user['email'],
        "user_name": user['name'],
        "vehicle_id": data['v_id'],
        "vehicle_model": target['model'],
        "price": str(data['price']),
        "total": str(data['price']),
        "payment_method": "UPI",
        "payment_id": data.get('pay_id', 'N/A'),
        "status": "Active",
        "date": datetime.now().strftime("%Y-%m-%d %H:%M")
    })

    save_db('vehicles', vehicles)
    save_db('rentals', rentals)

    return jsonify({
        "status": "success",
        "tx_id": tx_id,
        "date": datetime.now().strftime("%Y-%m-%d %H:%M")
    })


@app.route('/api/rent/return', methods=['POST'])
def process_return():
    if not session.get('user') or session['user']['role'] != 'admin':
        return jsonify({"error": "Unauthorized"}), 403

    data = request.json
    rentals = load_db('rentals')
    vehicles = load_db('vehicles')

    rental = next((r for r in rentals if r.get('tx_id') == data['tx_id']), None)

    if not rental:
        return jsonify({"error": "Not found"})

    vehicle = next((v for v in vehicles if str(v.get('id')) == str(rental['vehicle_id'])), None)

    kms = int(data.get('kms', 0))
    fine = float(data.get('fine', 0))

    rental['status'] = 'Closed'
    rental['total'] = str(float(rental.get('price', 0)) + fine)
    rental['return_date'] = datetime.now().strftime("%Y-%m-%d %H:%M")

    if vehicle:
      new_kms = int(vehicle.get('kms', 0)) + kms
      new_health = max(0, int(vehicle.get('health', 100)) - int(kms/50))

      vehicle['kms'] = str(new_kms)
      vehicle['health'] = str(new_health)

      if new_health < 40:
         vehicle['status'] = 'Maintenance'
         vehicle['maintenance_start'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
      else:
         vehicle['status'] = 'Available'

    save_db('rentals', rentals)
    save_db('vehicles', vehicles)

    return jsonify({"status": "success"})


@app.route('/api/auth/logout', methods=['POST'])
def logout():
    session.clear()
    return jsonify({"status": "success"})



# ==========================================
# YOUR FULL UI_CODE GOES HERE
# ==========================================

UI_CODE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>Drive Hub</title>
    <link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&display=swap" rel="stylesheet">
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
    <script src="https://cdn.jsdelivr.net/npm/sweetalert2@11"></script>
    <script src="https://cdn.jsdelivr.net/npm/canvas-confetti@1.6.0/dist/confetti.browser.min.js"></script>
    <style>
        :root { --p: #4F46E5; --p-dark: #3730A3; --bg: #F8FAFC; --txt: #0F172A; --border: #E2E8F0; }
        * { box-sizing: border-box; font-family: 'Plus Jakarta Sans', sans-serif; }
        body { margin: 0; background: var(--bg); color: var(--txt); height: 100vh; display: flex; }
        .input-error {
    border-color: #EF4444 !important;
    box-shadow: 0 0 0 2px rgba(239,68,68,0.2);
}
        
        /* AUTH PAGE - CINEMATIC */
        .auth-container { position: fixed; inset: 0; background: white; z-index: 9999; display: flex; }
        .auth-left { flex: 1.2; background: linear-gradient(135deg, #1e1b4b, #312e81); color: white; display: flex; flex-direction: column; justify-content: center; padding: 100px; position: relative; overflow: hidden; }
        .auth-left::before { content: ''; position: absolute; top:0; left:0; width:100%; height:100%; background: url('https://images.unsplash.com/photo-1568605117036-5fe5e7bab0b7?q=80&w=2070') center/cover; opacity: 0.3; mix-blend-mode: overlay; }
        .auth-content { position: relative; z-index: 2; }
        .auth-content h1 { font-size: 4rem; line-height: 1.1; margin-bottom: 25px; font-weight: 800; letter-spacing: -1px; }
        .highlight { color: #818CF8; background: rgba(255,255,255,0.1); padding: 0 10px; border-radius: 8px; }
        .auth-right { flex: 1; display: flex; align-items: center; justify-content: center; background: #fff; }
        .auth-box { width: 420px; padding: 50px; }
        
        .input-group { margin-bottom: 20px; }
        .input-group label { display: block; font-size: 0.85rem; font-weight: 700; margin-bottom: 8px; color: #475569; }
        .inp { width: 100%; padding: 14px; border: 1px solid var(--border); border-radius: 12px; font-size: 1rem; transition: 0.2s; background: #F8FAFC; }
        .inp:focus { border-color: var(--p); background: white; outline: none; box-shadow: 0 0 0 3px rgba(79, 70, 229, 0.1); }
        
        /* APP LAYOUT */
        .sidebar { width: 280px; background: white; border-right: 1px solid var(--border); padding: 30px; display: flex; flex-direction: column; }
        .brand { font-size: 1.6rem; font-weight: 800; color: var(--txt); display: flex; align-items: center; gap: 10px; margin-bottom: 50px; }
        .brand span { color: var(--p); }
        
        .nav-item { padding: 14px 16px; margin-bottom: 8px; border-radius: 12px; color: #64748B; cursor: pointer; font-weight: 600; display: flex; gap: 12px; align-items: center; transition: 0.2s; }
        .nav-item:hover { background: #F1F5F9; color: var(--txt); }
        .nav-item.active { background: #EEF2FF; color: var(--p); }
        
        .main { flex: 1; padding: 40px; overflow-y: auto; background: var(--bg); }
        .header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 30px; }
        .pg-title { font-size: 2rem; font-weight: 800; letter-spacing: -0.5px; }
        
        /* CARDS */
        .stat-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 24px; margin-bottom: 40px; }
        .stat-card { background: white; padding: 24px; border-radius: 20px; border: 1px solid var(--border); box-shadow: 0 4px 6px -1px rgba(0,0,0,0.02); }
        .stat-lbl { font-size: 0.75rem; font-weight: 800; color: #94A3B8; text-transform: uppercase; letter-spacing: 0.5px; }
        .stat-val { font-size: 2rem; font-weight: 800; margin-top: 5px; color: var(--txt); }

        .fleet-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(320px, 1fr)); gap: 30px; }
        .car-card { background: white; border-radius: 24px; border: 1px solid var(--border); overflow: hidden; transition: 0.3s; position: relative; }
        .car-card:hover { transform: translateY(-5px); box-shadow: 0 20px 30px -10px rgba(0,0,0,0.1); }
        .car-img { width: 100%; height: 220px; object-fit: cover; background: #F1F5F9; }
        .car-body { padding: 24px; }
        .tags { display: flex; gap: 8px; margin-bottom: 15px; flex-wrap: wrap; }
        .tag { padding: 4px 10px; border-radius: 6px; background: #F8FAFC; color: #64748B; font-size: 0.75rem; font-weight: 700; border: 1px solid #F1F5F9; }
        
        .badge { padding: 6px 12px; border-radius: 30px; font-size: 0.75rem; font-weight: 800; color: white; position: absolute; top: 15px; right: 15px; box-shadow: 0 4px 6px rgba(0,0,0,0.1); }
        .st-Available { background: #10B981; } .st-Rented { background: #EF4444; } .st-Maintenance { background: #F59E0B; }
        
        .btn { padding: 12px 24px; border: none; border-radius: 12px; font-weight: 700; cursor: pointer; transition: 0.2s; font-size: 0.95rem; }
        .btn-p { background: var(--p); color: white; } .btn-p:hover { background: var(--p-dark); box-shadow: 0 4px 12px rgba(79, 70, 229, 0.3); }
        .btn-o { background: white; border: 1px solid var(--border); color: #64748B; } .btn-o:hover { border-color: #94A3B8; }
        .btn-d { background: #FEF2F2; color: #EF4444; padding: 10px; border-radius: 10px; }

        /* TABLES */
        .tbl { width: 100%; border-collapse: collapse; background: white; border-radius: 16px; overflow: hidden; border: 1px solid var(--border); }
        .tbl th { background: #F8FAFC; padding: 16px; text-align: left; font-size: 0.8rem; font-weight: 700; color: #64748B; text-transform: uppercase; }
        .tbl td { padding: 16px; border-bottom: 1px solid #F1F5F9; color: #334155; font-size: 0.9rem; }
        .tbl tr:last-child td { border-bottom: none; }

        /* MODALS */
        .modal { position: fixed; inset: 0; background: rgba(0,0,0,0.6); backdrop-filter: blur(8px); display: none; align-items: center; justify-content: center; z-index: 2000; }
        .modal.active { display: flex; animation: fadeUp 0.3s ease; }
        @keyframes fadeUp { from { opacity: 0; transform: translateY(20px); } to { opacity: 1; transform: translateY(0); } }
        .modal-box { background: white; width: 500px; padding: 40px; border-radius: 30px; box-shadow: 0 25px 50px -12px rgba(0,0,0,0.25); }
        
        .receipt { background: #F8FAFC; padding: 20px; border: 1px dashed var(--border); border-radius: 12px; margin-bottom: 20px; font-family: monospace; font-size: 0.9rem; }
        .receipt div { display: flex; justify-content: space-between; margin-bottom: 5px; }

        .hidden { display: none !important; }
        #qr-ph {
    animation: pulseQR 2s infinite;
}
@keyframes pulseQR {
    0% { box-shadow: 0 0 0px #4F46E5; }
    50% { box-shadow: 0 0 20px #4F46E5; }
    100% { box-shadow: 0 0 0px #4F46E5; }
}

    </style>
</head>
<body>

    <div id="auth" class="auth-container">
        <div class="auth-left">
            <div class="auth-content">
                <h1>"The Road is Open.<br> <span class="highlight">Drive the Future.</span>"</h1>
                <p style="font-size: 1.3rem; opacity: 0.9; margin-top: 20px;">Select your role to access the premium fleet.</p>
            </div>
        </div>
        <div class="auth-right">
            <div class="auth-box">
                <div style="text-align: center; margin-bottom: 40px;">
                    <i class="fas fa-layer-group" style="font-size: 3rem; color: var(--p);"></i>
                    <h2 style="margin-top: 10px;">Welcome Back</h2>
                </div>
                
                <div id="login-form">
                    <div class="input-group">
                        <label>Email Address</label>
                        <input id="l-email" class="inp" placeholder="admin@rental.com">
                    </div>
                    <div class="input-group">
                        <label>Password</label>
                        <input id="l-pass" type="password" class="inp" placeholder="••••••••">
                    </div>
                    <button class="btn btn-p" style="width:100%" onclick="login()"> 
                    Access Dashboard
                    </button>
                    <p style="text-align:center; margin-top:20px; color:#64748B; cursor:pointer;" onclick="toggleAuth()">Create an account</p>
                </div>

                <div id="reg-form" class="hidden">
                    <div class="input-group"><label>Full Name</label><input id="r-name" class="inp"></div>
                    <div class="input-group"><label>Email</label><input id="r-email" class="inp"></div>
                    <div class="input-group"><label>Password</label><input id="r-pass" type="password" class="inp"></div>
                    <button class="btn btn-p" style="width:100%" onclick="register()">Create Account</button>
                    <p style="text-align:center; margin-top:20px; color:#64748B; cursor:pointer;" onclick="toggleAuth()">Back to Login</p>
                </div>
            </div>
        </div>
    </div>

    <div id="app" class="hidden" style="width:100%; height:100%; display:flex;">
        <aside class="sidebar">
            <div class="brand"><i class="fas fa-layer-group"></i> Drive<span>Hub</span></div>
            
            <div id="nav-admin" class="hidden">
                <div class="nav-item active" onclick="nav('dash', this)"><i class="fas fa-chart-pie"></i> Mission Control</div>
                <div class="nav-item" onclick="nav('fleet', this)"><i class="fas fa-car-side"></i> Fleet Command</div>
                <div class="nav-item" onclick="nav('ledger', this)"><i class="fas fa-file-invoice"></i> Ledger</div>
            </div>

            <div id="nav-user" class="hidden">
                <div class="nav-item active" onclick="nav('garage', this)"><i class="fas fa-warehouse"></i> My Garage</div>
                <div class="nav-item" onclick="nav('fleet', this)"><i class="fas fa-search"></i> Browse Fleet</div>
            </div>

            <div style="margin-top:auto;">
                <div style="display:flex; align-items:center; gap:12px; margin-bottom:20px; padding: 12px; background: #F8FAFC; border-radius: 12px;">
                    <div style="width:40px; height:40px; background:var(--p); border-radius:50%; display:flex; align-items:center; justify-content:center; font-weight:700; color:white;">U</div>
                    <div><div id="u-name" style="font-weight:700; font-size:0.9rem;">User</div><div id="u-role" style="font-size:0.75rem; color:#94A3B8; text-transform: uppercase;">Role</div></div>
                </div>
                <button class="btn btn-o" style="width:100%" onclick="logout()">Sign Out</button>
            </div>
        </aside>

        <main class="main">
            <div id="view-dash" class="hidden">
                <div class="header"><div class="pg-title">Mission Control</div></div>
                <div class="stat-grid">
                    <div class="stat-card"><div class="stat-lbl">Total Revenue</div><span class="stat-val" id="st-rev">₹0</span></div>
                    <div class="stat-card"><div class="stat-lbl">Active Missions</div><span class="stat-val" id="st-act">0</span></div>
                    <div class="stat-card"><div class="stat-lbl">Fleet Size</div><span class="stat-val" id="st-flt">0</span></div>
                    <div class="stat-card"><div class="stat-lbl">Total Distance</div><span class="stat-val" id="st-kms">0 km</span></div>
                </div>
                <h3 style="margin-bottom:20px;">Pending Returns</h3>
                <div id="active-list" style="display:grid; gap:15px;"></div>
            </div>

            <div id="view-garage" class="hidden">
                <div class="header"><div class="pg-title">My Garage</div></div>
                <div id="my-rentals" style="display:grid; gap:20px;"></div>
            </div>

            <div id="view-fleet" class="hidden">
                <div class="header">
                    <div class="pg-title">Fleet Command</div>
                    <button id="btn-add" class="btn btn-p hidden" onclick="openModal('mod-add')"><i class="fas fa-plus"></i> Add Vehicle</button>
                </div>
                <div id="fleet-grid" class="fleet-grid"></div>
            </div>

            <div id="view-ledger" class="hidden">
                <div class="header"><div class="pg-title">Transaction Ledger</div></div>
                <table class="tbl">
                    <thead><tr><th>TX ID</th><th>User</th><th>Vehicle</th><th>Amount</th><th>Status</th></tr></thead>
                    <tbody id="ledger-body"></tbody>
                </table>
            </div>
        </main>
    </div>

    <div id="mod-add" class="modal"><div class="modal-box">
        <h2 style="margin-bottom:25px;">Register Vehicle</h2>
        <div class="input-group"><label>Model Name</label><input id="mv-model" class="inp" placeholder="e.g. Porsche 911"></div>
        <div style="display:grid; grid-template-columns: 1fr 1fr; gap:15px;">
            <div class="input-group"><label>Price / Hr</label><input id="mv-price" type="number" class="inp"></div>
            <div class="input-group"><label>Year</label><input id="mv-year" type="number" class="inp" value="2024"></div>
        </div>
        <div style="display:grid; grid-template-columns: 1fr 1fr 1fr; gap:15px;">
            <div class="input-group"><label>Fuel</label>
                <select id="mv-fuel" class="inp"><option>Petrol</option><option>Electric</option><option>Diesel</option></select>
            </div>
            <div class="input-group"><label>Trans.</label>
                <select id="mv-trans" class="inp"><option>Auto</option><option>Manual</option></select>
            </div>
            <div class="input-group"><label>Seats</label><input id="mv-seats" type="number" class="inp" value="4"></div>
        </div>
        <div class="input-group"><label>Image</label><input id="mv-img" type="file" class="inp"></div>
        <button class="btn btn-p" style="width:100%" onclick="saveVehicle()">Add to Fleet</button>
        <button class="btn btn-o" style="width:100%; margin-top:10px;" onclick="closeAll()">Cancel</button>
    </div></div>

    <div id="mod-rent" class="modal"><div class="modal-box">
        <h2 style="margin-bottom:10px;">Secure Checkout</h2>
        <p id="rent-info" style="color:#64748B; margin-bottom:20px;"></p>
        
        <div style="display:flex; gap:10px; margin-bottom:20px;">
            <div style="flex:1; text-align:center;">
                <img id="qr-ph" src="" style="width:140px; border-radius:10px; border:1px solid #eee;">
                <div style="font-size:0.8rem; margin-top:5px; color:#64748B;">Scan UPI</div>
                <div id="final-amt" style="margin-top:8px; font-weight:700;"></div>

            </div>
            <div style="flex:1;">
                <div class="input-group">
    <label>Card / UPI ID</label>
    <input id="pay-id" class="inp" placeholder="user@okhdfcbank">
    <div id="pay-error" style="color:#EF4444; font-size:0.8rem; margin-top:6px; display:none;">
        Invalid UPI ID
    </div>
</div>

                <div class="input-group">
    <label>Coupon</label>
    <div style="display:flex; gap:8px;">
        <input id="pay-coup" class="inp" placeholder="Optional">
        <button class="btn btn-o" onclick="applyCoupon()">Apply</button>
    </div>
</div>

            </div>
        </div>
        
        <button class="btn btn-p" style="width:100%" onclick="confirmRent()">Confirm Payment</button>
        <button class="btn btn-o" style="width:100%; margin-top:10px;" onclick="closeAll()">Cancel</button>
    </div></div>

    <div id="mod-success" class="modal"><div class="modal-box" style="text-align:center;">
        <div style="font-size:4rem; color:#10B981; margin-bottom:10px;"><i class="fas fa-check-circle"></i></div>
        <h2>Payment Verified!</h2>
        <p style="color:#64748B; margin-bottom:20px;">Your vehicle has been unlocked.</p>
        <div class="receipt" id="receipt-box"></div>
        <button class="btn btn-p" onclick="closeAll()">Close & Drive</button>
    </div></div>
    <div id="mod-processing" class="modal">
        <div class="modal-box" style="text-align:center;">
    
    <div style="font-size:3rem; margin-bottom:15px;">
      <i class="fas fa-lock" style="color:#4F46E5;"></i>
    </div>

    <h2>Securing Payment</h2>
    <p style="color:#64748B; margin-bottom:20px;">
      Locking amount & verifying transaction...
    </p>

    <div style="height:8px; background:#E5E7EB; border-radius:10px; overflow:hidden;">
      <div id="pay-progress"
           style="width:0%; height:100%; 
           background:linear-gradient(90deg,#4F46E5,#6366F1);
           transition:0.4s;">
      </div>
    </div>

    <div style="margin-top:15px; font-size:0.85rem; color:#94A3B8;">
      Please do not close this window
    </div>

  </div>
</div>


    <div id="mod-ret" class="modal"><div class="modal-box">
        <h3>Vehicle Check-in</h3>
        <div class="input-group"><label>Kilometers Driven</label><input id="ret-kms" type="number" class="inp"></div>
        <div class="input-group"><label>Damage Fine (₹)</label><input id="ret-fine" type="number" class="inp" value="0"></div>
        <button class="btn btn-p" style="width:100%" onclick="processReturn()">Complete Return</button>
        <button class="btn btn-o" style="width:100%; margin-top:10px;" onclick="closeAll()">Cancel</button>
    </div></div>

    <script>
        let curV=null, curTx=null, role=null;
        let finalAmount = 0;

        function toggleAuth() { document.getElementById('login-form').classList.toggle('hidden'); document.getElementById('reg-form').classList.toggle('hidden'); }

        async function login() {
            const res = await fetch('/api/auth/login', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({email:document.getElementById('l-email').value, password:document.getElementById('l-pass').value})});
            const d = await res.json();
            if(d.status==='success') init(d.user); else Swal.fire('Error', d.message, 'error');
        }

        async function register() {
            const res = await fetch('/api/auth/register', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({name:document.getElementById('r-name').value, email:document.getElementById('r-email').value, password:document.getElementById('r-pass').value})});
            const d = await res.json();
            if(d.status==='success') { Swal.fire('Success', 'Login now', 'success'); toggleAuth(); } else Swal.fire('Error', d.message, 'error');
        }

        function init(user) {
            role = user.role;
            document.getElementById('auth').classList.add('hidden');
            document.getElementById('app').classList.remove('hidden');
            document.getElementById('u-name').innerText = user.name;
            document.getElementById('u-role').innerText = user.role.toUpperCase();

            if(role === 'admin') {
                document.getElementById('nav-admin').classList.remove('hidden');
                document.getElementById('btn-add').classList.remove('hidden');
                nav('dash', document.querySelector('#nav-admin .nav-item'));
            } else {
                document.getElementById('nav-user').classList.remove('hidden');
                nav('garage', document.querySelector('#nav-user .nav-item'));
            }
            sync();
        }

        async function sync() {
            const res = await fetch('/api/data/sync');
            const d = await res.json();
            const data = d.data;

            // RENDER FLEET
            document.getElementById('fleet-grid').innerHTML = data.vehicles.map(v => `
                <div class="car-card">
                    <span class="badge st-${v.status}">${v.status}</span>
                    <img class="car-img" src="${v.image ? '/static/uploads/'+v.image : 'https://placehold.co/400x250'}">
                    <div class="car-body">
                        <div style="display:flex; justify-content:space-between; align-items:start;">
                            <div>
                                <h3 style="margin:0 0 5px 0; font-size:1.2rem;">${v.model}</h3>
                                <div class="tags">
                                    <span class="tag"><i class="fas fa-calendar"></i> ${v.year}</span>
                                    <span class="tag"><i class="fas fa-cog"></i> ${v.transmission}</span>
                                    <span class="tag"><i class="fas fa-user"></i> ${v.seats}</span>
                                    <span class="tag"><i class="fas fa-gas-pump"></i> ${v.fuel}</span>
                                    <span class="tag"><i class="fas fa-road"></i> ${v.kms} km</span>
                                    <span class="tag"><i class="fas fa-heartbeat"></i> ${v.health}%</span>

                                </div>
                            </div>
                        </div>
                        <div style="display:flex; justify-content:space-between; align-items:center; margin-top:15px; padding-top:15px; border-top:1px solid #F1F5F9;">
                            <div><span style="font-size:1.4rem; font-weight:800; color:var(--p);">₹${v.price}</span> <span style="font-size:0.8rem; color:#94A3B8;">/ hr</span></div>
                            <div style="display:flex; gap:10px;">
                                ${role==='user' && v.status==='Available' ? `<button class="btn btn-p" style="padding:10px 20px;" onclick="openRent('${v.id}','${v.model}',${v.price})">Rent</button>` : ''}
                                ${role==='admin' ? `<button class="btn btn-d" onclick="delCar('${v.id}')"><i class="fas fa-trash"></i></button>` : ''}
                            </div>
                        </div>
                    </div>
                </div>`).join('');

            // RENDER ADMIN
            if(role === 'admin') {
                document.getElementById('st-rev').innerText = '₹' + data.stats.revenue.toLocaleString();
                document.getElementById('st-act').innerText = data.stats.active;
                document.getElementById('st-flt').innerText = data.stats.fleet;
                document.getElementById('st-kms').innerText = data.stats.kms;

                const active = data.rentals.filter(r => r.status === 'Active');
                document.getElementById('active-list').innerHTML = active.length ? active.map(r => `
                    <div style="background:white; padding:20px; border-radius:16px; border:1px solid #E2E8F0; display:flex; justify-content:space-between; align-items:center;">
                        <div>
                            <div style="font-weight:700; font-size:1.1rem;">${r.vehicle_model}</div>
                            <div style="color:#64748B; font-size:0.9rem;">Renter: ${r.user_name} • ${r.user_email}</div>
                        </div>
                        <button class="btn btn-p" onclick="openRet('${r.tx_id}')">Check-in</button>
                    </div>`).join('') : '<p style="color:#94A3B8;">No vehicles pending return.</p>';

                document.getElementById('ledger-body').innerHTML = data.rentals.map(r => `
                    <tr>
                        <td><code>${r.tx_id}</code></td>
                        <td>${r.user_name}</td>
                        <td>${r.vehicle_model}</td>
                        <td>₹${r.total}</td>
                        <td><span style="font-weight:700; color:${r.status==='Active'?'#10B981':'#64748B'}">${r.status}</span></td>
                    </tr>`).join('');
            }

            // RENDER USER
            if(role === 'user') {
                const myActive = data.rentals.filter(r => r.status === 'Active');
                document.getElementById('my-rentals').innerHTML = myActive.length ? myActive.map(r => `
                    <div style="background:white; padding:30px; border-radius:20px; border:1px solid #E2E8F0; text-align:center;">
                        <div style="font-size:3rem; margin-bottom:10px;">🚗</div>
                        <h2 style="margin:0 0 10px 0;">${r.vehicle_model}</h2>
                        <div style="background:#FEF2F2; color:#EF4444; padding:8px 16px; border-radius:30px; display:inline-block; font-weight:700; font-size:0.8rem; margin-bottom:15px;">ACTIVE RENTAL</div>
                        <p style="color:#64748B;">Please drive safely. Return to the station for check-in.</p>
                    </div>`).join('') : '<p style="color:#94A3B8;">No active rentals.</p>';
            }
        }

        function openRent(id, model, price) {

    curV = { v_id: id, price: price };
    finalAmount = price;

    document.getElementById('rent-info').innerText =
        `${model} - ₹${price}/day`;

    generateQR(finalAmount);

    openModal('mod-rent');
}

        
        async function confirmRent() {

    const payId = document.getElementById('pay-id').value;
    const payInput = document.getElementById('pay-id');
const errorBox = document.getElementById('pay-error');

// Simple UPI validation
const upiPattern = /^[a-zA-Z0-9._-]+@[a-zA-Z]+$/;

if(!upiPattern.test(payId)) {

    payInput.classList.add("input-error");
    errorBox.style.display = "block";
    errorBox.innerText = "Enter valid UPI ID (example: name@bank)";

    return;

} else {
    payInput.classList.remove("input-error");
    errorBox.style.display = "none";
}


    closeAll();
    openModal('mod-processing');

    let progress = 0;

    const progressBar = document.getElementById('pay-progress');

    const interval = setInterval(() => {
        progress += 25;
        progressBar.style.width = progress + "%";
    }, 400);

    // Simulated fintech processing
    setTimeout(async () => {

        clearInterval(interval);
        progressBar.style.width = "100%";

        const res = await fetch('/api/rent/create', {
            method:'POST',
            headers:{'Content-Type':'application/json'},
           body:JSON.stringify({
               v_id: curV.v_id,
               price: finalAmount,
               pay_id: payId
})


        });

        const d = await res.json();

        closeAll();
        sync();

        confetti({
            particleCount: 180,
            spread: 90,
            origin: { y: 0.6 }
        });

        document.getElementById('receipt-box').innerHTML = `
            <div><span>Transaction ID:</span> <b>${d.tx_id}</b></div>
            <div><span>Amount Paid:</span> <b>₹${finalAmount}</b></div>
            <div><span>Method:</span> <b>${payId}</b></div>
            <div><span>Status:</span> <b style="color:#10B981">SUCCESS</b></div>
        `;

        openModal('mod-success');

    }, 2000); // 2 second premium delay
}

function generateQR(amount) {
    const upiLink = `upi://pay?pa=nsuryachandra16@okicici&pn=DriveHub&am=${amount}&cu=INR`;
    const qrURL = 
        `https://api.qrserver.com/v1/create-qr-code/?size=200x200&data=${encodeURIComponent(upiLink)}`;

    document.getElementById('qr-ph').src = qrURL;
}
function applyCoupon() {
    const code = document.getElementById('pay-coup').value.trim().toUpperCase();

    if(code === "HUB20") {
        finalAmount = Math.round(curV.price * 0.8);
        Swal.fire('Coupon Applied', '20% Discount Activated!', 'success');
    } else if(code === "") {
        finalAmount = curV.price;
    } else {
        finalAmount = curV.price;
        Swal.fire('Invalid Code', 'No discount applied', 'warning');
    }

    document.getElementById('final-amt').innerText = "₹" + finalAmount;
    generateQR(finalAmount);
}


        function openRet(tx) { curTx=tx; openModal('mod-ret'); }
        async function processReturn() { 
            await fetch('/api/rent/return', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({
                tx_id:curTx, kms:document.getElementById('ret-kms').value, fine:document.getElementById('ret-fine').value
            })});
            closeAll(); sync(); Swal.fire('Success', 'Return Processed', 'success');
        }

        async function saveVehicle() {
            const fd = new FormData();
            ['model','price','year','fuel','trans','seats'].forEach(k => fd.append(k.replace('mv-',''), document.getElementById('mv-'+k).value));
            const f = document.getElementById('mv-img').files[0]; if(f) fd.append('image', f);
            await fetch('/api/vehicle/manage', {method:'POST', body:fd});
            closeAll(); sync();
        }

        async function delCar(id) { if(confirm('Delete vehicle?')) { await fetch('/api/vehicle/delete', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({id:id})}); sync(); } }
        async function logout() { await fetch('/api/auth/logout', {method:'POST'}); location.reload(); }
        function nav(v, el) { 
            document.querySelectorAll('.nav-item').forEach(x=>x.classList.remove('active')); el.classList.add('active');
            ['dash','garage','fleet','ledger'].forEach(x=>document.getElementById('view-'+x).classList.add('hidden'));
            document.getElementById('view-'+v).classList.remove('hidden');
        }
        function openModal(id) { document.getElementById(id).classList.add('active'); }
        function closeAll() { document.querySelectorAll('.modal').forEach(x=>x.classList.remove('active')); }
    

    </script>
</body>
</html>
"""

# ==========================================
# RUN
# ==========================================

if __name__ == '__main__':
    app.run(debug=True, port=5000)