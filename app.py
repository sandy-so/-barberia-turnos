from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
from flask_socketio import SocketIO, emit
from database import get_connection, init_db
import os
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'clave_secreta')
CORS(app)
socketio = SocketIO(app, cors_allowed_origins="*")

# Inicializar BD automáticamente
with app.app_context():
    try:
        init_db()
    except Exception as e:
        print(f"DB init error: {e}")

# ─────────────────────────────────────────────
# PÁGINAS
# ─────────────────────────────────────────────

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
# API TURNOS
# ─────────────────────────────────────────────

@app.route('/api/turno', methods=['POST'])
def registrar_turno():
    data = request.json
    nombre = data.get('nombre', '').strip()
    servicio = data.get('servicio', '').strip()
    if not nombre or not servicio:
        return jsonify({'error': 'Nombre y servicio son requeridos'}), 400
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT MAX(numero) as ultimo FROM turnos WHERE DATE(created_at) = CURDATE()")
    resultado = cursor.fetchone()
    ultimo = resultado['ultimo'] or 0
    nuevo_numero = ultimo + 1
    cursor.execute("""
        INSERT INTO turnos (numero, nombre, servicio, estado)
        VALUES (%s, %s, %s, 'esperando')
    """, (nuevo_numero, nombre, servicio))
    conn.commit()
    cursor.execute("""
        SELECT COUNT(*) as antes FROM turnos
        WHERE estado = 'esperando' AND numero < %s AND DATE(created_at) = CURDATE()
    """, (nuevo_numero,))
    antes = cursor.fetchone()['antes']
    cursor.close()
    conn.close()
    turno_info = {'numero': nuevo_numero, 'nombre': nombre, 'servicio': servicio, 'antes': antes}
    socketio.emit('turno_nuevo', turno_info)
    return jsonify({'success': True, 'turno': turno_info}), 201


@app.route('/api/turno/actual', methods=['GET'])
def turno_actual():
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("""
        SELECT * FROM turnos WHERE estado = 'en_atencion'
        ORDER BY updated_at DESC LIMIT 1
    """)
    turno = cursor.fetchone()
    cursor.close()
    conn.close()
    if turno:
        turno['created_at'] = str(turno['created_at'])
        turno['updated_at'] = str(turno['updated_at'])
    return jsonify({'turno_actual': turno})


@app.route('/api/turno/lista', methods=['GET'])
def lista_turnos():
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("""
        SELECT id, numero, nombre, servicio, estado, created_at FROM turnos
        WHERE estado IN ('esperando', 'en_atencion') AND DATE(created_at) = CURDATE()
        ORDER BY numero ASC
    """)
    turnos = cursor.fetchall()
    for t in turnos:
        t['created_at'] = str(t['created_at'])
    cursor.close()
    conn.close()
    return jsonify({'turnos': turnos})


@app.route('/api/turno/siguiente', methods=['PUT'])
def siguiente_turno():
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("UPDATE turnos SET estado = 'completado' WHERE estado = 'en_atencion'")
    cursor.execute("""
        SELECT * FROM turnos WHERE estado = 'esperando' AND DATE(created_at) = CURDATE()
        ORDER BY numero ASC LIMIT 1
    """)
    siguiente = cursor.fetchone()
    if siguiente:
        cursor.execute("UPDATE turnos SET estado = 'en_atencion' WHERE id = %s", (siguiente['id'],))
        conn.commit()
        siguiente['created_at'] = str(siguiente['created_at'])
        siguiente['updated_at'] = str(siguiente.get('updated_at', ''))
        socketio.emit('turno_cambiado', {'turno_actual': siguiente})
    else:
        conn.commit()
        socketio.emit('turno_cambiado', {'turno_actual': None})
    cursor.close()
    conn.close()
    return jsonify({'success': True, 'siguiente': siguiente})


