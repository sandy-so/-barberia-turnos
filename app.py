from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
from flask_socketio import SocketIO, emit
from database import get_connection, init_db
import os, threading, time
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'clave_secreta')
CORS(app)
socketio = SocketIO(app, cors_allowed_origins="*")

with app.app_context():
    try:
        init_db()
    except Exception as e:
        print(f"DB init error: {e}")

# ─────────────────────────────────────────────
# TURNO AUTOMÁTICO DESDE CITAS
# ─────────────────────────────────────────────

def generar_turnos_desde_citas():
    while True:
        try:
            conn = get_connection()
            cursor = conn.cursor(dictionary=True)
            cursor.execute("""
                SELECT c.* FROM citas c
                WHERE c.fecha = CURDATE()
                AND c.estado IN ('pendiente','confirmada')
                AND c.turno_generado = FALSE
                AND TIME(NOW()) BETWEEN SUBTIME(c.hora,'00:05:00') AND ADDTIME(c.hora,'00:15:00')
            """)
            citas = cursor.fetchall()
            for cita in citas:
                cursor.execute("""
                    SELECT MAX(numero) as ultimo FROM turnos
                    WHERE DATE(created_at) = CURDATE() AND barbero_id = %s
                """, (cita['barbero_id'],))
                res = cursor.fetchone()
                nuevo_numero = (res['ultimo'] or 0) + 1

                cursor.execute("""
                    INSERT INTO turnos (numero, nombre, servicio, barbero_id, tipo, estado)
                    VALUES (%s, %s, %s, %s, 'cita', 'esperando')
                """, (nuevo_numero, cita['nombre'], cita['servicio'], cita['barbero_id']))

                cursor.execute("UPDATE citas SET turno_generado=TRUE WHERE id=%s", (cita['id'],))
                conn.commit()
                print(f"Turno #{nuevo_numero} generado para {cita['nombre']} con barbero {cita['barbero_id']}")
                socketio.emit('turno_nuevo', {'barbero_id': cita['barbero_id']})
            cursor.close()
            conn.close()
        except Exception as e:
            print(f"Error generador turnos: {e}")
        time.sleep(60)

hilo = threading.Thread(target=generar_turnos_desde_citas, daemon=True)
hilo.start()

# ─────────────────────────────────────────────
# PÁGINAS
# ─────────────────────────────────────────────

@app.route('/setup')
def setup():
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("ALTER TABLE turnos ADD COLUMN IF NOT EXISTS barbero_id INT NOT NULL DEFAULT 1")
        cursor.execute("ALTER TABLE turnos ADD COLUMN IF NOT EXISTS tipo ENUM('walk-in','cita') DEFAULT 'walk-in'")
        cursor.execute("ALTER TABLE citas ADD COLUMN IF NOT EXISTS barbero_id INT NOT NULL DEFAULT 1")
        cursor.execute("ALTER TABLE citas ADD COLUMN IF NOT EXISTS turno_generado BOOLEAN DEFAULT FALSE")
        conn.commit()
        cursor.close(); conn.close()
        return "BD actualizada correctamente"
    except Exception as e:
        return f"Error: {e}"@app.route('/setup')
def setup():
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("ALTER TABLE turnos ADD COLUMN IF NOT EXISTS barbero_id INT NOT NULL DEFAULT 1")
        cursor.execute("ALTER TABLE turnos ADD COLUMN IF NOT EXISTS tipo ENUM('walk-in','cita') DEFAULT 'walk-in'")
        cursor.execute("ALTER TABLE citas ADD COLUMN IF NOT EXISTS barbero_id INT NOT NULL DEFAULT 1")
        cursor.execute("ALTER TABLE citas ADD COLUMN IF NOT EXISTS turno_generado BOOLEAN DEFAULT FALSE")
        conn.commit()
        cursor.close(); conn.close()
        return "BD actualizada correctamente"
    except Exception as e:
        return f"Error: {e}"

@app.route('/')
def cliente():
    return render_template('cliente.html')

@app.route('/barbero')
def barbero():
    return render_template('barbero.html')

