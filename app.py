"""
Smart Health Navigator
Full-stack Flask app with:
  - MySQL database (hospitals + contact messages)
  - Admin panel (add/delete hospitals, view contact messages)
  - Live hospital search via Geoapify
  - Custom disease search
  - Light theme across all pages
  - Footer: © 2026 Smart Health Navigator. All rights reserved.
"""

from flask import Flask, render_template, request, jsonify, redirect, url_for, session, flash
import requests, math, os
from datetime import datetime
from functools import wraps

# ─── Load .env file automatically ────────────────────────────────────────────
try:
    from dotenv import load_dotenv
    load_dotenv()
    print("✅ .env loaded")
except ImportError:
    print("⚠️  python-dotenv not installed — install with: pip install python-dotenv")

try:
    import mysql.connector
    MYSQL_AVAILABLE = True
except ImportError:
    MYSQL_AVAILABLE = False

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'shn-admin-secret-2026')

# ─── MySQL config (loaded from .env) ─────────────────────────────────────────
DB_CONFIG = {
    'host':     os.environ.get('DB_HOST',     'localhost'),
    'port':     int(os.environ.get('DB_PORT', 3306)),
    'user':     os.environ.get('DB_USER',     'root'),
    'password': os.environ.get('DB_PASSWORD', 'root'),
    'database': os.environ.get('DB_NAME',     'smart_health_navigator'),
}

# ─── Admin credentials (loaded from .env) ────────────────────────────────────
ADMIN_USERNAME = os.environ.get('ADMIN_USER', 'admin')
ADMIN_PASSWORD = os.environ.get('ADMIN_PASS', 'admin123')

# ─── Geoapify API key (loaded from .env) ─────────────────────────────────────
GEOAPIFY_API_KEY = os.environ.get('GEOAPIFY_KEY', '')
if not GEOAPIFY_API_KEY:
    print("⚠️  GEOAPIFY_KEY not set in .env — hospital search will not work")

# ═══════════════════════════════════════════════════════════════════════════
# DATABASE
# ═══════════════════════════════════════════════════════════════════════════

_mem_hospitals = []
_mem_contacts  = []
_mem_diseases  = []
_db_ok = False

# ─── JSON file fallback paths ─────────────────────────────────────────────────
import json
# Use absolute path so it works regardless of working directory
_APP_DIR = os.path.abspath(os.path.dirname(__file__))
DATA_DIR = os.path.join(_APP_DIR, 'data')
CONTACTS_FILE  = os.path.join(DATA_DIR, 'contacts.json')
HOSPITALS_FILE = os.path.join(DATA_DIR, 'hospitals.json')
DISEASES_FILE  = os.path.join(DATA_DIR, 'diseases.json')

# Create data dir immediately at import time
try:
    os.makedirs(DATA_DIR, exist_ok=True)
    print(f"📁 Data directory: {DATA_DIR}")
except Exception as e:
    print(f"⚠️  Could not create data dir: {e}")

def _ensure_data_dir():
    os.makedirs(DATA_DIR, exist_ok=True)

def _load_json(path):
    try:
        if os.path.exists(path):
            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f)
    except Exception as e:
        print(f"⚠️  JSON load error {path}: {e}")
    return []

def _save_json(path, data):
    try:
        _ensure_data_dir()
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2, default=str)
        print(f"💾 Saved {len(data)} record(s) → {path}")
    except Exception as e:
        print(f"⚠️  JSON save error {path}: {e}")


def get_db():
    if not MYSQL_AVAILABLE:
        return None
    try:
        return mysql.connector.connect(**DB_CONFIG)
    except Exception:
        return None


def init_db():
    global _db_ok
    conn = get_db()
    if conn is None:
        print("⚠  MySQL not available – using in-memory storage (restart to persist)")
        _db_ok = False
        return
    try:
        cur = conn.cursor()
        cur.execute("""CREATE TABLE IF NOT EXISTS hospitals (
            id          INT AUTO_INCREMENT PRIMARY KEY,
            name        VARCHAR(200) NOT NULL,
            address     VARCHAR(500),
            city        VARCHAR(100),
            state       VARCHAR(100),
            lat         DOUBLE,
            lng         DOUBLE,
            specialties VARCHAR(500),
            phone       VARCHAR(50),
            added_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )""")
        cur.execute("""CREATE TABLE IF NOT EXISTS contact_messages (
            id          INT AUTO_INCREMENT PRIMARY KEY,
            name        VARCHAR(100),
            email       VARCHAR(150),
            message     TEXT,
            received_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            is_read     TINYINT DEFAULT 0
        )""")
        cur.execute("""CREATE TABLE IF NOT EXISTS custom_diseases (
            id          INT AUTO_INCREMENT PRIMARY KEY,
            name        VARCHAR(150),
            specialties VARCHAR(300),
            icon        VARCHAR(10) DEFAULT '💊',
            added_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )""")
        conn.commit()
        conn.close()
        _db_ok = True
        print("✅  MySQL connected – tables ready")
    except Exception as e:
        print(f"⚠  MySQL init error: {e}")
        _db_ok = False


