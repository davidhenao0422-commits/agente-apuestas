# Arquitectura del Agente de Apuestas Deportivas

## Visión General

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
│ football-    │  │ Regresión        │  │  - Partidos           │
│ data.org     │  │ H2H analysis     │  │  - Predicciones       │
│ Scraping     │  │ Value betting    │  │  - Cache API          │
└──────────────┘  └──────────────────┘  └───────────────────────┘
```

## Estructura de Directorios

```
AGENTE DE APUESTAS DEPORTIVAS/
├── ARCHITECTURE.md           # Este archivo
├── requirements.txt          # Dependencias Python
├── .env                      # Variables de entorno (API keys, tokens)
├── .env.example              # Ejemplo de .env
├── config.py                 # Configuración global
├── main.py                   # Punto de entrada del bot
│
├── bot/
│   ├── __init__.py
│   ├── handlers.py           # Manejadores de comandos Telegram
│   ├── keyboards.py          # Teclados inline y reply
│   ├── formatters.py         # Formateo de mensajes para Telegram
│   └── middleware.py         # Rate limiting, logging, auth
│
├── collectors/
│   ├── __init__.py
│   ├── api_football.py       # Cliente API-Football
│   ├── football_data.py      # Cliente football-data.org
│   ├── scraper.py            # Web scraping (FBref, Transfermarkt)
│   └── cache.py              # Cache de respuestas API (Redis/SQLite)
│
├── analyzers/
│   ├── __init__.py
│   ├── stats.py              # Estadísticas básicas (goles, posesión, etc.)
│   ├── h2h.py                # Análisis de enfrentamientos directos
│   ├── poisson.py            # Modelo de Poisson para goles esperados
│   ├── value_betting.py      # Detección de valor en cuotas
│   └── form.py               # Análisis de forma reciente
│
├── predictors/
│   ├── __init__.py
│   ├── engine.py             # Motor principal de predicción
│   ├── probabilities.py      # Cálculo de probabilidades por mercado
│   └── recommendations.py    # Generación de recomendaciones finales
│
├── storage/
│   ├── __init__.py
│   ├── database.py           # Conexión y operaciones SQLite
│   ├── models.py             # Modelos de datos (dataclasses)
│   └── migrations.py         # Migraciones de esquema
│
└── tests/
    ├── __init__.py
    ├── test_poisson.py
    ├── test_h2h.py
    ├── test_formatters.py
    └── fixtures/              # Datos de prueba
        └── sample_data.json
```

## Flujo de Datos

```
1. USUARIO envía: "Real Madrid - La Liga, Barcelona - La Liga"
        │
        ▼
2. PARSEADOR extrae:
   - equipos: [{"name": "Real Madrid", "league": "La Liga"},
              {"name": "Barcelona", "league": "La Liga"}]
   - mercados: ["1X2", "Over/Under", "BTTS"] (default)
        │
        ▼
3. ORQUESTADOR inicia pipeline:
        │
        ├──▶ 3a. RECOLECTOR obtiene datos:
        │    ├── Stats temporada actual (API-Football)
        │    ├── Stats últimas 5 temporadas (cache/DB)
        │    ├── Head-to-head últimos 10 partidos
        │    └── Cuotas actuales del mercado (opcional)
        │
        ├──▶ 3b. ALMACÉN guarda/actualiza datos:
        │    ├── Tabla: teams (id, name, league, created_at)
        │    ├── Tabla: matches (id, home, away, date, stats...)
        │    ├── Tabla: h2h (team_a, team_b, results...)
        │    └── Tabla: predictions (id, match, recommendation...)
        │
        ├──▶ 3c. ANALIZADOR procesa:
        │    ├── Calcula promedios de temporada
        │    ├── Analiza forma últimos 10 partidos
        │    ├── Procesa H2H
        │    └── Ejecuta modelo Poisson
        │
        └──▶ 3d. PREDICTOR genera:
             ├── Probabilidades por mercado
             ├── Detección de value betting (si hay cuotas)
             ├── Nivel de confianza
             └── Recomendación final
        │
        ▼
4. FORMATEADOR crea mensaje Telegram con:
   - Tabla comparativa de estadísticas
   - Probabilidades y goles esperados
   - Recomendaciones priorizadas por confianza
   - Razonamiento en 2-3 oraciones
        │
        ▼
