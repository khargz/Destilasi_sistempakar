# app.py — Lapisan 2: Server Flask + MySQL (Railway)
# Sistem Pakar Distilasi Minyak Kayu Putih
# Mode: MySQL + Load Cell HX711 (Monitoring) + 42 Rules Sistem Pakar
#
# ══════════════════════════════════════════════════════════
#  STRUKTUR RULES (42 Total)
#  ├── R01–R20  : Rules Individual per Sensor (20 rules)
#  │    ├── R01–R06  : Suhu Produksi (6 rules)
#  │    ├── R07–R11  : Suhu Pendingin (5 rules)
#  │    ├── R12–R16  : pH Distilat (5 rules)
#  │    └── R17–R20  : TDS (4 rules)
#  └── R21–R42  : Rules Kombinasi Antar Sensor (22 rules)
#       ├── R21–R26  : Suhu Produksi × Suhu Pendingin (6 rules)
#       ├── R27–R31  : Suhu Produksi × pH (5 rules)
#       ├── R32–R36  : Suhu Produksi × TDS (5 rules)
#       ├── R37–R39  : Suhu Pendingin × TDS (3 rules)
#       ├── R40–R41  : pH × TDS (2 rules)
#       └── R42      : Kombinasi 3+ Sensor Bersamaan (1 rule)
# ══════════════════════════════════════════════════════════
 
from flask import Flask, request, jsonify, render_template
import random, os
from urllib.parse import urlparse
import pymysql
import pymysql.cursors
 
app = Flask(__name__)
 
# ─────────────────────────────────────────────
# DATABASE SETUP (KONEKSI MYSQL)
# ─────────────────────────────────────────────
 
DB_URL = os.environ.get('MYSQL_URL', 'mysql://root:@localhost:3306/railway')
 
if DB_URL.startswith('mysql+pymysql://'):
    DB_URL = DB_URL.replace('mysql+pymysql://', 'mysql://')
 
parsed_url = urlparse(DB_URL)
 
def get_db():
    """Membuka koneksi ke MySQL"""
    return pymysql.connect(
        host=parsed_url.hostname,
        user=parsed_url.username,
        password=parsed_url.password,
        port=parsed_url.port or 3306,
        database=parsed_url.path[1:],
        cursorclass=pymysql.cursors.DictCursor,
        autocommit=True
    )
 
def init_db():
    """Membuat tabel MySQL jika belum ada"""
    conn = get_db()
    with conn.cursor() as c:
        c.execute('''
            CREATE TABLE IF NOT EXISTS log_sensor (
                id             INT AUTO_INCREMENT PRIMARY KEY,
                waktu          DATETIME DEFAULT CURRENT_TIMESTAMP,
                suhu_prod      FLOAT,
                suhu_cool      FLOAT,
                ph             FLOAT,
                tds            FLOAT,
                berat_distilat FLOAT DEFAULT 0,
                status         VARCHAR(50),
                rules_aktif    TEXT,
                sumber         VARCHAR(50) DEFAULT 'manual'
            )
        ''')
        # Migrasi aman untuk database lama
        c.execute("SHOW COLUMNS FROM log_sensor LIKE 'berat_distilat'")
        if not c.fetchone():
            c.execute("ALTER TABLE log_sensor ADD COLUMN berat_distilat FLOAT DEFAULT 0 AFTER tds")
            print("✅ Kolom berat_distilat ditambahkan ke tabel lama.")
    conn.close()
 
# ══════════════════════════════════════════════════════════
# KAMUS RULES — 42 Rules Sistem Pakar
# ══════════════════════════════════════════════════════════
#
# RENTANG NILAI REFERENSI DISTILASI MINYAK KAYU PUTIH:
#   Suhu Produksi : <80°C terlalu rendah | 80–90°C rendah | 90–105°C NORMAL
#                   105–112°C tinggi     | >112°C KRITIS
#   Suhu Pendingin: <15°C sangat rendah  | 15–20°C rendah  | 20–35°C NORMAL
#                   35–42°C tinggi       | >42°C KRITIS
#   pH Distilat   : <4.5 sangat asam     | 4.5–5.5 asam    | 5.5–7.0 NORMAL
#                   7.0–8.0 basa         | >8.0 sangat basa
#   TDS           : <50 sangat rendah    | 50–300 NORMAL    | 300–500 tinggi
#                   >500 KRITIS
# ══════════════════════════════════════════════════════════
 