# ── Hospitals ────────────────────────────────────────────────────────────────
def db_add_hospital(name, address, city, state, lat, lng, specialties, phone=''):
    if _db_ok:
        conn = get_db()
        if conn:
            try:
                cur = conn.cursor()
                cur.execute(
                    "INSERT INTO hospitals (name,address,city,state,lat,lng,specialties,phone) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
                    (name, address, city, state, lat, lng, specialties, phone))
                conn.commit()
                conn.close()
                return
            except Exception as e:
                print(f"DB error: {e}")
    hospitals = _load_json(HOSPITALS_FILE)
    new_id = max((h.get('id', 0) for h in hospitals), default=0) + 1
    hospitals.append({
        'id': new_id, 'name': name, 'address': address,
        'city': city, 'state': state, 'lat': lat, 'lng': lng,
        'specialties': specialties, 'phone': phone,
        'added_at': datetime.now().strftime('%Y-%m-%d %H:%M')})
    _save_json(HOSPITALS_FILE, hospitals)


def db_get_hospitals():
    if _db_ok:
        conn = get_db()
        if conn:
            try:
                cur = conn.cursor(dictionary=True)
                cur.execute("SELECT * FROM hospitals ORDER BY added_at DESC")
                rows = cur.fetchall()
                conn.close()
                return rows
            except Exception:
                pass
    return list(reversed(_load_json(HOSPITALS_FILE)))


def db_delete_hospital(hid):
    if _db_ok:
        conn = get_db()
        if conn:
            try:
                cur = conn.cursor()
                cur.execute("DELETE FROM hospitals WHERE id=%s", (hid,))
                conn.commit()
                conn.close()
                return
            except Exception:
                pass
    hospitals = _load_json(HOSPITALS_FILE)
    hospitals = [h for h in hospitals if h.get('id') != int(hid)]
    _save_json(HOSPITALS_FILE, hospitals)


# ── Contact messages ─────────────────────────────────────────────────────────
def db_save_contact(name, email, message):
    """Save contact - tries MySQL first, always falls back to JSON file."""
    saved_to_mysql = False
    if _db_ok:
        conn = get_db()
        if conn:
            try:
                cur = conn.cursor()
                cur.execute(
                    "INSERT INTO contact_messages (name,email,message) VALUES (%s,%s,%s)",
                    (name, email, message))
                conn.commit()
                conn.close()
                print(f"[CONTACT] Saved to MySQL OK: {name}")
                saved_to_mysql = True
            except Exception as e:
                print(f"[CONTACT] MySQL insert failed: {e}")
                try: conn.close()
                except: pass

    if not saved_to_mysql:
        # Always save to JSON as fallback/backup
        contacts = _load_json(CONTACTS_FILE)
        new_id = max((c.get('id', 0) for c in contacts), default=0) + 1
        contacts.append({
            'id': new_id, 'name': name, 'email': email,
            'message': message,
            'received_at': datetime.now().strftime('%Y-%m-%d %H:%M'),
            'is_read': 0})
        _save_json(CONTACTS_FILE, contacts)
        print(f"[CONTACT] Saved to JSON file: {name}")

def db_get_contacts():
    """Get contacts - from MySQL if connected, else from JSON file."""
    if _db_ok:
        conn = get_db()
        if conn:
            try:
                cur = conn.cursor(dictionary=True)
                cur.execute("SELECT * FROM contact_messages ORDER BY received_at DESC")
                rows = cur.fetchall()
                conn.close()
                return rows
            except Exception as e:
                print(f"[CONTACT] db_get_contacts MySQL error: {e}")
    # JSON fallback
    contacts = _load_json(CONTACTS_FILE)
    return list(reversed(contacts))


def db_mark_read(cid):
    if _db_ok:
        conn = get_db()
        if conn:
            try:
                cur = conn.cursor()
                cur.execute("UPDATE contact_messages SET is_read=1 WHERE id=%s", (cid,))
                conn.commit()
                conn.close()
                return
            except Exception:
                pass
    contacts = _load_json(CONTACTS_FILE)
    for c in contacts:
        if c.get('id') == int(cid):
            c['is_read'] = 1
    _save_json(CONTACTS_FILE, contacts)


