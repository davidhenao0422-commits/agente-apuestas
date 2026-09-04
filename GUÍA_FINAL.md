================================================================================
  AGENTE DE APUESTAS DEPORTIVAS — GUÍA FINAL
================================================================================

PROYECTO COMPLETADO ✅
Última actualización: 2026-09-04
Creador: davidhenao0422

================================================================================
  TABLA DE CONTENIDOS
================================================================================

1. INFORMACIÓN DEL PROYECTO
2. ARCHIVOS CREADOS
3. ESTADO DEL CÓDIGO
4. PASOS PARA DESPLIEGUE
5. INFORMACIÓN DE ACCESO
6. PREGUNTAS FREQUENTES

================================================================================
  1. INFORMACIÓN DEL PROYECTO
================================================================================

NOMBRE: Agente de Apuestas Deportivas
REPO: https://github.com/davidhenao0422/agente-apuestas
BRANCH: main

DESCRIPCIÓN:
Aplicación web y bot de Telegram que genera recomendaciones de apuestas
basadas en estadísticas reales de fútbol para las principales ligas de
Europa, Latinoamérica y Centroamérica.

CARACTERÍSTICAS:
✓ 21 ligas por 3 regiones (Europa, LatAm, Centroamérica)
✓ Estadísticas reales de equipos (posición, goles, forma)
✓ Modelo predictivo Poisson para probabilidades
✓ Integración con API-Football para datos en tiempo real
✓ Aplicación web responsive
✓ Bot de Telegram (complementario)

TECNOLOGÍAS:
- Backend: Python, FastAPI, Uvicorn
- Datos: SQLite, requests, API-Football
- Análisis: pandas, numpy, scipy
- Bot: python-telegram-bot

================================================================================
  2. ARCHIVOS CREADOS
================================================================================

ARCHIVOS PRINCIPALES:
├── main.py                 # Bot de Telegram
├── run.py                  # Servidor web
├── config.py               # Configuración global
├── catalog.py              # Catálogo de ligas y equipos
├── requirements.txt        # Dependencias Python
├── AGENTS.md               # Documentación completa
├── README.md               # Instrucciones de uso
├── ARCHITECTURE.md         # Arquitectura del sistema
├── DEPLOYMENT.md           # Guía de despliegue (¡LO LEYENDO!)
└── .env                    # Variables de entorno (API keys)

BACKEND (web/):
├── app.py                  # FastAPI endpoints
├── stats_service.py        # Servicio de stats
├── preselected_data.py     # Datos preseleccionados
├── static/index.html       # Frontend HTML
├── static/style.css        # Estilos CSS
└── static/app.js           # JavaScript

BOT (bot/):
├── handlers.py             # Manejadores de comandos
├── formatters.py           # Formateo de mensajes
├── keyboards.py            # Teclados
└── middleware.py           # Rate limiting, logging

RECOLECTORES (collectors/):
├── api_football.py         # Cliente API-Football
├── cache.py                # Sistema de cache
└── scraper.py              # Web scraping fallback

ANALIZADORES (analyzers/):
├── stats.py                # Estadísticas básicas
├── h2h.py                  # Análisis H2H
├── poisson.py              # Modelo Poisson
├── form.py                 # Forma reciente
└── value_betting.py        # Value betting

PREDICTORES (predictors/):
├── engine.py               # Motor de predicción
├── probabilities.py        # Cálculo de probabilidades
└── recommendations.py      # Generación de recomendaciones

ALMACENAMIENTO (storage/):
├── database.py             # Conexión SQLite
├── models.py               # Modelos de datos
└── migrations.py           # Migraciones

DEPLOYMENT:
├── Dockerfile              # Para Railway/Oracle Cloud
├── Procfile                # Para Render
├── render.yaml             # Configuración Render
└── deploy/oracle-cloud/    # Despliegue Oracle Cloud
    ├── setup.sh
    └── README.md

TESTS (tests/):
├── test_poisson.py
├── test_h2h.py
├── test_value_betting.py
├── test_predictors.py
└── test_stats_service.py