RULES = {
 
    # ════════════════════════════════════════════
    # BAGIAN A — RULES INDIVIDUAL PER SENSOR
    # ════════════════════════════════════════════
 
    # ── A1. Suhu Produksi (R01–R06) ─────────────
    'R01': {
        'kondisi': 'Suhu produksi optimal (85°C–89°C)',
        'aksi'   : 'Proses distilasi berjalan optimal, lanjutkan',
        'level'  : 'normal'
    },
    'R02': {
        'kondisi': 'Suhu produksi rendah (80°C–84°C)',
        'aksi'   : 'Naikkan suhu pemanas secara bertahap',
        'level'  : 'anomali'
    },
    'R03': {
        'kondisi': 'Suhu produksi sangat rendah (<80°C)',
        'aksi'   : 'Proses belum mencapai titik didih, naikkan pemanas segera',
        'level'  : 'anomali'
    },
    'R04': {
        'kondisi': 'Suhu produksi tinggi (90°C–95°C)',
        'aksi'   : 'Kurangi intensitas pemanas, pantau terus',
        'level'  : 'anomali'
    },
    'R05': {
        'kondisi': 'Suhu produksi kritis (>95°C)',
        'aksi'   : 'BAHAYA — Matikan pemanas segera, risiko hangus',
        'level'  : 'kritis'
    },
    'R06': {
        'kondisi': 'Suhu produksi tidak stabil (fluktuasi cepat)',
        'aksi'   : 'Periksa sumber panas, kemungkinan tekanan uap tidak stabil',
        'level'  : 'anomali'
    },
 
    # ── A2. Suhu Pendingin (R07–R11) ────────────
    'R07': {
        'kondisi': 'Suhu pendingin optimal (20°C–35°C)',
        'aksi'   : 'Pendinginan kondensor berjalan baik',
        'level'  : 'normal'
    },
    'R08': {
        'kondisi': 'Suhu pendingin rendah (15°C–20°C)',
        'aksi'   : 'Kurangi aliran air dingin, hindari kondensasi berlebih',
        'level'  : 'anomali'
    },
    'R09': {
        'kondisi': 'Suhu pendingin sangat rendah (<15°C)',
        'aksi'   : 'Matikan pompa air dingin sementara, suhu terlalu rendah',
        'level'  : 'anomali'
    },
    'R10': {
        'kondisi': 'Suhu pendingin tinggi (35°C–42°C)',
        'aksi'   : 'Tingkatkan aliran air pendingin, efisiensi kondensor menurun',
        'level'  : 'anomali'
    },
    'R11': {
        'kondisi': 'Suhu pendingin kritis (>42°C)',
        'aksi'   : 'BAHAYA — Kondensor hampir gagal, tingkatkan pendingin darurat',
        'level'  : 'kritis'
    },
 
    # ── A3. pH Distilat (R12–R16) ───────────────
    'R12': {
        'kondisi': 'pH distilat normal (5.5–7.0)',
        'aksi'   : 'Kualitas kimia distilat baik, lanjutkan proses',
        'level'  : 'normal'
    },
    'R13': {
        'kondisi': 'pH distilat asam ringan (4.5–5.5)',
        'aksi'   : 'Keasaman meningkat, periksa kemungkinan kontaminasi asam organik',
        'level'  : 'anomali'
    },
    'R14': {
        'kondisi': 'pH distilat sangat asam (<4.5)',
        'aksi'   : 'KRITIS — Kontaminasi asam berat, hentikan pengumpulan distilat',
        'level'  : 'kritis'
    },
    'R15': {
        'kondisi': 'pH distilat basa ringan (7.0–8.0)',
        'aksi'   : 'Alkalinitas sedikit tinggi, periksa sumber air dan bahan baku',
        'level'  : 'anomali'
    },
    'R16': {
        'kondisi': 'pH distilat sangat basa (>8.0)',
        'aksi'   : 'KRITIS — Kontaminasi basa berat, periksa kondensor dan pipa',
        'level'  : 'kritis'
    },
 
    # ── A4. TDS / Kemurnian Distilat (R17–R20) ──
    'R17': {
        'kondisi': 'TDS normal (50–60 ppm)',
        'aksi'   : 'Kemurnian distilat baik, proses berjalan optimal',
        'level'  : 'normal'
    },
    'R18': {
        'kondisi': 'TDS sangat rendah (<50 ppm)',
        'aksi'   : 'Distilat sangat murni atau kemungkinan sensor TDS error',
        'level'  : 'normal'
    },
    'R19': {
        'kondisi': 'TDS tinggi (61–80 ppm)',
        'aksi'   : 'Kemurnian menurun, periksa kebersihan kondensor dan pipa',
        'level'  : 'anomali'
    },
    'R20': {
        'kondisi': 'TDS kritis (>80 ppm)',
        'aksi'   : 'HENTIKAN — Kemurnian sangat buruk, distilat tidak layak pakai',
        'level'  : 'kritis'
    },
 
    # ════════════════════════════════════════════
    # BAGIAN B — RULES KOMBINASI ANTAR SENSOR
    # ════════════════════════════════════════════
 
    # ── B1. Suhu Produksi × Suhu Pendingin (R21–R26) ──
    'R21': {
        'kondisi': 'Suhu produksi tinggi (90°C-95°C) DAN suhu pendingin tinggi (35°C-42°C)',
        'aksi'   : 'KRITIS GANDA — Kurangi pemanas DAN tingkatkan pendingin bersamaan',
        'level'  : 'kritis'
    },
    'R22': {
        'kondisi': 'Suhu produksi normal DAN suhu pendingin tinggi (35°C-42°C)',
        'aksi'   : 'Efisiensi kondensasi menurun meski suhu produksi normal, tingkatkan pendingin',
        'level'  : 'anomali'
    },
    'R23': {
        'kondisi': 'Suhu produksi rendah (80°C-84°C) DAN suhu pendingin sangat rendah (<15°C)',
        'aksi'   : 'Proses belum optimal, kurangi pendingin dan naikkan pemanas',
        'level'  : 'anomali'
    },
    'R24': {
        'kondisi': 'Suhu produksi kritis (>95°C) DAN suhu pendingin kritis (>42°C)',
        'aksi'   : 'DARURAT TOTAL — Matikan pemanas, aktifkan pendingin darurat, hentikan proses',
        'level'  : 'kritis'
    },
    'R25': {
        'kondisi': 'Suhu produksi normal DAN suhu pendingin rendah (15°C-20°C)',
        'aksi'   : 'Pendinginan berlebih meski suhu produksi normal, kurangi aliran air dingin',
        'level'  : 'anomali'
    },
    'R26': {
        'kondisi': 'Suhu produksi tinggi (90°C–95°C) DAN suhu pendingin normal',
        'aksi'   : 'Kurangi pemanas, kondensor masih mampu menangani beban saat ini',
        'level'  : 'anomali'
    },
 
    # ── B2. Suhu Produksi × pH (R27–R31) ──────
    'R27': {
        'kondisi': 'Suhu produksi kritis (>95°C) DAN pH sangat asam (<4.5)',
        'aksi'   : 'KRITIS — Suhu tinggi memperparah dekomposisi asam, hentikan proses segera',
        'level'  : 'kritis'
    },
    'R28': {
        'kondisi': 'Suhu produksi tinggi (90°C-95°C) DAN pH asam (4.5–5.5)',
        'aksi'   : 'Suhu tinggi mempercepat hidrolisis, turunkan suhu dan periksa pH',
        'level'  : 'kritis'
    },
    'R29': {
        'kondisi': 'Suhu produksi rendah (80°C-84°C) DAN pH basa (7.0-8.0)',
        'aksi'   : 'Suhu rendah dan pH basa, periksa kualitas bahan baku daun',
        'level'  : 'anomali'
    },
    'R30': {
        'kondisi': 'Suhu produksi normal DAN pH normal',
        'aksi'   : 'Kondisi suhu dan kualitas kimia optimal, proses distilasi ideal',
        'level'  : 'normal'
    },
    'R31': {
        'kondisi': 'Suhu produksi sangat rendah (<80°C) DAN pH sangat asam (<4.5)',
        'aksi'   : 'Proses tidak berjalan dan kualitas buruk, periksa bahan baku dan pemanas',
        'level'  : 'kritis'
    },
 
    # ── B3. Suhu Produksi × TDS (R32–R36) ─────
    'R32': {
        'kondisi': 'Suhu produksi kritis (>95°C) DAN TDS kritis (>80 ppm)',
        'aksi'   : 'DARURAT — Suhu berlebih melarutkan kontaminan, hentikan dan bersihkan sistem',
        'level'  : 'kritis'
    },
    'R33': {
        'kondisi': 'Suhu produksi tinggi (90°C-95°C) DAN TDS tinggi (61-80 ppm)',
        'aksi'   : 'Suhu tinggi meningkatkan kelarutan pengotor, turunkan suhu dan periksa kemurnian',
        'level'  : 'kritis'
    },
    'R34': {
        'kondisi': 'Suhu produksi normal DAN TDS tinggi (61–80 ppm)',
        'aksi'   : 'Kemurnian menurun meski suhu normal, periksa kebersihan kondensor',
        'level'  : 'anomali'
    },
    'R35': {
        'kondisi': 'Suhu produksi rendah (80°C-84°C) DAN TDS tinggi (61-80 ppm)',
        'aksi'   : 'Proses tidak optimal, distilat terkontaminasi, naikkan suhu dan periksa sistem',
        'level'  : 'anomali'
    },
    'R36': {
        'kondisi': 'Suhu produksi normal DAN TDS normal',
        'aksi'   : 'Suhu dan kemurnian distilat dalam kondisi terbaik',
        'level'  : 'normal'
    },
 
    # ── B4. Suhu Pendingin × TDS (R37–R39) ────
    'R37': {
        'kondisi': 'Suhu pendingin kritis (>42°C) DAN TDS kritis (>80 ppm)',
        'aksi'   : 'DARURAT — Kondensor gagal dan distilat sangat kotor, hentikan semua proses',
        'level'  : 'kritis'
    },
    'R38': {
        'kondisi': 'Suhu pendingin tinggi (35°C-42°C) DAN TDS tinggi (61–80 ppm)',
        'aksi'   : 'Pendinginan tidak efisien menyebabkan kemurnian menurun, perbaiki sistem pendingin',
        'level'  : 'kritis'
    },
    'R39': {
        'kondisi': 'Suhu pendingin normal DAN TDS normal',
        'aksi'   : 'Kondensor bekerja optimal, kemurnian distilat terjaga',
        'level'  : 'normal'
    },
 
    # ── B5. pH × TDS (R40–R41) ─────────────────
    'R40': {
        'kondisi': 'pH sangat asam (<4.5) DAN TDS kritis (>80 ppm)',
        'aksi'   : 'DARURAT KUALITAS — Distilat sangat asam dan sangat kotor, tidak dapat digunakan',
        'level'  : 'kritis'
    },
    'R41': {
        'kondisi': 'pH asam (4.5–5.5) DAN TDS tinggi (61–80 ppm)',
        'aksi'   : 'Kualitas distilat buruk ganda (asam + kotor), periksa keseluruhan sistem',
        'level'  : 'kritis'
    },
 
    # ── B6. Kombinasi 3+ Sensor (R42) ──────────
    'R42': {
        'kondisi': 'Suhu produksi kritis DAN suhu pendingin kritis DAN pH abnormal DAN TDS kritis',
        'aksi'   : 'KEGAGALAN SISTEM TOTAL — Hentikan semua proses, lakukan pengecekan menyeluruh',
        'level'  : 'kritis'
    },
}
 
 
# ══════════════════════════════════════════════════════════
# FORWARD CHAINING — Mesin Inferensi
# ══════════════════════════════════════════════════════════
 