def db_delete_contact(cid):
    if _db_ok:
        conn = get_db()
        if conn:
            try:
                cur = conn.cursor()
                cur.execute("DELETE FROM contact_messages WHERE id=%s", (cid,))
                conn.commit()
                conn.close()
                return
            except Exception:
                pass
    contacts = _load_json(CONTACTS_FILE)
    contacts = [c for c in contacts if c.get('id') != int(cid)]
    _save_json(CONTACTS_FILE, contacts)


# ── Custom diseases ──────────────────────────────────────────────────────────
def db_add_disease(name, specialties, icon='💊'):
    if _db_ok:
        conn = get_db()
        if conn:
            try:
                cur = conn.cursor()
                cur.execute(
                    "INSERT INTO custom_diseases (name,specialties,icon) VALUES (%s,%s,%s)",
                    (name, specialties, icon))
                conn.commit()
                conn.close()
                return
            except Exception as e:
                print(f"DB error: {e}")
    diseases = _load_json(DISEASES_FILE)
    new_id = max((d.get('id', 0) for d in diseases), default=0) + 1
    diseases.append({'id': new_id, 'name': name, 'specialties': specialties, 'icon': icon})
    _save_json(DISEASES_FILE, diseases)


def db_get_diseases():
    if _db_ok:
        conn = get_db()
        if conn:
            try:
                cur = conn.cursor(dictionary=True)
                cur.execute("SELECT * FROM custom_diseases ORDER BY id DESC")
                rows = cur.fetchall()
                conn.close()
                return rows
            except Exception:
                pass
    return list(reversed(_load_json(DISEASES_FILE)))


def db_delete_disease(did):
    if _db_ok:
        conn = get_db()
        if conn:
            try:
                cur = conn.cursor()
                cur.execute("DELETE FROM custom_diseases WHERE id=%s", (did,))
                conn.commit()
                conn.close()
                return
            except Exception:
                pass
    diseases = _load_json(DISEASES_FILE)
    diseases = [d for d in diseases if d.get('id') != int(did)]
    _save_json(DISEASES_FILE, diseases)


# ═══════════════════════════════════════════════════════════════════════════
# DOMAIN DATA
# ═══════════════════════════════════════════════════════════════════════════

MULTISPECIALTY_WORDS = [
    'safal','hope','medistar','sterling','apollo','shalby','zydus','kiran','nirma',
    'vedanta','narayana','manipal','kokilaben','fortis','max','medanta','medicity',
    'multispecialt','multi specialt','super specialt','superspecialt','multi-specialt',
    'general hospital','civil hospital','district hospital','government hospital',
    'govt hospital','municipal hospital','medical college','medical center',
    'medical centre','institute of medical','hospital and research',
    'hospital & research','comprehensive',
]

