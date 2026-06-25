import mysql.connector
import os
from dotenv import load_dotenv

load_dotenv()

def get_connection():
    return mysql.connector.connect(
        host=os.getenv("DB_HOST", "localhost"),
        user=os.getenv("DB_USER", "root"),
        password=os.getenv("DB_PASSWORD", ""),
        database=os.getenv("DB_NAME", "railway"),
        port=int(os.getenv("DB_PORT", 3306))
    )

def init_db():
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS turnos (
            id INT AUTO_INCREMENT PRIMARY KEY,
            numero INT NOT NULL,
            nombre VARCHAR(100) NOT NULL,
            servicio VARCHAR(100) NOT NULL,
            estado ENUM('esperando', 'en_atencion', 'completado', 'cancelado') DEFAULT 'esperando',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS configuracion (
            id INT PRIMARY KEY DEFAULT 1,
            turno_actual INT DEFAULT 0,
            barberia_nombre VARCHAR(100) DEFAULT 'Zero Grados Barbershop',
            activo BOOLEAN DEFAULT TRUE
        )
    """)

    cursor.execute("""
        INSERT IGNORE INTO configuracion (id, turno_actual, barberia_nombre)
        VALUES (1, 0, 'Zero Grados Barbershop')
    """)

    conn.commit()
    cursor.close()
    conn.close()
    print("Base de datos inicializada correctamente.")