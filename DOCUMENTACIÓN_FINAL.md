================================================================================
  AGENTE DE APUESTAS DEPORTIVAS — DOCUMENTACIÓN FINAL
================================================================================

PROYECTO: Agente de Apuestas Deportivas
FECHA DE CREACIÓN: 2026-09-04
CREADOR: davidhenao0422

================================================================================
  INFORMACIÓN DEL REPO
================================================================================

GitHub: https://github.com/davidhenao0422/agente-apuestas
Branch: main
Estado: ✅ Código listo (por hacer push)

================================================================================
  CARACTERÍSTICAS PRINCIPALES
================================================================================

✓ 21 ligas por 3 regiones (Europa, LatAm, Centroamérica)
✓ Estadísticas reales de equipos desde API-Football
✓ Modelo predictivo Poisson para probabilidades
✓ Integración con API-Football (100 requests/día, 10/minuto)
✓ Aplicación web responsive
✓ Bot de Telegram
✓ 25/25 tests pasando
✓ 100% gratis con Render Free

================================================================================
  ARCHIVOS PRINCIPALES
================================================================================

CONFIGURACIÓN:
├── .env                     # API keys (no subir a git)
├── .env.example             # Ejemplo de variables
├── config.py                # Configuración global
├── catalog.py               # Catálogo de ligas y equipos
├── requirements.txt         # Dependencias Python

ENTRADA:
├── main.py                  # Bot de Telegram
├── run.py                   # Servidor web
└── AGENTS.md                # Documentación completa

DOCUMETACIÓN:
├── README.md                # Instrucciones de uso
├── ARCHITECTURE.md          # Arquitectura del sistema
├── DEPLOYMENT.md            # Guía de despliegue
├── GUÍA_FINAL.md            # Documentación final

Tecnologías: Python 3.11+, FastAPI, Uvicorn, SQLite, pandas, numpy, scipy

================================================================================
  COMANDOS ÚTILES
================================================================================

# Instalar
pip install -r requirements.txt

# Ejecutar local
python run.py

# Ejecutar tests
python -m pytest tests/ -v

# Verificar compilación
python -m compileall -q web catalog collectors analyzers predictors bot storage

# Actualizar código (después de push)
git add -A
git commit -m "Tu mensaje"
git push origin main

================================================================================
  PASSOS PARA DESPLIEGUE (Render)
================================================================================

1. Subir código a GitHub:
   git push -u origin main

2. Crear cuenta en Render (https://render.com) - sin tarjeta

3. New → Web Service → Connect to Git
   - Repository: davidhenao0422/agente-apuestas
   - Build: pip install -r requirements.txt
   - Start: uvicorn web.app:app --host 0.0.0.0 --port $PORT

4. Environment → Add Secret:
   API_FOOTBALL_KEY=aa60ccff49a0ae41375c0cb6246e317d

5. Create Web Service → Esperar 2-3 min → ¡Listo!

URL final: https://agente-apuestas.onrender.com

================================================================================
  API-FOOTBALL CONFIGURATION
================================================================================

API_KEY: aa60ccff49a0ae41375c0cb6246e317d
BASE_URL: https://v3.football.api-sports.io

LÍMITES:
- 100 requests/día
- 10 requests/minuto
- Temporadas: 2022-2024

OPTIMIZACIÓN:
- 1 request por liga (no por equipo)
- Cache de 24 horas
- ~20 requests para actualizar 21 ligas

================================================================================
  COSTO TOTAL
================================================================================

- Hosting (Render Free): $0 para siempre
- API-Football (plan free): $0
- Dominio (opcional): gratis con subdominio .onrender.com
- TOTAL: $0

================================================================================
  PRÓXIMOS PASOS
================================================================================

1. Ejecutar: git push -u origin main
2. Crear cuenta en Render.com
3. Configurar Web Service con tu repo
4. Añadir API_FOOTBALL_KEY en Environment
5. Deploy y ¡listo!

================================================================================
  CONTACTO Y SOPORTE
================================================================================

- API-Football docs: https://www.api-football.com/documentation-v3
- Render docs: https://render.com/docs
- FastAPI docs: https://fastapi.tiangolo.com

================================================================================
*Documento generado el 2026-09-04*
*Despliegue: Render Free (gratuito para siempre)*
================================================================================
