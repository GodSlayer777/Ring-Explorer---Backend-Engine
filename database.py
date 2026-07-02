import sqlite3
import os
from contextlib import contextmanager


BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BASE_DIR, "hunter_bot.db")

# Importaciones de datos estáticos
try:
    from Data.armas_db import ARMAS_DB
    from Data.armaduras_db import ARMADURAS_DB
    from Data.items_db import TIENDA_OBJETOS
except ImportError:
    ARMAS_DB = []
    ARMADURAS_DB = []
    TIENDA_OBJETOS = []

# ==========================================
#  1. GESTOR DE CONEXIÓN (CORE)
# ==========================================
@contextmanager
def get_db():
    """Maneja la conexión a la base de datos de forma segura y ultrarrápida."""
    # El timeout=10.0 da margen si hay muchas personas jugando a la vez
    conn = sqlite3.connect(DB_PATH, timeout=10.0) 
    conn.row_factory = sqlite3.Row 
    
    #Permite leer y escribir al mismo tiempo
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;") 
    
    try:
        yield conn
        conn.commit() 
    except Exception as e:
        conn.rollback() 
        raise e
    finally:
        conn.close()

def init_db():
    """Inicializa tablas y aplica optimizaciones."""
    with get_db() as conn:
        conn.execute("PRAGMA journal_mode=WAL;")  
        conn.execute("PRAGMA synchronous=NORMAL;")
        conn.execute("PRAGMA cache_size=10000;")

        # TABLAS
        conn.execute('''CREATE TABLE IF NOT EXISTS jugadores (
            id INTEGER PRIMARY KEY,
            nombre_cazador TEXT,
            hr INTEGER DEFAULT 1,
            nivel INTEGER DEFAULT 1,
            zenny INTEGER DEFAULT 0,
            buff TEXT DEFAULT "Ninguno",
            hp INTEGER DEFAULT 100,
            hp_max INTEGER DEFAULT 100,
            mp INTEGER DEFAULT 50,
            mp_max INTEGER DEFAULT 50,
            energia INTEGER DEFAULT 100,
            ataque INTEGER DEFAULT 15,
            defensa INTEGER DEFAULT 5,
            agilidad INTEGER DEFAULT 10,
            arma_equipada TEXT DEFAULT "Cuchillo de Cazador",
            armadura_equipada TEXT DEFAULT "Ropa de Viajero",
            rango TEXT DEFAULT "Novato",
            reputacion INTEGER DEFAULT 0,
            experiencia INTEGER DEFAULT 0,
            puntos_maestria INTEGER DEFAULT 0,
            puntos_habilidad INTEGER DEFAULT 0,
            habilidades_adquiridas TEXT DEFAULT '',
            contador_maestria INTEGER DEFAULT 0,
            clase_divina TEXT DEFAULT NULL,
            ultima_mision TEXT DEFAULT NULL
        )''')

        conn.execute('''CREATE TABLE IF NOT EXISTS inventario (
            user_id INTEGER,
            item_nombre TEXT,
            cantidad INTEGER,
            PRIMARY KEY (user_id, item_nombre)
        )''')

        conn.execute('''CREATE TABLE IF NOT EXISTS misiones_completadas (
            user_id INTEGER,
            nombre_mision TEXT,
            PRIMARY KEY (user_id, nombre_mision)
        )''')

        conn.execute('''CREATE TABLE IF NOT EXISTS maestrias (
            user_id INTEGER,
            arma_nombre TEXT,
            nivel INTEGER DEFAULT 0,
            competencia INTEGER DEFAULT 0,
            PRIMARY KEY (user_id, arma_nombre)
        )''')

        conn.execute('''CREATE TABLE IF NOT EXISTS armas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT UNIQUE,
            tipo TEXT,
            ataque INTEGER,
            elemento TEXT DEFAULT "Físico",
            estado TEXT DEFAULT "Ninguno",
            precio INTEGER DEFAULT 0,
            rareza INTEGER DEFAULT 1
        )''')

        conn.execute('''CREATE TABLE IF NOT EXISTS armaduras (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT UNIQUE,
            defensa INTEGER,
            agilidad INTEGER DEFAULT 0,
            precio INTEGER DEFAULT 0,
            rareza INTEGER DEFAULT 1
        )''')

        conn.execute("CREATE INDEX IF NOT EXISTS idx_inv_user ON inventario(user_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_maestrias_user ON maestrias(user_id)")
        try:
            conn.execute("ALTER TABLE mascotas ADD COLUMN hp INTEGER DEFAULT 100")
        except sqlite3.OperationalError:
            pass
            
        try:
            conn.execute("ALTER TABLE mascotas ADD COLUMN hp_max INTEGER DEFAULT 100")
        except sqlite3.OperationalError:
            pass
        conn.execute("""CREATE TABLE IF NOT EXISTS huevos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT,
            especie TEXT,
            rareza TEXT DEFAULT 'Normal',
            fecha_obtencion TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )""")
        conn.execute('''CREATE TABLE IF NOT EXISTS habilidades_niveles (
            user_id TEXT,
            habilidad_id TEXT,
            nivel INTEGER DEFAULT 1,
            PRIMARY KEY (user_id, habilidad_id)
        )''')
        conn.execute("CREATE INDEX IF NOT EXISTS idx_hab_niveles_user ON habilidades_niveles(user_id);")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_jugadores_id ON jugadores(id);")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_inventario_user ON inventario(user_id);")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_mascotas_user ON mascotas(user_id);")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_misiones_user ON misiones_completadas(user_id);")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_huevos_user ON huevos(user_id);")

        inicializar_tabla_mascotas()
        migrar_mascotas_activas()
        migrar_mascotas_xp()
    _migrar_columnas_faltantes()
    print("✅ Base de datos inicializada y verificada.")

def inicializar_tabla_mascotas():
    """Crea la tabla si no existe. Asegúrate de que esta función se llame en init_db."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS mascotas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT,
            especie TEXT,
            nombre TEXT,
            nivel INTEGER,
            nivel_max INTEGER,
            rareza TEXT,
            stat_mult REAL,
            atk INTEGER,
            def INTEGER,
            agi INTEGER,
            hambre INTEGER,
            felicidad INTEGER,
            limpieza INTEGER,
            equipada INTEGER
        )
    """)
    conn.commit()
    conn.close()