@app.route('/pantalla')
def pantalla():
    return render_template('pantalla.html')

@app.route('/citas')
def citas():
    return render_template('citas.html')

@app.route('/admin')
def admin():
    return render_template('admin.html')

# ─────────────────────────────────────────────
# API BARBEROS
# ─────────────────────────────────────────────

@app.route('/api/barberos', methods=['GET'])
def listar_barberos():
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM barberos WHERE activo=TRUE ORDER BY id")
    barberos = cursor.fetchall()
    cursor.close(); conn.close()
    return jsonify({'barberos': barberos})

# ─────────────────────────────────────────────
# API TURNOS
# ─────────────────────────────────────────────

@app.route('/api/turno', methods=['POST'])
def registrar_turno():
    data = request.json
    nombre     = data.get('nombre', '').strip()
    servicio   = data.get('servicio', '').strip()
    barbero_id = data.get('barbero_id', 1)
    if not nombre or not servicio:
        return jsonify({'error': 'Nombre y servicio son requeridos'}), 400

    conn = get_connection()
    cursor = conn.cursor(dictionary=True)

    # Verificar si hay cita próxima para este barbero (próximos 30 min)
    cursor.execute("""
        SELECT COUNT(*) as total FROM citas
        WHERE fecha = CURDATE()
        AND barbero_id = %s
        AND estado IN ('pendiente','confirmada')
        AND turno_generado = FALSE
        AND STR_TO_DATE(hora, '%H:%i') BETWEEN NOW() AND DATE_ADD(NOW(), INTERVAL 30 MINUTE)
    """, (barbero_id,))
    citas_proximas = cursor.fetchone()['total']

    # Calcular posición correcta
    cursor.execute("""
        SELECT MAX(numero) as ultimo FROM turnos
        WHERE DATE(created_at) = CURDATE() AND barbero_id = %s
    """, (barbero_id,))
    ultimo = (cursor.fetchone()['ultimo'] or 0) + 1

    # Si hay citas próximas, el walk-in va después
    cursor.execute("""
        INSERT INTO turnos (numero, nombre, servicio, barbero_id, tipo, estado)
        VALUES (%s, %s, %s, %s, 'walk-in', 'esperando')
    """, (ultimo, nombre, servicio, barbero_id))
    conn.commit()

    cursor.execute("""
        SELECT COUNT(*) as antes FROM turnos
        WHERE estado='esperando' AND numero < %s
        AND DATE(created_at)=CURDATE() AND barbero_id=%s
    """, (ultimo, barbero_id))
    antes = cursor.fetchone()['antes']

    # Obtener nombre del barbero
    cursor.execute("SELECT nombre FROM barberos WHERE id=%s", (barbero_id,))
    barbero = cursor.fetchone()
    cursor.close(); conn.close()

    turno_info = {
        'numero': ultimo, 'nombre': nombre, 'servicio': servicio,
        'barbero_id': barbero_id, 'barbero_nombre': barbero['nombre'],
        'antes': antes, 'citas_proximas': citas_proximas
    }
    socketio.emit('turno_nuevo', {'barbero_id': barbero_id})
    return jsonify({'success': True, 'turno': turno_info}), 201


@app.route('/api/turno/actual', methods=['GET'])
def turno_actual():
    barbero_id = request.args.get('barbero_id', None)
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    if barbero_id:
        cursor.execute("""
            SELECT t.*, b.nombre as barbero_nombre FROM turnos t
            JOIN barberos b ON t.barbero_id = b.id
            WHERE t.estado='en_atencion' AND t.barbero_id=%s
            ORDER BY t.updated_at DESC LIMIT 1
        """, (barbero_id,))
    else:
        cursor.execute("""
            SELECT t.*, b.nombre as barbero_nombre FROM turnos t
            JOIN barberos b ON t.barbero_id = b.id
            WHERE t.estado='en_atencion'
            ORDER BY t.updated_at DESC LIMIT 1
        """)
    turno = cursor.fetchone()
    cursor.close(); conn.close()
    if turno:
        turno['created_at'] = str(turno['created_at'])
        turno['updated_at'] = str(turno['updated_at'])
    return jsonify({'turno_actual': turno})