def forward_chaining(d):
    sp  = float(d.get('suhu_prod', 0))
    sc  = float(d.get('suhu_cool', 0))
    ph  = float(d.get('ph', 7))
    tds = float(d.get('tds', 0))
    # berat_distilat hanya dicatat, tidak digunakan untuk status
 
    rules_aktif = []
 
    # ── Prioritas Status: kritis > anomali > normal ──
    # Dikumpulkan dulu, baru ditentukan status akhir
    status_set = set()
 
    def tambah(kode):
        rules_aktif.append(kode)
        status_set.add(RULES[kode]['level'])
 
    # ════════════════════════
    # BAGIAN A — INDIVIDUAL
    # ════════════════════════
 
    # -- Suhu Produksi --
    if 85 <= sp <= 89: tambah('R01')
    elif 80 <= sp < 84: tambah('R02')
    elif sp < 80: tambah('R03')
    elif 89 < sp <= 95: tambah('R04')
    elif sp > 95: tambah('R05')
 
    # -- Suhu Pendingin --
    if 20 <= sc <= 35: tambah('R07')
    elif 15 <= sc < 20: tambah('R08')
    elif sc < 15: tambah('R09')
    elif 35 < sc <= 42: tambah('R10')
    elif sc > 42: tambah('R11')
 
    # -- pH --
    if 5.5 <= ph <= 7.0: tambah('R12')
    elif 4.5 <= ph < 5.5: tambah('R13')
    elif ph < 4.5: tambah('R14')
    elif 7.0 < ph <= 8.0: tambah('R15')
    elif ph > 8.0: tambah('R16')
 
    # -- TDS --
    if 50 <= tds <= 60: tambah('R17')
    elif tds < 50: tambah('R18')
    elif 61 < tds <= 80: tambah('R19')
    elif tds > 80: tambah('R20')
 
    # ════════════════════════════
    # BAGIAN B — KOMBINASI
    # ════════════════════════════
 
