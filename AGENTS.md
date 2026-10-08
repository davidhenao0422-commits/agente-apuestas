# AGENTS.md — Agente de Apuestas Deportivas

## Descripción del Proyecto

Aplicación web y bot de Telegram que genera **recomendaciones de apuestas basadas en datos** para equipos de las principales ligas de fútbol de Europa, Latinoamérica y Centroamérica.

**Características principales:**
- 🌍 Catálogo de 21 ligas por 3 regiones (Europa, LatAm, Centroamérica)
- 📊 Estadísticas reales de equipos (posición, goles, forma, etc.)
- 🎯 **Ensemble Predictor** (Poisson + Dixon-Coles + Bivariate Poisson + Skellam + ELO + PI Ratings + xG) para probabilidades calibradas
- 🔄 Integración con API-Football + The Odds API para datos y cuotas en tiempo real
- 🌐 Aplicación web responsive con dashboard de transparencia, Monte Carlo, CLV tracking
- 🤖 Bot de Telegram + Scheduler automático (canal diario 8:00 AM)
- ☁️ Desplegada en Render Free (24/7, gratis para siempre)
- 📈 **Paper Trading Simulator** — Portfolios, picks, Kelly, P&L, auto-settle, métricas completas
- ⚠️ **Advanced Risk Management** — Límites exposición, correlaciones, stop-loss, Kelly optimization, alertas Telegram
- 🏆 **Bookmaker Sharp Ranking** — CLV, accuracy, consistency, volume, sharp factor ranking
- 🚀 **Steam Move Detection** — Odds snapshots, detector, alertas tiempo real en bookmakers sharp
- 🤖 **ML Pipeline** — Model Registry, Feature Engineering, Optuna Hyperopt, A/B Testing, Auto-Retrain
- 📊 **Advanced Analytics** — Performance Attribution, Regime Detection, Stress Testing, Factor Analysis

---

## Estado del Despliegue

- **URL:** https://agente-apuestas.onrender.com
- **Hosting:** Render Free ($0 para siempre)
- **GitHub:** https://github.com/davidhenao0422-commits/agente-apuestas
- **API Key:** `${API_FOOTBALL_KEY}` (ver `.env`)
- **Fecha:** 2026-10-08
- **Estado:** ✅ En línea (deploy automático desde main)
- **Último commit:** 6aae7d3 - feat: Phase 7 - Advanced Analytics Dashboard (attribution, regime detection, stress testing, Monte Carlo, factor analysis, scheduler jobs)

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
│ The Odds API │  │ Dixon-Coles      │  │  - Partidos           │
│ Scraping     │  │ Bivariate Poisson│  │  - Predicciones       │
│              │  │ Skellam          │  │  - Cache API          │
│              │  │ ELO + PI Ratings │  │  - Prediction Locks   │
│              │  │ xG Model         │  │  - Calibration Recs   │
│              │  │ Ensemble         │  │  - CLV Records        │
│              │  │ Injury Model     │  │  - Bookmaker Scores   │
│              │  │ Value betting    │  │  - Odds Snapshots     │
│              │  │ Steam Moves      │  │  - Paper Trading      │
│              │  │ Bookmaker Rank   │  │  - Risk Management    │
│              │  │ Risk Manager     │  │  - ML Pipeline        │
│              │  │ Analytics        │  │  - Analytics          │
└──────────────┘  └──────────────────┘  └───────────────────────┘
```

### Flujo de Datos (Core)

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
        ├──▶ ANALIZADOR calcula stats, forma, H2H, lesiones, ELO
        ├──▶ ENSEMBLE combina 7 modelos predictivos
        └──▶ PREDICTOR genera probabilidades y recomendaciones
        │
        ▼
4. FORMATEADOR crea mensaje con tablas y recomendaciones
        │
        ▼
5. BOT envía respuesta al USUARIO
```

### Pipeline Automático (Scheduler 8:00 AM)

```
┌─────────────────┐
│  DAILY JOB      │  (08:00 AM)
└────────┬────────┘
         │
         ▼
┌─────────────────┐     ┌──────────────────┐
│ FETCH FIXTURES  │────▶│ ANALYZE EACH     │
│ (priority leagues)  │   │ MATCH (Ensemble) │
└─────────────────┘     └────────┬─────────┘
                                 │
                    ┌────────────┼────────────┐
                    ▼            ▼            ▼
            ┌────────────┐ ┌───────────┐ ┌─────────────┐
            │ STORE      │ │ STEAM MOVE│ │ BOOKMAKER   │
            │ PREDICTIONS│ │ DETECTION │ │ RANK UPDATE │
            └────────────┘ └───────────┘ └─────────────┘
                    │            │            │
                    ▼            ▼            ▼
            ┌─────────────────────────────────────┐
            │       TELEGRAM CHANNEL ALERT        │
            └─────────────────────────────────────┘
```

### Flujo Paper Trading + Risk + ML