@app.route('/api/turno/lista', methods=['GET'])
def lista_turnos():
    barbero_id = request.args.get('barbero_id', None)
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    if barbero_id:
        cursor.execute("""
            SELECT t.*, b.nombre as barbero_nombre FROM turnos t
            JOIN barberos b ON t.barbero_id = b.id
            WHERE t.estado IN ('esperando','en_atencion')
            AND DATE(t.created_at)=CURDATE() AND t.barbero_id=%s
            ORDER BY t.numero ASC
        """, (barbero_id,))
    else:
        cursor.execute("""
            SELECT t.*, b.nombre as barbero_nombre FROM turnos t
            JOIN barberos b ON t.barbero_id = b.id
            WHERE t.estado IN ('esperando','en_atencion')
            AND DATE(t.created_at)=CURDATE()
            ORDER BY t.barbero_id ASC, t.numero ASC
        """)
    turnos = cursor.fetchall()
    for t in turnos:
        t['created_at'] = str(t['created_at'])
    cursor.close(); conn.close()
    return jsonify({'turnos': turnos})


@app.route('/api/turno/siguiente', methods=['PUT'])
def siguiente_turno():
    data = request.json or {}
    barbero_id = data.get('barbero_id', 1)
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("UPDATE turnos SET estado='completado' WHERE estado='en_atencion' AND barbero_id=%s", (barbero_id,))

    # Priorizar citas sobre walk-ins
    cursor.execute("""
        SELECT * FROM turnos
        WHERE estado='esperando' AND DATE(created_at)=CURDATE() AND barbero_id=%s
        ORDER BY tipo DESC, numero ASC LIMIT 1
    """, (barbero_id,))
    siguiente = cursor.fetchone()
    if siguiente:
        cursor.execute("UPDATE turnos SET estado='en_atencion' WHERE id=%s", (siguiente['id'],))
        conn.commit()
        siguiente['created_at'] = str(siguiente['created_at'])
        siguiente['updated_at'] = str(siguiente.get('updated_at',''))
        socketio.emit('turno_cambiado', {'barbero_id': barbero_id, 'turno_actual': siguiente})
    else:
        conn.commit()
        socketio.emit('turno_cambiado', {'barbero_id': barbero_id, 'turno_actual': None})
    cursor.close(); conn.close()
    return jsonify({'success': True, 'siguiente': siguiente})


@app.route('/api/turno/cancelar/<int:turno_id>', methods=['PUT'])
def cancelar_turno(turno_id):
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT barbero_id FROM turnos WHERE id=%s", (turno_id,))
    t = cursor.fetchone()
    cursor.execute("UPDATE turnos SET estado='cancelado' WHERE id=%s", (turno_id,))
    conn.commit()
    cursor.close(); conn.close()
    if t:
        socketio.emit('turno_cancelado', {'id': turno_id, 'barbero_id': t['barbero_id']})
    return jsonify({'success': True})


@app.route('/api/turno/posicion/<int:numero>', methods=['GET'])
def posicion_turno(numero):
    barbero_id = request.args.get('barbero_id', 1)
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("""
        SELECT COUNT(*) as antes FROM turnos
        WHERE estado='esperando' AND numero<%s
        AND DATE(created_at)=CURDATE() AND barbero_id=%s
    """, (numero, barbero_id))
    antes = cursor.fetchone()['antes']
    cursor.execute("SELECT * FROM turnos WHERE numero=%s AND DATE(created_at)=CURDATE() AND barbero_id=%s", (numero, barbero_id))
    turno = cursor.fetchone()
    cursor.close(); conn.close()
    if turno:
        turno['created_at'] = str(turno['created_at'])
        turno['updated_at'] = str(turno.get('updated_at',''))
    return jsonify({'antes': antes, 'turno': turno})


# ─────────────────────────────────────────────
# API CITAS
# ─────────────────────────────────────────────

