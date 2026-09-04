# AGENTS.md — Agente de Apuestas Deportivas

## Descripción del Proyecto

Aplicación web y bot de Telegram que genera **recomendaciones de apuestas basadas en datos** para equipos de las principales ligas de fútbol de Europa, Latinoamérica y Centroamérica.

**Características principales:**
- 🌍 Catálogo de 21 ligas por 3 regiones (Europa, LatAm, Centroamérica)
- 📊 Estadísticas reales de equipos (posición, goles, forma, etc.)
- 🎯 Modelo predictivo Poisson para generar probabilidades de apuestas
- 🔄 Integración con API-Football para datos en tiempo real
- 🌐 Aplicación web responsive (accesible desde cualquier navegador)
- 🤖 Bot de Telegram (funcional, complementario a la web)
- ☁️ Desplegada en Render Free (24/7, gratis para siempre)

---

## Estado del Despliegue

- **URL:** https://agente-apuestas.onrender.com
- **Hosting:** Render Free ($0 para siempre)
- **GitHub:** https://github.com/davidhenao0422-commits/agente-apuestas
- **API Key:** aa60ccff49a0ae41375c0cb6246e317d
- **Fecha:** 2026-09-04
- **Estado:** ✅ En línea

---

## Arquitectura

```
┌─────────────────────────────────────────────────────────────────┐
│                      TELEGRAM BOT (Frontend)                    │
│  python-telegram-bot ── Maneja comandos, mensajes, callbacks    │
└───────────────┬─────────────────────────────┬───────────────────┘
                │                             │
                ▼                             ▼
┌───────────────────────┐     ┌───────────────────────────────────┐
│   PARSEADOR DE INPUT  │     │      FORMATEADOR DE SALIDA        │
│   Extrae equipos,     │     │   Genera tablas, emojis,          │
│   ligas, mercados     │     │   formatea para Telegram          │
└───────────┬───────────┘     └─────────────▲─────────────────────┘
            │                               │
            ▼                               │
┌───────────────────────────────────────────┴─────────────────────┐
│                     ORQUESTADOR (Core)                          │
│  Coordina: recolección → procesamiento → predicción → entrega  │
└──────┬──────────────────┬──────────────────────┬────────────────┘
       │                  │                      │
       ▼                  ▼                      ▼
┌──────────────┐  ┌──────────────────┐  ┌───────────────────────┐
│ RECOLECTOR   │  │ MOTOR DE ANÁLISIS│  │   ALMACÉN (Storage)   │
│ DE DATOS     │  │ ESTADÍSTICO      │  │                       │
│              │  │                  │  │  SQLite (local)       │
│ API-Football │  │ Poisson          │  │  - Historial equipos  │
│ Scraping     │  │ Regresión        │  │  - Partidos           │
│              │  │ H2H analysis     │  │  - Predicciones       │
│              │  │ Value betting    │  │  - Cache API          │
└──────────────┘  └──────────────────┘  └───────────────────────┘
```

### Flujo de Datos

```
1. USUARIO envía: "Real Madrid - La Liga, Barcelona - La Liga"
        │
        ▼
2. PARSEADOR extrae equipos y ligas
        │
        ▼
3. ORQUESTADOR inicia pipeline:
        ├──▶ RECOLECTOR obtiene datos desde API-Football (1 request/liga)
        ├──▶ ALMACÉN guarda en SQLite con cache 24h
        ├──▶ ANALIZADOR calcula stats, forma, H2H
        └──▶ PREDICTOR genera probabilidades y recomendaciones
        │
        ▼
4. FORMATEADOR crea mensaje con tablas y recomendaciones
        │
        ▼
5. BOT envía respuesta al USUARIO
```

---

## Estructura de Directorios