```
USER / WEB UI
     │
     ▼
┌──────────────────┐     ┌──────────────────┐
│ PAPER TRADING    │────▶│ RISK MANAGER     │
│ ENGINE           │     │ (exposure, corr, │
│ - portfolios     │     │  stop-loss,      │
│ - picks/Kelly    │     │  Kelly opt)      │
│ - auto-settle    │     └────────┬─────────┘
└────────┬─────────┘              │
         │                        ▼
         │               ┌──────────────────┐
         │               │ TELEGRAM ALERTS  │
         │               └──────────────────┘
         │
         ▼
┌──────────────────┐     ┌──────────────────┐
│ ANALYTICS ENGINE │────▶│ ML PIPELINE      │
│ - Attribution    │     │ - Feature Eng    │
│ - Regime Detect  │     │ - Model Registry │
│ - Stress Test    │     │ - Optuna Hyperopt│
│ - Monte Carlo    │     │ - A/B Testing    │
│ - Factor Analysis│     │ - Auto-Retrain   │
└──────────────────┘     └──────────────────┘
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
│   ├── scraper.py           # Web scraping (fallback)
│   ├── odds_aggregator.py   # Agregador odds multi-fuente
│   └── odds_api.py          # Cliente The Odds API
│
├── analyzers/               # Motor de análisis estadístico
│   ├── stats.py             # Estadísticas básicas
│   ├── h2h.py               # Análisis de enfrentamientos directos
│   ├── poisson.py           # Modelo de Poisson
│   ├── form.py              # Análisis de forma reciente
│   ├── value_betting.py     # Detección de valor en cuotas
│   ├── ensemble.py          # Ensemble predictor (7 modelos)
│   ├── dixon_coles.py       # Modelo Dixon-Coles
│   ├── bivariate_poisson.py # Poisson Bivariado
│   ├── skellam.py           # Distribución Skellam
│   ├── elo.py               # Ratings ELO
│   ├── pi_ratings.py        # PI Ratings
│   ├── xg_model.py          # Expected Goals model
│   ├── injury_model.py      # Modelo de lesiones
│   ├── steam_moves.py       # Steam Move Detection
│   ├── bookmaker_ranking.py # Bookmaker Sharp Ranking
│   ├── paper_trading.py     # Paper Trading Engine
│   ├── risk_management.py   # Advanced Risk Management
│   ├── ml_pipeline.py       # ML Pipeline (Model Registry, Optuna, A/B)
│   └── analytics.py         # Advanced Analytics (Attribution, Regime, Stress, Factor)
│
├── predictors/              # Motor de predicción
│   ├── engine.py            # Motor principal de predicción
│   ├── probabilities.py     # Cálculo de probabilidades
│   ├── recommendations.py   # Generación de recomendaciones
│   └── staking.py           # Kelly, Half-Kelly, Monte Carlo
│
├── storage/                 # Persistencia
│   ├── database.py          # Conexión SQLite + esquema completo
│   ├── models.py            # Modelos de datos
│   └── migrations.py        # Migraciones
│
├── deploy/                  # Scripts de despliegue
│   └── oracle-cloud/
│       ├── setup.sh         # Script de instalación
│       └── README.md        # Instrucciones Oracle Cloud
│
├── tests/                   # Tests unitarios
│   ├── test_poisson.py
│   ├── test_h2h.py
│   ├── test_value_betting.py
│   ├── test_predictors.py
│   ├── test_stats_service.py
│   ├── test_db.py
│   ├── test_engine.py
│   └── test_ensemble.py
│
└── scripts/                 # Scripts utilitarios
    ├── scheduler.py         # Scheduler automático (canal 8:00 AM + steam + bookmakers)
    ├── test_channel.py      # Test conexión bot-canal
    └── debug_ensemble.py    # Debug ensemble predictor
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
  - `/fixtures?date={date}&status=NS` — Próximos partidos (sin season)
- **Temporadas accesibles (plan free):** 2022-2024

### The Odds API (Cuotas en tiempo real)
- **URL base:** `https://api.the-odds-api.com/v4`
- **Plan gratuito:** 500 requests/mes
- **Endpoints:** `/sports/soccer/odds` — Cuotas pre-match multi-bookmaker
- **Bookmakers soportados:** Pinnacle, Bet365, William Hill, Betfair, 1xBet, etc.

### Football-data.org (Secundario)
- **URL base:** `https://api.football-data.org/v4`
- **Plan gratuito:** 10 requests/minuto
- **Ligas cubiertas:** La Liga, Premier, Serie A, Bundesliga, Ligue 1, CL

---

## Modelo Predictivo

### Ensemble Predictor (7 modelos combinados)
El motor principal combina 7 modelos con pesos dinámicos calibrados por Brier score:

| Modelo | Descripción | Uso |
|--------|-------------|-----|
| **Poisson** | Distribución independiente de goles | Base λ home/away |
| **Dixon-Coles** | Corrige correlación 0-0 y underdispersion | Partidos bajos goles |
| **Bivariate Poisson** | Dependencia explícita goles local/visitante | H2H fuertes |
| **Skellam** | Diferencia de goles (local - visitante) | Handicap, spreads |
| **ELO Ratings** | Skill dinámico basado en resultados históricos | Forma a largo plazo |
| **PI Ratings** | Attack/defense strength + home advantage | Ligas regulares |
| **xG Model** | Expected Goals (calidad ocasiones) | Stats avanzadas |

**Combinación:** Pesos dinámicos por liga/temporada → minimiza Brier score histórico
**Output:** Probabilidades calibradas + confidence score (0-100) + Kelly stakes

### Modelo de Poisson (Base)
Calcula la probabilidad de marcadores exactos usando:
```
P(goles = k) = (λ^k × e^-λ) / k!
```
Donde λ = goles esperados del equipo.