# R21-R26 (Suhu Prod x Pendingin)
    if sp > 95 and sc > 42: tambah('R24')
    elif 90 < sp <= 95 and 35 < sc <= 42: tambah('R21')
    elif 85 <= sp <= 89 and 35 < sc <= 42: tambah('R22')
    elif 80 <= sp < 84 and sc < 15: tambah('R23')
    elif 85 <= sp <= 89 and 15 < sc <= 20: tambah('R25')
    elif 90 < sp <= 95 and 20 <= sc <= 35: tambah('R26')

    # R27-R31 (Suhu Prod x pH)
    if sp > 95 and ph < 4.5: tambah('R27')
    elif 90 < sp <= 95 and 4.5 <= ph < 5.5: tambah('R28')
    elif 80 <= sp < 84 and 7.0 < ph <= 8.0: tambah('R29')
    elif 85 <= sp <= 89 and 5.5 <= ph <= 7.0: tambah('R30')
    elif sp < 80 and ph < 4.5: tambah('R31')

    # R32-R36 (Suhu Prod x TDS)
    if sp > 95 and tds > 80: tambah('R32')
    elif 90 < sp <= 95 and 61 < tds <= 80: tambah('R33')
    elif 85 <= sp <= 89 and 61 < tds <= 80: tambah('R34')
    elif 80 <= sp < 84 and 61 < tds <= 80: tambah('R35')
    elif 85 <= sp <= 89 and 50 <= tds <= 60: tambah('R36')

    # R37-R39 (Pendingin x TDS)
    if sc > 42 and tds > 80: tambah('R37')
    elif 35 < sc <= 42 and 61 < tds <= 80: tambah('R38')
    elif 20 <= sc <= 35 and 50 <= tds <= 60: tambah('R39')

    # R40-R41 (pH x TDS)
    if ph < 4.5 and tds > 80: tambah('R40')
    elif 4.5 <= ph < 5.5 and 61 < tds <= 80: tambah('R41')

    # R42 (Kombinasi 3+ Sensor)
    if sp > 95 and sc > 42 and (ph < 4.5 or ph > 8.0) and tds > 80: tambah('R42')

    # Tentukan status akhir berdasarkan level tertinggi
    status = 'normal'
    if 'kritis' in status_set: status = 'kritis'
    elif 'anomali' in status_set: status = 'anomali'

    rekomendasi = [RULES[r]['aksi'] for r in rules_aktif]
    return status, rules_aktif, rekomendasi
 
 