```
AGENTE DE APUESTAS DEPORTIVAS/
├── AGENTS.md                # Este archivo
├── ARCHITECTURE.md          # Documentación de arquitectura
├── README.md                # Instrucciones de uso y despliegue
├── config.py                # Configuración global (API keys, pesos)
├── catalog.py               # Catálogo de ligas y equipos por región
├── main.py                  # Punto de entrada del bot de Telegram
├── run.py                   # Punto de entrada de la app web
├── requirements.txt         # Dependencias Python
├── Dockerfile               # Para Railway/Oracle Cloud
├── Procfile                 # Para Render
├── render.yaml              # Configuración Render
├── .env                     # Variables de entorno (secretos)
├── .env.example             # Ejemplo de .env
├── .gitignore               # Archivos excluidos de git
│
├── bot/                     # Bot de Telegram
│   ├── handlers.py          # Manejadores de comandos
│   ├── formatters.py        # Formateo de mensajes
│   ├── keyboards.py         # Teclados interactivos
│   └── middleware.py        # Rate limiting, logging
│
├── web/                     # Aplicación web
│   ├── app.py               # Backend FastAPI (endpoints REST)
│   ├── stats_service.py     # Servicio de stats (real vs preseleccionado)
│   ├── preselected_data.py  # Stats preseleccionadas por equipo
│   └── static/              # Frontend (HTML/CSS/JS)
│       ├── index.html
│       ├── style.css
│       └── app.js
│
├── collectors/              # Clientes de APIs de datos
│   ├── api_football.py      # Cliente API-Football (principal)
│   ├── football_data.py     # Cliente football-data.org (secundario)
│   ├── cache.py             # Sistema de cache SQLite
│   └── scraper.py           # Web scraping (fallback)
│
├── analyzers/               # Motor de análisis estadístico
│   ├── stats.py             # Estadísticas básicas
│   ├── h2h.py               # Análisis de enfrentamientos directos
│   ├── poisson.py           # Modelo de Poisson
│   ├── form.py              # Análisis de forma reciente
│   └── value_betting.py     # Detección de valor en cuotas
│
├── predictors/              # Motor de predicción
│   ├── engine.py            # Motor principal de predicción
│   ├── probabilities.py     # Cálculo de probabilidades
│   └── recommendations.py   # Generación de recomendaciones
│
├── storage/                 # Persistencia
│   ├── database.py          # Conexión SQLite
│   ├── models.py            # Modelos de datos
│   └── migrations.py        # Migraciones
│
├── deploy/                  # Scripts de despliegue
│   └── oracle-cloud/
│       ├── setup.sh         # Script de instalación
│       └── README.md        # Instrucciones Oracle Cloud
│
└── tests/                   # Tests unitarios
    ├── test_poisson.py
    ├── test_h2h.py
    ├── test_value_betting.py
    ├── test_predictors.py
    └── test_stats_service.py
```

---

## APIs y Datos

### API-Football (Principal)
- **URL base:** `https://v3.football.api-sports.io`
- **Plan gratuito:** 100 requests/día, 10 requests/minuto
- **Endpoints usados:**
  - `/standings?league={id}&season={year}` — Tabla de posiciones (1 request por liga)
  - `/teams?search={name}` — Búsqueda de equipos
  - `/teams?season=&team=&league=` — Stats detalladas por equipo
  - `/fixtures/headtohead` — Enfrentamientos directos
- **Temporadas accesibles (plan free):** 2022-2024

### Football-data.org (Secundario)
- **URL base:** `https://api.football-data.org/v4`
- **Plan gratuito:** 10 requests/minuto
- **Ligas cubiertas:** La Liga, Premier, Serie A, Bundesliga, Ligue 1, CL

---

## Modelo Predictivo

### Modelo de Poisson
Calcula la probabilidad de marcadores exactos usando:
```
P(goles = k) = (λ^k × e^-λ) / k!
```
Donde λ = goles esperados del equipo.

### Ponderación de Factores
| Factor | Peso | Fuente |
|---|---|---|
| Forma reciente (10 partidos) | 40% | API + scraping |
| Enfrentamientos directos | 30% | API + DB |
| Estadísticas de temporada | 20% | API |
| Factor local/visitante | 10% | DB |

### Mercados Analizados
- **1X2** — Resultado final (Local/Empate/Visitante)
- **Over/Under 2.5** — Goles totales
- **BTTS** — Ambos equipos anotan
- **Clean Sheet** — Portería a cero