### Ponderación de Factores (Legado - usado en fallback)
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
- **Double Chance** — 1X, X2, 12
- **Asian Handicap** — Ventaja/desventaja goles

### Value Betting
```
Valor = (Probabilidad_calculada × Cuota) - 1
Si Valor > 0 → Apuesta con valor detectada
```

### Staking (Kelly Criterion)
```
Kelly Fraction = (p × b - q) / b
Half-Kelly = Kelly × 0.5 (recomendado)
Max bet = 5% bankroll
Monte Carlo: 2000 paths × 500 bets para risk-of-ruin
```

---

## Bookmaker Sharp Ranking

Evalúa la calidad e integridad de bookmakers para identificar los "sharp" (líderes de mercado).

### Métricas
| Métrica | Peso | Descripción |
|---------|------|-------------|
| **CLV Score** | 40% | % mercados que baten línea de cierre + CLV promedio |
| **Accuracy** | 25% | Brier score inverso, log-loss vs resultado real |
| **Consistency** | 20% | Inverso de volatilidad de odds (estabilidad líneas) |
| **Volume** | 15% | Liquidez / número de mercados ofrecidos |

### Output
- **Sharp Factor** (0-100): Score combinado ponderado
- **Ranking global** por liga y período
- **Dashboard** en `/api/bookmakers/ranking` y `/api/transparency/bookmakers`

### Bookmakers Sharp de Referencia
Pinnacle, Betfair, Bet365, Circa, Bookmaker.eu, TheGreek, 5Dimes, SBO, Maxbet

### Almacenamiento
Tabla `bookmaker_scores` + `odds_snapshots` (con flag `is_sharp`)

---

## Steam Move Detection

Detecta movimientos bruscos de líneas en bookmakers sharp causados por apuestas grandes de sharps/sindicados.

### Umbrales por Defecto
| Mercado | Umbral % |
|---------|----------|
| 1X2 (H2H) | 3% |
| Totals (O/U) | 2.5% |
| BTTS | 3% |
| Spreads/Handicap | 2% |

### Ventana de Detección
- **15 minutos** entre snapshots
- Mínimo 2 snapshots para comparación
- Severidad: low / medium / high / extreme

### Output
- `SteamMove` dataclass con: match, bookmaker, market, direction, old/new odds, % change, severity, timestamp
- Alertas Telegram en tiempo real
- Endpoints: `/api/steam-moves`, `/api/steam-moves/summary`, `/api/steam-moves/poll`

### Integración Scheduler
- Polling automático cada 5 min durante horas pre-partido
- Almacena snapshots en `odds_snapshots`
- Actualiza `bookmaker_scores` periódicamente

---

## Paper Trading Simulator

Simulador completo de apuestas sin dinero real para validar estrategias.

### Características
- **Portfolios** múltiples con bankroll, Kelly fraction, max bet %, currency
- **Picks** manuales o desde recomendaciones (auto/source scheduler)
- **Mercados**: 1X2, Over/Under, BTTS, Clean Sheet, Double Chance, Asian Handicap
- **Staking**: Kelly fraccionado configurable por portfolio
- **Auto-settlement**: Post-partido usando resultados reales
- **Métricas**: ROI, Win Rate, Sharpe, Max Drawdown, P&L por mercado/liga

### Flujo
```
1. CREATE PORTFOLIO → 2. PLACE PICK (manual/auto) → 3. MONITOR (pending)
                                              ↓
4. AUTO-SETTLE (post-match) ← 5. FETCH RESULT ← 6. CALCULATE P&L
```

### Endpoints Principales
| Método | Ruta | Descripción |
|---|---|---|
| GET | `/api/paper/portfolios` | Listar portfolios |
| POST | `/api/paper/portfolios` | Crear portfolio |
| GET | `/api/paper/portfolios/{id}/performance` | Métricas completas |
| POST | `/api/paper/portfolios/{id}/picks` | Colocar pick manual |
| POST | `/api/paper/portfolios/{id}/picks/from-recommendation` | Pick desde recomendación |
| POST | `/api/paper/portfolios/{id}/auto-settle` | Auto-settle picks pendientes |

### Almacenamiento
Tablas: `paper_portfolio`, `paper_picks`, `paper_settlements`

---

## Advanced Risk Management

Gestión de riesgo profesional para portfolios de paper trading.

### Límites Configurables
| Límite | Default | Descripción |
|--------|---------|-------------|
| Max Exposure Total | 30% bankroll | Picks simultáneos máx |
| Max Exposure Liga | 15% | Por liga individual |
| Max Exposure Mercado | 20% | Por tipo mercado |
| Max Exposure Equipo | 10% | Por equipo individual |
| Max Correlación | 0.70 | Entre picks activos |
| Max Drawdown | 20% | Desde peak bankroll |
| Stop Loss | 10% | Desde peak, alerta/trigger |
| Max Concurrent Picks | 20 | Picks pendientes simultáneos |
| Kelly Fraction Range | 0.10 - 0.50 | Límites fracción Kelly |

### Análisis de Correlación
- **Shared Team**: Mismo equipo en picks distintos
- **Shared League**: Misma liga
- **Shared Market**: Mismo tipo mercado
- Score de correlación compuesto (0-1)