def crear_registro_mascota(user_id, especie, nombre_personalizado, rareza, limite_nivel, multiplicador):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        INSERT INTO mascotas (
            user_id, especie, nombre, nivel, nivel_max, rareza, 
            stat_mult, atk, def, agi, hambre, felicidad, limpieza, equipada
        ) VALUES (?, ?, ?, 1, ?, ?, ?, ?, 10, 10, 5, 100, 100, 100, 0)
    """, (str(user_id), especie, nombre_personalizado, limite_nivel, rareza, multiplicador))
    conn.commit()
    conn.close()

def _migrar_columnas_faltantes():
    columnas_nuevas = [
        ("jugadores", "reputacion", "INTEGER DEFAULT 0"),
        ("jugadores", "experiencia", "INTEGER DEFAULT 0"),
        ("jugadores", "puntos_maestria", "INTEGER DEFAULT 0"),
        ("jugadores", "clase_divina", "TEXT DEFAULT NULL"),
        ("jugadores", "ultima_mision", "TEXT DEFAULT NULL"),
        ("maestrias", "competencia", "INTEGER DEFAULT 0"),
        ("jugadores", "mp", "INTEGER DEFAULT 50"),
        ("jugadores", "mp_max", "INTEGER DEFAULT 50"),
        ("jugadores", "nivel", "INTEGER DEFAULT 1"),
        ("jugadores", "hp_max", "INTEGER DEFAULT 100"),
        ("jugadores", "agilidad", "INTEGER DEFAULT 25"),
        ("jugadores", "puntos_habilidad", "INTEGER DEFAULT 0"),
        ("jugadores", "contador_maestria", "INTEGER DEFAULT 0"),
        ("jugadores", "habilidades_adquiridas", "TEXT DEFAULT ''"),
        ("habilidades_niveles", "usos", "INTEGER DEFAULT 0")
    ]
    with get_db() as conn:
        for tabla, col, tipo in columnas_nuevas:
            try:
                conn.execute(f"ALTER TABLE {tabla} ADD COLUMN {col} {tipo}")
            except sqlite3.OperationalError:
                pass 

def check_and_update_db():
    
    try:
        conn = sqlite3.connect(DB_PATH) # Usa el nombre de tu archivo
        c = conn.cursor()
        
        # Intentamos añadir la columna. Si ya existe, dará un error y pasará al 'except' sin romper nada.
        c.execute("ALTER TABLE jugadores ADD COLUMN piso_torre INTEGER DEFAULT 1")
        conn.commit()
        print("✅ Base de datos actualizada: Columna 'piso_torre' añadida.")
        c.execute("ALTER TABLE jugadores ADD COLUMN torre_buff_hp REAL DEFAULT 1.0")
        c.execute("ALTER TABLE jugadores ADD COLUMN torre_buff_atk REAL DEFAULT 1.0")
        c.execute("ALTER TABLE jugadores ADD COLUMN torre_buff_def REAL DEFAULT 1.0")
        c.execute("ALTER TABLE jugadores ADD COLUMN torre_buff_fortuna INTEGER DEFAULT 0")
        
        conn.commit()
        print("✅ Base de datos actualizada: Columnas de Torre añadidas.")
    except sqlite3.OperationalError:
        # Esto significa que la columna ya existe, todo está perfecto.
        pass
    except Exception as e:
        print(f"Error actualizando DB: {e}")
    finally:
        conn.close()
    init_db()

# ==========================================
#  HELPER INTERNO
# ==========================================
def _add_material_db(conn, user_id, item_nombre, cantidad):
    """
    Versión interna de add_material que recibe una conexión ya abierta.
    Evita el error 'database is locked'.
    """
    
    conn.execute('''
        INSERT INTO inventario (user_id, item_nombre, cantidad) VALUES (?, ?, ?)
        ON CONFLICT(user_id, item_nombre) DO UPDATE SET cantidad = cantidad + ?
    ''', (user_id, item_nombre, cantidad, cantidad))

# ==========================================
#  2. SINCRONIZACIÓN DE DATOS
# ==========================================
def sincronizar_catalogo():
    print(" Sincronizando catálogos")
    with get_db() as conn:
        for a in ARMAS_DB:
            conn.execute('''
                INSERT INTO armas (nombre, tipo, ataque, precio, rareza, elemento, estado)
                VALUES (:nombre, :tipo, :ataque, :precio, :rareza, :elemento, :estado)
                ON CONFLICT(nombre) DO UPDATE SET
                tipo=excluded.tipo, ataque=excluded.ataque, precio=excluded.precio, 
                rareza=excluded.rareza, elemento=excluded.elemento, estado=excluded.estado
            ''', {
                'nombre': a['nombre'], 'tipo': a.get('tipo', 'Desconocido'),
                'ataque': a.get('ataque', 0), 'precio': a.get('precio', 0),
                'rareza': a.get('rareza', 1), 'elemento': a.get('elemento', 'Físico'),
                'estado': a.get('estado', 'Ninguno')
            })
        
        for ar in ARMADURAS_DB:
            conn.execute('''
                INSERT INTO armaduras (nombre, defensa, agilidad, precio, rareza)
                VALUES (:nombre, :defensa, :agilidad, :precio, :rareza)
                ON CONFLICT(nombre) DO UPDATE SET
                defensa=excluded.defensa, agilidad=excluded.agilidad, 
                precio=excluded.precio, rareza=excluded.rareza
            ''', {
                'nombre': ar['nombre'], 'defensa': ar.get('defensa', 1),
                'agilidad': ar.get('agilidad', 0), 'precio': ar.get('precio', 0),
                'rareza': ar.get('rareza', 1)
            })
    print("✅ Catálogos sincronizados.")

# ==========================================
# 3. JUGADOR Y ESTADÍSTICAS
# ==========================================

def crear_nuevo_jugador(user_id, nombre):
    with get_db() as conn:
        try:
            conn.execute("INSERT INTO jugadores (id, nombre_cazador, zenny) VALUES (?, ?, 2000)", (user_id, nombre))
            # USAMOS LA VERSIÓN INTERNA CON LA CONEXIÓN YA ABIERTA
            _add_material_db(conn, user_id, "Hongo Sanador", 10) 
            return True
        except sqlite3.IntegrityError:
            return False

def get_player_data(user_id):
    with get_db() as conn:
        return conn.execute("SELECT * FROM jugadores WHERE id = ?", (user_id,)).fetchone()

def update_player_hp(user_id, nuevo_hp):
    with get_db() as conn:
        conn.execute("UPDATE jugadores SET hp = ? WHERE id = ?", (nuevo_hp, user_id))

def update_player_mp(user_id, nuevo_mp):
    """Actualiza los Puntos de Magia/Sistema del jugador, asegurando que no baje de 0."""
    nuevo_mp = max(0, nuevo_mp)
    with get_db() as conn:
        conn.execute("UPDATE jugadores SET mp = ? WHERE id = ?", (nuevo_mp, user_id))

def guardar_ultima_mision(user_id, nombre_mision):
    with get_db() as conn:
        conn.execute("UPDATE jugadores SET ultima_mision = ? WHERE id = ?", (nombre_mision, user_id))

def dar_xp_jugador(user_id, xp_ganada):
    """
    Otorga XP al jugador humano. Si supera el umbral, sube de nivel 
    y aumenta permanentemente sus estadísticas base.
    """
    with get_db() as conn:
        # Obtenemos los datos actuales del jugador
        row = conn.execute("SELECT nivel, experiencia, hp, hp_max, mp, mp_max, ataque, defensa, agilidad, puntos_habilidad FROM jugadores WHERE id = ?", (str(user_id),)).fetchone()
        if not row:
            return None, False # El jugador no existe
            
        nivel_actual = row['nivel']
        xp_actual = row['experiencia'] + xp_ganada
        
        # Estadísticas actuales
        hp = row['hp']
        hp_max = row['hp_max']
        ataque = row['ataque']
        defensa = row['defensa']
        agilidad = row['agilidad']
        mp = row['mp']
        mp_max = row['mp_max']
        
        subio_nivel = False
        
        # Fórmula de XP requerida para el siguiente nivel
        xp_req = int(100 * (nivel_actual ** 1.5))
        
        while xp_actual >= xp_req:
            xp_actual -= xp_req
            nivel_actual += 1
            subio_nivel = True
            
            hp_max += max(10, int(hp_max * 0.20))      # Sube 20%, o mínimo +10
            ataque += max(2, int(ataque * 0.15))       # Sube 15%, o mínimo +2
            defensa += max(1, int(defensa * 0.10))     # Sube 10%, o mínimo +1
            agilidad += max(1, int(agilidad * 0.10))   # Sube 10%, o mínimo +1
            mp_max += max(1, int(mp_max * 0.05))               # Sube 10%, o mínimo +1
            
            try:
                conn.execute("UPDATE jugadores SET puntos_habilidad = puntos_habilidad + 1 WHERE id = ?", (str(user_id),))
            except: pass


            xp_req = int(100 * (nivel_actual ** 1.5))
            
        if subio_nivel:

            hp = hp_max
            mp = mp_max
            conn.execute("""
                UPDATE jugadores 
                SET nivel = ?, experiencia = ?, hp = ?, hp_max = ?, mp = ?, mp_max = ?, ataque = ?, defensa = ?, agilidad = ?
                WHERE id = ?
            """, (nivel_actual, xp_actual, hp, hp_max, mp, mp_max, ataque, defensa, agilidad, str(user_id)))
            
            stats_nuevos = {
                "nivel": nivel_actual, "hp_max": hp_max, "mp": mp, "mp_max": mp_max,
                "ataque": ataque, "defensa": defensa, "agilidad": agilidad
            }
            return stats_nuevos, True
        else:
            conn.execute("UPDATE jugadores SET experiencia = ? WHERE id = ?", (xp_actual, str(user_id)))
            return {"experiencia": xp_actual, "xp_req": xp_req}, False

def obtener_agilidad_jugador(user_id):
    with get_db() as conn:
        res = conn.execute('''
            SELECT j.agilidad as base_agi, a.agilidad as armadura_agi_porcentaje 
            FROM jugadores j
            LEFT JOIN armaduras a ON j.armadura_equipada = a.nombre
            WHERE j.id = ?
        ''', (str(user_id),)).fetchone()
        
        if res:
            base = res['base_agi'] if res['base_agi'] else 25
            porcentaje = res['armadura_agi_porcentaje'] if res['armadura_agi_porcentaje'] else 0
            

            agilidad_final = int(base + (base * (porcentaje / 100.0)))
            return agilidad_final
            
        return 25

def get_clase_divina(user_id):
    with get_db() as conn:
        res = conn.execute("SELECT clase_divina FROM jugadores WHERE id = ?", (user_id,)).fetchone()
        return res['clase_divina'] if res else None

def set_clase_divina(user_id, clase):
    with get_db() as conn:
        conn.execute("UPDATE jugadores SET clase_divina = ? WHERE id = ?", (clase, user_id))

def update_buff_stats(user_id, buff_texto, nuevo_hp_ignorado, nueva_energia_ignorada, nuevo_ataque, nueva_defensa):
    with get_db() as conn:

        jugador = conn.execute("SELECT hp_max FROM jugadores WHERE id = ?", (user_id,)).fetchone()
        
        hp_tope = int(jugador['hp_max'] * 1.5) if "Vida" in buff_texto else jugador['hp_max']
        energia_tope = 150 if "Vida" in buff_texto else 100 
        

        conn.execute('''UPDATE jugadores 
                        SET buff = ?, hp = ?, energia = ?, ataque = ?, defensa = ?
                        WHERE id = ?''', 
                     (buff_texto, hp_tope, energia_tope, nuevo_ataque, nueva_defensa, user_id))

def admin_restar_vida(user_id, cantidad):
    with get_db() as conn:
        conn.execute("UPDATE jugadores SET hp = MAX(1, hp - ?) WHERE id = ?", (cantidad, user_id))

# ==========================================
#  4. INVENTARIO Y ECONOMÍA
# ==========================================

def get_material_cantidad(user_id, item_nombre):
    with get_db() as conn:

        if "Huevo" in item_nombre:

            conn.execute("DELETE FROM huevos WHERE julianday('now') - julianday(fecha_obtencion) > 6")
            
            especie = item_nombre.replace("Huevo de ", "") if item_nombre.startswith("Huevo de ") else item_nombre
            res = conn.execute("SELECT COUNT(*) as total FROM huevos WHERE user_id = ? AND especie = ?", (str(user_id), especie)).fetchone()
            return res['total'] if res else 0
            
        #  2. COMPORTAMIENTO NORMAL (INVENTARIO)
        res = conn.execute("SELECT cantidad FROM inventario WHERE user_id = ? AND item_nombre = ?", (str(user_id), item_nombre)).fetchone()
        return res['cantidad'] if res else 0


def add_material(user_id, item_nombre, cantidad):
    """Versión pública: abre su propia conexión e intercepta huevos."""
    with get_db() as conn:

        if "Huevo" in item_nombre:
            especie = item_nombre.replace("Huevo de ", "") if item_nombre.startswith("Huevo de ") else item_nombre
            
            for _ in range(cantidad):
                conn.execute("INSERT INTO huevos (user_id, especie, rareza) VALUES (?, ?, 'Normal')", (str(user_id), especie))
            return 


        _add_material_db(conn, user_id, item_nombre, cantidad)


def remove_material(user_id, item_nombre, cantidad):
    with get_db() as conn:

        if "Huevo" in item_nombre:
            especie = item_nombre.replace("Huevo de ", "") if item_nombre.startswith("Huevo de ") else item_nombre
            
            conn.execute("""
                DELETE FROM huevos 
                WHERE id IN (
                    SELECT id FROM huevos 
                    WHERE user_id = ? AND especie = ? 
                    ORDER BY fecha_obtencion ASC 
                    LIMIT ?
                )
            """, (str(user_id), especie, cantidad))
            return 


        conn.execute("UPDATE inventario SET cantidad = MAX(0, cantidad - ?) WHERE user_id = ? AND item_nombre = ?", (cantidad, str(user_id), item_nombre))


def get_inventory(user_id):
    with get_db() as conn:
        rows = conn.execute("SELECT item_nombre, cantidad FROM inventario WHERE user_id = ? AND cantidad > 0", (user_id,)).fetchall()
        return [(r['item_nombre'], r['cantidad']) for r in rows]

def add_zenny(user_id, cantidad):
    with get_db() as conn:
        conn.execute("UPDATE jugadores SET zenny = zenny + ? WHERE id = ?", (cantidad, user_id))

def cobrar_zenny(user_id, cantidad):
    with get_db() as conn:
        row = conn.execute("SELECT zenny FROM jugadores WHERE id = ?", (user_id,)).fetchone()
        if row and row['zenny'] >= cantidad:
            conn.execute("UPDATE jugadores SET zenny = zenny - ? WHERE id = ?", (cantidad, user_id))
            return True
        return False

def usar_objeto_curativo(user_id, nombre_objeto, cantidad_cura_ignorada):
    with get_db() as conn:
        inv = conn.execute("SELECT cantidad FROM inventario WHERE user_id = ? AND item_nombre = ?", (user_id, nombre_objeto)).fetchone()
        if not inv or inv['cantidad'] < 1: return "❌ No tienes ese objeto."
        

        jugador = conn.execute("SELECT hp, hp_max, buff FROM jugadores WHERE id = ?", (user_id,)).fetchone()
        

        max_hp = int(jugador['hp_max'] * 1.5) if "Vida" in jugador['buff'] else jugador['hp_max']
        
        if jugador['hp'] >= max_hp: return "💚 Salud llena."
        

        curacion_porcentual = int(max_hp * 0.25)
        

        nuevo_hp = min(jugador['hp'] + curacion_porcentual, max_hp)
        recuperado = nuevo_hp - jugador['hp']
        
        conn.execute("UPDATE inventario SET cantidad = cantidad - 1 WHERE user_id = ? AND item_nombre = ?", (user_id, nombre_objeto))
        conn.execute("UPDATE jugadores SET hp = ? WHERE id = ?", (nuevo_hp, user_id))
        
        return f"✨ Recuperaste {recuperado} PV (25%)."

# ==========================================
#  5. EQUIPO Y MAESTRÍA
# ==========================================

def equipar_arma(user_id, nombre_arma):
    with get_db() as conn:
        row = conn.execute("SELECT arma_equipada FROM jugadores WHERE id = ?", (user_id,)).fetchone()
        if row and row['arma_equipada']:
            _add_material_db(conn, user_id, row['arma_equipada'], 1)
        

        conn.execute("UPDATE jugadores SET arma_equipada = ? WHERE id = ?", (nombre_arma, user_id))

def equipar_armadura(user_id, nombre_armadura):
    with get_db() as conn:
        row = conn.execute("SELECT armadura_equipada FROM jugadores WHERE id = ?", (user_id,)).fetchone()
        if row and row['armadura_equipada'] and row['armadura_equipada'] != "Ropa de Viajero":
            _add_material_db(conn, user_id, row['armadura_equipada'], 1)
            

        conn.execute("UPDATE jugadores SET armadura_equipada = ? WHERE id = ?", (nombre_armadura, user_id))

def get_maestria_arma(user_id, arma_nombre):
    with get_db() as conn:
        res = conn.execute("SELECT nivel FROM maestrias WHERE user_id = ? AND arma_nombre = ?", (user_id, arma_nombre)).fetchone()
        return res['nivel'] if res else 0

def get_maestria_status(user_id, arma_nombre):
    with get_db() as conn:
        res = conn.execute("SELECT nivel, competencia FROM maestrias WHERE user_id = ? AND arma_nombre = ?", (user_id, arma_nombre)).fetchone()
        return (res['nivel'], res['competencia']) if res else (0, 0)

def add_competencia_arma(user_id, arma_nombre, cantidad=1):
    META_NIVEL = 15
    with get_db() as conn:
        res = conn.execute("SELECT nivel, competencia FROM maestrias WHERE user_id = ? AND arma_nombre = ?", (user_id, arma_nombre)).fetchone()
        if not res: return False, 0
        
        nivel, xp = res['nivel'], res['competencia'] + cantidad
        subio = False
        
        if xp >= META_NIVEL:
            subidos = xp // META_NIVEL
            nivel += subidos
            xp %= META_NIVEL
            subio = True
            
        conn.execute("UPDATE maestrias SET nivel = ?, competencia = ? WHERE user_id = ? AND arma_nombre = ?", (nivel, xp, user_id, arma_nombre))
        return subio, nivel

def subir_nivel_maestria(user_id, arma_nombre):
    with get_db() as conn:
        conn.execute('''
            INSERT INTO maestrias (user_id, arma_nombre, nivel) VALUES (?, ?, 1)
            ON CONFLICT(user_id, arma_nombre) DO UPDATE SET nivel = nivel + 1
        ''', (user_id, arma_nombre))

def add_puntos_maestria(user_id, cantidad):
    with get_db() as conn:
        conn.execute("UPDATE jugadores SET puntos_maestria = puntos_maestria + ? WHERE id = ?", (cantidad, user_id))

def get_puntos_maestria(user_id):
    with get_db() as conn:
        res = conn.execute("SELECT puntos_maestria FROM jugadores WHERE id = ?", (user_id,)).fetchone()
        return res['puntos_maestria'] if res else 0

def consumir_punto_maestria(user_id, cantidad=1):
    with get_db() as conn:
        conn.execute("UPDATE jugadores SET puntos_maestria = MAX(0, puntos_maestria - ?) WHERE id = ?", (cantidad, user_id))

def add_experiencia_global(user_id, cantidad=1):
    META_GLOBAL = 30
    subio = False
    with get_db() as conn:
        conn.execute("UPDATE jugadores SET contador_maestria = contador_maestria + ? WHERE id = ?", (cantidad, str(user_id)))
        row = conn.execute("SELECT contador_maestria FROM jugadores WHERE id = ?", (str(user_id),)).fetchone()
        
        xp = row['contador_maestria']
        if xp >= META_GLOBAL:
            pts = xp // META_GLOBAL
            xp %= META_GLOBAL
            conn.execute("UPDATE jugadores SET contador_maestria = ?, puntos_maestria = puntos_maestria + ? WHERE id = ?", (xp, pts, str(user_id)))
            subio = True
    return subio

def add_reputacion(user_id, cantidad):
    with get_db() as conn:
        conn.execute("UPDATE jugadores SET reputacion = reputacion + ? WHERE id = ?", (cantidad, user_id))

# ==========================================
#  6. SISTEMA DE MISIONES
# ==========================================

def registrar_mision_completada(user_id, nombre_mision):
    from Data.misiones_db import MISIONES_CLAVE, URGENTES_POR_RANGO
    
    with get_db() as conn:
        existe = conn.execute("SELECT 1 FROM misiones_completadas WHERE user_id = ? AND nombre_mision = ?", (user_id, nombre_mision)).fetchone()
        msg = ""
        puntos = 0
        
        if not existe:
            conn.execute("INSERT INTO misiones_completadas VALUES (?, ?)", (user_id, nombre_mision))
            if nombre_mision in MISIONES_CLAVE:
                puntos = 20
                conn.execute("UPDATE jugadores SET reputacion = reputacion + ? WHERE id = ?", (puntos, user_id))
                msg = f"\n✨ **¡Reputación +{puntos}!** (Misión Clave)"
            
            jugador = conn.execute("SELECT rango FROM jugadores WHERE id = ?", (user_id,)).fetchone()
            urgente = URGENTES_POR_RANGO.get(jugador['rango'])
            
            if urgente and nombre_mision == urgente['mision']:
                nuevo_rango = urgente['siguiente']
                conn.execute("UPDATE jugadores SET rango = ? WHERE id = ?", (nuevo_rango, user_id))
                msg += f"\n🏆 **¡ASCENSO!** Ahora eres rango **{nuevo_rango}**."
        else:
            msg = "\n(Ya completada, sin bonificación extra)."
            
        return msg, puntos

def get_completed_missions(user_id):
    with get_db() as conn:
        rows = conn.execute("SELECT nombre_mision FROM misiones_completadas WHERE user_id = ?", (user_id,)).fetchall()
        return [row['nombre_mision'] for row in rows]

# ==========================================
#  UTILS ADMIN / EXTRAS
# ==========================================
def admin_set_progress(user_id, nuevo_rango, nueva_reputacion):
    with get_db() as conn:
        conn.execute("UPDATE jugadores SET rango = ?, reputacion = ? WHERE id = ?", (nuevo_rango, nueva_reputacion, user_id))

def update_piso_torre(user_id, nuevo_piso):
    try:
        conn = sqlite3.connect(DB_PATH) # Usa DB_PATH para que encuentre bien el archivo
        c = conn.cursor()
        c.execute("UPDATE jugadores SET piso_torre = ? WHERE id = ?", (nuevo_piso, str(user_id)))
        conn.commit()
    except Exception as e:
        print(f"Error actualizando piso: {e}")
    finally:
        conn.close()
# ==========================================
#  SISTEMA DE DIFICULTADES COMPLETADAS
# ==========================================
def marcar_dificultad_completada(user_id, dificultad):
    with get_db() as conn:
        try:
            row = conn.execute("SELECT torre_completadas FROM jugadores WHERE id = ?", (str(user_id),)).fetchone()
            completadas = row['torre_completadas'] if row and row['torre_completadas'] else ""
            lista = completadas.split(',') if completadas else []
            
            if dificultad not in lista:
                lista.append(dificultad)
                nueva_cadena = ",".join(lista)
                conn.execute("UPDATE jugadores SET torre_completadas = ? WHERE id = ?", (nueva_cadena, str(user_id)))
        except sqlite3.OperationalError:
            conn.execute("ALTER TABLE jugadores ADD COLUMN torre_completadas TEXT DEFAULT ''")
            conn.execute("UPDATE jugadores SET torre_completadas = ? WHERE id = ?", (dificultad, str(user_id)))

def obtener_dificultades_completadas(user_id):
    with get_db() as conn:
        try:
            row = conn.execute("SELECT torre_completadas FROM jugadores WHERE id = ?", (str(user_id),)).fetchone()
            if row and row['torre_completadas']:
                return row['torre_completadas'].split(',')
        except sqlite3.OperationalError:
            pass
    return []

def update_dificultad_torre(user_id, dificultad):
    with get_db() as conn:
        try:
            conn.execute("UPDATE jugadores SET torre_dificultad = ? WHERE id = ?", (dificultad, str(user_id)))
        except sqlite3.OperationalError:
            conn.execute("ALTER TABLE jugadores ADD COLUMN torre_dificultad TEXT DEFAULT 'Explorador'")
            conn.execute("UPDATE jugadores SET torre_dificultad = ? WHERE id = ?", (dificultad, str(user_id)))

def reset_torre_buffs(user_id):
    """Limpia todas las bendiciones acumuladas en la Torre y restaura la vida/energía base."""
    with get_db() as conn:
        try:
            row = conn.execute("SELECT buff FROM jugadores WHERE id = ?", (str(user_id),)).fetchone()
            hp_base = 150 if row and row['buff'] and "Vida" in row['buff'] else 100
            
            conn.execute("""
                UPDATE jugadores 
                SET torre_buff_hp = 1.0, 
                    torre_buff_atk = 1.0, 
                    torre_buff_def = 1.0, 
                    torre_buff_fortuna = 0,
                    hp = ?,
                    energia = 100
                WHERE id = ?
            """, (hp_base, str(user_id)))
        except sqlite3.OperationalError:
            pass


def equipar_mascota_db(user_id, id_mascota):
    """Desequipa todas las mascotas y activa únicamente la nueva seleccionada."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    # 1. Mandamos TODAS las mascotas del jugador a la reserva (inactivas y sin equipar)
    c.execute("UPDATE mascotas SET equipada = 0, activa = 0 WHERE user_id = ?", (str(user_id),))
    
    # 2. Equipamos y ACTIVAMOS solo la mascota elegida
    c.execute("UPDATE mascotas SET equipada = 1, activa = 1 WHERE id = ?", (id_mascota,))
    
    conn.commit()
    conn.close()