### Value Betting
```
Valor = (Probabilidad_calculada × Cuota) - 1
Si Valor > 0 → Apuesta con valor detectada
```

---

## Endpoints API (App Web)

| Método | Ruta | Descripción |
|---|---|---|
| GET | `/` | Frontend |
| GET | `/api/regiones` | Regiones disponibles |
| GET | `/api/ligas/{region}` | Ligas de una región |
| GET | `/api/equipos/{liga}` | Equipos y stats de una liga |
| GET | `/api/recomendaciones/{liga}/{equipo}` | Recomendaciones de un equipo |
| GET | `/api/equipo/{liga}/{equipo}` | Stats de un equipo |
| POST | `/api/actualizar/{liga}` | Actualizar datos desde API-Football |

---

## Catálogo de Ligas

### Europa
| Liga | Código | API ID | Equipos |
|---|---|---|---|
| La Liga (España) | PD | 140 | 20 |
| Premier League (Inglaterra) | PL | 39 | 20 |
| Serie A (Italia) | SA | 135 | 20 |
| Bundesliga (Alemania) | BL1 | 78 | 18 |
| Ligue 1 (Francia) | FL1 | 61 | 18 |
| Primeira Liga (Portugal) | PPL | 94 | 15 |
| Eredivisie (Países Bajos) | ERE | 88 | 19 |
| Champions League | CL | 2 | 10 |

### Latinoamérica
| Liga | Código | API ID | Equipos |
|---|---|---|---|
| Liga Profesional (Argentina) | ARG | 128 | 16 |
| Brasileirão (Brasil) | BRA | 71 | 16 |
| Liga MX (México) | MEX | 262 | 16 |
| Liga BetPlay (Colombia) | COL | 239 | 14 |
| Liga 1 (Perú) | PER | 301 | 12 |

### Centroamérica
| Liga | Código | API ID | Equipos |
|---|---|---|---|
| Liga Nacional (Honduras) | HON | 332 | 10 |
| Liga Nacional (Guatemala) | GUA | 333 | 10 |
| Primera División (Costa Rica) | CRC | 329 | 11 |
| Liga Panameña | PAN | 331 | 11 |

---

## Base de Datos (SQLite)

### Tablas

```sql
-- Equipos registrados
CREATE TABLE teams (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    league TEXT NOT NULL,
    api_id INTEGER,
    created_at TEXT DEFAULT (datetime('now')),
    UNIQUE(name, league)
);

-- Stats de temporada
CREATE TABLE team_stats (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    team_id INTEGER REFERENCES teams(id),
    season TEXT NOT NULL,
    league TEXT,
    position INTEGER,
    played INTEGER DEFAULT 0,
    won INTEGER DEFAULT 0,
    drawn INTEGER DEFAULT 0,
    lost INTEGER DEFAULT 0,
    goals_for INTEGER DEFAULT 0,
    goals_against INTEGER DEFAULT 0,
    shots_on_target INTEGER DEFAULT 0,
    corners INTEGER DEFAULT 0,
    possession_avg REAL DEFAULT 0,
    home_won INTEGER DEFAULT 0,
    home_drawn INTEGER DEFAULT 0,
    home_lost INTEGER DEFAULT 0,
    home_goals_for INTEGER DEFAULT 0,
    home_goals_against INTEGER DEFAULT 0,
    away_won INTEGER DEFAULT 0,
    away_drawn INTEGER DEFAULT 0,
    away_lost INTEGER DEFAULT 0,
    away_goals_for INTEGER DEFAULT 0,
    away_goals_against INTEGER DEFAULT 0,
    UNIQUE(team_id, season)
);

-- Cache de API
CREATE TABLE api_cache (
    cache_key TEXT PRIMARY KEY,
    data TEXT,
    fetched_at TEXT DEFAULT (datetime('now')),
    expires_at TEXT
);

-- Predicciones generadas
CREATE TABLE predictions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    match_description TEXT,
    recommendations TEXT,
    confidence TEXT,
    probabilities TEXT,
    expected_goals REAL,
    reasoning TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);
```