### Alertas (con Telegram)
| Tipo | Severidad | Trigger |
|------|-----------|---------|
| `exposure_breach` | critical | Límite exposición superado |
| `correlation_high` | warning | Correlación > 0.70 |
| `drawdown_warning` | warning | Drawdown > 15% |
| `stop_loss_triggered` | critical | Drawdown > 20% |

### Portfolio Optimization
- **Kelly fraccionado con constraints** (optimización convexa)
- Respeta todos los límites de exposición y correlación
- Endpoint: `/api/risk/portfolio/{id}/optimize-kelly`

### Endpoints
`/api/risk/portfolio/{id}/dashboard`, `/metrics`, `/limits`, `/correlations`, `/alerts`, `/check`

### Almacenamiento
Tablas: `risk_limits`, `risk_alerts`, `portfolio_correlations`

---

## ML Pipeline

Pipeline completo de ML para reentrenamiento automático, model registry y A/B testing.

### Componentes

#### 1. Feature Engineering (`FeatureEngineer`)
- Features: forma reciente (5/10/20 partidos), H2H, stats temporada, ELO, PI, xG, lesiones, mercado odds
- Target: resultado (home/draw/away), goles totales, BTTS
- Dataset construidos desde `matches`, `team_stats`, `odds_snapshots`

#### 2. Model Registry (`ModelRegistry`)
- **Versionado semántico** (major.minor.patch)
- **Champion/Challenger**: Un modelo campeón por tipo
- **Lineage**: Trackea parent_version, training_config, métricas
- **Artifacts**: Pickle + metadatos JSON en `models/{model_name}/v{version}/`

#### 3. Hyperparameter Tuning (Optuna)
- Optimiza pesos del ensemble (7 modelos)
- Objetivo: minimizar Brier score / maximizar ROI
- Trials configurables (default 50, timeout 1h)
- Pruning automático de trials malos

#### 4. A/B Testing Framework
- Experimentos: champion vs challenger
- Asignación aleatoria tráfico (configurable %)
- Análisis estadístico: t-test, confidence intervals, minimum detectable effect
- Decisión automática promote/archive basada en significancia

#### 5. Automated Retraining
- Job semanal programado (scheduler)
- Lookback window configurable (default 365 días)
- Minimum matches threshold (default 500)
- Validation split temporal (default 20%)
- Deploy automático si métricas superan thresholds

### Modelos Soportados
Poisson, Dixon-Coles, Bivariate Poisson, Skellam, ELO, PI Ratings, xG, Ensemble

### Endpoints
`/api/ml/models`, `/models/{name}/champion`, `/models/{name}/lineage`, `/models/compare`, `/models/{name}/promote`, `/models/{name}/archive`, `/training-runs`, `/retrain`, `/retrain-all`, `/optimize-ensemble`, `/ab-experiments`, `/features`

### Almacenamiento
Tablas: `model_versions`, `training_runs`, `ab_experiments`, `feature_importance`

---

## Advanced Analytics

Analytics de nivel institucional para paper trading y model evaluation.

### 1. Performance Attribution
Descompone ROI en factores contribuyentes (estilo Brinson):
- **Selection Effect**: Skill picking winners
- **Allocation Effect**: Sizing correcto (Kelly)
- **Interaction Effect**: Selección × Asignación
- **By Model/Liga/Mercado/Timing/Luck**: Desglose granular

### 2. Regime Detection
Detecta regímenes de mercado usando HMM / changepoint detection:
- **Tipos**: bull, bear, volatile, calm, trending, mean_reverting
- Métricas: volatilidad realizada, correlación media, skew, kurtosis, win rate
- Confidence score por régimen
- Endpoints: `/api/analytics/regime`, `/current`, `/history`

### 3. Stress Testing
Escenarios extremos para validar robustez:
- **Crash**: -30% bankroll shock
- **High Volatility**: 2x volatilidad histórica
- **Correlation Breakdown**: Correlaciones → 1.0
- **Model Decay**: Brier score +50%
- **Liquidity Crisis**: Spreads +200bps
- Output: Max DD, VaR 95%, Expected Shortfall, Survival Probability, Recovery Time

### 4. Monte Carlo Portfolio
- 2000 paths × 500 bets (configurable)
- Samplea de distribución empírica de picks históricos
- Risk-of-ruin, percentiles bankroll final, drawdown distribution
- Endpoint: `/api/analytics/monte-carlo`

### 5. Factor Analysis (PCA + Regresión)
- PCA sobre features de picks para identificar drivers
- Regresión lineal: ROI ~ factores principales
- Identifica: momentum, value, quality, size, league factors
- Endpoint: `/api/analytics/factor-analysis`

### 6. Full Report
Reporte consolidado con todas las métricas + visualizaciones data-ready
Endpoint: `/api/analytics/full-report`