def get_mascota_equipada(user_id):
    """Retorna los datos de la mascota activa."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("SELECT * FROM mascotas WHERE user_id = ? AND equipada = 1", (str(user_id),))
    res = c.fetchone()
    conn.close()
    return res

def crear_registro_mascota(user_id, especie, nombre_personalizado, rareza, limite_nivel, multiplicador, color_huevo="Normal"):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    c.execute("SELECT COUNT(*) FROM mascotas WHERE user_id = ? AND activa = 1", (str(user_id),))
    cantidad_activas = c.fetchone()[0]
    activa_status = 1 if cantidad_activas < 1 else 0

    rango_stats = {
        "Normal": (1, 20), "Alpha": (10, 30), "Apex": (25, 60),
        "Primal": (30, 80), "Portadora de Sangre Divina": (100, 150)
    }
    min_stat, max_stat = rango_stats.get(rareza, (1, 20))

    import random
    atk_inicial = random.randint(min_stat, max_stat)
    def_inicial = random.randint(min_stat, max_stat)
    hp_inicial = random.randint(min_stat * 5, max_stat * 5)
    
    if color_huevo == "Rojo":
        hp_inicial = int(hp_inicial * 1.5)  # +50% Vida
        def_inicial = int(def_inicial * 1.5) # +50% Defensa
    elif color_huevo == "Verde":
        atk_inicial = int(atk_inicial * 1.5) # +50% Ataque
        hp_inicial = int(hp_inicial * 0.7)   # -30% Vida
        def_inicial = int(def_inicial * 0.7) # -30% Defensa
        
    agi_inicial = random.randint(1, min_stat // 2 + 5)
    agi_inicial = min(agi_inicial, 20)

    c.execute("""
        INSERT INTO mascotas (
            user_id, especie, nombre, nivel, nivel_max, rareza, 
            stat_mult, atk, def, agi, hp, hp_max, hambre, felicidad, limpieza, equipada, activa
        ) VALUES (?, ?, ?, 1, 25, ?, ?, ?, ?, ?, ?, ?, 100, 100, 100, ?, ?)
    """, (str(user_id), especie, nombre_personalizado, rareza, multiplicador, 
          atk_inicial, def_inicial, agi_inicial, hp_inicial, hp_inicial, activa_status, activa_status))
    
    conn.commit()
    conn.close()


def get_todas_mascotas(user_id):
    """Busca todas las mascotas de un jugador en la tabla mascotas."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("SELECT * FROM mascotas WHERE user_id = ?", (str(user_id),))
    res = c.fetchall()
    conn.close()
    return [dict(r) for r in res]