---

## Tecnologías

| Componente | Tecnología | Versión |
|---|---|---|
| Lenguaje | Python | 3.11+ |
| Bot Telegram | python-telegram-bot | 21.6+ |
| API web | FastAPI | 0.141+ |
| Servidor ASGI | Uvicorn | 0.34+ |
| Datos API | requests | 2.32+ |
| Análisis | pandas | 2.2+ |
| Numérico | numpy | 1.26+ |
| Estadística | scipy | 1.14+ |
| Almacenamiento | SQLite | built-in |
| Scraping | BeautifulSoup4 | 4.12+ |
| Tests | pytest | 8.3+ |

---

## Variables de Entorno (.env)

```bash
# Telegram Bot
TELEGRAM_BOT_TOKEN=

# API-Football
API_FOOTBALL_KEY=aa60ccff49a0ae41375c0cb6246e317d
API_FOOTBALL_BASE_URL=https://v3.football.api-sports.io

# Football-data.org (opcional)
FOOTBALL_DATA_KEY=

# Configuración
BOT_LANGUAGE=es
DEFAULT_MARKETS=1X2,BTS,OVER_UNDER
DEFAULT_TIMEZONE=Europe/Madrid

# Database
DB_PATH=betting_agent.db
```

---

## Despliegue

### Render Free (Recomendado)
- **Costo:** $0 para siempre
- **Limitación:** Se duerme tras 15 min de inactividad (despierta en 30s)
- **Sin tarjeta de crédito**
- Ver `render.yaml` y `Procfile`

### Local
```bash
pip install -r requirements.txt
python run.py
# Abrir http://localhost:8000
```

### Otras opciones (requieren tarjeta)
- Fly.io Free: 30 días de prueba
- Oracle Cloud Always Free: Requiere tarjeta de crédito

---

## Comandos Útiles

```bash
# Ejecutar app web
python run.py

# Ejecutar bot de Telegram
python main.py

# Ejecutar tests
python -m pytest tests/ -v

# Verificar compilación
python -m compileall -q web catalog collectors analyzers predictors bot storage

# Actualizar código (después de cambios)
git add -A
git commit -m "Tu mensaje"
git push origin main
```

---

## Historial de Desarrollo

### Fase 1: Fundamentos
- Estructura de directorios
- Configuración global
- Modelos de datos
- Base de datos SQLite
- requirements.txt

### Fase 2: Recolector de Datos
- Cliente API-Football con cache y rate limiting
- Cliente football-data.org
- Web scraping fallback (FBref, Transfermarkt)
- Sistema de cache SQLite con TTL

### Fase 3: Motor de Análisis
- Estadísticas básicas
- Análisis H2H
- Modelo de Poisson
- Análisis de forma reciente
- Detección de value betting

### Fase 4: Predictor
- Motor principal de predicción
- Cálculo de probabilidades
- Generación de recomendaciones

### Fase 5: Bot de Telegram
- Handlers de comandos
- Formateo de mensajes
- Teclados interactivos
- Middleware (rate limit, logging)

### Fase 6: App Web
- Backend FastAPI con endpoints REST
- Frontend HTML/CSS/JS responsive
- Integración API-Football real (standings-based)
- Stats service (real vs preseleccionado)

### Fase 7: Despliegue
- Oracle Cloud Always Free
- Script setup.sh automatizado
- Instrucciones paso a paso

### Bugs Corregidos
- API-Football no permite `league` + `search` juntos
- Goles en `row.all.goals` no en `row.goals`
- Rate limit de 10/min no estaba controlado
- Temporada 2025 no accesible en plan free (usar 2024)
- Nombres de equipos con acentos (normalización Unicode)

---

## Avisos Legales

Las recomendaciones son de naturaleza **estadística** y **no garantizan resultados**. Las apuestas deportivas implican riesgo económico. Juega responsablemente.

---

*Documento generado el 2026-09-04. Última actualización: despliegue Fly.io (gratuito, sin tarjeta de crédito).*
