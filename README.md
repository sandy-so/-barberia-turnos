# 💈 Zero Grados Barbershop — Sistema de Turnos Inteligente

Sistema IoT de turnos en tiempo real para barbería. Tres vistas:
- `/` — App del cliente (desde el celular vía QR)
- `/barbero` — Panel del barbero
- `/pantalla` — Pantalla grande de la barbería

## 🛠️ Instalación

### 1. Requisitos
- Python 3.10+
- MySQL 8.0+

### 2. Clonar/copiar el proyecto
```bash
cd barberia_turnos
```

### 3. Instalar dependencias
```bash
pip install -r requirements.txt
```

### 4. Configurar variables de entorno
```bash
cp .env.example .env
# Edita .env con tus datos de MySQL
```

### 5. Ejecutar
```bash
python app.py
```
La app crea la base de datos automáticamente al iniciar.

### 6. Acceso
- `http://localhost:5000` → Cliente
- `http://localhost:5000/barbero` → Barbero
- `http://localhost:5000/pantalla` → Pantalla TV

### 7. QR para celular
Genera un QR apuntando a `http://TU_IP_LOCAL:5000`
Ejemplo: `http://192.168.1.100:5000`

## 📁 Estructura
```
barberia_turnos/
├── app.py           # Flask + API + WebSockets
├── database.py      # Conexión y creación de BD
├── requirements.txt
├── .env             # Variables de entorno (no subir a git)
└── templates/
    ├── cliente.html  # App del cliente
    ├── barbero.html  # Panel del barbero
    └── pantalla.html # Pantalla grande
```

## 🔌 API Endpoints
| Método | Ruta | Descripción |
|--------|------|-------------|
| POST | `/api/turno` | Registrar nuevo turno |
| GET | `/api/turno/actual` | Turno en atención |
| GET | `/api/turno/lista` | Todos los turnos del día |
| PUT | `/api/turno/siguiente` | Avanzar al siguiente |
| PUT | `/api/turno/cancelar/<id>` | Cancelar turno |
| GET | `/api/turno/posicion/<numero>` | Posición de un turno |

## 📡 WebSocket Events
- `turno_nuevo` → Se registró un nuevo turno
- `turno_cambiado` → El turno actual cambió
- `turno_cancelado` → Se canceló un turno

## 🚀 Deploy gratuito (Railway)
1. Subir el proyecto a GitHub
2. Entrar a railway.app y conectar el repo
3. Agregar las variables de entorno del .env
4. Railway despliega automáticamente
