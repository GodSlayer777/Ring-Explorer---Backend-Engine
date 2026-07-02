import random
from Data.database import (
    update_player_hp, 
    registrar_mision_completada, 
    add_zenny, 
    add_material, 
    get_player_data, 
    add_experiencia_global, 
    add_competencia_arma, 
    add_puntos_maestria, 
    get_material_cantidad,
    remove_material
)
from Data.data import MISIONES_DB, DROPS_MISIONES, DROPS_MONSTRUOS, ARMAS_DB,ARMADURAS_DB
from Logica.servicio_mejoras import ServicioMejoras

class ServicioCombate:
    
    # =========================================================
    # ATAQUE DEL JUGADOR (CON MEJORAS Y DEFENSA)
    # =========================================================
    @staticmethod
    def calcular_ataque_jugador(jugador, monstruo, mecanica_arma, view_context):
        """
        Calcula el ataque considerando el Nivel de Mejora (+1, +2...) del arma
        y restando la defensa del monstruo objetivo.
        """
        # 1. Obtener nombre del arma equipada 
        nombre_arma_equip = jugador['arma_equipada'] 
        
        # 2. Separar nombre base y nivel
        nombre_base, nivel_mejora = ServicioMejoras.obtener_info_item(nombre_arma_equip)
        
        # 3. Buscar stats base en la base de datos estática
        stats_db = next((a for a in ARMAS_DB if a['nombre'] == nombre_base), None)
        ataque_base_de_arma = stats_db['ataque'] if stats_db else 0
        
        # 4. Calcular daño potenciado del arma
        ataque_arma_mejorado = ServicioMejoras.calcular_stats(nombre_arma_equip, ataque_base_de_arma)
        
        # 5. Obtener el daño BRUTO desde la mecánica del arma (Ataque total + crits + combos)
        daño_bruto, mensaje = mecanica_arma.calcular_daño_normal(
            view=view_context,
            stats_jugador=jugador, 
            monstruo=monstruo,
            daño_arma_mejorado=jugador['ataque'] 
        )
        
        # Obtenemos la defensa actual del monstruo (usando .get por seguridad)
        defensa_monstruo = monstruo.get('def', 0)
        
        # Restamos la defensa al daño bruto. 
        daño_final = max(1, daño_bruto - defensa_monstruo)
        
        return daño_final, mensaje

    # =========================================================
    #  ATAQUE DEL MONSTRUO
    # =========================================================
    @staticmethod
    def calcular_ataque_monstruo(stats_monstruo, defensa_jugador, mecanica_arma, view_context=None):
        """
        Calcula el daño: (Atk Monstruo - Def Jugador) +/- RNG -> Mitigación Arma.
        Considera buffs temporales como Piel Absorbente.
        """
        defensa_final_jugador = defensa_jugador
        
        if view_context and getattr(view_context, 'buff_piel_activa', 0.0) > 0:
            bono_piel = view_context.buff_piel_activa
            # Aumentamos la defensa temporalmente
            defensa_final_jugador += int(defensa_jugador * bono_piel)
            # Consumimos el buff
            view_context.buff_piel_activa = 0.0

        # 2. Daño Base con RNG (Variación del 10%)
        daño_neto = max(1, stats_monstruo['atk'] - defensa_final_jugador)
        daño_base = int(daño_neto * random.uniform(0.9, 1.1))
        
        # 3. Aplicar Mitigación del Arma 
        daño_final, msg_arma = mecanica_arma.recibir_golpe(daño_base)
        
        return daño_final, f"{msg_arma}"

    # =========================================================
    #  NUEVO MÉTODO: CALCULAR AGILIDAD TOTAL (CON MEJORAS)
    # =========================================================
    @staticmethod
    def calcular_agilidad_total(jugador):
        """
        Calcula la agilidad total: Base Jugador + Agilidad Armadura (Mejorada +X).
        """
        # 1. Agilidad Base del Jugador (Stats propios)
        agilidad_base = jugador.get('agilidad', 0)
        
        # 2. Obtener Armadura Equipada
        nombre_armor_full = jugador['armadura_equipada']
        nombre_base, _ = ServicioMejoras.obtener_info_item(nombre_armor_full)
        
        # 3. Buscar la armadura en la DB
        stats_armor = next((a for a in ARMADURAS_DB if a['nombre'] == nombre_base), None)
        
        agilidad_armor_final = 0
        
        if stats_armor:
            # Obtenemos la agilidad base de la armadura 
            agi_armor_base = stats_armor.get('agilidad', 0)
            
          
            if agi_armor_base > 0:
                agilidad_armor_final = ServicioMejoras.calcular_stats(nombre_armor_full, agi_armor_base)
        
        # 4. Sumar todo
        return agilidad_base + agilidad_armor_final
    