SPECIALTIES = {
    'orthopedic':    {'label': '🦴 Orthopedic & Bone', 'icon': '🦴',
        'keywords': ['ortho','orthopedic','orthopaedic','bone','joint','fracture','spine','spinal','disc','lumbar','cervical','arthroplasty','arthritis','ligament','tendon','musculo','skeletal','trauma center','sports medicine','sports injury','hand surgery','knee surgery','shoulder surgery','hip replacement']},
    'physio':        {'label': '💪 Physiotherapy', 'icon': '💪',
        'keywords': ['physio','physiotherapy','physiotherapist','rehab','rehabilitation','chiro','chiropractic','occupational therapy']},
    'neurology':     {'label': '🧠 Neurology & Brain', 'icon': '🧠',
        'keywords': ['neuro','neurology','neurological','neurologist','neurosurg','brain','stroke','epilepsy','parkinson','alzheimer']},
    'ent':           {'label': '👂 ENT', 'icon': '👂',
        'keywords': ['ent','ear','nose','throat','sinus','tonsil','otolaryngology','audiolog','hearing','rhinology','laryngology','thyroid']},
    'ophthalmology': {'label': '👁️ Eye Hospital', 'icon': '👁️',
        'keywords': ['eye','ophthalm','vision','retina','cataract','lasik','glaucoma','netralaya','drishti','ocular']},
    'cardiology':    {'label': '❤️ Cardiology & Heart', 'icon': '❤️',
        'keywords': ['cardio','cardiac','cardiology','cardiologist','heart','cardiovascular','angioplasty','bypass','pacemaker','coronary']},
    'pulmonology':   {'label': '🫁 Pulmonology & Chest', 'icon': '🫁',
        'keywords': ['pulmo','pulmonary','pulmonologist','lung','lungs','chest hospital','respiratory','asthma clinic','tb hospital','tuberculosis','broncho','thoracic']},
    'gastro':        {'label': '🫃 Gastroenterology', 'icon': '🫃',
        'keywords': ['gastro','gastroenterology','gastroenterologist','digestive','intestine','bowel','colon','colonoscopy','endoscopy','abdominal','gastric']},
    'liver':         {'label': '🫀 Liver & Hepatology', 'icon': '🫀',
        'keywords': ['liver','hepato','hepatology','hepatologist','pancrea','bile','jaundice','cirrhosis','liver transplant']},
    'oncology':      {'label': '🎗️ Cancer & Oncology', 'icon': '🎗️',
        'keywords': ['onco','oncology','oncologist','cancer','tumour','tumor','radiotherapy','chemotherapy','radiation','haematology']},
    'nephrology':    {'label': '🫘 Kidney & Nephrology', 'icon': '🫘',
        'keywords': ['nephro','nephrology','nephrologist','kidney','renal','dialysis','urology','urologist','urinary']},
    'endocrinology': {'label': '💊 Diabetes & Endocrinology', 'icon': '💊',
        'keywords': ['endocrin','endocrinology','diabetes','diabetology','diabetologist','hormone','insulin','bariatric']},
    'dermatology':   {'label': '🧴 Skin & Dermatology', 'icon': '🧴',
        'keywords': ['derma','dermatology','dermatologist','skin clinic','cosmet','cosmetic','hair clinic','trichology']},
    'psychiatry':    {'label': '🧘 Psychiatry & Mental Health', 'icon': '🧘',
        'keywords': ['psychiatr','psychology','mental health','mental hospital','de-addiction','addiction','counselling','counseling']},
    'general':       {'label': '🏥 General Medicine', 'icon': '🏥',
        'keywords': ['general medicine','general physician','family medicine','primary care','polyclinic','nursing home']},
}

BODY_PART_SPECIALTIES = {
    'head': ['neurology','ent','ophthalmology','psychiatry'],
    'neck': ['ent','neurology','orthopedic'],
    'chest': ['cardiology','pulmonology'],
    'stomach': ['gastro','liver'],
    'shoulders': ['orthopedic','physio'],
    'arms': ['orthopedic','physio'],
    'back': ['orthopedic','neurology','physio'],
    'knees': ['orthopedic','physio'],
    'legs': ['orthopedic','physio'],
    'feet': ['orthopedic','physio'],
}

ILLNESS_SPECIALTIES = {
    'fever':         ['general'],
    'cough':         ['pulmonology','ent'],
    'cold':          ['ent','general'],
    'diarrhea':      ['gastro'],
    'cancer':        ['oncology'],
    'heart_disease': ['cardiology'],
    'bp':            ['cardiology','general'],
    'diabetes':      ['endocrinology'],
    'asthma':        ['pulmonology'],
    'kidney':        ['nephrology'],
    'skin':          ['dermatology'],
    'eye':           ['ophthalmology'],
    'headache':      ['neurology','general'],
    'migraine':      ['neurology'],
    'liver':         ['liver','gastro'],
    'depression':    ['psychiatry'],
    'anxiety':       ['psychiatry'],
    'thyroid':       ['ent','endocrinology'],
    'arthritis':     ['orthopedic','physio'],
    'back_pain':     ['orthopedic','physio','neurology'],
}

COMMON_ILLNESSES = {
    'fever':         {'icon': '🌡️', 'label': 'Fever'},
    'cough':         {'icon': '😷', 'label': 'Cough'},
    'cold':          {'icon': '🤧', 'label': 'Cold & Flu'},
    'diarrhea':      {'icon': '🚽', 'label': 'Diarrhea'},
    'cancer':        {'icon': '🎗️', 'label': 'Cancer'},
    'heart_disease': {'icon': '❤️',  'label': 'Heart Disease'},
    'bp':            {'icon': '💉', 'label': 'High BP'},
    'diabetes':      {'icon': '💊', 'label': 'Diabetes'},
    'asthma':        {'icon': '🫁', 'label': 'Asthma'},
    'kidney':        {'icon': '🫘', 'label': 'Kidney Issues'},
    'skin':          {'icon': '🧴', 'label': 'Skin Problems'},
    'eye':           {'icon': '👁️', 'label': 'Eye Problems'},
    'headache':      {'icon': '🤕', 'label': 'Headache'},
    'migraine':      {'icon': '😖', 'label': 'Migraine'},
    'liver':         {'icon': '🫀', 'label': 'Liver Issues'},
    'depression':    {'icon': '😔', 'label': 'Depression'},
    'anxiety':       {'icon': '😰', 'label': 'Anxiety'},
    'thyroid':       {'icon': '🦋', 'label': 'Thyroid'},
    'arthritis':     {'icon': '🦴', 'label': 'Arthritis'},
    'back_pain':     {'icon': '🔙', 'label': 'Back Pain'},
}