def check_mascotas_migration():
    """Añade la columna activa si no existe."""
    with get_db() as conn:
        try:
            conn.execute("ALTER TABLE mascotas ADD COLUMN activa INTEGER DEFAULT 0")
        except sqlite3.OperationalError:
            pass # Ya existe

def get_mascotas_por_estado(user_id, activas=True):
    """Obtiene mascotas activas (activa=1) o inactivas (activa=0)."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    val = 1 if activas else 0
    c.execute("SELECT * FROM mascotas WHERE user_id = ? AND activa = ?", (str(user_id), val))
    res = c.fetchall()
    conn.close()
    return [dict(r) for r in res]


inicializar_tabla_mascotas()
def migrar_mascotas_activas():
    """Añade la columna 'activa' a la tabla mascotas si no existe."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    try:
        c.execute("ALTER TABLE mascotas ADD COLUMN activa INTEGER DEFAULT 0")
        conn.commit()
        print("✅ Base de datos actualizada: Columna 'activa' añadida a mascotas.")
    except sqlite3.OperationalError:
        pass
    finally:
        conn.close()

def cambiar_nombre_mascota(mascota_id, nuevo_nombre):
    """Actualiza el nombre de una mascota en la base de datos."""
    import sqlite3
    conn = sqlite3.connect(DB_PATH)
    conn.execute("UPDATE mascotas SET nombre = ? WHERE id = ?", (nuevo_nombre, mascota_id))
    conn.commit()
    conn.close()

