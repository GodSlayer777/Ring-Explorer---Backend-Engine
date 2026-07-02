from Data.data import ARMAS_DB, ARMADURAS_DB # 👈 CORRECCIÓN DE IMPORTACIÓN
from Data.database import get_maestria_status
from Logica.servicio_mejoras import ServicioMejoras
from Logica.servicio_maestria import ServicioMaestria

class ServicioJugador:
    @staticmethod
    def obtener_stats_reales(jugador_bd):
        """
        Calcula ataque, defensa y agilidad final sumando equipo y maestría.
        """
        jugador = dict(jugador_bd)
        nombre_arma = jugador.get('arma_equipada', 'Ninguna')
        nombre_armadura = jugador.get('armadura_equipada', 'Ninguna')

        nombre_base_arma, _ = ServicioMejoras.obtener_info_item(nombre_arma)
        stats_arma = next((a for a in ARMAS_DB if a['nombre'].strip().lower() == nombre_base_arma.strip().lower()), None)
        tipo_arma = stats_arma['tipo'] if stats_arma else "Desconocido"

        nombre_base_armor, _ = ServicioMejoras.obtener_info_item(nombre_armadura)
        stats_armor = next((a for a in ARMADURAS_DB if a['nombre'].strip().lower() == nombre_base_armor.strip().lower()), None)

        # 2. CÁLCULO DE MEJORAS (+1, +2...) SOLO DEL ARMA
        atk_base_arma = stats_arma['ataque'] if stats_arma else 0
        ataque_eq = ServicioMejoras.calcular_stats(nombre_arma, atk_base_arma)

        def_base_armor = stats_armor['defensa'] if stats_armor else 0
        defensa_eq = ServicioMejoras.calcular_stats(nombre_armadura, def_base_armor)

        agi_base_armor = stats_armor['agilidad'] if stats_armor else 0
        agi_eq = ServicioMejoras.calcular_stats(nombre_armadura, agi_base_armor, es_agilidad=True)

        # 3. BONOS DE MAESTRÍA
        nivel_maestria, _ = get_maestria_status(jugador['id'], tipo_arma)
        bonos = ServicioMaestria.obtener_stats_maestria(tipo_arma, nivel_maestria)

        # 4. EXTRACCIÓN DE STATS PUROS DEL HUMANO
        humano_atk = jugador.get('ataque', 15)
        if humano_atk > 1000: humano_atk = 15
        
        humano_def = jugador.get('defensa', 5)
        if humano_def > 1000: humano_def = 5
        
        humano_agi = jugador.get('agilidad', 15)

        # 5. TOTALES FINALES (ORDEN CORRECTO DE MATEMÁTICAS)
        buff_comida = jugador.get('buff', 'Ninguno')
        jugador['energia_max'] = 150 if "Vida" in buff_comida else 100
        
        # También centralizamos la Vida para que el Embed no tenga que calcularla
        mult_comida_vida = 1.5 if "Vida" in buff_comida else 1.0
        jugador['hp_max'] = int(jugador.get('hp_max', 100) * mult_comida_vida)
        mult_atk_comida = 1.3 if "Ataque" in buff_comida else 1.0
        mult_def_comida = 1.3 if "Defensa" in buff_comida else 1.0

        # A) Sumamos Base Humana + Daño del Arma (+1, +2...)
        atk_total_bruto = humano_atk + ataque_eq
        # B) Al total bruto le sacamos el porcentaje de maestría
        bono_maestria_atk = int(atk_total_bruto * (bonos.get('inc_dano', 0) / 100.0))
        # C) Multiplicamos por la comida
        jugador['ataque'] = int((atk_total_bruto + bono_maestria_atk) * mult_atk_comida)
        
        # Misma lógica para defensa
        def_total_bruta = humano_def + defensa_eq + bonos.get('defensa', 0) + bonos.get('defensa_base', 0)
        jugador['defensa'] = int(def_total_bruta * mult_def_comida)
        
        # Agilidad: Base + Armadura + Maestría (Tope 90%)
        factor_armadura = 1.0 + (agi_eq / 100.0)
        factor_maestria = 1.0 + (bonos.get('evasion', 0) / 100.0)
        
        # 3. Aplicamos el límite máximo de 90
        jugador['agilidad'] = int(humano_agi * factor_armadura * factor_maestria)

        from Data.database import obtener_habilidades_jugador
        _, adquiridas = obtener_habilidades_jugador(jugador['id'])
        
        # AQUÍ las pasivas multiplican el último 10% y ponen el TOPE DE 90 definitivo
        from Logica.servicio_habilidades import ServicioHabilidades
        jugador = ServicioHabilidades.aplicar_pasivas(jugador, adquiridas)

        # 6. DICCIONARIO DE DESGLOSE (Para la interfaz visual de Embeds)
        stats_desglosados = {
            "atk_humano": humano_atk,
            "atk_arma": ataque_eq,
            "atk_maestria_pct": bonos.get('inc_dano', 0),
            "atk_buff": mult_atk_comida,
            
            "def_humano": humano_def,
            "def_armadura": defensa_eq,
            "def_maestria": bonos.get('defensa', 0) + bonos.get('defensa_base', 0),
            "def_buff": mult_def_comida,
            
            "agi_humano": humano_agi,
            "agi_armadura": agi_eq,
            "agi_maestria": bonos.get('evasion', 0)
        }

        return jugador, tipo_arma, nivel_maestria, stats_desglosados