# ═══════════════════════════════════════════════════════════════════════════
# UTILS
# ═══════════════════════════════════════════════════════════════════════════

def haversine(lat1, lon1, lat2, lon2):
    R = 6371
    dlat = math.radians(lat2 - lat1)
    dlng = math.radians(lon2 - lon1)
    a = (math.sin(dlat/2)**2 +
         math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) *
         math.sin(dlng/2)**2)
    return round(R * 2 * math.atan2(math.sqrt(a), math.sqrt(1-a)), 2)


def is_multispecialty(name, address=''):
    text = (name + ' ' + address).lower()
    return any(w in text for w in MULTISPECIALTY_WORDS)


def spec_score(name, address, sid):
    text = (name + ' ' + address).lower()
    return sum(1 for kw in SPECIALTIES[sid]['keywords'] if kw in text)


def classify(h, needed):
    matched = [(s, spec_score(h['name'], h.get('address',''), s)) for s in needed]
    return [m[0] for m in sorted(matched, key=lambda x: -x[1]) if m[1] > 0]


def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get('admin_logged_in'):
            return redirect(url_for('admin_login'))
        return f(*args, **kwargs)
    return decorated


# ═══════════════════════════════════════════════════════════════════════════
# PUBLIC ROUTES
# ═══════════════════════════════════════════════════════════════════════════

@app.route('/')
def index():
    all_illnesses = dict(COMMON_ILLNESSES)
    for d in db_get_diseases():
        key = d['name'].lower().replace(' ', '_')
        all_illnesses[key] = {'icon': d.get('icon','💊'), 'label': d['name']}
    return render_template('index.html', illnesses=all_illnesses)


@app.route('/hospitals')
def hospitals():
    return render_template('hospitals.html')


@app.route('/about')
def about():
    return render_template('about.html')


@app.route('/tips')
def tips():
    return render_template('tips.html')


@app.route('/contact')
def contact():
    return render_template('contact.html')


# ═══════════════════════════════════════════════════════════════════════════
# ADMIN ROUTES
# ═══════════════════════════════════════════════════════════════════════════

@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        if (request.form.get('username') == ADMIN_USERNAME and
                request.form.get('password') == ADMIN_PASSWORD):
            session['admin_logged_in'] = True
            return redirect(url_for('admin_dashboard'))
        flash('Invalid credentials', 'error')
    return render_template('admin/login.html')


@app.route('/admin/logout')
def admin_logout():
    session.pop('admin_logged_in', None)
    return redirect(url_for('admin_login'))


@app.route('/admin')
@app.route('/admin/dashboard')
@admin_required
def admin_dashboard():
    hospitals_list  = db_get_hospitals()
    contacts_list   = db_get_contacts()
    unread_count    = sum(1 for c in contacts_list if not c.get('is_read'))
    custom_diseases = db_get_diseases()
    return render_template('admin/dashboard.html',
        hospitals=hospitals_list,
        contacts=contacts_list,
        unread_count=unread_count,
        custom_diseases=custom_diseases,
        db_ok=_db_ok,
        all_specialties=list(SPECIALTIES.keys()))


@app.route('/admin/hospitals/add', methods=['POST'])
@admin_required
def admin_add_hospital():
    name  = request.form.get('name','').strip()
    if not name:
        flash('Name is required', 'error')
        return redirect(url_for('admin_dashboard'))
    try:
        lat = float(request.form.get('lat') or 0)
        lng = float(request.form.get('lng') or 0)
    except ValueError:
        lat = lng = 0.0
    db_add_hospital(
        name        = name,
        address     = request.form.get('address','').strip(),
        city        = request.form.get('city','').strip(),
        state       = request.form.get('state','').strip(),
        lat         = lat,
        lng         = lng,
        specialties = request.form.get('specialties','').strip(),
        phone       = request.form.get('phone','').strip(),
    )
    flash(f'✅ Hospital "{name}" added!', 'success')
    return redirect(url_for('admin_dashboard') + '#hospitals')


