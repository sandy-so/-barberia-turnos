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
        CREATE TABLE IF NOT EXISTS barberos (
            id INT AUTO_INCREMENT PRIMARY KEY,
            nombre VARCHAR(100) NOT NULL,
            activo BOOLEAN DEFAULT TRUE
        )
    """)

    cursor.execute("""
        INSERT IGNORE INTO barberos (id, nombre) VALUES
        (1, 'Cristian'),
        (2, 'Barbero 2'),
        (3, 'Barbero 3')
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS turnos (
            id INT AUTO_INCREMENT PRIMARY KEY,
            numero INT NOT NULL,
            nombre VARCHAR(100) NOT NULL,
            servicio VARCHAR(100) NOT NULL,
            barbero_id INT NOT NULL DEFAULT 1,
            tipo ENUM('walk-in','cita') DEFAULT 'walk-in',
            estado ENUM('esperando','en_atencion','completado','cancelado') DEFAULT 'esperando',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS citas (
            id INT AUTO_INCREMENT PRIMARY KEY,
            nombre VARCHAR(100) NOT NULL,
            telefono VARCHAR(20) NOT NULL,
            email VARCHAR(100),
            servicio VARCHAR(100) NOT NULL,
            barbero_id INT NOT NULL DEFAULT 1,
            fecha DATE NOT NULL,
            hora VARCHAR(10) NOT NULL,
            estado ENUM('pendiente','confirmada','cancelada','completada') DEFAULT 'pendiente',
            turno_generado BOOLEAN DEFAULT FALSE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    conn.commit()
    cursor.close()
    conn.close()
    print("Base de datos inicializada correctamente.")