### Almacenamiento
Tablas: `analytics_reports`, `regime_history`, `stress_test_results`

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
| GET | `/api/proximos-todos` | Próximos partidos de TODAS las ligas (1 request) |
| GET | `/api/mejores-apuestas` | Value bets del día (con demo mode) |
| GET | `/api/transparency/predictions-locked` | Predicciones bloqueadas (auditoría) |
| GET | `/api/transparency/calibration` | Dashboard calibración modelos |
| GET | `/api/transparency/clv` | Closing Line Value tracking |
| GET | `/api/transparency/bookmakers` | Scores de bookmakers |
| GET | `/api/confidence/{liga}/{local}/{visitante}` | Confidence breakdown (8 factores) |
| GET | `/api/monte-carlo/{liga}/{local}/{visitante}` | Simulación Monte Carlo bankroll |
| POST | `/api/refresh-odds` | Refrescar odds multi-fuente |
| GET | `/api/odds/{liga}/{local}/{visitante}` | Mejores odds para un partido |
| GET | `/api/steam-moves` | Steam moves detectados |
| GET | `/api/steam-moves/summary` | Resumen steam moves por severidad |
| GET | `/api/steam-moves/{match_id}/history` | Historial odds para un partido |
| POST | `/api/steam-moves/poll` | Polling manual de odds |
| GET | `/api/bookmakers/ranking` | Ranking bookmakers por liga |
| GET | `/api/bookmakers/{bookmaker}/detail` | Detalle score bookmaker |
| POST | `/api/bookmakers/refresh-scores` | Recalcular scores bookmakers |
| GET | `/api/bookmakers/leagues` | Ligas disponibles para bookmakers |
| GET | `/api/paper/portfolios` | Listar portfolios |
| POST | `/api/paper/portfolios` | Crear portfolio |
| GET | `/api/paper/portfolios/{id}` | Detalle portfolio |
| GET | `/api/paper/portfolios/{id}/performance` | Métricas completas |
| GET | `/api/paper/portfolios/{id}/picks` | Listar picks |
| GET | `/api/paper/portfolios/{id}/pending` | Picks pendientes |
| POST | `/api/paper/portfolios/{id}/picks` | Colocar pick manual |
| POST | `/api/paper/portfolios/{id}/picks/from-recommendation` | Pick desde recomendación |
| POST | `/api/paper/picks/{pick_id}/cancel` | Cancelar pick pendiente |
| POST | `/api/paper/picks/{pick_id}/settle` | Settle manual pick |
| POST | `/api/paper/portfolios/{id}/auto-settle` | Auto-settle pendientes |
| GET | `/api/paper/portfolios/{id}/activity` | Historial actividad |
| GET | `/api/risk/portfolio/{id}/dashboard` | Dashboard riesgo completo |
| GET | `/api/risk/portfolio/{id}/metrics` | Métricas de riesgo |
| GET | `/api/risk/portfolio/{id}/limits` | Límites configurados |
| POST | `/api/risk/portfolio/{id}/limits` | Actualizar límites |
| GET | `/api/risk/portfolio/{id}/correlations` | Análisis correlaciones |
| GET | `/api/risk/portfolio/{id}/alerts` | Alertas activas |
| POST | `/api/risk/alerts/{alert_id}/acknowledge` | Reconocer alerta |
| POST | `/api/risk/portfolio/{id}/check` | Check riesgo completo |
| POST | `/api/risk/portfolio/{id}/optimize-kelly` | Optimizar Kelly con constraints |
| POST | `/api/risk/portfolio/{id}/init-defaults` | Inicializar límites por defecto |
| GET | `/api/ml/models` | Listar modelos registrados |
| GET | `/api/ml/models/{name}/champion` | Modelo campeón actual |
| GET | `/api/ml/models/{name}/lineage` | Lineage del modelo |
| GET | `/api/ml/models/compare` | Comparar versiones |
| POST | `/api/ml/models/{name}/promote` | Promover challenger a champion |
| POST | `/api/ml/models/{name}/archive` | Archivar versión |
| GET | `/api/ml/training-runs` | Historial entrenamientos |
| POST | `/api/ml/retrain` | Reentrenar modelo específico |
| POST | `/api/ml/retrain-all` | Reentrenar todos |
| POST | `/api/ml/optimize-ensemble` | Optuna hyperopt ensemble |
| POST | `/api/ml/ab-experiments` | Crear experimento A/B |
| GET | `/api/ml/ab-experiments` | Listar experimentos |
| GET | `/api/ml/ab-experiments/{exp_id}` | Detalle experimento |
| POST | `/api/ml/ab-experiments/{exp_id}/start` | Iniciar experimento |
| POST | `/api/ml/ab-experiments/{exp_id}/analyze` | Analizar resultados |
| GET | `/api/ml/features` | Features disponibles |
| GET | `/api/analytics/attribution/{portfolio_id}` | Performance attribution |
| GET | `/api/analytics/regime` | Regímenes históricos |
| GET | `/api/analytics/regime/current` | Régimen actual |
| GET | `/api/analytics/regime/history` | Historial regímenes |
| POST | `/api/analytics/stress-test` | Ejecutar stress test |
| GET | `/api/analytics/stress-tests` | Historial stress tests |
| POST | `/api/analytics/monte-carlo` | Monte Carlo portfolio |
| POST | `/api/analytics/factor-analysis` | Factor analysis (PCA) |
| GET | `/api/analytics/factor-analysis` | Historial factor analysis |
| POST | `/api/analytics/full-report` | Reporte completo analytics |
| GET | `/api/analytics/reports` | Historial reportes |

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