@app.route('/admin/hospitals/delete/<int:hid>', methods=['POST'])
@admin_required
def admin_delete_hospital(hid):
    db_delete_hospital(hid)
    flash('Hospital deleted', 'success')
    return redirect(url_for('admin_dashboard') + '#hospitals')


@app.route('/admin/contacts/read/<int:cid>', methods=['POST'])
@admin_required
def admin_mark_read(cid):
    db_mark_read(cid)
    return redirect(url_for('admin_dashboard') + '#contacts')


@app.route('/admin/contacts/delete/<int:cid>', methods=['POST'])
@admin_required
def admin_delete_contact(cid):
    db_delete_contact(cid)
    flash('Message deleted', 'success')
    return redirect(url_for('admin_dashboard') + '#contacts')


@app.route('/admin/contacts/reply/<int:cid>')
@admin_required
def admin_reply(cid):
    """Return JSON with the pre-built mailto URL — JS opens it client-side."""
    import urllib.parse
    contacts = db_get_contacts()
    c = next((x for x in contacts if x.get('id') == cid), None)
    if not c:
        return jsonify({'error': 'Contact not found'}), 404

    to      = str(c.get('email', '')).strip()
    name    = str(c.get('name',  '')).strip()
    orig    = str(c.get('message', ''))
    subject = 'Re: Your message to Smart Health Navigator'
    body    = (
        f"Dear {name},\n\n"
        f"Thank you for reaching out to Smart Health Navigator.\n\n"
        f"--- Your original message ---\n"
        f"{orig}\n\n"
        f"Best regards,\nSmart Health Navigator Team"
    )
    mailto = (
        f"mailto:{to}"
        f"?subject={urllib.parse.quote(subject)}"
        f"&body={urllib.parse.quote(body)}"
    )
    return jsonify({
        'email':  to,
        'name':   name,
        'mailto': mailto
    })


@app.route('/admin/contacts/view/<int:cid>')
@admin_required
def admin_view_contact(cid):
    """Return contact data as JSON for the modal."""
    contacts = db_get_contacts()
    c = next((x for x in contacts if x.get('id') == cid), None)
    if not c:
        return jsonify({'error': 'Not found'}), 404
    # Mark as read
    db_mark_read(cid)
    return jsonify({
        'id':          c.get('id'),
        'name':        c.get('name', ''),
        'email':       c.get('email', ''),
        'message':     c.get('message', ''),
        'received_at': str(c.get('received_at', '')),
        'reply_url':   url_for('admin_reply', cid=cid)
    })


@app.route('/admin/diseases/add', methods=['POST'])
@admin_required
def admin_add_disease():
    name = request.form.get('name','').strip()
    if name:
        db_add_disease(name,
            request.form.get('specialties','').strip(),
            request.form.get('icon','💊').strip() or '💊')
        flash(f'Disease "{name}" added', 'success')
    return redirect(url_for('admin_dashboard') + '#diseases')


@app.route('/admin/diseases/delete/<int:did>', methods=['POST'])
@admin_required
def admin_delete_disease(did):
    db_delete_disease(did)
    flash('Disease removed', 'success')
    return redirect(url_for('admin_dashboard') + '#diseases')


# ═══════════════════════════════════════════════════════════════════════════
# API ROUTES
# ═══════════════════════════════════════════════════════════════════════════