# =========================================================
    # ⚡ ESQUIVES (SISTEMA BASADO EN ESTADÍSTICAS)
    # =========================================================
    @staticmethod
    def procesar_esquive(agilidad_jugador_total, velocidad_monstruo, energia_actual, reduccion_pasiva=0.0):
        """
        Calcula el éxito y el costo de energía real aplicando la nueva fórmula.
        Costo base = 25. Si velocidad_monstruo > agilidad_jugador, +1 costo por cada 2 puntos de diferencia.
        """
        # 1. Nueva Fórmula de Costo de Energía
        costo_base = 25
        diferencia = velocidad_monstruo - agilidad_jugador_total
        
        if diferencia > 0:
            # Sumamos 1 de costo por cada 2 puntos que el monstruo supere al jugador
            costo_base += int(diferencia / 2)
            
        # 2. Aplicar Reducción de Pasivas (Habilidad 'Eficiencia Oscura', etc)
        coste_final = int(costo_base * (1.0 - reduccion_pasiva))
        coste_final = max(1, coste_final) # Mínimo 1 siempre
        
        msg_detalle = "💨 *Atk evitado*"
        
        # 3. Evaluar Energía
        if energia_actual >= coste_final:
            nueva_energia = energia_actual - coste_final
            exito = True
            msg_resultado = f"(⚡ -{coste_final}e) {msg_detalle}"
        else:
            nueva_energia = energia_actual
            exito = False
            faltante = coste_final - energia_actual
            msg_resultado = f"❌ *Intentas esquivar, pero te faltan {faltante}e. ¡Recibes el golpe!*"
            
        return exito, nueva_energia, msg_resultado, agilidad_jugador_total, velocidad_monstruo

    # =========================================================
    # 🧪 CURACIÓN
    # =========================================================
    @staticmethod
    def procesar_curacion(user_id, cantidad_solicitada, hongos_usados_combate, hp_actual, hp_maximo):
        """Maneja la lógica de curación."""
        MAX_POCIONES = 10
        if hongos_usados_combate >= MAX_POCIONES:
            return 0, 0, "🚫 ¡Estómago lleno! No puedes comer más de 10 hongos."

        tienes = get_material_cantidad(user_id, "Hongo Sanador")
        if tienes <= 0:
            return 0, 0, "❌ No tienes hongos en tu inventario."

        permitidas_batalla = MAX_POCIONES - hongos_usados_combate
        usar = min(cantidad_solicitada, tienes, permitidas_batalla)

        if usar > 0:
            remove_material(user_id, "Hongo Sanador", usar)
            recuperacion_total = usar * 35
            return usar, recuperacion_total, None
        
        return 0, 0, "No se pudo usar el objeto."

    @staticmethod
    def procesar_derrota(user_id):
        # Curamos al jugador a 10 HP al perder
        update_player_hp(user_id, 10)

    # =========================================================
    # 🏆 RESULTADOS Y LOOT (OPTIMIZADO O(1))
    # =========================================================
    @staticmethod
    def calcular_resultado_final(user_id, nombre_mision, nombre_monstruo, tipo_arma):
        import random
        from Data.database import get_player_data, registrar_mision_completada, add_zenny, add_material, add_experiencia_global, add_competencia_arma, add_puntos_maestria,dar_xp_jugador
        from Data.data import MISIONES_DB, DROPS_MISIONES, DROPS_MONSTRUOS, obtener_evento_diario

        jugador = dict(get_player_data(user_id))
        rep_previa = jugador['reputacion']
        es_torre = "Torre de Babel" in nombre_mision

        # 1. Registrar Misión y Reputación
        msg_mision, puntos_rep_ganados = registrar_mision_completada(user_id, nombre_mision)

        # 2. Calcular Zenny y Nombre Real del Monstruo
        recompensa_zenny = 0
        nombre_real_monstruo = nombre_monstruo
        
        for lista in MISIONES_DB.values():
            for m in lista:
                if m['nombre'] == nombre_mision:
                    recompensa_zenny = m.get('recompensa', 0)
                    nombre_real_monstruo = m.get('monstruo', nombre_monstruo)
                    break
            if recompensa_zenny > 0: break
        
        # 3. Calcular Drops Base (En memoria RAM)
        items_obtenidos = {}
        tabla_drops = DROPS_MISIONES.get(nombre_mision) or DROPS_MONSTRUOS.get(nombre_real_monstruo, DROPS_MONSTRUOS.get("DEFAULT", []))
        
        if tabla_drops:
            for _ in range(random.randint(8, 10)):
                try:
                    item = random.choices([d['item'] for d in tabla_drops], [d['prob'] for d in tabla_drops], k=1)[0]
                    items_obtenidos[item] = items_obtenidos.get(item, 0) + 1
                except: pass

        # 4. APLICAR MULTIPLICADORES DE LA TORRE
        if es_torre:
            dificultad = jugador.get('torre_dificultad', 'Visitante')
            MULT_RECOMPENSAS = {"Visitante": 1, "Explorador": 2, "Cazarrecompensas": 3, "Investigador": 4, "Conquistador": 5, "Señor de la torre": 6}
            mult_dif = MULT_RECOMPENSAS.get(dificultad, 1)
            
            recompensa_zenny *= mult_dif
            puntos_rep_ganados *= mult_dif
            for item in list(items_obtenidos.keys()): items_obtenidos[item] *= mult_dif

            # Drops Especiales de la Torre (Esencia y Gracia)
            import re
            match = re.search(r"Piso (\d+)", nombre_mision)
            piso_actual = int(match.group(1)) if match else 1
            es_jefe = (piso_actual % 10 == 0)

            drop_esencia = random.randint(5, 8) if es_jefe else (random.randint(1, 2) if random.random() <= 0.20 else 0)
            if drop_esencia > 0:
                items_obtenidos["Esencia Divina"] = items_obtenidos.get("Esencia Divina", 0) + (drop_esencia * mult_dif)

            gracia_base = 50 if es_jefe else 10
            items_obtenidos["Puntos de Gracia"] = items_obtenidos.get("Puntos de Gracia", 0) + (gracia_base * mult_dif)

        # 5. APLICAR BENDICIÓN DE FORTUNA (Torre)
        if es_torre and jugador.get('torre_buff_fortuna', 0) >= 1:
            recompensa_zenny *= 2 
            puntos_rep_ganados *= 2
            items_obtenidos["Puntos de Gracia"] = items_obtenidos.get("Puntos de Gracia", 0) * 2
            for item in list(items_obtenidos.keys()):
                if item not in ["Puntos de Gracia", "Esencia Divina"]:
                    items_obtenidos[item] = int(items_obtenidos[item] * 1.3)

        # 6. APLICAR EVENTO DIARIO GLOBAL
        evento = obtener_evento_diario()
        if evento:
            if evento['id'] in ['zenny', 'all']: recompensa_zenny = int(recompensa_zenny * evento['mult'])
            if evento['id'] in ['botin', 'all']:
                for item in list(items_obtenidos.keys()):
                    if item not in ["Puntos de Gracia", "Esencia Divina"]:
                        items_obtenidos[item] = int(items_obtenidos[item] * evento['mult'])

        # ==========================================
        # 🌟 NUEVO: PROGRESO DEL JUGADOR (XP Y NIVEL)
        # ==========================================
        # Calculamos la XP base según el rango de la misión
        # (Podemos usar tu índice_rango: 50 XP base * 1.5 por rango)
        jugador_previo = dict(get_player_data(user_id))
        rango_idx = 0 
        xp_a_dar = int(50 * (1.3 ** rango_idx)) 
        
        
        resultado_xp, subio_nivel = dar_xp_jugador(user_id, xp_a_dar)

        # ==========================================
        # 7. GUARDAR TODO EN BASE DE DATOS 
        # ==========================================
        if recompensa_zenny > 0: add_zenny(user_id, recompensa_zenny)
        for item, cant in items_obtenidos.items():
            if cant > 0: add_material(user_id, item, cant)

        # ==========================================
        # 8. SISTEMAS DE PROGRESO 
        # ==========================================
        progreso_cazador_log = []
        progreso_maestro_log = []

        # --- A) PROGRESO DEL CAZADOR (Niveles Humanos) ---
        if subio_nivel:
            progreso_cazador_log.append(f"🎊 **¡SUBIDA DE NIVEL!** Ahora eres **Nivel {resultado_xp['nivel']}**")
            progreso_cazador_log.append(f"📈 *Stats: +HP, +ATK, +DEF, +AGI | ✨ +1 Pto. Habilidad*")
            if resultado_xp['nivel'] % 5 == 0:
                progreso_cazador_log.append(f"📖 **¡NUEVO CONOCIMIENTO!** Revisa tu Códice de Habilidades.")
        else:
            # Mostramos la barra de progreso si no subió
            barra_xp = "🟦" * int((resultado_xp['experiencia'] / resultado_xp['xp_req']) * 10)
            progreso_cazador_log.append(f"✨ **XP Jugador:** +{xp_a_dar}\n`{barra_xp.ljust(10, '⬛')}` ({resultado_xp['experiencia']}/{resultado_xp['xp_req']})")

        # --- B) PROGRESO MAESTRO (Solo activo si Reputación >= 100) ---
        rep_actual = rep_previa + puntos_rep_ganados 
        es_ascension = (rep_previa < 100 and rep_actual >= 100)
        
        if rep_actual >= 100:
            # 1. Experiencia global de maestría
            if add_experiencia_global(user_id, 1): 
                progreso_maestro_log.append("💠 **¡Has obtenido 1 Punto de Maestría Global!**")
            
            # 2. Competencia de arma
            subio_arma, nivel_nuevo = add_competencia_arma(user_id, tipo_arma, 1)
            if subio_arma: 
                progreso_maestro_log.append(f"⚔️ **¡TU ARMA HA EVOLUCIONADO!**\nTu maestría en **{tipo_arma}** es Nivel {nivel_nuevo}.")
                
        if es_ascension: 
            add_puntos_maestria(user_id, 1)

        return {
            "zenny": recompensa_zenny, 
            "items": items_obtenidos, 
            "puntos_rep": puntos_rep_ganados,
            "progreso_cazador_txt": "\n".join(progreso_cazador_log), 
            "progreso_maestro_txt": "\n".join(progreso_maestro_log), 
            "subio_nivel": subio_nivel,
            "nivel_actual": resultado_xp.get('nivel') if subio_nivel else jugador_previo['nivel'],
            "es_ascension": es_ascension
        }
    # =========================================================
    # 🐉 PREPARACIÓN DE MONSTRUOS (SPAWNERS)
    # =========================================================
    @staticmethod
    def preparar_monstruo_caza(nombre_mision):
        """Busca la misión y escala los stats del monstruo según el rango."""
        from Data.data import MISIONES_DB, INFO_MONSTRUOS, ESCALADO_RANGO
        
        nombre_monstruo = "Desconocido"
        rango_mision = "Novato"
        
        for rango, misiones in MISIONES_DB.items():
            for m in misiones:
                if m['nombre'] == nombre_mision:
                    nombre_monstruo = m['monstruo']
                    rango_mision = rango
                    break
        
        stats_base = INFO_MONSTRUOS.get(nombre_monstruo, INFO_MONSTRUOS["DEFAULT"]).copy()
        multi = ESCALADO_RANGO.get(rango_mision, ESCALADO_RANGO["Novato"])
        velocidad_base = stats_base.get('velocidad', 20)

        stats_base['hp'] = int(stats_base['hp'] * multi['hp'])
        stats_base['atk'] = int(stats_base['atk'] * multi['atk'])
        stats_base['def'] = int(stats_base['def'] * multi['def'])
        stats_base['velocidad'] = int(velocidad_base * (multi['def'] * 0.8))
        nombre_mostrar = f"{multi['prefijo']} {nombre_monstruo}".strip()
        
        return nombre_mostrar, stats_base

    @staticmethod
    def preparar_monstruo_torre(piso, dificultad):
        """Genera un monstruo aleatorio o jefe de la Torre y escala sus stats."""
        import random
        from Data.data import INFO_MONSTRUOS
        
        MULTIPLICADOR_DIFICULTAD = {
            "Visitante": 1.0, "Explorador": 2.0, "Cazarrecompensas": 3.0,
            "Investigador": 5.0, "Conquistador": 8.0, "Señor de la torre": 12.0
        }
        mult_dif = MULTIPLICADOR_DIFICULTAD.get(dificultad, 1.0)

        JEFES_TORRE = {
            10: "Primogénito Cornudo", 20: "Progenitor Escamado",
            30: "Progenitor Abisal", 40: "Titán de Impacto", 50: "Progenitor Entomante", 60: "La Anomalía Perfecta"
        }

        if piso in JEFES_TORRE:
            nombre_base_monstruo = JEFES_TORRE[piso]
            stats_base = INFO_MONSTRUOS.get(nombre_base_monstruo, INFO_MONSTRUOS["DEFAULT"]).copy()
            nombre_mostrar = f"SEÑOR DE RAZA {nombre_base_monstruo}"
            stats_base['hp'] = int(stats_base['hp'] * 20.0 * mult_dif)
            stats_base['atk'] = int(stats_base['atk'] * 15.0 * mult_dif)
            stats_base['def'] = int(stats_base['def'] * 10.0 * mult_dif)
            stats_base['velocidad'] = int(velocidad_base * mult_dif)
        else:
            if piso < 10: monstruos_torre = ["Astazur", "Cráneo Vivo", "Cornisombra", "Astafauce", "Retorcido del Anillo","Desollador Pétreo","Uñabruma"]
            elif piso < 20: monstruos_torre = ["Syrrakel", "Vorthyx", "Kaelmyr", "Zhaeroth", "Cravex","Raxandor","Velkareth","Keralith"]
            elif piso < 30: monstruos_torre = ["Sargassum Rex", "Dorsal del Abismo", "Nautyrr", "Umbrothal", "Ophydral","Criptomarea","Gravemarea","Kryssmare"]
            elif piso < 40: monstruos_torre = ["Plomogron", "Retumbón", "Punzón Colosal", "Crushbehem", "Megalastre","Aplastador del Valle","Ferrocrash","Tremorak"]
            elif piso < 50: monstruos_torre = ["Excavador Abisal", "Coraza Prismática", "Rey Escarabeo", "Centípodo de Fosas", "Portador de Larvas","Tejedor Umbrío","Custodio del Nido","Aguijón Solar","Reina Quitinaria"]
            else: monstruos_torre = ["Larva Eterna", "Feromona Muerta", "Colmena Individual", "Bruto Opuesto", "El Que Nunca Cae","Bruto de Masa Infinita","El Que No Flota","Leviatán Descompuesto"]

            nombre_base_monstruo = random.choice(monstruos_torre)
            stats_base = INFO_MONSTRUOS.get(nombre_base_monstruo, INFO_MONSTRUOS["DEFAULT"]).copy()

            multiplicador = 10.0 + ((piso - 1) * 0.5)
            nombre_mostrar = f"APEX {nombre_base_monstruo}"
            velocidad_base = stats_base.get('velocidad', 20)

            stats_base['hp'] = int(stats_base['hp'] * multiplicador * mult_dif)
            stats_base['atk'] = int(stats_base['atk'] * multiplicador * mult_dif)
            stats_base['def'] = int(stats_base['def'] * multiplicador * mult_dif)
            stats_base['velocidad'] = int(velocidad_base *mult_dif)
        return nombre_mostrar, stats_base
    
    @staticmethod
    async def ejecutar_paso_sombrio(self, interaction):
    # 1. Consumo de recursos
        self.mp_jugador -= 15
        self.jugador['mp'] = self.mp_jugador
        
        # 2. MECÁNICA ÚNICA: Forzamos el éxito del esquive
        self.intento_esquive = True
        self.esquive_exitoso = True # Esto ignora el cálculo de agilidad del motor
        
        # 3. No consume Energía (⚡), por lo que no tocamos self.energia
        
        msg = ""
        
        # 4. Ejecutamos el turno (Esto hará que el monstruo ataque y falle)
        await self.ejecutar_turno(interaction, "habilidad", msg_personalizado=msg)