# ─────────────────────────────────────────────
# ROUTES
# ─────────────────────────────────────────────
 
@app.route('/')
def index():
    return render_template('dashboard.html')
 
@app.route('/scada')
def scada_view():
    return render_template('scada.html')
 
@app.route('/api/sensor', methods=['GET', 'POST'])
def terima_sensor():
    """Terima data dari ESP32 (berat_distilat = logging only, tidak mempengaruhi rules)"""
 
    if request.method == 'GET':
        return jsonify({
            'status' : 'ok',
            'message': 'Endpoint aktif. Gunakan POST untuk mengirim data sensor.',
            'total_rules': len(RULES),
            'format_data': {
                'suhu_prod'     : 'float — Suhu ruang produksi (°C)',
                'suhu_cool'     : 'float — Suhu air pendingin (°C)',
                'ph'            : 'float — Nilai pH distilat',
                'tds'           : 'float — Total Dissolved Solids (ppm)',
                'berat_distilat': 'float — Berat distilat HX711 (gram) [monitoring only]',
                'sumber'        : 'string — Sumber data (opsional)'
            }
        }), 200
 
    try:
        data = request.get_json(force=True)
        if not data:
            return jsonify({'error': 'Data tidak valid atau kosong'}), 400
 
        data['suhu_prod']      = float(data.get('suhu_prod', 0))
        data['suhu_cool']      = float(data.get('suhu_cool', 0))
        data['ph']             = float(data.get('ph', 7))
        data['tds']            = float(data.get('tds', 0))
        data['berat_distilat'] = max(0.0, float(data.get('berat_distilat', 0)))
 
        status, rules, rekomendasi = forward_chaining(data)
        sumber = data.get('sumber', 'manual')
 
        conn = get_db()
        with conn.cursor() as c:
            c.execute('''
                INSERT INTO log_sensor
                    (suhu_prod, suhu_cool, ph, tds, berat_distilat, status, rules_aktif, sumber)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            ''', (
                data['suhu_prod'], data['suhu_cool'],
                data['ph'],        data['tds'],
                data['berat_distilat'],
                status, ','.join(rules), sumber
            ))
            last_id = c.lastrowid
        conn.close()
 
        return jsonify({
            'success'        : True,
            'id'             : last_id,
            'status'         : status,
            'rules'          : rules,
            'jumlah_rules'   : len(rules),
            'rekomendasi'    : rekomendasi,
            'berat_distilat' : data['berat_distilat']
        }), 201
 
    except Exception as e:
        print(f"Error di terima_sensor: {e}")
        return jsonify({'error': f'Sistem Crash Karena: {str(e)}'}), 500
 
 