@app.route('/api/cita', methods=['POST'])
def crear_cita():
    data = request.json
    nombre     = data.get('nombre','').strip()
    telefono   = data.get('telefono','').strip()
    email      = data.get('email','').strip()
    servicio   = data.get('servicio','').strip()
    barbero_id = data.get('barbero_id', 1)
    fecha      = data.get('fecha','').strip()
    hora       = data.get('hora','').strip()
    if not all([nombre, telefono, servicio, fecha, hora]):
        return jsonify({'error': 'Faltan campos requeridos'}), 400
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT id FROM citas WHERE fecha=%s AND hora=%s AND barbero_id=%s AND estado!='cancelada'",
                   (fecha, hora, barbero_id))
    if cursor.fetchone():
        cursor.close(); conn.close()
        return jsonify({'error': 'Ese horario ya está ocupado con ese barbero. Elige otro.'}), 409
    cursor.execute("""
        INSERT INTO citas (nombre,telefono,email,servicio,barbero_id,fecha,hora)
        VALUES (%s,%s,%s,%s,%s,%s,%s)
    """, (nombre, telefono, email, servicio, barbero_id, fecha, hora))
    conn.commit()
    cursor.execute("SELECT nombre FROM barberos WHERE id=%s", (barbero_id,))
    barbero = cursor.fetchone()
    cursor.close(); conn.close()
    return jsonify({'success': True, 'barbero': barbero['nombre'],
                    'mensaje': f'Cita agendada para el {fecha} a las {hora}'}), 201


@app.route('/api/citas', methods=['GET'])
def listar_citas():
    fecha      = request.args.get('fecha','')
    barbero_id = request.args.get('barbero_id','')
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    query = "SELECT c.*, b.nombre as barbero_nombre FROM citas c JOIN barberos b ON c.barbero_id=b.id WHERE c.fecha>=CURDATE()"
    params = []
    if fecha:
        query = "SELECT c.*, b.nombre as barbero_nombre FROM citas c JOIN barberos b ON c.barbero_id=b.id WHERE c.fecha=%s"
        params.append(fecha)
    if barbero_id:
        query += " AND c.barbero_id=%s"
        params.append(barbero_id)
    query += " ORDER BY c.fecha ASC, c.hora ASC"
    cursor.execute(query, params)
    citas = cursor.fetchall()
    for c in citas:
        c['fecha'] = str(c['fecha'])
        c['created_at'] = str(c['created_at'])
    cursor.close(); conn.close()
    return jsonify({'citas': citas})


@app.route('/api/cita/<int:cita_id>', methods=['PUT'])
def actualizar_cita(cita_id):
    data = request.json
    estado = data.get('estado','')
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE citas SET estado=%s WHERE id=%s", (estado, cita_id))
    conn.commit()
    cursor.close(); conn.close()
    return jsonify({'success': True})


@app.route('/api/horarios', methods=['GET'])
def horarios_disponibles():
    fecha      = request.args.get('fecha','')
    barbero_id = request.args.get('barbero_id', 1)
    todos = ['09:00','09:30','10:00','10:30','11:00','11:30',
             '12:00','12:30','13:00','13:30','14:00','14:30',
             '15:00','15:30','16:00','16:30','17:00','17:30',
             '18:00','18:30','19:00','19:30']
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT hora FROM citas WHERE fecha=%s AND barbero_id=%s AND estado!='cancelada'",
                   (fecha, barbero_id))
    ocupados = [row[0] for row in cursor.fetchall()]
    cursor.close(); conn.close()
    return jsonify({'disponibles': [h for h in todos if h not in ocupados], 'ocupados': ocupados})


# ─────────────────────────────────────────────
# WEBSOCKETS
# ─────────────────────────────────────────────

@socketio.on('connect')
def on_connect():
    print('Cliente conectado')

@socketio.on('disconnect')
def on_disconnect():
    print('Cliente desconectado')

if __name__ == '__main__':
    init_db()
    socketio.run(app, debug=True, host='0.0.0.0', port=5000)
