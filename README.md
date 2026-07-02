# Ring-Explorer---Backend-Engine
Este repositorio contiene el motor central de Ring Explorer, un ecosistema de juego desarrollado para Discord.
Tecnologías:
Python

SQLite (Gestión de persistencia optimizada con modo WAL)

Discord.py API

Arquitectura:
El proyecto sigue un patrón MVC (Modelo-Vista-Controlador) para garantizar la escalabilidad:

Database: Gestor de persistencia con optimizaciones para concurrencia.

Logic (Servicios): Lógica centralizada de combate y economía, separada de la capa visual.

Vistas: Interfaz interactiva basada en componentes de Discord.

Puntos clave de ingeniería:
Gestión de estados asíncronos y persistentes.

Cálculos matemáticos de progresión (Daño, Maestría, Niveles).

Manejo de concurrencia y prevención de bloqueos de base de datos.