@app.route('/api/search-hospitals', methods=['POST'])
def api_search_hospitals():
    try:
        data         = request.get_json()
        body_part    = data.get('body_part','').lower().strip()
        illness_type = data.get('illness_type','').lower().strip()
        user_lat     = float(data.get('lat', 0))
        user_lng     = float(data.get('lng', 0))
        radius       = int(data.get('radius', 5000))
        limit        = int(data.get('limit', 30))
        custom_query = data.get('custom_query','').lower().strip()

        if not user_lat or not user_lng:
            return jsonify({'error': 'Missing location'}), 400

        # Determine specialties
        if custom_query:
            custom_diseases = db_get_diseases()
            m = next((d for d in custom_diseases if custom_query in d['name'].lower()), None)
            if m:
                needed = [s.strip() for s in m['specialties'].split(',') if s.strip()]
                label  = m['name']
            else:
                best   = next((k for k in ILLNESS_SPECIALTIES if custom_query in k.replace('_',' ')), None)
                needed = ILLNESS_SPECIALTIES.get(best, ['general'])
                label  = custom_query.title()
        elif illness_type and illness_type in ILLNESS_SPECIALTIES:
            needed = ILLNESS_SPECIALTIES[illness_type]
            label  = COMMON_ILLNESSES.get(illness_type, {}).get('label', illness_type.title())
        elif body_part and body_part in BODY_PART_SPECIALTIES:
            needed = BODY_PART_SPECIALTIES[body_part]
            label  = body_part.title()
        else:
            needed = ['general']
            label  = 'General'

        raw = []

        # DB hospitals
        for h in db_get_hospitals():
            if not (h.get('lat') and h.get('lng')):
                continue
            dist = haversine(user_lat, user_lng, float(h['lat']), float(h['lng']))
            if dist <= radius / 1000:
                raw.append({'name': h['name'],
                    'address': ' '.join(filter(None, [h.get('address'), h.get('city'), h.get('state')])),
                    'lat': float(h['lat']), 'lng': float(h['lng']),
                    'distance': dist, 'type': 'Hospital',
                    'place_id': f"db:{h['id']}", 'popularity': 10.0,
                    'display_rating': 4.8, 'priority_rank': 3, 'source': 'database',
                    'phone': h.get('phone','')})

        # Geoapify
        try:
            resp = requests.get('https://api.geoapify.com/v2/places', params={
                'categories': 'healthcare.hospital,healthcare.clinic_or_praxis,healthcare',
                'filter': f'circle:{user_lng},{user_lat},{radius}',
                'bias': f'proximity:{user_lng},{user_lat}',
                'limit': 50, 'apiKey': GEOAPIFY_API_KEY}, timeout=15)
            if resp.status_code == 200:
                for place in resp.json().get('features', []):
                    props  = place.get('properties', {})
                    coords = place.get('geometry', {}).get('coordinates', [])
                    if len(coords) < 2:
                        continue
                    name   = props.get('name') or props.get('address_line1') or 'Healthcare Facility'
                    addr   = props.get('formatted') or props.get('address_line2') or ''
                    cats   = props.get('categories', [])
                    ptype  = 'Hospital' if 'healthcare.hospital' in cats else 'Clinic' if 'healthcare.clinic_or_praxis' in cats else 'Healthcare'
                    dist   = haversine(user_lat, user_lng, coords[1], coords[0])
                    rank   = props.get('rank', {})
                    pop    = float(rank.get('popularity', 0) or 0)
                    imp    = float(rank.get('importance', 0) or 0)
                    rating = round(1.0+(min(pop,9.0)/9.0)*4.0,1) if pop>0 else (round(1.0+imp*4.0,1) if imp>0 else 0)
                    raw.append({'name': name, 'address': addr,
                        'lat': coords[1], 'lng': coords[0], 'distance': dist,
                        'type': ptype, 'place_id': props.get('place_id',''),
                        'popularity': pop, 'display_rating': rating,
                        'priority_rank': 0, 'source': 'live'})
        except Exception:
            pass

        # Group
        multi_bucket = []
        spec_buckets = {s: [] for s in needed}
        unmatched    = []
        seen         = set()

        for h in sorted(raw, key=lambda x: (-x.get('priority_rank',0), -x.get('popularity',0), x['distance'])):
            uid = f"{h['name'].strip().lower()}|{h.get('address','').strip().lower()}"
            if uid in seen:
                continue
            seen.add(uid)
            if is_multispecialty(h['name'], h.get('address','')):
                h['specialty_label'] = '⭐ Multispecialty'
                multi_bucket.append(h)
            else:
                matched = classify(h, needed)
                if matched:
                    h['specialty_label'] = SPECIALTIES.get(matched[0],{}).get('label', matched[0])
                    spec_buckets[matched[0]].append(h)
                else:
                    h['specialty_label'] = '🏥 General'
                    unmatched.append(h)

        groups = []
        if multi_bucket:
            groups.append({'id':'multispecialty','label':'⭐ Multispecialty Hospitals','icon':'⭐','hospitals':multi_bucket})
        for sid in needed:
            if spec_buckets.get(sid):
                sp = SPECIALTIES.get(sid, {})
                groups.append({'id':sid,'label':sp.get('label',sid.title()),'icon':sp.get('icon','🏥'),'hospitals':spec_buckets[sid]})
        if not groups and unmatched:
            groups.append({'id':'general','label':'🏥 Hospitals Nearby','icon':'🏥','hospitals':unmatched[:15]})

        remaining = limit
        trimmed   = []
        for g in groups:
            if remaining <= 0: break
            hs = g['hospitals'][:remaining]
            if hs:
                trimmed.append({**g,'hospitals':hs})
                remaining -= len(hs)

        return jsonify({'success':True,'groups':trimmed,
            'total':sum(len(g['hospitals']) for g in trimmed),
            'search_label':label,'radius_km':radius/1000})

    except Exception as e:
        import traceback; traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@app.route('/api/geocode', methods=['POST'])
