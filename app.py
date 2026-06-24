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

# ─────────────────────────────────────────────
# PÁGINAS
# ─────────────────────────────────────────────

@app.route('/')
def cliente():
    """App del cliente — tomar turno y ver posición"""
    return render_template('cliente.html')

@app.route('/barbero')
def barbero():
    """Panel del barbero — ver y avanzar turnos"""
    return render_template('barbero.html')

@app.route('/pantalla')
def pantalla():
    """Pantalla grande de la barbería — turno actual"""
    return render_template('pantalla.html')

# ─────────────────────────────────────────────
# API TURNOS
# ─────────────────────────────────────────────

@app.route('/api/turno', methods=['POST'])
def registrar_turno():
    """El cliente registra su turno"""
    data = request.json
    nombre = data.get('nombre', '').strip()
    servicio = data.get('servicio', '').strip()

    if not nombre or not servicio:
        return jsonify({'error': 'Nombre y servicio son requeridos'}), 400

    conn = get_connection()
    cursor = conn.cursor(dictionary=True)

    # Calcular siguiente número de turno
    cursor.execute("SELECT MAX(numero) as ultimo FROM turnos WHERE DATE(created_at) = CURDATE()")
    resultado = cursor.fetchone()
    ultimo = resultado['ultimo'] or 0
    nuevo_numero = ultimo + 1

    cursor.execute("""
        INSERT INTO turnos (numero, nombre, servicio, estado)
        VALUES (%s, %s, %s, 'esperando')
    """, (nuevo_numero, nombre, servicio))

    conn.commit()

    # Contar cuántos hay antes
    cursor.execute("""
        SELECT COUNT(*) as antes FROM turnos
        WHERE estado = 'esperando'
        AND numero < %s
        AND DATE(created_at) = CURDATE()
    """, (nuevo_numero,))
    antes = cursor.fetchone()['antes']

    cursor.close()
    conn.close()

    turno_info = {
        'numero': nuevo_numero,
        'nombre': nombre,
        'servicio': servicio,
        'antes': antes
    }

    # Notificar a todos en tiempo real
    socketio.emit('turno_nuevo', turno_info)

    return jsonify({'success': True, 'turno': turno_info}), 201


@app.route('/api/turno/actual', methods=['GET'])
def turno_actual():
    """Retorna el turno que se está atendiendo ahora"""
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("""
        SELECT * FROM turnos
        WHERE estado = 'en_atencion'
        ORDER BY updated_at DESC
        LIMIT 1
    """)
    turno = cursor.fetchone()

    cursor.close()
    conn.close()

    if turno:
        # Serializar datetime
        turno['created_at'] = str(turno['created_at'])
        turno['updated_at'] = str(turno['updated_at'])

    return jsonify({'turno_actual': turno})


@app.route('/api/turno/lista', methods=['GET'])
def lista_turnos():
    """Lista de turnos en espera"""
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("""
        SELECT id, numero, nombre, servicio, estado, created_at
        FROM turnos
        WHERE estado IN ('esperando', 'en_atencion')
        AND DATE(created_at) = CURDATE()
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
    """Barbero avanza al siguiente turno"""
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)

    # Marcar el turno actual como completado
    cursor.execute("""
        UPDATE turnos SET estado = 'completado'
        WHERE estado = 'en_atencion'
    """)

    # Llamar al siguiente en espera
    cursor.execute("""
        SELECT * FROM turnos
        WHERE estado = 'esperando'
        AND DATE(created_at) = CURDATE()
        ORDER BY numero ASC
        LIMIT 1
    """)
    siguiente = cursor.fetchone()

    if siguiente:
        cursor.execute("""
            UPDATE turnos SET estado = 'en_atencion'
            WHERE id = %s
        """, (siguiente['id'],))
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
    """Cancela un turno específico"""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        UPDATE turnos SET estado = 'cancelado'
        WHERE id = %s
    """, (turno_id,))

    conn.commit()
    cursor.close()
    conn.close()

    socketio.emit('turno_cancelado', {'id': turno_id})
    return jsonify({'success': True})


@app.route('/api/turno/posicion/<int:numero>', methods=['GET'])
def posicion_turno(numero):
    """Cuántos hay antes de este turno"""
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("""
        SELECT COUNT(*) as antes FROM turnos
        WHERE estado = 'esperando'
        AND numero < %s
        AND DATE(created_at) = CURDATE()
    """, (numero,))
    antes = cursor.fetchone()['antes']

    cursor.execute("""
        SELECT * FROM turnos
        WHERE numero = %s AND DATE(created_at) = CURDATE()
    """, (numero,))
    turno = cursor.fetchone()

    cursor.close()
    conn.close()

    if turno:
        turno['created_at'] = str(turno['created_at'])
        turno['updated_at'] = str(turno.get('updated_at', ''))

    return jsonify({'antes': antes, 'turno': turno})


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