def migrar_mascotas_xp():
    """Añade la columna 'xp' a la tabla mascotas si no existe."""
    import sqlite3
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    try:
        c.execute("ALTER TABLE mascotas ADD COLUMN xp INTEGER DEFAULT 0")
        conn.commit()
        print("✅ Base de datos actualizada: Columna 'xp' añadida a mascotas.")
    except sqlite3.OperationalError:
        pass
    finally:
        conn.close()

def dar_xp_mascota(mascota_id, xp_ganada):
    """Suma XP a la mascota, calcula subidas de nivel y actualiza la BD respetando el adiestramiento."""
    import sqlite3
    from Data.database import DB_PATH 
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("SELECT * FROM mascotas WHERE id = ?", (mascota_id,))
    m = dict(c.fetchone())
    
    nivel_actual = m['nivel']
    if nivel_actual >= m['nivel_max']:
        conn.close()
        return m, False 
        
    xp_actual = m['xp'] + xp_ganada
    xp_req = int(100 * (1.15 ** (nivel_actual - 1)))
    
    subio_nivel = False
    atk = m['atk']
    df = m['def']
    agi = m['agi']
    
    hp = m.get('hp', 100)
    hp_max = m.get('hp_max', 100)
    mult = m['stat_mult']
    
    while xp_actual >= xp_req and nivel_actual < m['nivel_max']:
        xp_actual -= xp_req
        nivel_actual += 1
        subio_nivel = True
        
        # Multiplicamos el stat actual por 1.05 (5% extra) y luego sumamos el bono de rareza
        atk = int(atk * 1.02) + int(5 * mult)
        df = int(df * 1.02) + int(5 * mult)
        
        agi = min(90, agi + 1)
        
        aumento_hp = int(hp_max * 0.02) + int(100 * mult)
        hp_max += aumento_hp
        hp += aumento_hp 
        
        xp_req = int(100 * (1.15 ** (nivel_actual - 1)))

    if nivel_actual >= m['nivel_max']:
        xp_actual = 0 

    c.execute("""
        UPDATE mascotas 
        SET nivel = ?, xp = ?, atk = ?, def = ?, agi = ?, hp = ?, hp_max = ? 
        WHERE id = ?
    """, (nivel_actual, xp_actual, atk, df, agi, hp, hp_max, mascota_id))
    
    conn.commit()
    
    c.execute("SELECT * FROM mascotas WHERE id = ?", (mascota_id,))
    m_actualizada = dict(c.fetchone())
    conn.close()
    
    return m_actualizada, subio_nivel