@app.route('/api/simulate', methods=['POST'])
def auto_simulate():
    """Generate data sensor acak realistis untuk semua mode"""
    mode = request.json.get('mode', 'normal') if request.json else 'normal'
 
    if mode == 'normal':
        data = {
            'suhu_prod'     : round(random.uniform(90,  105), 1),
            'suhu_cool'     : round(random.uniform(20,  35),  1),
            'ph'            : round(random.uniform(5.5, 7.0), 2),
            'tds'           : round(random.uniform(50,  300), 1),
            'berat_distilat': round(random.uniform(50,  200), 1),
            'sumber'        : 'simulator'
        }
    elif mode == 'anomali':
        data = {
            'suhu_prod'     : round(random.uniform(105, 112), 1),
            'suhu_cool'     : round(random.uniform(35,  42),  1),
            'ph'            : round(random.uniform(4.5, 5.5), 2),
            'tds'           : round(random.uniform(300, 500), 1),
            'berat_distilat': round(random.uniform(10,  50),  1),
            'sumber'        : 'simulator'
        }
    else:  # kritis
        data = {
            'suhu_prod'     : round(random.uniform(112, 125), 1),
            'suhu_cool'     : round(random.uniform(42,  55),  1),
            'ph'            : round(random.uniform(3.0, 4.5), 2),
            'tds'           : round(random.uniform(500, 800), 1),
            'berat_distilat': round(random.uniform(0,   10),  1),
            'sumber'        : 'simulator'
        }
 
    status, rules, rekomendasi = forward_chaining(data)
 
    conn = get_db()
    with conn.cursor() as c:
        c.execute('''
            INSERT INTO log_sensor
                (suhu_prod, suhu_cool, ph, tds, berat_distilat, status, rules_aktif, sumber)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        ''', (
            data['suhu_prod'], data['suhu_cool'],
            data['ph'],        data['tds'],
            data['berat_distilat'],
            status, ','.join(rules), data['sumber']
        ))
    conn.close()
 
    return jsonify({
        'success'     : True,
        'data'        : data,
        'status'      : status,
        'rules'       : rules,
        'jumlah_rules': len(rules),
        'rekomendasi' : rekomendasi
    })
 
 