@app.route('/api/turno/cancelar/<int:turno_id>', methods=['PUT'])
def cancelar_turno(turno_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE turnos SET estado = 'cancelado' WHERE id = %s", (turno_id,))
    conn.commit()
    cursor.close()
    conn.close()
    socketio.emit('turno_cancelado', {'id': turno_id})
    return jsonify({'success': True})


@app.route('/api/turno/posicion/<int:numero>', methods=['GET'])
def posicion_turno(numero):
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("""
        SELECT COUNT(*) as antes FROM turnos
        WHERE estado = 'esperando' AND numero < %s AND DATE(created_at) = CURDATE()
    """, (numero,))
    antes = cursor.fetchone()['antes']
    cursor.execute("SELECT * FROM turnos WHERE numero = %s AND DATE(created_at) = CURDATE()", (numero,))
    turno = cursor.fetchone()
    cursor.close()
    conn.close()
    if turno:
        turno['created_at'] = str(turno['created_at'])
        turno['updated_at'] = str(turno.get('updated_at', ''))
    return jsonify({'antes': antes, 'turno': turno})


# ─────────────────────────────────────────────
# API CITAS
# ─────────────────────────────────────────────

@app.route('/api/cita', methods=['POST'])
def crear_cita():
    data = request.json
    nombre   = data.get('nombre', '').strip()
    telefono = data.get('telefono', '').strip()
    email    = data.get('email', '').strip()
    servicio = data.get('servicio', '').strip()
    fecha    = data.get('fecha', '').strip()
    hora     = data.get('hora', '').strip()
    if not all([nombre, telefono, servicio, fecha, hora]):
        return jsonify({'error': 'Faltan campos requeridos'}), 400
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT id FROM citas WHERE fecha=%s AND hora=%s AND estado!='cancelada'", (fecha, hora))
    if cursor.fetchone():
        cursor.close(); conn.close()
        return jsonify({'error': 'Ese horario ya está ocupado. Elige otro.'}), 409
    cursor.execute("""
        INSERT INTO citas (nombre, telefono, email, servicio, fecha, hora)
        VALUES (%s, %s, %s, %s, %s, %s)
    """, (nombre, telefono, email, servicio, fecha, hora))
    conn.commit()
    cursor.close(); conn.close()
    return jsonify({'success': True, 'mensaje': f'Cita agendada para el {fecha} a las {hora}'}), 201


@app.route('/api/citas', methods=['GET'])
def listar_citas():
    fecha = request.args.get('fecha', '')
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    if fecha:
        cursor.execute("SELECT * FROM citas WHERE fecha=%s ORDER BY hora ASC", (fecha,))
    else:
        cursor.execute("SELECT * FROM citas WHERE fecha>=CURDATE() ORDER BY fecha ASC, hora ASC")
    citas = cursor.fetchall()
    for c in citas:
        c['fecha'] = str(c['fecha'])
        c['created_at'] = str(c['created_at'])
    cursor.close(); conn.close()
    return jsonify({'citas': citas})


@app.route('/api/cita/<int:cita_id>', methods=['PUT'])
def actualizar_cita(cita_id):
    data = request.json
    estado = data.get('estado', '')
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE citas SET estado=%s WHERE id=%s", (estado, cita_id))
    conn.commit()
    cursor.close(); conn.close()
    return jsonify({'success': True})


@app.route('/api/horarios', methods=['GET'])
def horarios_disponibles():
    fecha = request.args.get('fecha', '')
    todos = ['09:00','09:30','10:00','10:30','11:00','11:30',
             '12:00','12:30','13:00','13:30','14:00','14:30',
             '15:00','15:30','16:00','16:30','17:00','17:30',
             '18:00','18:30','19:00','19:30']
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT hora FROM citas WHERE fecha=%s AND estado!='cancelada'", (fecha,))
    ocupados = {row[0] for row in cursor.fetchall()}
    cursor.close(); conn.close()
    return jsonify({'disponibles': [h for h in todos if h not in ocupados]})


# ─────────────────────────────────────────────
# WEBSOCKETS
# ─────────────────────────────────────────────

@socketio.on('connect')
def on_connect():
    print('Cliente conectado')

@socketio.on('disconnect')
def on_disconnect():
    print('Cliente desconectado')

# ─────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────

if __name__ == '__main__':
    init_db()
    socketio.run(app, debug=True, host='0.0.0.0', port=5000)