def update_mascota_hp(mascota_id, nuevo_hp):
    """Actualiza la vida actual de la mascota en la base de datos."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("UPDATE mascotas SET hp = ? WHERE id = ?", (nuevo_hp, mascota_id))
    conn.commit()
    conn.close()
    
def evolucionar_mascota_db(mascota_id, nuevo_max):
    """Actualiza el nivel máximo permitido de la mascota tras evolucionar."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("UPDATE mascotas SET nivel_max = ? WHERE id = ?", (nuevo_max, mascota_id))
    conn.commit()
    conn.close()

def modificar_felicidad_mascota(mascota_id, cantidad):
    import sqlite3
    from Data.database import DB_PATH
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    
    c.execute("SELECT felicidad FROM mascotas WHERE id = ?", (mascota_id,))
    row = c.fetchone()
    if not row:
        conn.close()
        return 100
        
    nueva_felicidad = row['felicidad'] + cantidad
    nueva_felicidad = max(0, min(100, nueva_felicidad))
    
    c.execute("UPDATE mascotas SET felicidad = ? WHERE id = ?", (nueva_felicidad, mascota_id))
    conn.commit()
    conn.close()
    
    return nueva_felicidad

def migrar_mascotas_instrucciones():
    """Añade la columna para contar cuántas mejoras de maestría ha recibido la mascota."""
    import sqlite3
    conn = sqlite3.connect(DB_PATH)
    try:
        conn.execute("ALTER TABLE mascotas ADD COLUMN instrucciones_usadas INTEGER DEFAULT 0")
        conn.commit()
        print("✅ Base de datos actualizada: Columna 'instrucciones_usadas' añadida.")
    except sqlite3.OperationalError:
        pass
    finally:
        conn.close()

