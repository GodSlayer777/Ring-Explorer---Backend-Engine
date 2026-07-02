import discord # type: ignore
import asyncio
import random
from Data.data import ARMAS_DB, MISIONES_DB, INFO_MONSTRUOS, DROPS_MISIONES, DROPS_MONSTRUOS, obtener_emoji,MIMMI_ASSETS
from Data.database import (
    get_player_data, obtener_agilidad_jugador, add_zenny, add_material, 
    get_material_cantidad, remove_material, registrar_mision_completada, 
    guardar_ultima_mision, update_player_hp, get_maestria_arma,update_piso_torre
)
from Vistas.Embeds import embed_batalla, embed_aldea, embed_lore_final
from Logica.mecanicas import obtener_mecanica
from Logica.servicio_combate import ServicioCombate
from Logica.servicio_jugador import ServicioJugador
from io import BytesIO
# ==========================================
# 1. VISTA PREVIA (BOTÓN "IR A CAZAR")
# ==========================================

class MisionActivaView(discord.ui.View):
    def __init__(self, nombre_mision, user_id):
        super().__init__(timeout=None)
        self.nombre_mision = nombre_mision
        self.user_id = user_id

    @discord.ui.button(label="⚔️ IR A CAZAR", style=discord.ButtonStyle.success)
    async def cazar(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id: return
        
        # 1. DEFER (Evita timeouts)
        await interaction.response.defer()
        
        try:
            jugador_bd = get_player_data(self.user_id)
            if not jugador_bd:
                return await interaction.followup.send("Error: No se encontró tu perfil.", ephemeral=True)
            
            guardar_ultima_mision(self.user_id, self.nombre_mision)
            jugador_real, tipo_arma, nivel_maestria, _ = ServicioJugador.obtener_stats_reales(jugador_bd)
            agilidad = jugador_real['agilidad']
            
            # B. Datos del Monstruo (DELEGADO AL SERVICIO)
            nombre_mostrar, stats_base = ServicioCombate.preparar_monstruo_caza(self.nombre_mision)
            
            # Traer la mascota equipada
            from Data.database import get_mascota_equipada
            mascota_db = get_mascota_equipada(self.user_id)
            mascota_dict = dict(mascota_db) if mascota_db else None
            
            # --- 3. INICIAR LA VISTA DE BATALLA ---
            vista_batalla = BatallaView(
                user_id=self.user_id,
                jugador=jugador_real, 
                nombre_mision=self.nombre_mision,
                nombre_monstruo=nombre_mostrar, 
                stats_monstruo=stats_base,      
                agilidad=agilidad,
                nivel_maestria=nivel_maestria,
                tipo_arma_cache=tipo_arma,
                mascota=mascota_dict 
            )
            texto_inicio = "¡El monstruo te ha visto!" if "especie" in stats_base else "¡Has llegado a la zona! Preparas tus herramientas para extraer recursos."
            
            embed_final = embed_batalla(
                vista_batalla.jugador, 
                vista_batalla.nombre_monstruo, 
                vista_batalla.stats, 
                vista_batalla.hp_monstruo, 
                vista_batalla.stats['img_idle'], 
                texto_inicio, 
                vista_batalla.energia, 
                vista_batalla.energia_max,
                mascota=vista_batalla.mascota
            )
            
            await interaction.edit_original_response(
                content=f"⚔️ **¡CAZA INICIADA!**\nObjetivo: {self.nombre_mision}", 
                embed=embed_final,
                view=vista_batalla
            )

        except Exception as e:
            print(f"❌ ERROR AL INICIAR CAZA: {e}")
            await interaction.followup.send(f"Ocurrió un error crítico: {e}", ephemeral=True)

    @discord.ui.button(label="🔙 Cancelar", style=discord.ButtonStyle.secondary, row=0)
    async def cancelar(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id: return
        await interaction.response.defer()
        
        from Data.data import MISIONES_DB
        from Data.database import get_player_data, get_completed_missions
        from Vistas.vistas import ListaMisionesView, MisionesView
        from Vistas.Embeds import embed_misiones_main
        
        # ⚡ 1. Generamos la caché aquí mismo para alimentar a las vistas
        jugador_cache = dict(get_player_data(self.user_id))
        completadas_cache = get_completed_missions(self.user_id)
        
        # 2. Buscamos a qué categoría pertenece la misión
        categoria_origen = None
        for cat, misiones in MISIONES_DB.items():
            for m in misiones:
                if m['nombre'] == self.nombre_mision:
                    categoria_origen = cat
                    break
            if categoria_origen: break
            
        # 3. Si es urgente, de la torre, o no se encuentra, mandamos al menú principal
        if categoria_origen == "URGENTE" or not categoria_origen:
            await interaction.edit_original_response(
                content=None,
                embed=embed_misiones_main(),
                view=MisionesView(self.user_id, jugador_cache, completadas_cache)
            )
        else:
            # 4. Volvemos a la lista de misiones con el orden de argumentos CORRECTO
            vista_misiones = ListaMisionesView(self.user_id, categoria_origen, completadas_cache, jugador_cache)
            await interaction.edit_original_response(
                content=None,
                embed=vista_misiones.generar_embed(),
                view=vista_misiones
            )

# ==========================================
# 2. MODAL DE CURACIÓN
# ==========================================
class CuracionBatallaModal(discord.ui.Modal):
    def __init__(self, view_batalla):
        super().__init__(title="Usar Hongos curativos")
        self.view_batalla = view_batalla
        
        # 👇 1. Detectamos si estamos en la Torre
        self.es_torre = "Torre de Babel" in view_batalla.nombre_mision
        
        usadas = getattr(self.view_batalla, 'Hongos_usados', 0)
        
        # 👇 2. Cambiamos el texto visual dependiendo de dónde esté
        if self.es_torre:
            texto_label = "Cantidad a usar (Ilimitado en la Torre)"
        else:
            restantes = 10 - usadas
            texto_label = f"Oportunidades restantes: {restantes}"
            
        self.cantidad = discord.ui.TextInput(
            label=texto_label, 
            placeholder="Ej: 5", min_length=1, max_length=3
        )
        self.add_item(self.cantidad)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer()
        
        try:
            qty = int(self.cantidad.value)
            if qty <= 0: raise ValueError
        except:
            return await interaction.followup.send("Número inválido.", ephemeral=True)
            
        usados_para_limite = -999999 if self.es_torre else self.view_batalla.Hongos_usados

        usados_real, hp_recuperado, error = ServicioCombate.procesar_curacion(
            self.view_batalla.user_id,
            qty,
            usados_para_limite, 
            self.view_batalla.hp_jugador,
            self.view_batalla.hp_max_jugador
        )

        if error:
            
            return await interaction.followup.send(error, ephemeral=True)

        self.view_batalla.Hongos_usados += usados_real
        self.view_batalla.hp_jugador = min(
            self.view_batalla.hp_jugador + hp_recuperado, 
            self.view_batalla.hp_max_jugador
        )
        self.view_batalla.jugador['hp'] = self.view_batalla.hp_jugador

        msg_extra = ""
        if usados_real < qty:
            motivo = "falta de inventario" if self.es_torre else "límite de 10 o falta de inventario"
            msg_extra = f"\n(Solo usaste **{usados_real}** por {motivo})."

        texto_limite = "∞" if self.es_torre else f"{self.view_batalla.Hongos_usados}/10"

        await self.view_batalla.ejecutar_turno(
            interaction, 
            "curar", 
            msg_personalizado=f"🧪 Te has curado (+{hp_recuperado} HP).{msg_extra}"
        )

# ==========================================
# 3. VISTA DE BATALLA PRINCIPAL
# ==========================================
class BatallaView(discord.ui.View):
    def __init__(self, user_id, jugador, nombre_mision, nombre_monstruo, stats_monstruo, 
                 agilidad=0, nivel_maestria=0, tipo_arma_cache=None, dificultad="Visitante",mascota=None):
        super().__init__(timeout=None)
        self.dificultad = dificultad
        self.user_id = user_id
        self.jugador = dict(jugador)
        self.mascota = mascota
        self.usos_habilidades = {}

        # 1. CARGAR HABILIDADES PARA CÁLCULOS DINÁMICOS
        from Data.database import obtener_habilidades_jugador
        from Data.habilidades_db import HABILIDADES_HUMANO
        _, self.adquiridas = obtener_habilidades_jugador(self.user_id)

        # Variables para factores de energía
        factor_energia_max = 1.0
        self.reduccion_energia_total = 0.0
        # (La recuperación se usará en el fin de turno, pero el máximo debe estar bien calculado aquí)

        self.reduccion_mp_total = 0.0
        self.es_mago_de_sangre = False

        for hab_id in self.adquiridas:
            hab = HABILIDADES_HUMANO.get(hab_id)
            if hab and hab.get('categoria') == 'Pasiva' and hab.get('activacion') == 'automatica':
                # Aumento de energía máxima (Pasiva todo el tiempo)
                factor_energia_max += hab.get('aumento_pasivo_energia', 0.0)
                # Reducción de consumo (Solo en batalla, la guardamos en self)
                self.reduccion_energia_total += hab.get('reduccion_pasivo_energia', 0.0)

                self.reduccion_mp_total += hab.get('reduccion_costo_mp', 0.0)
                if hab.get('magia_de_sangre', 0) == 1:
                    self.es_mago_de_sangre = True
        # 👇 Calculamos su probabilidad de ataque según la rareza
        if self.mascota:
            rareza = self.mascota.get('rareza', 'Normal')
            if rareza == "Portadora de Sangre Divina": self.prob_atk_mascota = 100
            elif rareza == "Primal": self.prob_atk_mascota = 70
            elif rareza == "Apex": self.prob_atk_mascota = 60
            elif rareza == "Alpha": self.prob_atk_mascota = 50
            else: self.prob_atk_mascota = 40
            
        self.nombre_mision = nombre_mision
        self.indice_rango = 0
        if "Torre de Babel" in self.nombre_mision:
            DIF_TOWER = ["Visitante", "Explorador", "Cazarrecompensas", "Investigador", "Conquistador", "Señor de la torre"]
            if self.dificultad in DIF_TOWER:
                self.indice_rango = DIF_TOWER.index(self.dificultad)
        else:
            from Data.data import MISIONES_DB
            RANGOS = ["Novato", "Explorador", "Cazador", "Mercenario", "Veterano", "Maestro", "Héroe de la Aldea", "Cazador de Élite", "Comandante", "Leyenda", "Gremio Dorado"]
            for rango, misiones in MISIONES_DB.items():
                if any(m['nombre'] == self.nombre_mision for m in misiones):
                    if rango in RANGOS:
                        self.indice_rango = RANGOS.index(rango)
                    break
        self.nombre_monstruo = nombre_monstruo
        self.stats = stats_monstruo
        self.Hongos_usados = 0
        self.hp_monstruo = stats_monstruo['hp']
        self.hp_max_monstruo = stats_monstruo['hp'] # Guardamos el máximo real
        self.en_rabia = False # Interruptor del modo rabia
        self.jugador_perfora_armadura = False
        self.monstruo_perfora_armadura = False
        # 👇 1. VERIFICAMOS SI ESTAMOS EN LA TORRE
        es_torre = "Torre de Babel" in self.nombre_mision
        mult_divino = self.jugador.get('torre_buff_hp', 1.0) if es_torre else 1.0
        
        # 1. Vida Máxima: Ya viene con Comida y Pasivas desde ServicioJugador
        # Solo aplicamos el multiplicador de la Torre si estamos en ella.
        self.hp_max_jugador = int(self.jugador.get('hp_max', 100) * mult_divino)
        self.jugador['hp_max'] = self.hp_max_jugador # Sincronizamos dict
        
        # 2. Energía Máxima: Ya viene con Comida y Pasivas (como Inagotable)
        self.energia_max = int(self.jugador.get('energia_max', 100) * mult_divino)
        self.jugador['energia_max'] = self.energia_max # Sincronizamos dict

        # 3. Ajuste de Vida y Energía Actuales
        # Evitamos que la vida/energía actual sea mayor al nuevo máximo (por si acaso)
        self.hp_jugador = min(self.jugador.get('hp', self.hp_max_jugador), self.hp_max_jugador)
        self.energia = min(self.jugador.get('energia', self.energia_max), self.energia_max)
        
        # Sincronizamos el diccionario interno
        self.jugador['hp'] = self.hp_jugador
        self.jugador['energia'] = self.energia
        
        self.mp_jugador = self.jugador.get('mp', 50)
        self.mp_max_jugador = self.jugador.get('mp_max', 50)

        self.agilidad = self.jugador.get('agilidad', 0) 
        self.cargas = 0
        self.fatiga_pendiente = False
        self.turnos_derribado = 0
        self.habilidad_cargando = False
        # Identificar arma
        self.arma_nombre = self.jugador['arma_equipada']
        if tipo_arma_cache:
            self.tipo_arma = tipo_arma_cache
        else:
            self.tipo_arma = "Desconocido"
            for a in ARMAS_DB:
                if a['nombre'] == self.arma_nombre:
                    self.tipo_arma = a['tipo']
                    break

        # Cargar Mecánica y Maestría
        self.mecanica = obtener_mecanica(self.tipo_arma)
        if hasattr(self.mecanica, 'aplicar_maestria'):
            self.mecanica.aplicar_maestria(nivel_maestria)

        self.actualizar_botones()

# --- ⚡ OPTIMIZACIÓN: CÁLCULOS EN CACHÉ ---
        rango_jugador = self.jugador.get('rango', 'Novato')
        RANGOS_ORDENADOS = ["Novato", "Explorador", "Cazador", "Mercenario", "Veterano", "Maestro", "Héroe de la Aldea", "Cazador de Élite", "Comandante", "Leyenda", "Gremio Dorado"]
        try: self.nivel_rango = RANGOS_ORDENADOS.index(rango_jugador) + 1
        except ValueError: self.nivel_rango = 1

        self.xp_acumulada_pet = 0 # 👈 Guardará la XP en RAM para evitar escribir a la DB en cada turno
        
        if self.mascota:
            self.nombre_pet = self.mascota['nombre'].replace('Pequeño ', '')
            nivel_pet = self.mascota['nivel']
            nivel_max_pet = self.mascota['nivel_max']
            
            if nivel_max_pet >= 70 and nivel_pet >= 55: self.estado_pet = "👑 Portadora de Sangre Divina"
            elif nivel_max_pet >= 55 and nivel_pet >= 40: self.estado_pet = "🟣 Primal"
            elif nivel_max_pet >= 40 and nivel_pet >= 30: self.estado_pet = "🟠 Apex"
            elif nivel_max_pet >= 30 and nivel_pet >= 25: self.estado_pet = "🔵 Alpha"
            elif nivel_pet >= 21: self.estado_pet = "🐉 Adulto"
            elif nivel_pet >= 11: self.estado_pet = "🐺 Joven"
            else: self.estado_pet = "🐣 Cría"
            
            stats_base_pet = INFO_MONSTRUOS.get(self.mascota['especie'], {})
            self.emj_sprite_pet = stats_base_pet.get('emojis_fases', {}).get(self.estado_pet, "")
            if not self.emj_sprite_pet:
                self.emj_sprite_pet = obtener_emoji(self.mascota['especie'])
                if self.emj_sprite_pet == "🔹": self.emj_sprite_pet = ""

    def actualizar_botones(self):
        # 1. ATAQUE
        boton_ataque = self.children[0] 
        if hasattr(self.mecanica, 'obtener_boton_ataque'):
            txt_atk, style_atk = self.mecanica.obtener_boton_ataque()
            boton_ataque.label = txt_atk
            boton_ataque.style = style_atk

        # 2. ESPECIAL
        boton_esp = self.children[1]
        if hasattr(self.mecanica, 'obtener_estado_boton_avanzado'):
             texto, estilo, disabled = self.mecanica.obtener_estado_boton_avanzado(self)
        else:
             texto, estilo, disabled = self.mecanica.obtener_estado_boton(self.energia)

        boton_esp.label = texto
        boton_esp.style = estilo
        boton_esp.disabled = disabled

        # 3. ESQUIVAR
        boton_esq = self.children[2]
        puede_esquivar = True
        if hasattr(self.mecanica, 'puede_esquivar'):
            puede_esquivar = self.mecanica.puede_esquivar()

        if not puede_esquivar:
            boton_esq.label = "🚫 Muy Pesado"
            boton_esq.style = discord.ButtonStyle.secondary
            boton_esq.disabled = True
        else:
            vel_monstruo = self.stats.get('velocidad', 0)
            coste_simulado = max(5, int(vel_monstruo - self.agilidad))
            
            coste_simulado = int(coste_simulado * (1.0 - getattr(self, 'reduccion_energia_total', 0.0)))
            coste_simulado = max(1, coste_simulado) 
            
            if self.energia >= coste_simulado:
                boton_esq.label = f"Esquivar (-{coste_simulado}⚡)"
                boton_esq.style = discord.ButtonStyle.success
                boton_esq.disabled = False
            else:
                boton_esq.label = f"Faltan {coste_simulado - self.energia}⚡"
                boton_esq.style = discord.ButtonStyle.danger
                boton_esq.disabled = False

    @discord.ui.button(label="⚔️ Atacar", style=discord.ButtonStyle.danger, row=0)
    async def atacar(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id: return
        await interaction.response.defer()
        
        recuperado = 0
        if self.energia < self.energia_max:
            recuperado = 20
            self.energia = min(self.energia_max, self.energia + 20)
        texto_recarga = f" (+{recuperado}⚡)" if recuperado > 0 else ""
        
        # ==========================================
        # 🗡️ APLICAR PERFORACIÓN DEL JUGADOR
        # ==========================================
        def_monstruo_orig = self.stats['def']
        if getattr(self, 'jugador_perfora_armadura', False):
            self.stats['def'] = int(def_monstruo_orig * 0.70) # Ignoramos 30% de la defensa
            
        daño_final, msg_extra_arma = ServicioCombate.calcular_ataque_jugador(
            jugador=self.jugador, monstruo=self.stats, mecanica_arma=self.mecanica, view_context=self           
        )
        
        self.stats['def'] = def_monstruo_orig # Restauramos la defensa a la normalidad
        
        if getattr(self, 'jugador_perfora_armadura', False):
            msg_extra_arma += "\n> 🗡️ **¡Ataque Perforante!** *(Ignoraste 30% de su armadura)*"
            self.jugador_perfora_armadura = False # Consumimos el buff
        # ==========================================

        # ==========================================
        # 💨 CÁLCULO DE EVASIÓN DEL MONSTRUO (Basado en Velocidad)
        # ==========================================
        
        # Extraemos velocidades (usamos max(1, ...) para evitar división por cero si el jugador tiene 0 agilidad)
        vel_monstruo = self.stats.get('velocidad', 0)
        vel_jugador = max(1, self.jugador.get('agilidad', 10)) 
        
        # Calculamos la proporción de velocidad
        ratio_vel = vel_monstruo / vel_jugador
        
        if ratio_vel >= 2.0:
            probabilidad_esquive = 1.00  # 100%: El monstruo es el doble de rápido o más
        elif ratio_vel >= 1.5:
            probabilidad_esquive = 0.50  # 50%: El monstruo es 1.5 veces más rápido
        elif ratio_vel >= 1.0:
            probabilidad_esquive = 0.25  # 25%: Velocidades iguales o el monstruo es ligeramente superior
        elif ratio_vel > (1 / 1.2):      # (Aprox 0.83)
            probabilidad_esquive = 0.05  # 5%: Monstruo es más lento, pero no por tanto
        else:
            probabilidad_esquive = 0.00  # 0%: El jugador es 1.2 veces (o más) rápido que el monstruo

        # Modificadores adicionales de la misión y estados
        if "Torre de Babel" in self.nombre_mision: probabilidad_esquive += 0.05 
        if getattr(self, 'en_rabia', False): probabilidad_esquive -= 0.20
        
        # Nos aseguramos de que el porcentaje final se mantenga entre 0% y 100%
        probabilidad_esquive = max(0.0, min(1.0, probabilidad_esquive))
            
        monstruo_esquiva = False
        if self.tipo_arma != "Escudo Espejo Contundente":
            if self.turnos_derribado == 0 and random.random() < probabilidad_esquive:
                monstruo_esquiva = True
                
        # ==========================================
            
        if monstruo_esquiva:
            daño_final = 0
            if "especie" not in self.stats:
                msg_personalizado = f" 💨 Trabajas{texto_recarga}... ¡Pero tu herramienta rebota en una superficie dura!\n> ⚠️ **Pierdes el equilibrio.**"
            else:
                msg_personalizado = f" 💨 Atacas{texto_recarga}... ¡Pero el **{self.nombre_monstruo}** ESQUIVA tu golpe!\n> ⚠️ **¡Quedaste expuesto! El monstruo te ataca con furia.**"
        else:
            if self.turnos_derribado == 0 and random.random() < 0.05: 
                self.turnos_derribado = 3 
                if "especie" not in self.stats:
                    msg_extra_arma += "\n> 💥 **¡HAS AGRIETADO LA ESTRUCTURA! (Es más fácil extraer por 3 turnos)**"
                else:
                    msg_extra_arma += "\n> 💥 **¡HAS DERRIBADO AL MONSTRUO! (Pierde 3 turnos)**"
                    
            if "especie" not in self.stats:
                # Si es un nodo de recolección, siempre extrae, sin importar el arma que lleves
                msg_personalizado = f" 🪓 Extraes recursos{texto_recarga}, reduciendo la integridad en {daño_final}.{msg_extra_arma}"
            else:
                # Si es un monstruo vivo, revisamos si llevas el Escudo o un arma normal
                if self.tipo_arma == "Escudo Espejo Contundente":
                    msg_personalizado = f" 🛡️ Te preparas para el impacto{texto_recarga}...{msg_extra_arma}"
                else:
                    msg_personalizado = f" ⚔️ Atacas{texto_recarga} e infliges {daño_final} dmg.{msg_extra_arma}"

        await self.ejecutar_turno(interaction, "atacar", daño_final, msg_personalizado=msg_personalizado)

    @discord.ui.button(label="Habilidad", style=discord.ButtonStyle.secondary, row=0)
    async def especial(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id: return
        await interaction.response.defer()
        
        coste = self.mecanica.coste_especial
        if self.energia >= coste:
            await self.mecanica.ejecutar_especial(self, interaction)
        else:
            self.energia = 0
            self.fatiga_pendiente = True
            msg = "\n> ⚠️ ¡SOBREESFUERZO! (Fatiga: Pierdes el próximo turno)."
            await self.ejecutar_turno(interaction, "fatiga", 0, msg_personalizado=msg)
    
    @discord.ui.button(label="Esquivar", style=discord.ButtonStyle.secondary, emoji="💨", row=1)
    async def esquivar(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id: return
        await interaction.response.defer()

        vel_monstruo = self.stats.get('velocidad', 0)

        # Llamamos al servicio pasando la reducción pasiva que calculamos en el __init__
        exito, nueva_energia, msg_resultado, _, _ = ServicioCombate.procesar_esquive(
            agilidad_jugador_total=self.agilidad, 
            velocidad_monstruo=vel_monstruo, 
            energia_actual=self.energia,
            reduccion_pasiva=getattr(self, 'reduccion_energia_total', 0.0) # <--- PASAMOS LA REDUCCIÓN
        )

        # Guardamos el estado (El servicio ya nos dio la energía restada correctamente)
        self.energia = nueva_energia
        self.jugador['energia'] = self.energia
        self.intento_esquive = True
        self.esquive_exitoso = exito

        # Procesar efectos visuales (Limpieza de texto que hicimos antes)
        if exito:
            self.jugador_perfora_armadura = True
            msg_mecanica = ""
            if hasattr(self.mecanica, 'procesar_esquive'):
                msg_mecanica = self.mecanica.procesar_esquive(True)
            
            from Logica.servicio_habilidades import ServicioHabilidades
            msg_pasivas = ServicioHabilidades.procesar_pasivas_esquive(self.user_id, self)
            
            efectos_limpios = f"{msg_mecanica}{msg_pasivas}".replace("\n> ", " | ").replace("\n", " | ").strip()
            if efectos_limpios.startswith("|"): efectos_limpios = efectos_limpios[1:].strip()
            texto_efectos = f"\n> ✨ **Efectos:** {efectos_limpios}" if efectos_limpios else ""
            
            msg_personalizado = f"{msg_resultado}\n> 🗡️ (+30% Prf) **Contraataque listo**{texto_efectos}"
        else:
            msg_personalizado = f"{msg_resultado}\n> ⚠️ **¡Quedas indefenso ante su ataque!**"
            
        await self.ejecutar_turno(interaction, "esquivar", 0, msg_personalizado)
        

    @discord.ui.button(label="🧪 Curarse", style=discord.ButtonStyle.success, row=1)
    async def curarse(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id: return
        await interaction.response.send_modal(CuracionBatallaModal(self))

    @discord.ui.button(label="🏃 Huir", style=discord.ButtonStyle.secondary, row=1)
    async def huir(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id: return
        await interaction.response.defer()
        
        if self.mascota:
            from Data.database import update_mascota_hp
            update_mascota_hp(self.mascota['id'], self.mascota.get('hp_max', 100))
            
        from Vistas.vistas import AldeaView, embed_aldea
        await interaction.edit_original_response(content="🏃💨 Escapaste...", embed=embed_aldea(), view=AldeaView(self.user_id), attachments=[])

    @discord.ui.button(label="✨ Habilidades", style=discord.ButtonStyle.primary, row=2)
    async def mostrar_menu_habilidades(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id: 
            return await interaction.response.send_message("❌ Esta no es tu batalla.", ephemeral=True)
            
        # Reemplazamos los botones inferiores por el menú desplegable en el MISMO mensaje de la batalla
        vista_habilidades = VistaSeleccionHabilidad(self)
        
        # edit_message solo sobreescribe la Vista (View), manteniendo intacto el Embed de la pelea
        await interaction.response.edit_message(view=vista_habilidades)

    async def actualizar_embed_combate(self, interaction, log_texto, img_clave="img_idle", edit_type="response"):   
        url_sprite = self.stats.get(img_clave, self.stats.get('img_idle'))
        
        embed = embed_batalla(
            self.jugador, self.nombre_monstruo, self.stats, self.hp_monstruo, 
            url_sprite, log_texto, self.energia, self.energia_max, mascota=self.mascota
        )

        if getattr(self, 'viene_de_habilidad', False) and hasattr(self, 'mensaje_batalla'):
            await self.mensaje_batalla.edit(embed=embed, view=self)
            return

        if edit_type == "response":
            if not interaction.response.is_done():
                await interaction.response.edit_message(embed=embed, view=self)
            else:
                await interaction.edit_original_response(embed=embed, view=self)
        else:
            await interaction.edit_original_response(embed=embed, view=self)

    # --- LÓGICA DE TURNO CENTRAL ---
    async def ejecutar_turno(self, interaction, accion_jugador, daño_jugador=0, msg_personalizado=None):
        
        # ==========================================
        # 1. FASE JUGADOR Y MASCOTA
        # ==========================================
        log_jugador = msg_personalizado if msg_personalizado else "..."

        # Añadimos "esquivar" a las acciones válidas
        if accion_jugador in ["atacar", "habilidad", "esquivar"]:
            if accion_jugador in ["atacar", "habilidad"]:
                self.hp_monstruo -= daño_jugador
                self.hp_monstruo = max(0, self.hp_monstruo)
            
            if self.mascota and self.mascota.get('hp', 100) > 0 and self.hp_monstruo > 0:
                if random.randint(1, 100) <= self.prob_atk_mascota:
                    daño_pet = self.mascota['atk']
                    
                    # Habilidad (10%)
                    uso_habilidad_pet = False
                    stats_base = INFO_MONSTRUOS.get(self.mascota['especie'], {})
                    if random.random() <= 0.10:
                        uso_habilidad_pet = True
                        nombre_hab_pet = stats_base.get('habilidad', 'Ataque Especial')
                        daño_pet = int(daño_pet * stats_base.get('daño_Habilidad', 1.5))
                    
                    # Traición o Ataque
                    if self.mascota.get('felicidad', 100) < 30 and random.random() <= 0.50:
                        self.hp_jugador -= daño_pet
                        self.jugador['hp'] = self.hp_jugador
                        log_jugador += f"\n> 💢 {self.emj_sprite_pet} **¡{self.nombre_pet} se rebela y te ataca!** Recibes {daño_pet} dmg."
                        
                        if self.hp_jugador <= 0:
                            await self.actualizar_embed_combate(interaction, log_jugador, "img_idle", "response")
                            await asyncio.sleep(2)
                            return await self.manejar_derrota(interaction)
                    else:
                        self.hp_monstruo = max(0, self.hp_monstruo - daño_pet)
                        
                        # ⚡ MAGIA: Acumulamos XP en memoria, no tocamos la DB mid-turn
                        xp_golpe = int(20 * (1.5 ** getattr(self, 'indice_rango', 0)))
                        self.xp_acumulada_pet += xp_golpe
                        
                        if "especie" not in self.stats:
                            log_jugador += f"\n> 🐾 {self.emj_sprite_pet} **{self.nombre_pet}** te ayuda a recolectar ({daño_pet} de avance). [+{xp_golpe} XP]"
                        else:
                            if uso_habilidad_pet:
                                log_jugador += f"\n> ✨ {self.emj_sprite_pet} **¡{self.nombre_pet} desata {nombre_hab_pet.upper()}!** ({daño_pet} dmg). [+{xp_golpe} XP]"
                            else:
                                log_jugador += f"\n> {self.emj_sprite_pet} **{self.nombre_pet}** ataca e inflige {daño_pet} dmg. [+{xp_golpe} XP]"
            
            # Chequeo de Rabia (Solo si es un ser vivo)
            if "especie" in self.stats and not getattr(self, 'en_rabia', False) and self.hp_monstruo > 0 and self.hp_monstruo <= (self.hp_max_monstruo * 0.40):
                self.en_rabia = True
                self.stats['atk'] = int(self.stats['atk'] * 1.30) 
                self.stats['def'] = int(self.stats['def'] * 0.70) 
                log_jugador += f"\n> 💢 **¡EL {self.nombre_monstruo.upper()} ENTRA EN MODO RABIA!**"

        # ¿Murió el monstruo / Se rompió el objeto?
        if self.hp_monstruo <= 0:
            return await self.manejar_victoria(interaction)


        # ==========================================
        # 2. FASE MONSTRUO (Cálculo Inmediato)
        # ==========================================
        
        if getattr(self, 'saltar_turno_monstruo', False):
            # Reducimos las acciones extra si hay, si no, apagamos la bandera
            if getattr(self, 'acciones_extra', 0) > 0:
                self.acciones_extra -= 1
            else:
                self.saltar_turno_monstruo = False
                
            # Saltamos todo el cálculo del monstruo y le decimos al jugador que actúe
            log_monstruo = f"{log_jugador}\n> ⚡ **[Reacción Acelerada]** El enemigo apenas comienza a moverse."
            
        elif self.turnos_derribado > 0:
            self.turnos_derribado -= 1
            if "especie" not in self.stats:
                log_monstruo = f"{log_jugador}\n> ⛏️ La estructura de {self.nombre_monstruo} está agrietada y cede fácilmente."
            else:
                log_monstruo = f"{log_jugador}\n> 💫 El {self.nombre_monstruo} intenta levantarse pero cae al suelo..."
        else:
            def_jugador_orig = self.jugador['defensa']
            empezo_a_cargar = False # Bandera para saber si solo está gritando
            log_arma_defensa = "" 
            
            if getattr(self, 'monstruo_perfora_armadura', False):
                self.jugador['defensa'] = int(def_jugador_orig * 0.70) 
                
            if getattr(self, 'habilidad_cargando', False):
                # Si el jugador esquivó con éxito, el monstruo falla la habilidad masiva
                if getattr(self, 'esquive_exitoso', False):
                    self.habilidad_cargando = False
                    nombre_hab = self.stats.get('habilidad', 'su habilidad especial')
                    log_arma_defensa = f"\n> 💨 **¡ESQUIVASTE {nombre_hab.upper()}!** El {self.nombre_monstruo} gastó toda su energía y falló."
                    daño_final_m = 0
                else:
                    daño_final_m, log_arma_defensa_extra = ServicioCombate.calcular_ataque_monstruo(self.stats, self.jugador['defensa'], self.mecanica, self)
                    mult_hab = self.stats.get('daño_Habilidad', 2)
                    daño_final_m = int(daño_final_m * mult_hab)
                    
                    # Penalización de 30% si intentaste esquivar pero fallaste el roll
                    if getattr(self, 'intento_esquive', False): 
                        daño_final_m = int(daño_final_m * 1.3)
                        
                    nombre_hab = self.stats.get('habilidad', 'su habilidad definitiva')
                    log_arma_defensa = f"\n> ☄️ **¡EL MONSTRUO DESATA {nombre_hab.upper()}!** *(Daño masivo)*" + log_arma_defensa_extra
                    self.habilidad_cargando = False 
                
            else:
                
                # 🎲 👇 LÓGICA DE PROBABILIDAD DINÁMICA DE LA BASE DE DATOS 👇
                probabilidad_habilidad = self.stats.get('pro_habilidad', 10) / 100.0
                
                if "especie" in self.stats and random.random() <= probabilidad_habilidad:
                    self.habilidad_cargando = True
                    empezo_a_cargar = True
                    daño_final_m = 0 # No hace daño este turno, solo avisa
                    nombre_hab = self.stats.get('habilidad', 'un ataque letal')
                    
                    log_arma_defensa = f"\n> ⚠️ **¡ATENCIÓN CUIDADO!** \n> El {self.nombre_monstruo}\n> **¡Se prepara para usar {nombre_hab}!**"
                else:
                    # Si esquivaste un ataque normal con éxito
                    if getattr(self, 'esquive_exitoso', False):
                        log_arma_defensa = f"\n> 💨 El {self.nombre_monstruo} intentó atacarte, pero falló"
                        daño_final_m = 0
                    else:
                        # Ataque normal
                        daño_final_m, log_arma_defensa = ServicioCombate.calcular_ataque_monstruo(self.stats, self.jugador['defensa'], self.mecanica, self)
                        # Penalización de 30% si fallaste el esquive
                        if getattr(self, 'intento_esquive', False): 
                            daño_final_m = int(daño_final_m * 1.3)

            self.jugador['defensa'] = def_jugador_orig 
            
            esquive_ahora = getattr(self, 'esquive_exitoso', False)
            
            # Limpiamos las banderas de esquive para el siguiente turno (Importante)
            self.intento_esquive = False
            self.esquive_exitoso = False
            
            if getattr(self, 'monstruo_perfora_armadura', False) and daño_final_m > 0:
                log_arma_defensa += "\n> 🩸 **¡Contraataque!** (-30% Def)"
                self.monstruo_perfora_armadura = False 

            log_mascota_defensa = ""

            # 2. La Mascota salta a protegerte (Si hay daño entrante)
            if getattr(self, 'mascota', None) and self.mascota.get('hp', 100) > 0 and daño_final_m > 0 and self.mascota.get('felicidad', 100) >= 30:
                
                nivel_pet = self.mascota['nivel']
                nivel_max_pet = self.mascota['nivel_max']
                
                if nivel_max_pet >= 70 and nivel_pet >= 55: emj_fase = ""; estado_pet = "👑 Portadora de Sangre Divina"
                elif nivel_max_pet >= 55 and nivel_pet >= 40: emj_fase = ""; estado_pet = "🟣 Primal"
                elif nivel_max_pet >= 40 and nivel_pet >= 30: emj_fase = ""; estado_pet = "🟠 Apex"
                elif nivel_max_pet >= 30 and nivel_pet >= 25: emj_fase = "🔵"; estado_pet = "🔵 Alpha"
                elif nivel_pet >= 21: emj_fase = ""; estado_pet = "🐉 Adulto"
                elif nivel_pet >= 11: emj_fase = ""; estado_pet = "🐺 Joven"
                else: emj_fase = ""; estado_pet = "🐣 Cría"
                
                stats_base = INFO_MONSTRUOS.get(self.mascota['especie'], {})
                emojis_fases = stats_base.get('emojis_fases', {})
                emj_sprite = emojis_fases.get(estado_pet, "")
                
                if not emj_sprite:
                    emj_sprite = obtener_emoji(self.mascota['especie'])
                    if emj_sprite == "🔹": emj_sprite = ""

                nombre_pet = self.mascota['nombre'].replace('Pequeño ', '')
                
                # Obtener la probabilidad de que la mascota salte a defender. Usando 20 por defecto si no existe.
                prob_mascota = getattr(self, 'prob_atk_mascota', 20)

                if random.randint(1, 100) <= prob_mascota:
                    porc_mitigado = random.randint(30, 100)
                    daño_a_mascota_base = int(daño_final_m * (porc_mitigado / 100.0))
                    daño_al_jugador = daño_final_m - daño_a_mascota_base
                    
                    if random.randint(1, 100) <= self.mascota.get('agi', 0):
                        log_mascota_defensa += f"\n> {emj_fase} {emj_sprite} **{nombre_pet}** distrajo al monstruo, esquivando el {porc_mitigado}% del ataque."
                    else:
                        daño_a_mascota_real = max(0, daño_a_mascota_base - self.mascota.get('def', 0))
                        self.mascota['hp'] -= daño_a_mascota_real
                        log_mascota_defensa += f"\n> {emj_sprite} **{nombre_pet}** interceptó el {porc_mitigado}% del golpe (Recibe {daño_a_mascota_real} dmg)."
                        
                        if self.mascota['hp'] <= 0:
                            self.mascota['hp'] = 0
                            log_mascota_defensa += f"\n> 💀 {emj_sprite} **¡{nombre_pet} ha caído inconsciente!**"
                    
                    daño_final_m = daño_al_jugador

            # 3. El Jugador recibe el daño final restante
            self.hp_jugador -= daño_final_m
            self.jugador['hp'] = self.hp_jugador
            from Data.database import update_player_hp
            update_player_hp(self.user_id, self.hp_jugador)
            

            if empezo_a_cargar:
                log_monstruo = f"{log_jugador}{log_arma_defensa}"
            elif "especie" not in self.stats:
                
                textos_entorno = [
                    "⛏️ Extraes materiales con cuidado...",
                    "🍃 El viento sopla tranquilamente mientras trabajas.",
                    "🌲 Te adentras un poco más en la zona.",
                    "🪨 Golpeas la superficie revelando más recursos."
                ]
                log_monstruo = f"{log_jugador}\n> {random.choice(textos_entorno)}"
            elif esquive_ahora:
                # Si lograste esquivar, el mensaje de tu esquive ya está en log_arma_defensa
                log_monstruo = f"{log_jugador}{log_arma_defensa}"
            else:
                # Si fallaste el esquive O atacaste normal, SIEMPRE imprime esto (incluso si recibes 0 de daño)
                log_monstruo = f"{log_jugador}\n> 🔻 **{self.nombre_monstruo}** ataca con furia.{log_arma_defensa}{log_mascota_defensa}\n> 💥 Recibes **{daño_final_m}** de daño final."
            
        
        # ¿Murió el jugador?
        if self.hp_jugador <= 0:
            return await self.manejar_derrota(interaction)

        # Si el monstruo murió por el daño reflejado de tu escudo en su propio turno:
        if self.hp_monstruo <= 0:
            self.hp_monstruo = 0 # Limpiamos el número negativo para evitar bugs visuales
            return await self.manejar_victoria(interaction)
            

        # ==========================================
        # 3. FASE FATIGA (Si se quedó sin energía)
        # ==========================================
        if self.fatiga_pendiente:
            self.fatiga_pendiente = False
            # Calculamos daño extra por estar cansado
            daño_fatiga, _ = ServicioCombate.calcular_ataque_monstruo(self.stats, self.jugador['defensa'], self.mecanica, self)
            self.hp_jugador = max(0, self.hp_jugador - daño_fatiga)
            self.jugador['hp'] = self.hp_jugador
            
            
            # 💡 IMPORTANTE: Usar += para añadir al log existente
            log_monstruo += f"\n> 💤 **¡EXTENUADO!** Al no tener energía, recibes {daño_fatiga} dmg extra de fatiga."
            
            if self.hp_jugador <= 0:
                return await self.manejar_derrota(interaction)

        # ==========================================
        # 4. GUARDADO FINAL Y ACTUALIZACIÓN VISUAL
        # ==========================================
        # ⚡ OPTIMIZACIÓN: Solo escribimos en la BD UNA vez por turno, eliminando el lag.

        from Logica.servicio_habilidades import ServicioHabilidades
        msg_pasivas = ServicioHabilidades.procesar_pasivas_fin_de_turno(self.user_id, self)
        if msg_pasivas:
            pasivas_limpias = msg_pasivas.replace("\n> ", " | ").replace("\n", " | ").strip()
            if pasivas_limpias.startswith("|"): 
                pasivas_limpias = pasivas_limpias[1:].strip()
            log_monstruo += f"\n> {pasivas_limpias}"

        from Data.database import update_player_hp
        update_player_hp(self.user_id, self.hp_jugador)

        self.actualizar_botones() 
        await self.actualizar_embed_combate(interaction, log_monstruo, "img_idle", "response")

    async def manejar_victoria(self, interaction):
        from Data.data import obtener_evento_diario, obtener_emoji
        from Vistas.Embeds import embed_victoria_batalla
        await asyncio.sleep(0.5)
        
        texto_xp_mascota = "" 
        evento = obtener_evento_diario()
        mult_evento_xp = evento['mult'] if evento and evento['id'] in ['xp', 'all'] else 1.0

        # 👇 1. MASCOTA A TRAVÉS DEL SERVICIO 👇
        if self.mascota:
            from Logica.servicio_mascotas import ServicioMascotas
            xp_acumulada = getattr(self, 'xp_acumulada_pet', 0)
            res_pet = ServicioMascotas.procesar_mascota_post_combate(self.mascota, True, getattr(self, 'indice_rango', 0), mult_evento_xp, xp_acumulada)
            
            if res_pet['m_act']:
                nombre_pet = res_pet['m_act']['nombre'].replace("Pequeño ", "")
                especie_pet = res_pet['m_act']['especie']
                bonus_txt = f" (x{evento['mult']} Evento!)" if evento and evento['id'] in ['xp', 'all'] else ""
                
                if res_pet['m_act']['nivel'] >= res_pet['m_act']['nivel_max'] and not res_pet['subio_nivel']:
                    texto_xp_mascota = f"🌟 **{nombre_pet}** ({especie_pet}) ya ha alcanzado su nivel máximo."
                elif res_pet['subio_nivel']:
                    texto_xp_mascota = f"🎉 **{nombre_pet}** ({especie_pet}) ha subido al **Nivel {res_pet['m_act']['nivel']}**!{bonus_txt}"
                else:
                    texto_xp_mascota = f"✨ **{nombre_pet}** ({especie_pet}) ha recibido **{res_pet['xp_ganada']} XP**{bonus_txt}."
                
                texto_xp_mascota += f"\n❤️ **Felicidad:** {res_pet['felicidad']}/100 (+10)"

        # 2. CALCULAR RECOMPENSAS
        nombre_para_botin = self.nombre_monstruo
        if "Torre de Babel" in self.nombre_mision:
            nombre_para_botin = self.nombre_monstruo
            
        titulos_a_borrar = ["APEX ", "SEÑOR DE RAZA ", "Feroz ", "Peligroso ", "Amenazante ", "Brutal ", "Inclemente ", "Veterano ", "Curtido ", "Apex ", "Archicurtido ", "Calamidad "]
        for t in titulos_a_borrar: nombre_para_botin = nombre_para_botin.replace(t, "").strip()

        resultado = ServicioCombate.calcular_resultado_final(
        self.user_id, self.nombre_mision, nombre_para_botin, self.tipo_arma
    )
        
        lista_visual = []
        puntos_gracia = resultado['items'].pop("Puntos de Gracia", 0)
        for nombre, cant in resultado['items'].items():
            lista_visual.append(f"{obtener_emoji(nombre)} **{nombre}** x{cant}")
        texto_recompensas = "\n".join(lista_visual) if lista_visual else "Nada..."

        from Data.database import procesar_usos_habilidades_fin_batalla
        
        from Data.habilidades_db import HABILIDADES_HUMANO
        for hab_id in getattr(self, 'adquiridas', []):
            hab = HABILIDADES_HUMANO.get(hab_id)
            
            # Verificamos que exista y sea una pasiva automática
            if hab and hab.get('categoria') == 'Pasiva' and hab.get('activacion') == 'automatica':
                
                # Revisamos si es una pasiva que modifica los stats base 
                llaves_estado = [
                    'aumento_pasivo_ataque', 'aumento_pasivo_defensa', 'aumento_pasivo_agilidad', 
                    'aumento_pasivo_vida', 'aumento_pasivo_miasma', 'aumento_pasivo_energia'
                ]
                
                es_pasiva_estado = any(hab.get(llave, 0.0) > 0 for llave in llaves_estado)
                
                # Si es una pasiva de estado, le otorgamos EXACTAMENTE 3 usos por ganar
                if es_pasiva_estado:
                    self.usos_habilidades[hab_id] = self.usos_habilidades.get(hab_id, 0) + 3
        
        # 👇 1. PROCESAR USOS DE HABILIDADES EN LOTE 👇
        from Data.database import procesar_usos_habilidades_fin_batalla
        subidas_habilidades = procesar_usos_habilidades_fin_batalla(self.user_id, getattr(self, 'usos_habilidades', {}))
        
        texto_habilidades = ""
        if subidas_habilidades:
            for mensaje_subida in subidas_habilidades:
                texto_habilidades += f"> {mensaje_subida}\n"

        embed_vic = embed_victoria_batalla(self.nombre_monstruo, resultado, puntos_gracia, texto_recompensas, texto_xp_mascota, texto_habilidades)


        if resultado['es_ascension']:
            url_gif_ascension = "https://i.imgur.com/zVR1V2x.png" 
            embed_ascension = discord.Embed(
                title="✨ Seleccion de Candidato ✨",
                description="**¡Has sido elegido entre tantos, por las deidades de este mundo para terminar lo que ellos empezaron, por favor salva este mundo**",
                color=0xffff00
            )
            embed_ascension.set_image(url=url_gif_ascension)
            await interaction.edit_original_response(content=None, embed=embed_ascension, view=None)
            await asyncio.sleep(8)

        vista_final = discord.ui.View()
        
        stats_monstruo_real = INFO_MONSTRUOS.get(nombre_para_botin, {})
        
        # El nido solo aparece si NO es la torre, si el monstruo SI es una criatura viva (tiene 'especie') y cae el 20%
        if "Torre de Babel" not in self.nombre_mision and "especie" in stats_monstruo_real and random.random() <= 1.0:
            boton_nido = discord.ui.Button(label="🪺 Investigar Nido", style=discord.ButtonStyle.primary)
            
            async def nido_cb(int_btn):
                if int_btn.user.id != self.user_id: return
                
                embed_nido = discord.Embed(
                    title=f"🪺 Nido de {nombre_para_botin}",
                    description=(
                        "Has encontrado el nido del monstruo derrotado escondido entre la maleza.\n\n"
                        "Por desgracia, tu mochila está casi llena y **solo tienes espacio para llevar un huevo**.\n\n"
                        "Selecciona el huevo a llevar:\n"
                        "🔴 **Huevo Rojo:** Está pesado.\n"
                        "🟢 **Huevo Verde:** Está ligero pero huele mal.\n"
                        "🔵 **Huevo Azul:** Está fracturado pero se siente cálido."
                    ),
                    color=0xe67e22
                )
                await int_btn.response.edit_message(embed=embed_nido, view=NidoEncontradoView(self.user_id, nombre_para_botin), attachments=[])
            
            boton_nido.callback = nido_cb
            vista_final.add_item(boton_nido)

        boton_volver = discord.ui.Button(label="↩️ Volver a la Aldea", style=discord.ButtonStyle.success)
        
        async def volver_cb(int_btn):
            if int_btn.user.id != self.user_id: return
            from Vistas.vistas import AldeaView, embed_aldea
            # IMPORTANTE: attachments=[] para limpiar cualquier imagen residual
            await int_btn.response.edit_message(embed=embed_aldea(), view=AldeaView(self.user_id), attachments=[])
        
        boton_volver.callback = volver_cb
        vista_final.add_item(boton_volver)
        # ====================================================
        # 🗼 LÓGICA DE LA TORRE DE BABEL
        # ====================================================
        if "Torre de Babel" in self.nombre_mision:
            from Data.database import update_piso_torre, get_player_data, add_zenny, add_material
            
            piso_superado = self.jugador.get('piso_torre', 1)
            
            # 👇 1. LÓGICA DEL FINAL ABSOLUTO (PISO 50) 👇
            if piso_superado == 60:
                # Entregamos los premios
                add_zenny(self.user_id, 100000)
                add_material(self.user_id, "Huevo Misterioso", 1)
                add_material(self.user_id, "Caja Misteriosa", 1)
                
                # NUEVO: Guardamos la dificultad actual como completada
                from Data.database import marcar_dificultad_completada
                dif_superada = getattr(self, 'dificultad', 'Visitante')
                marcar_dificultad_completada(self.user_id, dif_superada)
                
                embed_vic = discord.Embed(
                    title=f"👑 ¡SEÑOR DE BABEL [{dif_superada}]!",
                    description="*El inmenso cuerpo del Dios de la Torre se desploma, haciendo temblar los cimientos del mundo. Una luz dorada desciende sobre ti...*\n\n**¡HAS CONQUISTADO LA CIMA DE LA TORRE!**\nLos dioses, atónitos ante tu fuerza, reconocen tu inmenso poder y te otorgan sus tesoros más sagrados.",
                    color=0xffd700
                )
                embed_vic.add_field(name="💰 Recompensa Divina", value="**+100,000 Crops**", inline=False)
                embed_vic.add_field(name="🎁 Tesoros Sagrados", value="🥚 **Huevo Misterioso** x1\n📦 **Caja Misteriosa** x1", inline=False)
                embed_vic.set_image(url="https://i.imgur.com/GRuVVsJ.png")
                
                # Reseteamos el piso a 1
                update_piso_torre(self.user_id, 1)

                
                async def victoria_cb(int_btn):
                    if int_btn.user.id != self.user_id: return
                    from Vistas.vistas import AldeaView
                    from Vistas.Embeds import embed_aldea
                    await int_btn.response.edit_message(content=None, embed=embed_aldea(), view=AldeaView(self.user_id), attachments=[])
                await interaction.edit_original_response(content="¡Torre Superada!", embed=embed_vic, view=vista_final, attachments=[])
                return 


            # 2. SI NO ES EL PISO 50, AVANZAMOS NORMAL
            nuevo_piso = piso_superado + 1
            update_piso_torre(self.user_id, nuevo_piso)

            # --- BOTÓN 1: AVANZAR AL SIGUIENTE PISO ---
            boton_avanzar = discord.ui.Button(label=f"⚔️ Avanzar al Piso {nuevo_piso}", style=discord.ButtonStyle.danger)
            
            async def avanzar_cb(int_btn):
                if int_btn.user.id != self.user_id: return
                await int_btn.response.defer()
                
                
                from Data.database import get_player_data, get_mascota_equipada
                
                # 👇 1. OBTENEMOS LAS ESTADÍSTICAS REALES DESDE EL PRINCIPIO 👇
                jugador_bd = get_player_data(self.user_id)
                jugador_real, tipo_arma, nivel_maestria = ServicioJugador.obtener_stats_reales(jugador_bd)
                
                # 2. Conservamos la energía del piso anterior
                energia_actual = getattr(self, 'energia', self.jugador.get('energia', 100))
                jugador_real['energia'] = energia_actual 
                
                # 3. Aplicamos los Buffs Divinos de la Torre
                mult_atk = jugador_real.get('torre_buff_atk', 1.0)
                mult_def = jugador_real.get('torre_buff_def', 1.0)
                jugador_real['ataque'] = int(jugador_real['ataque'] * mult_atk)
                jugador_real['defensa'] = int(jugador_real['defensa'] * mult_def)
                
                # ====================================================
                # --- EVENTO: SALA DE BENDICIÓN (Pisos 5, 15, 25...) ---
                # ====================================================
                if nuevo_piso % 10 == 5:
                    from Vistas.vistasBatalla import TorreBendicionView
                    embed_bendicion = discord.Embed(
                        title=f"🗼 TORRE DE BABEL - PISO {nuevo_piso}",
                        description="*Entras a una inmensa sala vacía iluminada por una luz tenue. No hay rastro de monstruos.*\n> 👁️ **Estás siendo observado por entidades superiores...**\n```Has demostrado valor, mortal. Elige una recompensa para continuar tu ascenso.```",
                        color=0xf1c40f
                    )
                    
                    hp_max = getattr(self, 'hp_max_jugador', getattr(self, 'hp_max_anterior', 100))
                    en_max = getattr(self, 'energia_max', getattr(self, 'energia_max_anterior', 100))
                    
                    await int_btn.edit_original_response(
                        embed=embed_bendicion, 
                        view=TorreBendicionView(self.user_id, nuevo_piso, jugador_real, hp_max, en_max, getattr(self, 'dificultad', 'Visitante')), 
                        attachments=[]
                    )
                    return

                # ====================================================
                # --- LÓGICA DE SELECCIÓN DE MONSTRUO Y DIFICULTAD ---
                # ====================================================
                MULTIPLICADOR_DIFICULTAD = {
                    "Visitante": 1.0, "Explorador": 2.0, "Cazarrecompensas": 3.0,
                    "Investigador": 5.0, "Conquistador": 8.0, "Señor de la torre": 12.0
                }
                dif_actual = getattr(self, 'dificultad', 'Visitante')
                mult_dif = MULTIPLICADOR_DIFICULTAD.get(dif_actual, 1.0)

                JEFES_TORRE = {
                    10: "Primogénito Cornudo", 20: "Progenitor Escamado",
                    30: "Progenitor Abisal", 40: "Titán de Impacto", 50: "Progenitor Entomante", 60: "La Anomalía Perfecta"
                }

                if nuevo_piso in JEFES_TORRE:
                    nombre_base_monstruo = JEFES_TORRE[nuevo_piso]
                    stats_base = INFO_MONSTRUOS.get(nombre_base_monstruo, INFO_MONSTRUOS["DEFAULT"]).copy()
                    nombre_mostrar = f"SEÑOR DE RAZA {nombre_base_monstruo}"
                    stats_base['hp'] = int(stats_base['hp'] * 20.0 * mult_dif)
                    stats_base['atk'] = int(stats_base['atk'] * 15.0 * mult_dif)
                    stats_base['def'] = int(stats_base['def'] * 10.0 * mult_dif)
                else:
                    if nuevo_piso < 10: monstruos_torre = ["Astazur", "Cráneo Vivo", "Cornisombra", "Astafauce", "Retorcido del Anillo","Desollador Pétreo","Uñabruma"]
                    elif nuevo_piso < 20: monstruos_torre = ["Syrrakel", "Vorthyx", "Kaelmyr", "Zhaeroth", "Cravex","Raxandor","Velkareth","Keralith"]
                    elif nuevo_piso < 30: monstruos_torre = ["Sargassum Rex", "Dorsal del Abismo", "Nautyrr", "Umbrothal", "Ophydral","Criptomarea","Gravemarea","Kryssmare"]
                    elif nuevo_piso < 40: monstruos_torre = ["Plomogron", "Retumbón", "Punzón Colosal", "Crushbehem", "Megalastre","Rompelínea","Ferrocrash","Tremorak"]
                    elif nuevo_piso < 50: monstruos_torre = ["Excavador Abisal", "Coraza Prismática", "Rey Escarabeo", "Centípodo de Fosas", "Portador de Larvas","Tejedor Umbrío","Custodio del Nido","Aguijón Solar","Reina Quitinaria"]
                    else: monstruos_torre = ["Larva Eterna", "Feromona Muerta", "Colmena Individual", "Bruto Opuesto", "El Que Nunca Cae","Bruto de Masa Infinita","El Que No Flota","Leviatán Descompuesto"]

                    nombre_base_monstruo = random.choice(monstruos_torre)
                    stats_base = INFO_MONSTRUOS.get(nombre_base_monstruo, INFO_MONSTRUOS["DEFAULT"]).copy()
                    multiplicador = 10.0 + ((nuevo_piso - 1) * 0.5)
                    nombre_mostrar = f" APEX {nombre_base_monstruo}"
                    
                    stats_base['hp'] = int(stats_base['hp'] * multiplicador * mult_dif)
                    stats_base['atk'] = int(stats_base['atk'] * multiplicador * mult_dif)
                    stats_base['def'] = int(stats_base['def'] * multiplicador * mult_dif)

                # ====================================================
                # --- CREAR Y LANZAR LA VISTA DE BATALLA ---
                # ====================================================
                mascota_db = get_mascota_equipada(self.user_id)
                mascota_dict = dict(mascota_db) if mascota_db else None
                
                from Vistas.vistasBatalla import BatallaView
                nueva_vista = BatallaView(
                    user_id=self.user_id,
                    jugador=jugador_real, 
                    nombre_mision=f"Torre de Babel - Piso {nuevo_piso}",
                    nombre_monstruo=nombre_mostrar,
                    stats_monstruo=stats_base,
                    agilidad=jugador_real['agilidad'],
                    nivel_maestria=nivel_maestria,
                    tipo_arma_cache=tipo_arma,
                    dificultad=dif_actual,
                    mascota=mascota_dict
                )
                
                from Vistas.Embeds import embed_batalla
                embed_siguiente = embed_batalla(
                    nueva_vista.jugador, nueva_vista.nombre_monstruo, nueva_vista.stats, 
                    nueva_vista.hp_monstruo, nueva_vista.stats['img_idle'], 
                    f"⛩️ ¡Avanzas al PISO {nuevo_piso}!\n> Un **{nombre_mostrar}** bloquea tu camino.", 
                    nueva_vista.energia, nueva_vista.energia_max, mascota=nueva_vista.mascota
                )
                embed_siguiente.color = 0x5c0000 
                await int_btn.edit_original_response(content=f"🗼 ASCENSIÓN: PISO {nuevo_piso}", embed=embed_siguiente, view=nueva_vista, attachments=[])

            boton_avanzar.callback = avanzar_cb
            vista_final.add_item(boton_avanzar)

        async def actualizar_pantalla_victoria(content=None, embed=None, view=None, attachments=[]):
            if getattr(self, 'viene_de_habilidad', False) and hasattr(self, 'mensaje_batalla'):
                await self.mensaje_batalla.edit(content=content, embed=embed, view=view, attachments=attachments)
            else:
                await interaction.edit_original_response(content=content, embed=embed, view=view, attachments=attachments)

        # ====================================================

        if "Torre de Babel" in self.nombre_mision:
            await actualizar_pantalla_victoria(content="¡Piso Superado!", embed=embed_vic, view=vista_final, attachments=[])
            
        # 👑 Final del Juego (Excepción Dios Negro)
        elif self.nombre_mision == "El Dios Negro":
            await actualizar_pantalla_victoria(content="⚠️ ANOMALÍA DETECTADA...", embed=embed_vic, view=None, attachments=[])
            await asyncio.sleep(6) 
            from Vistas.vistas import LoreFinalView
            await actualizar_pantalla_victoria(content=None, embed=embed_lore_final(), view=LoreFinalView(self.user_id))
            
        # ⚔️ Victoria Normal
        else:
            await actualizar_pantalla_victoria(content="¡Victoria!", embed=embed_vic, view=vista_final, attachments=[])

    async def manejar_derrota(self, interaction):
        await asyncio.sleep(1)
        ServicioCombate.procesar_derrota(self.user_id)
        
        if self.mascota:
            from Logica.servicio_mascotas import ServicioMascotas
            ServicioMascotas.procesar_mascota_post_combate(self.mascota, False, 0, 1.0, 0)
        
        from Vistas.Embeds import embed_derrota_batalla
        
        vista_final = discord.ui.View()
        boton_volver = discord.ui.Button(label="🩹 Recuperarse en la Aldea", style=discord.ButtonStyle.secondary)
        async def volver_cb(int_btn):
            if int_btn.user.id != self.user_id: return
            from Vistas.vistas import AldeaView, embed_aldea
            await int_btn.response.edit_message(embed=embed_aldea(), view=AldeaView(self.user_id), attachments=[])
            
        boton_volver.callback = volver_cb
        vista_final.add_item(boton_volver)

        if getattr(self, 'viene_de_habilidad', False) and hasattr(self, 'mensaje_batalla'):
            await self.mensaje_batalla.edit(content=None, embed=embed_derrota_batalla(), view=vista_final, attachments=[])
        else:
            await interaction.edit_original_response(content=None, embed=embed_derrota_batalla(), view=vista_final, attachments=[])

# ==========================================
# 🔮 MENU DE HABILIDADES INLINE 
# ==========================================
class VistaSeleccionHabilidad(discord.ui.View):
    def __init__(self, vista_batalla):
        super().__init__(timeout=None)
        self.vista_batalla = vista_batalla
        self.user_id = vista_batalla.user_id
        
        from Data.habilidades_db import HABILIDADES_HUMANO
        from Data.database import obtener_habilidades_jugador

        _, adquiridas = obtener_habilidades_jugador(self.user_id)
        
        opciones = []
        for hab_id in adquiridas:
            hab_data = HABILIDADES_HUMANO.get(hab_id)
            if hab_data and hab_data.get("activacion") == "boton":
                desc_corta = (hab_data["descripcion"][:45] + '...') if len(hab_data["descripcion"]) > 45 else hab_data["descripcion"]
                opciones.append(
                    discord.SelectOption(
                        label=hab_data["nombre"], 
                        description=f"{desc_corta} | Costo: {hab_data['costo_mp']} PM", 
                        emoji="✨",
                        value=hab_id 
                    )
                )

        if not opciones:
            opciones.append(discord.SelectOption(label="Sin habilidades", description="No tienes habilidades activas.", value="ninguna"))

        select = discord.ui.Select(
            placeholder="Elige una habilidad para desatar...", 
            options=opciones,
            row=0
        )
        if len(opciones) == 1 and opciones[0].value == "ninguna":
            select.disabled = True
        
        # ⚡ Lógica de selección
        async def select_cb(interaction: discord.Interaction):
            if interaction.user.id != self.user_id: return
            seleccion = select.values[0]
            
            from Logica.servicio_habilidades import ServicioHabilidades
            exito, msg = ServicioHabilidades.ejecutar_habilidad_batalla(
                user_id=interaction.user.id,
                hab_id_elegida=seleccion, 
                view_batalla=self.vista_batalla
            )

            if not exito:
                return await interaction.response.send_message(msg, ephemeral=True)

            # Si tiene éxito, blindamos contra lag y ejecutamos el turno normal
            await interaction.response.defer()
            await self.vista_batalla.ejecutar_turno(interaction, "habilidad", msg_personalizado=msg)
            
        select.callback = select_cb
        self.add_item(select)
        
        # 🔙 Botón Volver (Restaura la pantalla de batalla normal sin gastar turno)
        btn_volver = discord.ui.Button(label="🔙 Cancelar Habilidad", style=discord.ButtonStyle.secondary, row=1)
        async def volver_cb(inter):
            if inter.user.id != self.user_id: return
            # Devolvemos la vista a la vista de batalla original
            await inter.response.edit_message(view=self.vista_batalla)
            
        btn_volver.callback = volver_cb
        self.add_item(btn_volver)

# ==========================================
# 🎁 SALA DE BENDICIONES (PISOS 5, 15, 25...)
# ==========================================
class TorreBendicionView(discord.ui.View):
    def __init__(self, user_id, piso, jugador, hp_max_anterior, energia_max_anterior, dificultad="Visitante"):
        super().__init__(timeout=None)
        self.dificultad = dificultad
        self.user_id = user_id
        self.piso = piso
        self.jugador = jugador
        self.hp_max_anterior = hp_max_anterior
        self.energia_max_anterior = energia_max_anterior

    async def procesar_eleccion(self, interaction, mensaje):
        from Data.database import update_piso_torre
        nuevo_piso = self.piso + 1
        update_piso_torre(self.user_id, nuevo_piso)

        embed = discord.Embed(
            title="✨ LOS DIOSES SONRÍEN",
            description=mensaje + f"\n\n⛩️ **El camino al Piso {nuevo_piso} se ha abierto.**",
            color=0xf1c40f
        )

        vista_transicion = discord.ui.View()
        boton_avanzar = discord.ui.Button(label=f"⚔️ Avanzar al Piso {nuevo_piso}", style=discord.ButtonStyle.danger)
        
        async def avanzar_cb(int_btn):
                if int_btn.user.id != self.user_id: return
                await int_btn.response.defer()
                
                
                from Data.database import get_player_data, get_mascota_equipada
                
                jugador_bd = get_player_data(self.user_id)
                jugador_real, tipo_arma, nivel_maestria = ServicioJugador.obtener_stats_reales(jugador_bd)
                
                # 2. Conservamos la energía del piso anterior
                energia_actual = getattr(self, 'energia', self.jugador.get('energia', 100))
                jugador_real['energia'] = energia_actual 
                
                # 3. Aplicamos los Buffs Divinos de la Torre
                mult_atk = jugador_real.get('torre_buff_atk', 1.0)
                mult_def = jugador_real.get('torre_buff_def', 1.0)
                jugador_real['ataque'] = int(jugador_real['ataque'] * mult_atk)
                jugador_real['defensa'] = int(jugador_real['defensa'] * mult_def)
                
                # ====================================================
                # --- EVENTO: SALA DE BENDICIÓN (Pisos 5, 15, 25...) ---
                # ====================================================
                if nuevo_piso % 10 == 5:
                    from Vistas.vistasBatalla import TorreBendicionView
                    embed_bendicion = discord.Embed(
                        title=f"🗼 TORRE DE BABEL - PISO {nuevo_piso}",
                        description="*Entras a una inmensa sala vacía iluminada por una luz tenue. No hay rastro de monstruos.*\n> 👁️ **Estás siendo observado por entidades superiores...**\n```Has demostrado valor, mortal. Elige una recompensa para continuar tu ascenso.```",
                        color=0xf1c40f
                    )
                    
                    hp_max = getattr(self, 'hp_max_jugador', getattr(self, 'hp_max_anterior', 100))
                    en_max = getattr(self, 'energia_max', getattr(self, 'energia_max_anterior', 100))
                    
                    await int_btn.edit_original_response(
                        embed=embed_bendicion, 
                        view=TorreBendicionView(self.user_id, nuevo_piso, jugador_real, hp_max, en_max, getattr(self, 'dificultad', 'Visitante')), 
                        attachments=[]
                    )
                    return

                # ----------------------------------------------------
                # LÓGICA DE SELECCIÓN DE MONSTRUO Y DIFICULTAD (Delegado al Servicio)
                # ----------------------------------------------------
                dif_actual = getattr(self, 'dificultad', 'Visitante')
                nombre_mostrar, stats_base = ServicioCombate.preparar_monstruo_torre(nuevo_piso, dif_actual)

                # ====================================================
                # --- CREAR Y LANZAR LA VISTA DE BATALLA ---
                # ====================================================
                mascota_db = get_mascota_equipada(self.user_id)
                mascota_dict = dict(mascota_db) if mascota_db else None
                
                from Vistas.vistasBatalla import BatallaView
                nueva_vista = BatallaView(
                    user_id=self.user_id,
                    jugador=jugador_real, 
                    nombre_mision=f"Torre de Babel - Piso {nuevo_piso}",
                    nombre_monstruo=nombre_mostrar,
                    stats_monstruo=stats_base,
                    agilidad=jugador_real['agilidad'], 
                    nivel_maestria=nivel_maestria,
                    tipo_arma_cache=tipo_arma,
                    dificultad=dif_actual,
                    mascota=mascota_dict
                )
                
                from Vistas.Embeds import embed_batalla
                embed_siguiente = embed_batalla(
                    nueva_vista.jugador, nueva_vista.nombre_monstruo, nueva_vista.stats, 
                    nueva_vista.hp_monstruo, nueva_vista.stats['img_idle'], 
                    f"⛩️ ¡Avanzas al PISO {nuevo_piso}!\n> Un **{nombre_mostrar}** bloquea tu camino.", 
                    nueva_vista.energia, nueva_vista.energia_max, mascota=nueva_vista.mascota
                )
                embed_siguiente.color = 0x5c0000 
                await int_btn.edit_original_response(content=f"🗼 ASCENSIÓN: PISO {nuevo_piso}", embed=embed_siguiente, view=nueva_vista, attachments=[])

        boton_avanzar.callback = avanzar_cb
        vista_transicion.add_item(boton_avanzar)
        
        boton_huir = discord.ui.Button(label="🏃 Huir a la Aldea", style=discord.ButtonStyle.secondary)
        async def huir_cb(int_btn):
            if int_btn.user.id != self.user_id: return
            
            
            from Data.database import get_mascota_equipada, update_mascota_hp
            mascota_db = get_mascota_equipada(self.user_id)
            if mascota_db:
                m = dict(mascota_db)
                update_mascota_hp(m['id'], m.get('hp_max', 100))
                
            from Vistas.vistas import AldeaView
            from Vistas.Embeds import embed_aldea
            await int_btn.response.edit_message(content=None, embed=embed_aldea(), view=AldeaView(self.user_id), attachments=[])
            
        boton_huir.callback = huir_cb
        vista_transicion.add_item(boton_huir)

        await interaction.response.edit_message(embed=embed, view=vista_transicion)

    # ===============================================
    # LOS BOTONES DE BENDICIÓN (AHORA TE CURAN AL 100%)
    # ===============================================

    @discord.ui.button(label="❤️ Vitalidad (+30% HP y Curación)", style=discord.ButtonStyle.success)
    async def vitalidad(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id: return
        try:
            import sqlite3
            from Data.database import DB_PATH
            
            # 1. Al elegir Vitalidad, el nuevo máximo se duplica.
            self.hp_max_anterior *= 1.3
            self.energia_max_anterior *= 1.2
            
            conn = sqlite3.connect(DB_PATH)
            c = conn.cursor()
            # 2. Guarda el multiplicador, y además te CURA a ese nuevo máximo
            c.execute("UPDATE jugadores SET torre_buff_hp = torre_buff_hp * 2.0, hp = ?, energia = ? WHERE id = ?", 
                      (self.hp_max_anterior, self.energia_max_anterior, str(self.user_id)))
            conn.commit()
            conn.close()
        except Exception as e: print(f"Error Vitalidad: {e}")
        await self.procesar_eleccion(interaction, "**❤️ Tu Vida Máxima se ha duplicado y has sido curado por completo.**")

    @discord.ui.button(label="⚔️ Poderío (+30% Atk/Def y Curación)", style=discord.ButtonStyle.danger)
    async def poderio(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id: return
        try:
            import sqlite3
            from Data.database import DB_PATH
            conn = sqlite3.connect(DB_PATH)
            c = conn.cursor()
            # Sube ataque, defensa y TE CURA al 100% del máximo actual
            c.execute("UPDATE jugadores SET torre_buff_atk = torre_buff_atk * 1.3, torre_buff_def = torre_buff_def * 1.3, hp = ?, energia = ? WHERE id = ?", 
                      (self.hp_max_anterior, self.energia_max_anterior, str(self.user_id)))
            conn.commit()
            conn.close()
        except Exception as e: print(f"Error Poderío: {e}")
        await self.procesar_eleccion(interaction, "**⚔️ Tu Ataque y Defensa aumentaron un 30% y has sido curado por completo.**")

    @discord.ui.button(label="🎁 Fortuna (Más Botín y Curación)", style=discord.ButtonStyle.primary)
    async def fortuna(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id: return
        try:
            import sqlite3
            from Data.database import DB_PATH
            conn = sqlite3.connect(DB_PATH)
            c = conn.cursor()
            # Da fortuna y TE CURA al 100% del máximo actual
            c.execute("UPDATE jugadores SET torre_buff_fortuna = 1, hp = ?, energia = ? WHERE id = ?", 
                      (self.hp_max_anterior, self.energia_max_anterior, str(self.user_id)))
            conn.commit()
            conn.close()
        except Exception as e: print(f"Error Fortuna: {e}")
        await self.procesar_eleccion(interaction, "**🎁 Has recibido la 'Fortuna de Babel' y has sido curado por completo.**")

# ==========================================
# 🪺 VISTA: EVENTO ALEATORIO DE NIDO
# ==========================================
class NidoEncontradoView(discord.ui.View):
    def __init__(self, user_id, nombre_monstruo):
        super().__init__(timeout=None)
        self.user_id = user_id
        self.nombre_monstruo = nombre_monstruo

    async def procesar_huevo(self, interaction: discord.Interaction, color_elegido, descripcion_resultado):
        from Data.database import anadir_huevo_db

        anadir_huevo_db(self.user_id, self.nombre_monstruo, rareza="Normal", color=color_elegido)

        embed_res = discord.Embed(
            title="🥚 ¡Huevo asegurado!",
            description=(
                f"Has tomado el **Huevo {color_elegido}** del nido de {self.nombre_monstruo}.\n\n"
                f"*{descripcion_resultado}*\n\n"
                f"> ⏳ **Atención:** Este huevo perderá su vitalidad y se echará a perder en exactamente **6 días**. ¡Incúbalo o encántalo pronto!"
            ),
            color=0x2ecc71
        )
        embed_res.set_thumbnail(url="https://i.imgur.com/IsfPvor.png") 
        
        vista_volver = discord.ui.View()
        boton_volver = discord.ui.Button(label="↩️ Volver a la Aldea", style=discord.ButtonStyle.success)
        
        async def volver_cb(int_btn):
            if int_btn.user.id != self.user_id: return
            from Vistas.vistas import AldeaView, embed_aldea
            await int_btn.response.edit_message(embed=embed_aldea(), view=AldeaView(self.user_id), attachments=[])
            
        boton_volver.callback = volver_cb
        vista_volver.add_item(boton_volver)
        
        await interaction.response.edit_message(embed=embed_res, view=vista_volver)

    @discord.ui.button(label="Huevo Rojo", emoji="🔴", style=discord.ButtonStyle.danger)
    async def huevo_rojo(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id: return
        await self.procesar_huevo(interaction, "Rojo", "Pesa muchísimo, ¡parece que la cría en su interior será muy fuerte y resistente!")

    @discord.ui.button(label="Huevo Verde", emoji="🟢", style=discord.ButtonStyle.success)
    async def huevo_verde(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id: return
        await self.procesar_huevo(interaction, "Verde", "El mal olor casi te hace vomitar al agarrarlo, pero lograste guardarlo a salvo en tu mochila.")

    @discord.ui.button(label="Huevo Azul", emoji="🔵", style=discord.ButtonStyle.primary)
    async def huevo_azul(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id: return
        await self.procesar_huevo(interaction, "Azul", "Sientes un latido muy cálido contra tu mano a través de las grietas de la cáscara.")
    
    