5. BOT envía mensaje al USUARIO
```

## Componentes Clave

### 1. Recolector de Datos (`collectors/`)

**API-Football** (principal):
- 100 requests/día (plan gratuito)
- Datos: fixtures, estadísticas de partidos, standings
- Rate limit: manejar con cola y retry

**Football-data.org** (secundario):
- 10 requests/minuto (plan gratuito)
- Datos: clasificaciones, resultados históricos

**Web Scraping** (fallback):
- FBref: estadísticas avanzadas (xG, shots, corners)
- Transfermarkt: values, injuries
- Solo como respaldo cuando APIs no tienen datos

**Cache**:
- SQLite con TTL de 24 horas para datos de partidos
- Reducir llamadas a API innecesarias

### 2. Motor de Análisis (`analyzers/`)

**Poisson**:
```
λ (goles esperados) = promedio_goles_favor × promedio_goles_contra_rival
P(goles = k) = (λ^k × e^-λ) / k!
```

**Ponderación de factores**:
| Factor | Peso | Fuente |
|---|---|---|
| Forma reciente (10 partidos) | 40% | API + scraping |
| Enfrentamientos directos | 30% | API + DB |
| Estadísticas de temporada | 20% | API |
| Factor local/visitante | 10% | DB |

**Value Betting**:
```
Valor = (Probabilidad_calculada × Cuota) - 1
Si Valor > 0 → Apuesta con valor detectada
```

### 3. Almacén (`storage/`)

**SQLite** (sin dependencias externas):

```sql
-- Equipos registrados
CREATE TABLE teams (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    league TEXT NOT NULL,
    api_id INTEGER,  -- ID en API-Football
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Partidos históricos
CREATE TABLE matches (
    id INTEGER PRIMARY KEY,
    home_team_id INTEGER REFERENCES teams(id),
    away_team_id INTEGER REFERENCES teams(id),
    match_date DATE,
    home_goals INTEGER,
    away_goals INTEGER,
    home_shots INTEGER,
    away_shots INTEGER,
    home_corners INTEGER,
    away_corners INTEGER,
    home_possession REAL,
    away_possession REAL,
    league TEXT,
    season TEXT
);

-- Cache de API
CREATE TABLE api_cache (
    cache_key TEXT PRIMARY KEY,
    data TEXT,  -- JSON
    fetched_at TIMESTAMP,
    expires_at TIMESTAMP
);

-- Predicciones generadas
CREATE TABLE predictions (
    id INTEGER PRIMARY KEY,
    match_description TEXT,
    recommendations TEXT,  -- JSON
    confidence_level TEXT,
    created_at TIMESTAMP
);
```

### 4. Bot de Telegram (`bot/`)

**Comandos**:
| Comando | Descripción |
|---|---|
| `/start` | Bienvenida y instrucciones |
| `/analizar` | Analizar equipos específicos |
| `/ligas` | Ver ligas disponibles |
| `/historial` | Ver predicciones anteriores |
| `/ayuda` | Ayuda y formatos de uso |
| `/cuotas` | Configurar casa de apuestas |

**Ejemplo de interacción**:
```
Usuario: /analizar Real Madrid - La Liga, Barcelona - La Liga
Bot:     📊 Analizando 2 equipos...
        ⏳ Obteniendo datos históricos...
        ✅ Análisis completado

        [Aquí va el mensaje formateado con tablas y recomendaciones]
```

## Tecnologías

| Componente | Tecnología | Justificación |
|---|---|---|
| Lenguaje | Python 3.11+ | Ecosistema ML/análisis, simplicidad |
| Bot Telegram | python-telegram-bot v20 | Mantenido, bien documentado |
| Datos API | requests + httpx | HTTP client confiable |
| Análisis | pandas + numpy | Manipulación de datos eficiente |
| Estadística | scipy.stats | Modelos Poisson, regresión |
| Almacenamiento | SQLite (sqlite3) | Sin servidor, portable |
| Cache | SQLite con TTL | Simple, sin dependencias |
| Configuración | python-dotenv | Seguridad de API keys |
| Logging | logging stdlib | Debugging y monitoreo |
| Tests | pytest | Estándar de la industria |

## Plan de Implementación

### Fase 1: Fundamentos (Día 1)
- [ ] Estructura de directorios
- [ ] `config.py` y `.env`
- [ ] Modelos de datos (`storage/models.py`)
- [ ] Base de datos SQLite (`storage/database.py`)
- [ ] `requirements.txt`

### Fase 2: Recolector de Datos (Día 1-2)
- [ ] Cliente API-Football (`collectors/api_football.py`)
- [ ] Cliente football-data.org (`collectors/football_data.py`)
- [ ] Sistema de cache (`collectors/cache.py`)
- [ ] Web scraping fallback (`collectors/scraper.py`)

### Fase 3: Motor de Análisis (Día 2-3)
- [ ] Estadísticas básicas (`analyzers/stats.py`)
- [ ] Análisis H2H (`analyzers/h2h.py`)
- [ ] Modelo Poisson (`analyzers/poisson.py`)
- [ ] Análisis de forma (`analyzers/form.py`)
- [ ] Detección de value betting (`analyzers/value_betting.py`)

### Fase 4: Predictor (Día 3)
- [ ] Motor principal (`predictors/engine.py`)
- [ ] Cálculo de probabilidades (`predictors/probabilities.py`)
- [ ] Generación de recomendaciones (`predictors/recommendations.py`)

### Fase 5: Bot de Telegram (Día 3-4)
- [ ] Handlers de comandos (`bot/handlers.py`)
- [ ] Formateo de mensajes (`bot/formatters.py`)
- [ ] Teclados interactivos (`bot/keyboards.py`)
- [ ] Middleware (rate limit, logging) (`bot/middleware.py`)
- [ ] Punto de entrada (`main.py`)

### Fase 6: Testing y polish (Día 4-5)
- [ ] Tests unitarios
- [ ] Tests de integración
- [ ] Manejo de errores
- [ ] Documentación de uso

## Consideraciones Importantes

1. **Limitaciones de API**: El plan gratuito de API-Football tiene 100 requests/día. Usar cache agresivamente.
2. **Legalidad**: Las apuestas deportivas están reguladas. El bot es una herramienta de análisis, NO garantiza ganancias.
3. **Rate Limits**: Implementar cola de requests con retry y backoff exponencial.
4. **Precisión**: El modelo Poisson es una aproximación. Incluir disclaimers sobre la naturaleza probabilística.
5. **Escalabilidad**: SQLite es suficiente para un usuario. Si se necesita multi-usUARIO, migrar a PostgreSQL.