def instruir_mascota_db(mascota_id, stat_name, nuevo_valor):
    """Sube una estadística básica y consume una oportunidad de instrucción."""
    import sqlite3
    conn = sqlite3.connect(DB_PATH)
    # stat_name será 'atk', 'def', o 'agi'
    conn.execute(f"UPDATE mascotas SET {stat_name} = ?, instrucciones_usadas = instrucciones_usadas + 1 WHERE id = ?", (nuevo_valor, mascota_id))
    conn.commit()
    conn.close()

def instruir_mascota_vida_db(mascota_id, nuevo_hp_max, aumento_hp):
    """Sube la vida máxima, cura esa misma cantidad, y consume la instrucción."""
    import sqlite3
    conn = sqlite3.connect(DB_PATH)
    conn.execute("UPDATE mascotas SET hp_max = ?, hp = hp + ?, instrucciones_usadas = instrucciones_usadas + 1 WHERE id = ?", (nuevo_hp_max, aumento_hp, mascota_id))
    conn.commit()
    conn.close()

def eliminar_mascota(mascota_id):
    """Elimina permanentemente a una mascota (Para el Ritual de Absorción)."""
    import sqlite3
    from Data.database import DB_PATH
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("DELETE FROM mascotas WHERE id = ?", (mascota_id,))
    conn.commit()
    conn.close()

def anadir_huevo_db(user_id, especie, rareza="Normal", color="Normal"):
    import sqlite3
    from Data.database import DB_PATH
    conn = sqlite3.connect(DB_PATH)
    try:
        conn.execute("ALTER TABLE huevos ADD COLUMN color TEXT DEFAULT 'Normal'")
        conn.commit()
    except:
        pass
    conn.execute("INSERT INTO huevos (user_id, especie, rareza, color) VALUES (?, ?, ?, ?)", (str(user_id), especie, rareza, color))
    conn.commit()
    conn.close()

def obtener_huevos_validos(user_id):
    import sqlite3
    from Data.database import DB_PATH
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("DELETE FROM huevos WHERE julianday('now') - julianday(fecha_obtencion) > 6")
    conn.commit()
    try:
        c.execute("SELECT id, user_id, especie, rareza, color, datetime(fecha_obtencion, '+6 days') as caducidad FROM huevos WHERE user_id = ?", (str(user_id),))
    except sqlite3.OperationalError:
        c.execute("SELECT id, user_id, especie, rareza, 'Normal' as color, datetime(fecha_obtencion, '+6 days') as caducidad FROM huevos WHERE user_id = ?", (str(user_id),))
    
    huevos = [dict(row) for row in c.fetchall()]
    conn.close()
    return huevos

