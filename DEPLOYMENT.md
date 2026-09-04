# DEPLOYMENT.md — Guía de Despliegue Completa

## ✅ Estado del Proyecto

**Nombre del repo:** `agente-apuestas`  
**Repositorio:** https://github.com/davidhenao0422/agente-apuestas  
**Estado:** Código subido a GitHub (branch: main)

---

## 🚀 Opción de Despliegue Recomendada: Render Free

### Por qué Render Free:
- ✅ **$0 para siempre** (no es una prueba de 30 días)
- ✅ **Sin tarjeta de crédito**
- ✅ **No requiere instalación de CLI**
- ✅ **Integración directa con GitHub**
- ❌ Se duerme tras 15 min de inactividad (despierta en 30s)

### Pasos para desplegar en Render (5 minutos):

#### Paso 1: Crear cuenta en Render
1. Ve a [https://render.com](https://render.com)
2. Clic en **"Sign Up"**
3. Usa email o GitHub
4. **NO pide tarjeta de crédito**

#### Paso 2: Crear Web Service
1. En el dashboard, clic **"New +"** → **"Web Service"**
2. Selecciona **"Connect to Git repository"**
3. Elige tu repo: `davidhenao0422/agente-apuestas`
4. Clic **"Connect"**

#### Paso 3: Configurar la app
Rellena los campos:

| Campo | Valor |
|---|---|
| **Name** | `agente-apuestas` |
| **Region** | `Frankfurt (EU)` o `Ohio (US)` |
| **Branch** | `main` |
| **Root Directory** | (dejar vacío) |
| **Runtime** | `Python 3` |
| **Build Command** | `pip install -r requirements.txt` |
| **Start Command** | `uvicorn web.app:app --host 0.0.0.0 --port $PORT` |

#### Paso 4: Variables de entorno
Clic en **"Environment"** tab → **"Add Secret"**:

| Clave | Valor |
|---|---|
| `API_FOOTBALL_KEY` | `aa60ccff49a0ae41375c0cb6246e317d` |

#### Paso 5: Deploy
1. Clic en **"Create Web Service"**
2. Espera 2-3 minutos mientras Render builda
3. ¡Listo! Tu app estará en `https://agente-apuestas.onrender.com`

---

## 📋 Comandos Útiles después del despliegue

```bash
# Ver logs
# En Render: Dashboard → Your Service → Logs

# Reiniciar
# En Render: Dashboard → Your Service → Manual Deploy → Deploy latest commit

# Actualizar código (después de cambios locales)
git add -A
git commit -m "Tu mensaje"
git push origin main
# Render auto-deployará en 1-2 min
```

---

## 🔧 Configuración Local (Para desarrollo)

### Instalar dependencias
```bash
pip install -r requirements.txt
```

### Configurar variables
Crea un archivo `.env` en la carpeta del proyecto:

```
API_FOOTBALL_KEY=aa60ccff49a0ae41375c0cb6246e317d
```

### Ejecutar
```bash
python run.py
```

### Acceder
- **Web:** http://localhost:8000
- **API:** http://localhost:8000/api/regiones

---

## 🌐 Estructura de la Aplicación

### Backend (FastAPI)
```
web/app.py
├── GET /                    # Frontend
├── GET /api/regiones        # Regiones disponibles
├── GET /api/ligas/{region}  # Ligas por región
├── GET /api/equipos/{liga}  # Equipos y stats
├── GET /api/recomendaciones/{liga}/{equipo}
├── GET /api/equipo/{liga}/{equipo}
└── POST /api/actualizar/{liga}
```

### Catálogo de Ligas
- **Europa:** La Liga, Premier, Serie A, Bundesliga, Ligue 1, Primeira Liga, Eredivisie, Champions
- **Latinoamérica:** Argentina, Brasil, México, Colombia, Perú
- **Centroamérica:** Honduras, Guatemala, Costa Rica, Panamá

### Estadísticas en tiempo real
- 1 request por liga (no por equipo)
- Cache de 24 horas
- Límite: 100 requests/día, 10 requests/minuto

---

## 🎯 Prueba del Funcionamiento

### Verificar API local
```bash
# Regiones
curl http://localhost:8000/api/regiones

# Equipos de La Liga
curl http://localhost:8000/api/equipos/PD

# Recomendaciones
curl http://localhost:8000/api/recomendaciones/PD/Real%20Madrid
```

### Verificar actualización con API-Football
```bash
# Actualizar La Liga (1 request)
curl -X POST http://localhost:8000/api/actualizar/PD
```

---

## 📊 Arquitectura Técnica

```
Frontend (HTML/CSS/JS)
    ↓
Backend (FastAPI + Uvicorn)
    ↓
├── Catálogo de ligas (catalog.py)
├── Preselección de stats (web/preselected_data.py)
├── Servicio de stats (web/stats_service.py)
├── Motor de análisis (analyzers/)
│   ├── stats.py, h2h.py, poisson.py
│   ├── value_betting.py
├── Motor de predicción (predictors/)
│   ├── engine.py, probabilities.py
└── Almacén (SQLite)
```

---

## 🔐 Seguridad

- `.env` → Excluido de Git (contiene API keys)
- `.gitignore` → Excluye DB, cache, Python files
- API-Football key → No se comparte públicamente

---

## 🆘 Solución de Problemas

### Render no arranca
- Verificar `Start Command` en configuración
- Verificar `API_FOOTBALL_KEY` en Environment
- Revisar logs en Render dashboard

### Local no funciona
- Verificar Python 3.11+
- Verificar `pip install -r requirements.txt`
- Verificar `.env` con API key

### API-Football limitada
- Usar cache (24h)
- 1 request por liga (no por equipo)
- Si se pasa el límite, esperar 24h o usar stats preseleccionadas

---

## 📞 Contacto y Soporte

- **API-Football docs:** https://www.api-football.com/documentation-v3
- **Render docs:** https://render.com/docs
- **FastAPI docs:** https://fastapi.tiangolo.com

---

*Última actualización: 2026-09-04*  
*Proyecto: Agente de Apuestas Deportivas*  
*Despliegue: Render Free (gratuito para siempre)*