def api_geocode():
    try:
        address = request.get_json().get('address','')
        if not address:
            return jsonify({'error': 'Address required'}), 400
        resp = requests.get('https://api.geoapify.com/v1/geocode/search',
            params={'text':address,'limit':1,'filter':'countrycode:in','bias':'countrycode:in','apiKey':GEOAPIFY_API_KEY}, timeout=10)
        if resp.status_code == 200:
            features = resp.json().get('features', [])
            if features:
                f = features[0]
                c = f['geometry']['coordinates']
                return jsonify({'success':True,'lat':c[1],'lng':c[0],
                    'formatted_address':f['properties'].get('formatted',address)})
        return jsonify({'error':'Address not found'}), 404
    except Exception as e:
        return jsonify({'error':str(e)}), 500


@app.route('/api/reverse-geocode', methods=['POST'])
def api_reverse_geocode():
    try:
        data = request.get_json() or {}
        lat  = float(data.get('lat', 0))
        lng  = float(data.get('lng', 0))
        if not lat or not lng:
            return jsonify({'error':'Lat/lng required'}), 400
        resp = requests.get('https://api.geoapify.com/v1/geocode/reverse',
            params={'lat':lat,'lon':lng,'format':'json','apiKey':GEOAPIFY_API_KEY}, timeout=10)
        if resp.status_code == 200:
            results = resp.json().get('results', [])
            if results:
                r = results[0]
                return jsonify({'success':True,
                    'formatted_address':r.get('formatted') or r.get('city') or r.get('state') or f'{lat},{lng}',
                    'city':r.get('city',''),'state':r.get('state',''),'country':r.get('country','')})
        return jsonify({'error':'Location not found'}), 404
    except Exception as e:
        return jsonify({'error':str(e)}), 500


@app.route('/api/contact', methods=['POST'])
def api_contact():
    try:
        data = request.get_json(force=True, silent=True) or {}
        name    = str(data.get('name','')).strip()
        email   = str(data.get('email','')).strip()
        message = str(data.get('message','')).strip()
        print(f"📩 Contact form: name={name!r}, email={email!r}, msg_len={len(message)}")
        if not name or not email or not message:
            return jsonify({'error': 'All fields required'}), 400
        db_save_contact(name, email, message)
        # Verify it was actually saved
        saved = db_get_contacts()
        print(f"✅ Contact saved. Total contacts now: {len(saved)}")
        return jsonify({'success': True, 'message': 'Thank you! We will get back to you soon.'})
    except Exception as e:
        import traceback; traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@app.route('/api/contact/check')
def api_contact_check():
    """Debug: see how many contacts are stored and where"""
    contacts = db_get_contacts()
    result = {
        'count': len(contacts),
        'data_dir': DATA_DIR,
        'contacts_file': CONTACTS_FILE,
        'file_exists': os.path.exists(CONTACTS_FILE),
        'db_ok': _db_ok,
        'latest': contacts[:3] if contacts else []
    }
    # Also test direct MySQL query
    if _db_ok:
        conn = get_db()
        if conn:
            try:
                cur = conn.cursor(dictionary=True)
                cur.execute("SELECT COUNT(*) as cnt FROM contact_messages")
                row = cur.fetchone()
                cur.execute("SHOW TABLES LIKE 'contact_messages'")
                table_exists = cur.fetchone() is not None
                conn.close()
                result['mysql_count'] = row['cnt'] if row else 0
                result['mysql_table_exists'] = table_exists
            except Exception as e:
                result['mysql_error'] = str(e)
    return jsonify(result)


@app.route('/api/diseases')
def api_diseases():
    combined = [{'key':k,'label':v['label'],'icon':v['icon'],'source':'builtin'}
                for k,v in COMMON_ILLNESSES.items()]
    for d in db_get_diseases():
        combined.append({'key':d['name'].lower().replace(' ','_'),
                         'label':d['name'],'icon':d.get('icon','💊'),'source':'custom'})
    return jsonify(combined)


# ═══════════════════════════════════════════════════════════════════════════
if __name__ == '__main__':
    init_db()
    print("="*55)
    print("🏥  Smart Health Navigator")
    print("🌐  http://localhost:5000")
    print("🔐  http://localhost:5000/admin  (admin / admin123)")
    print("="*55)
    app.run(debug=True, host='0.0.0.0', port=5000)
else:
    init_db()