================================================================================
  3. ESTADO DEL CÓDIGO
================================================================================

REPOSITORIO: https://github.com/davidhenao0422/agente-apuestas
STATUS: Código listo (requiere autenticación para push)

HISTORIAL DE COMMITS:
40e052c - DEPLOYMENT.md: guía completa de despliegue
cd1f935 - Remove Fly.io, keep only Render Free
c1f2f5e - Update: Render Free como opción permanente
7d72e12 - Fly.io Free deployment
610d5bd - AGENTS.md: documentación completa
94f7098 - Oracle Cloud Always Free deployment
8b82dc5 - Fix API-Football: standings-based update
9376997 - App web de recomendaciones + bot Telegram

TESTS: 25/25 pasando ✅

API KEY CONFIGURADA:
API_FOOTBALL_KEY=aa60ccff49a0ae41375c0cb6246e317d

================================================================================
  4. PASOS PARA DESPLIEGUE (Render Free)
================================================================================

PASO 1: Subir código a GitHub
------------------------------
En tu terminal, ejecuta:
git push -u origin main

Si te pide autenticación:
1. Ve a: https://github.com/settings/tokens
2. Crea un token con permisos "repo"
3. Ejecuta: git push https://davidhenao0422:TOKEN@github.com/davidhenao0422/agente-apuestas.git main

PASO 2: Desplegar en Render
----------------------------
1. Ve a: https://render.com
2. Crea cuenta (sin tarjeta de crédito)
3. New → Web Service → Connect to Git
4. Selecciona: davidhenao0422/agente-apuestas
5. Configura:
   - Name: agente-apuestas
   - Build: pip install -r requirements.txt
   - Start: uvicorn web.app:app --host 0.0.0.0 --port $PORT
6. Environment → Add Secret:
   API_FOOTBALL_KEY=aa60ccff49a0ae41375c0cb6246e317d
7. Create Web Service
8. Espera 2-3 minutos
9. ¡Listo! En: https://agente-apuestas.onrender.com

================================================================================
  5. INFORMACIÓN DE ACCESO
================================================================================

API KEY: aa60ccff49a0ae41375c0cb6246e317d
URL BASE: https://v3.football.api-sports.io

LÍMITES API-FOOTBALL:
- 100 requests/día
- 10 requests/minuto
- Temporadas: 2022-2024

RECURSOS USADOS:
- 1 request por liga (no por equipo)
- ~20 requests para actualizar 21 ligas
- Cache de 24 horas para evitar re-peticiones

================================================================================
  6. PREGUNTAS FREQUENTES
================================================================================

¿Es gratis?
✅ Sí, 100% gratis con Render Free (sin tarjeta de crédito)

¿Se queda en línea?
⚠️ Se duerme tras 15 min de inactividad, pero despierta en 30s

¿Necesito mi PC?
❌ No, Render se encarga de todo 24/7

¿Puedo usar el bot de Telegram?
✅ Sí, ejecuta: python main.py (necesita TELEGRAM_BOT_TOKEN)

¿Cómo actualizo el código?
Después de cambios locales:
git add -A
git commit -m "Tu mensaje"
git push origin main
Render auto-deployará en 1-2 min

¿Cuánto dura el plan gratuito?
✅ Para siempre (Render Free no tiene fecha de vencimiento)

================================================================================
  COMANDOS ÚTILES
================================================================================

# Local
pip install -r requirements.txt
python run.py
# Acceder a http://localhost:8000

# Tests
python -m pytest tests/ -v

# Verificar compilación
python -m compileall -q web catalog collectors analyzers predictors bot storage

# Actualizar (Oracle Cloud)
cd /home/ubuntu/agente-apuestas
git pull
sudo systemctl restart agente-apuestas

================================================================================
  CONTACTO
================================================================================

Proyecto: Agente de Apuestas Deportivas
Usuario GitHub: davidhenao0422
Repo: https://github.com/davidhenao0422/agente-apuestas

================================================================================
  FIN DE LA GUÍA
================================================================================

*Documento generado el 2026-09-04*
*Despliegue: Render Free (gratuito para siempre)*