-- Predicciones bloqueadas (transparencia/auditoría)
CREATE TABLE prediction_locks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    match_id TEXT NOT NULL,
    home_team TEXT NOT NULL,
    away_team TEXT NOT NULL,
    league TEXT NOT NULL,
    kickoff TEXT NOT NULL,
    locked_at TEXT NOT NULL,
    probabilities TEXT NOT NULL,
    expected_goals TEXT NOT NULL,
    recommendations TEXT NOT NULL,
    ensemble_weights TEXT NOT NULL,
    brier_scores TEXT NOT NULL,
    confidence_score INTEGER,
    confidence_breakdown TEXT,
    kelly_stakes TEXT,
    immutable_hash TEXT NOT NULL,
    UNIQUE(match_id, locked_at)
);

-- Registros de calibración por modelo/liga/temporada
CREATE TABLE calibration_records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    model_name TEXT NOT NULL,
    league TEXT NOT NULL,
    season TEXT NOT NULL,
    date TEXT NOT NULL,
    brier_score REAL,
    log_loss REAL,
    ece REAL,
    sample_size INTEGER,
    reliability_data TEXT,
    UNIQUE(model_name, league, season, date)
);

-- Registros de Closing Line Value
CREATE TABLE clv_records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    match_id TEXT NOT NULL,
    home_team TEXT NOT NULL,
    away_team TEXT NOT NULL,
    league TEXT NOT NULL,
    opening_odds TEXT,
    closing_odds TEXT,
    model_probs TEXT,
    actual_result TEXT,
    clv_home REAL,
    clv_draw REAL,
    clv_away REAL,
    beat_closing_line INTEGER,
    date TEXT NOT NULL,
    UNIQUE(match_id)
);

-- Scores de calidad/integridad de bookmakers
CREATE TABLE bookmaker_scores (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    bookmaker TEXT NOT NULL,
    league TEXT NOT NULL,
    period_days INTEGER NOT NULL,
    accuracy REAL,
    consistency REAL,
    clv_score REAL,
    volume INTEGER,
    last_updated TEXT NOT NULL,
    UNIQUE(bookmaker, league, period_days, last_updated)
);

-- Snapshots de odds para steam move detection
CREATE TABLE odds_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    match_id TEXT NOT NULL,
    home_team TEXT NOT NULL,
    away_team TEXT NOT NULL,
    league TEXT NOT NULL,
    kickoff TEXT NOT NULL,
    bookmaker TEXT NOT NULL,
    market TEXT NOT NULL,
    odds_home REAL,
    odds_draw REAL,
    odds_away REAL,
    odds_over REAL,
    odds_under REAL,
    odds_btts_yes REAL,
    odds_btts_no REAL,
    snapshot_at TEXT NOT NULL,
    is_sharp INTEGER DEFAULT 0,
    UNIQUE(match_id, bookmaker, market, snapshot_at)
);

-- Paper Trading: Portfolios
CREATE TABLE paper_portfolio (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL DEFAULT 'Default',
    initial_bankroll REAL NOT NULL DEFAULT 1000,
    current_bankroll REAL NOT NULL DEFAULT 1000,
    currency TEXT NOT NULL DEFAULT 'EUR',
    kelly_fraction REAL NOT NULL DEFAULT 0.25,
    max_bet_pct REAL NOT NULL DEFAULT 0.05,
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now')),
    is_active INTEGER DEFAULT 1
);

-- Paper Trading: Picks
CREATE TABLE paper_picks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    portfolio_id INTEGER NOT NULL REFERENCES paper_portfolio(id),
    match_id TEXT NOT NULL,
    home_team TEXT NOT NULL,
    away_team TEXT NOT NULL,
    league TEXT NOT NULL,
    kickoff TEXT NOT NULL,
    market TEXT NOT NULL,
    choice TEXT NOT NULL,
    odds REAL NOT NULL,
    probability REAL NOT NULL,
    edge REAL,
    kelly_stake_pct REAL,
    stake_units REAL NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',  -- pending, won, lost, void, settled
    result TEXT,  -- win, loss, push
    pnl REAL,
    settled_at TEXT,
    placed_at TEXT DEFAULT (datetime('now')),
    source TEXT,  -- 'manual', 'auto', 'scheduler'
    confidence_score INTEGER,
    ensemble_weights TEXT,
    expected_goals TEXT
);

-- Paper Trading: Settlements
CREATE TABLE paper_settlements (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    pick_id INTEGER NOT NULL REFERENCES paper_picks(id),
    actual_result TEXT,  -- home_win, draw, away_win, over, under, btts_yes, btts_no
    actual_score TEXT,  -- "2-1"
    settled_at TEXT NOT NULL,
    pnl REAL NOT NULL,
    roi_pct REAL
);

-- Risk Management: Límites
CREATE TABLE risk_limits (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    portfolio_id INTEGER NOT NULL REFERENCES paper_portfolio(id),
    limit_type TEXT NOT NULL,  -- max_exposure_league, max_exposure_market, max_correlation, max_drawdown, stop_loss_pct
    limit_value REAL NOT NULL,
    current_value REAL DEFAULT 0,
    is_active INTEGER DEFAULT 1,
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now')),
    UNIQUE(portfolio_id, limit_type)
);