@app.route('/api/rules')
def get_rules():
    """Tampilkan seluruh daftar rules sistem pakar (42 rules)"""
    kategori = {
        'individual': {k: v for k, v in RULES.items() if int(k[1:]) <= 20},
        'kombinasi' : {k: v for k, v in RULES.items() if int(k[1:]) > 20},
    }
    return jsonify({
        'total_rules': len(RULES),
        'rules'       : RULES,
        'per_kategori': kategori
    })
 
 
@app.route('/api/log')
def get_log():
    """Ambil data log terbaru"""
    limit = request.args.get('limit', 50, type=int)
    conn = get_db()
    with conn.cursor() as c:
        c.execute('SELECT * FROM log_sensor ORDER BY id DESC LIMIT %s', (limit,))
        rows = c.fetchall()
    conn.close()
    for r in rows:
        if r.get('waktu'):
            r['waktu'] = str(r['waktu'])
    return jsonify(rows)
 
 
@app.route('/api/latest')
def get_latest():
    """Ambil 1 data terbaru untuk gauge realtime"""
    conn = get_db()
    with conn.cursor() as c:
        c.execute('SELECT * FROM log_sensor ORDER BY id DESC LIMIT 1')
        row = c.fetchone()
    conn.close()
    if row and row.get('waktu'):
        row['waktu'] = str(row['waktu'])
    return jsonify(row if row else {})
 
 
@app.route('/api/stats')
def get_stats():
    """Statistik ringkasan + monitoring berat distilat"""
    conn = get_db()
    with conn.cursor() as c:
        c.execute('SELECT COUNT(*) as n FROM log_sensor')
        total = c.fetchone()['n']
        c.execute("SELECT COUNT(*) as n FROM log_sensor WHERE status='normal'")
        normal = c.fetchone()['n']
        c.execute("SELECT COUNT(*) as n FROM log_sensor WHERE status='anomali'")
        anomali = c.fetchone()['n']
        c.execute("SELECT COUNT(*) as n FROM log_sensor WHERE status='kritis'")
        kritis = c.fetchone()['n']
        c.execute('''
            SELECT
                ROUND(AVG(berat_distilat), 2) as avg_berat,
                ROUND(MAX(berat_distilat), 2) as max_berat,
                ROUND(MIN(berat_distilat), 2) as min_berat,
                ROUND(SUM(berat_distilat), 2) as total_berat
            FROM log_sensor WHERE berat_distilat > 0
        ''')
        bs = c.fetchone()
    conn.close()
    return jsonify({
        'total'  : total,
        'normal' : normal,
        'anomali': anomali,
        'kritis' : kritis,
        'monitoring_berat_distilat': {
            'rata_rata_gram': bs['avg_berat']   or 0,
            'tertinggi_gram': bs['max_berat']   or 0,
            'terendah_gram' : bs['min_berat']   or 0,
            'total_gram'    : bs['total_berat'] or 0,
        }
    })
 
 
@app.route('/api/clear', methods=['DELETE'])
def clear_log():
    """Hapus semua log (untuk testing)"""
    conn = get_db()
    with conn.cursor() as c:
        c.execute('DELETE FROM log_sensor')
    conn.close()
    return jsonify({'success': True, 'message': 'Semua log dihapus'})
 
 
# ─────────────────────────────────────────────
# MAIN & INISIALISASI
# ─────────────────────────────────────────────
 
try:
    init_db()
except Exception as e:
    print(f"Gagal koneksi atau membuat tabel: {e}")
 
if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    print("=" * 60)
    print("  SISTEM PAKAR DISTILASI MINYAK KAYU PUTIH (MYSQL)")
    print("  42 Rules: 20 Individual + 22 Kombinasi Antar Sensor")
    print("  + Load Cell HX711 (Monitoring & Logging Only)")
    print("=" * 60)
    app.run(host='0.0.0.0', port=port, debug=False)