def actualizar_rareza_huevo(huevo_id, nueva_rareza):
    import sqlite3
    from Data.database import DB_PATH
    conn = sqlite3.connect(DB_PATH)
    conn.execute("UPDATE huevos SET rareza = ? WHERE id = ?", (nueva_rareza, huevo_id))
    conn.commit()
    conn.close()

def eliminar_huevo_db(huevo_id):
    import sqlite3
    from Data.database import DB_PATH
    conn = sqlite3.connect(DB_PATH)
    conn.execute("DELETE FROM huevos WHERE id = ?", (huevo_id,))
    conn.commit()
    conn.close()

def actualizar_felicidad_mascota(mascota_id, aumento):
    import sqlite3
    from Data.database import DB_PATH
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    
    c.execute("SELECT felicidad FROM mascotas WHERE id = ?", (mascota_id,))
    row = c.fetchone()
    if row:
        nueva_felicidad = min(100, row['felicidad'] + aumento)
        c.execute("UPDATE mascotas SET felicidad = ? WHERE id = ?", (nueva_felicidad, mascota_id))
        conn.commit()
        conn.close()
        return nueva_felicidad
    conn.close()
    return 100

def obtener_habilidades_jugador(user_id):
    """Devuelve los puntos actuales y una lista de IDs de habilidades compradas."""
    with get_db() as conn:
        row = conn.execute("SELECT puntos_habilidad, habilidades_adquiridas FROM jugadores WHERE id = ?", (str(user_id),)).fetchone()
        if not row: return 0, []
        
        puntos = row['puntos_habilidad']
        adquiridas_str = row['habilidades_adquiridas']
        lista_adquiridas = adquiridas_str.split(',') if adquiridas_str else []
        return puntos, lista_adquiridas

def comprar_habilidad_db(user_id, hab_id, costo):
    """Resta los puntos y guarda la habilidad en la base de datos a nivel 1."""
    with get_db() as conn:
        puntos, adquiridas = obtener_habilidades_jugador(user_id) 
        if puntos < costo or hab_id in adquiridas:
            return False
            
        adquiridas.append(hab_id)
        nueva_cadena = ",".join(adquiridas)
        
        conn.execute("UPDATE jugadores SET puntos_habilidad = puntos_habilidad - ?, habilidades_adquiridas = ? WHERE id = ?", 
                     (costo, nueva_cadena, str(user_id)))
                     
        conn.execute("INSERT OR IGNORE INTO habilidades_niveles (user_id, habilidad_id, nivel) VALUES (?, ?, 1)", (str(user_id), hab_id))
        return True

def añadir_puntos_habilidad(user_id, cantidad):
    import sqlite3
    from Data.database import DB_PATH
    
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("UPDATE jugadores SET puntos_habilidad = puntos_habilidad + ? WHERE id = ?", (cantidad, str(user_id)))
    conn.commit()
    conn.close()

# ==========================================
#  SISTEMA DE NIVELES DE HABILIDADES
# ==========================================

def obtener_nivel_habilidad(user_id, habilidad_id):
    """Devuelve el nivel actual de una habilidad. Si no existe registro, devuelve 1 por defecto."""
    with get_db() as conn:
        res = conn.execute("SELECT nivel FROM habilidades_niveles WHERE user_id = ? AND habilidad_id = ?", (str(user_id), habilidad_id)).fetchone()
        return res['nivel'] if res else 1

def obtener_todos_niveles_habilidades(user_id):
    """Devuelve un diccionario con {habilidad_id: nivel} para procesar rápido las pasivas."""
    with get_db() as conn:
        rows = conn.execute("SELECT habilidad_id, nivel FROM habilidades_niveles WHERE user_id = ?", (str(user_id),)).fetchall()
        return {row['habilidad_id']: row['nivel'] for row in rows}

def procesar_usos_habilidades_fin_batalla(user_id, usos_dict):
    """
    Toma un diccionario {habilidad_id: cantidad_usos} acumulado en RAM.
    Lo suma a la BD y calcula subidas de nivel con un límite máximo.
    Retorna una lista de textos con las habilidades que subieron.
    """
    from Data.habilidades_db import HABILIDADES_HUMANO
    subidas = []
    if not usos_dict:
        return subidas
        
    with get_db() as conn:
        for hab_id, usos_ganados in usos_dict.items():
            if usos_ganados <= 0: continue
            
            row = conn.execute("SELECT nivel, usos FROM habilidades_niveles WHERE user_id = ? AND habilidad_id = ?", (str(user_id), hab_id)).fetchone()
            
            if not row:
                conn.execute("INSERT INTO habilidades_niveles (user_id, habilidad_id, nivel, usos) VALUES (?, ?, 1, ?)", (str(user_id), hab_id, usos_ganados))
                nivel_actual = 1
                usos_actuales = usos_ganados
            else:
                nivel_actual = row['nivel']
                usos_actuales = row['usos'] + usos_ganados
                
            # Traemos las condiciones de la plantilla
            hab_base = HABILIDADES_HUMANO.get(hab_id, {})
            usos_req = hab_base.get("condicion_usos", 100)
            
            nivel_maximo = hab_base.get("nivel_maximo", 10) 
            
            if nivel_actual >= nivel_maximo:
                conn.execute("UPDATE habilidades_niveles SET nivel = ?, usos = 0 WHERE user_id = ? AND habilidad_id = ?", 
                             (nivel_maximo, str(user_id), hab_id))
                continue
            
            subio = False
            while usos_actuales >= usos_req and nivel_actual < nivel_maximo:
                nivel_actual += 1
                usos_actuales -= usos_req
                subio = True
                
            if nivel_actual >= nivel_maximo:
                usos_actuales = 0
                
            # Guarda el nuevo estado
            conn.execute("UPDATE habilidades_niveles SET nivel = ?, usos = ? WHERE user_id = ? AND habilidad_id = ?", 
                         (nivel_actual, usos_actuales, str(user_id), hab_id))
            
            if subio:
                nombre_visual = hab_base.get('nombre', hab_id)
                
                if nivel_actual == nivel_maximo:
                    subidas.append(f"👑 **[{nombre_visual}]** ha alcanzado el Nivel MÁXIMO ({nivel_actual}).")
                else:
                    subidas.append(f"🌟 **[{nombre_visual}]** ascendió al Nivel {nivel_actual}.")
                
    return subidas






migrar_mascotas_instrucciones()
migrar_mascotas_xp()