-- Risk Management: Alertas
CREATE TABLE risk_alerts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    portfolio_id INTEGER NOT NULL REFERENCES paper_portfolio(id),
    alert_type TEXT NOT NULL,  -- exposure_breach, correlation_high, drawdown_warning, stop_loss_triggered
    severity TEXT NOT NULL,    -- info, warning, critical
    message TEXT NOT NULL,
    metric_value REAL,
    limit_value REAL,
    acknowledged INTEGER DEFAULT 0,
    created_at TEXT DEFAULT (datetime('now')),
    acknowledged_at TEXT
);

-- Risk Management: Correlaciones entre picks
CREATE TABLE portfolio_correlations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    portfolio_id INTEGER NOT NULL REFERENCES paper_portfolio(id),
    pick_id_a INTEGER NOT NULL REFERENCES paper_picks(id),
    pick_id_b INTEGER NOT NULL REFERENCES paper_picks(id),
    correlation REAL NOT NULL,
    shared_team INTEGER DEFAULT 0,      -- 1 if same team involved
    shared_league INTEGER DEFAULT 0,    -- 1 if same league
    shared_market INTEGER DEFAULT 0,    -- 1 if same market type
    calculated_at TEXT DEFAULT (datetime('now')),
    UNIQUE(pick_id_a, pick_id_b)
);

-- ML Pipeline: Versiones de modelos
CREATE TABLE model_versions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    model_name TEXT NOT NULL,           -- poisson, dixon_coles, ensemble, etc.
    version TEXT NOT NULL,              -- semver: 1.2.3
    parameters TEXT NOT NULL,           -- JSON con hiperparámetros
    metrics TEXT NOT NULL,              -- JSON con métricas (brier, log_loss, roi, etc.)
    parent_version TEXT,                -- Versión padre para lineage
    training_config TEXT,               -- JSON con config de entrenamiento
    artifact_path TEXT,                 -- Ruta al archivo pickle
    is_champion INTEGER DEFAULT 0,      -- 1 si es el modelo campeón actual
    status TEXT DEFAULT 'active',       -- active, archived, deprecated
    created_at TEXT DEFAULT (datetime('now')),
    UNIQUE(model_name, version)
);

-- ML Pipeline: Ejecuciones de entrenamiento
CREATE TABLE training_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    model_name TEXT NOT NULL,
    version TEXT NOT NULL,
    run_type TEXT,                      -- scheduled, manual, hyperopt, ab_test
    lookback_days INTEGER,
    min_matches INTEGER,
    validation_split REAL,
    metrics TEXT,                       -- JSON con métricas finales
    status TEXT,                        -- running, completed, failed
    started_at TEXT,
    completed_at TEXT,
    error_message TEXT
);

-- ML Pipeline: Experimentos A/B
CREATE TABLE ab_experiments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    experiment_name TEXT NOT NULL,
    champion_model TEXT NOT NULL,
    champion_version TEXT NOT NULL,
    challenger_model TEXT NOT NULL,
    challenger_version TEXT NOT NULL,
    traffic_split REAL DEFAULT 0.5,     -- % tráfico al challenger
    min_sample_size INTEGER,
    status TEXT DEFAULT 'draft',        -- draft, running, completed, archived
    results TEXT,                       -- JSON con análisis estadístico
    decision TEXT,                      -- promote_challenger, keep_champion, inconclusive
    created_at TEXT DEFAULT (datetime('now')),
    started_at TEXT,
    completed_at TEXT
);

-- Advanced Analytics: Reportes
CREATE TABLE analytics_reports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    report_type TEXT NOT NULL,          -- full_report, attribution, regime, stress_test, factor_analysis
    portfolio_id INTEGER,
    period_days INTEGER,
    data TEXT NOT NULL,                 -- JSON con resultados completos
    created_at TEXT DEFAULT (datetime('now'))
);

-- Advanced Analytics: Historial de regímenes
CREATE TABLE regime_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    regime_type TEXT NOT NULL,          -- bull, bear, volatile, calm, trending, mean_reverting
    start_date TEXT NOT NULL,
    end_date TEXT,
    metrics TEXT,                       -- JSON con métricas del régimen
    confidence REAL,
    description TEXT
);

-- Advanced Analytics: Resultados stress tests
CREATE TABLE stress_test_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    portfolio_id INTEGER,
    scenario_name TEXT NOT NULL,
    parameters TEXT,                    -- JSON con parámetros del escenario
    results TEXT,                       -- JSON con métricas de resultado
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
| ML/Stats | scikit-learn | 1.5+ |
| Optimización | optuna | 4.0+ |
| Almacenamiento | SQLite | built-in |
| Scraping | BeautifulSoup4 | 4.12+ |
| Scheduler | schedule | 1.2.2 |
| Tests | pytest | 8.3+ |

---

## Variables de Entorno (.env)

```bash
# Telegram Bot
TELEGRAM_BOT_TOKEN=

# API-Football
API_FOOTBALL_KEY=
API_FOOTBALL_BASE_URL=https://v3.football.api-sports.io

# Football-data.org (opcional)
FOOTBALL_DATA_KEY=

# The Odds API (opcional)
ODDS_API_KEY=

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

# Ejecutar scheduler automático (canal diario 8:00 AM)
python scheduler.py

# Test conexión bot-canal
python test_channel.py

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

### Fase 8: Ensemble Predictor + Transparencia
- 7 modelos predictivos combinados (Poisson, Dixon-Coles, Bivariate Poisson, Skellam, ELO, PI Ratings, xG)
- Pesos dinámicos calibrados por Brier score
- Confidence score (0-100) con 8 factores
- Prediction locking (SHA256 inmutable) para auditoría
- Monte Carlo simulation (2000 paths × 500 bets)
- Odds aggregator multi-fuente (The Odds API + OpticOdds)
- CLV tracking (Closing Line Value)
- Bookmaker quality scores

### Fase 3 (v2): Bookmaker Sharp Ranking
- CLV, accuracy, consistency, volume scoring
- Sharp Factor ranking (0-100)
- Dashboard bookmakers + scheduler job
- Tabla `bookmaker_scores` + `odds_snapshots`

### Fase 4 (v2): Paper Trading Simulator
- Portfolios multi-currency con Kelly config
- Picks manuales/auto con 6 mercados
- Auto-settle post-partido
- Métricas: ROI, Sharpe, Max DD, Win Rate
- Tablas: `paper_portfolio`, `paper_picks`, `paper_settlements`

### Fase 5 (v2): Advanced Risk Management
- Límites exposición (total/liga/mercado/equipo)
- Análisis correlación picks (shared team/league/market)
- Stop-loss dinámico + max drawdown alerts
- Kelly optimization con constraints convexas
- Alertas Telegram (exposure_breach, correlation_high, drawdown_warning, stop_loss_triggered)
- Tablas: `risk_limits`, `risk_alerts`, `portfolio_correlations`

### Fase 6 (v2): ML Pipeline
- Feature Engineering (forma, H2H, stats, ELO, PI, xG, injuries, odds)
- Model Registry con versionado semántico + lineage
- Champion/Challenger pattern
- Optuna hyperopt para pesos ensemble
- A/B testing framework (t-test, CI, MDE)
- Auto-retrain semanal (lookback 365d, min 500 matches)
- Tablas: `model_versions`, `training_runs`, `ab_experiments`, `feature_importance`

### Fase 7 (v2): Advanced Analytics Dashboard
- Performance Attribution (Brinson-style: selection/allocation/interaction)
- Regime Detection (HMM/changepoint: bull/bear/volatile/calm/trending/mean_reverting)
- Stress Testing (crash, high vol, correlation breakdown, model decay, liquidity crisis)
- Monte Carlo Portfolio (2000 paths × 500 bets, risk-of-ruin, percentiles)
- Factor Analysis (PCA + regresión: momentum, value, quality, size, league)
- Full Report consolidado
- Tablas: `analytics_reports`, `regime_history`, `stress_test_results`

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

## Bot de Telegram - Configuración Completada

### Bot Creado
- **Nombre:** Fútbol Pronóstico
- **Username:** @futbol_stats_2024_bot
- **Token:** `${TELEGRAM_BOT_TOKEN}` (ver `.env`)
- **Fecha creación:** 2026-10-01

### Canal de Recomendaciones
- **Nombre:** Apuestas_Futbol
- **Enlace:** https://t.me/apuestasdefutbol229804
- **Propósito:** Recibir recomendaciones automáticas diarias

### Comandos del Bot
| Comando | Descripción |
|---------|-------------|
| `/start` | Iniciar el bot y ver instrucciones |
| `/analizar` | Analizar equipos específicos |
| `/historial` | Ver predicciones anteriores |
| `/ayuda` | Más información |

### Archivos Principales

#### scheduler.py
Sistema automatizado que:
- Obtiene partidos de todas las ligas (prioriza: La Liga, Premier League, Serie A, Bundesliga, Ligue 1, Champions League)
- Analiza cada partido con el Ensemble Predictor
- Detecta steam moves en bookmakers sharp
- Actualiza bookmaker scores
- Envía recomendaciones + alertas al canal de Telegram
- Se ejecuta todos los días a las 8:00 AM + polling steam moves cada 5 min

#### test_channel.py
Script de prueba para verificar la conexión entre el bot y el canal.

### Ejecución

**Bot interactivo (terminal local):**
```bash
python main.py
```

**Scheduler automático (envío al canal + steam moves + bookmaker ranks):**
```bash
python scheduler.py
```

**Prueba de conexión al canal:**
```bash
python test_channel.py
```

### Notas Importantes

1. **Límite de API:** 100 requests/día (plan gratuito API-Football)
   - Scheduler prioriza 6 ligas principales para no agotar el cupo
   - Cada liga consume ~1-2 requests por ejecución

2. **Canal de Telegram:**
   - El bot debe ser administrador del canal
   - Debe tener permisos para publicar mensajes
   - Si el canal es privado, se necesita el ID numérico

3. **Ejecución continua:**
   - El bot en PC local solo funciona cuando la PC está encendida
   - Para 24/7, considerar Oracle Cloud Always Free (requiere tarjeta)

### Estado Actual
- ✅ Bot de Telegram configurado y funcionando
- ✅ Canal de recomendaciones creado
- ✅ Scheduler automático implementado (8:00 AM diario + steam moves polling)
- ✅ Ensemble predictor integrado (7 modelos)
- ✅ Bookmaker ranking + steam detection integrados en scheduler
- ✅ Paper trading + risk management + ML pipeline + analytics operativos via API web

---

*Documento generado el 2026-09-04. Última actualización: 2026-10-08 - Phase 7 Advanced Analytics (attribution, regime detection, stress testing, Monte Carlo, factor analysis, scheduler jobs).*
