# Agente de Apuestas Deportivas — Aplicación Web

Aplicación web que genera **recomendaciones de apuestas basadas en datos** para
equipos de las principales ligas de **Europa, Latinoamérica y Centroamérica**.

Funciona **24/7 sin necesidad de mantener la PC encendida** (backend en la nube).

---

## ✨ Características

- 🌍 Catálogo precargado de ligas por región:
  - **Europa**: La Liga, Premier League, Serie A, Bundesliga, Ligue 1, Primeira Liga, Eredivisie, Champions.
  - **Latinoamérica**: Argentina, Brasil, México, Colombia, Perú.
  - **Centroamérica**: Honduras, Guatemala, Costa Rica, Panamá.
- 📊 Estadísticas de cada equipo: posición, goles, recibidos, forma, tiros, córners, posesión.
- 🎯 Lista de apuestas recomendadas por equipo, ordenadas por confianza y con razonamiento.
- ⚽ Modelo predictivo (Poisson) que estima goles esperados y probabilidades.
- 🔄 Botón "Actualizar datos" (opcional, conecta con API-Football).

---

## 🚀 Despliegue 24/7 gratis

### Opción A — Render (más sencillo, con `render.yaml`)

1. Sube este proyecto a un repositorio de GitHub.
2. En [render.com](https://render.com) crea una cuenta gratis.
3. Ve a **New → Web Service** y selecciona tu repo.
4. Render detecta `render.yaml` automáticamente **o** configúralo manualmente:
   - **Runtime**: Python 3
   - **Build**: `pip install -r requirements.txt`
   - **Start**: `uvicorn web.app:app --host 0.0.0.0 --port $PORT`
5. Da clic en **Create Web Service**.
6. Obtienes una URL tipo `https://agente-apuestas.onrender.com`.

> ⚠️ El plan gratuito de Render "duerme" el servicio tras unos minutos de inactividad
> y lo despierta al recibir una petición (tarda ~30-60s la primera carga). Es suficiente
> para uso personal.

### Opción B — Railway (free tier)

1. Crea un proyecto en [railway.app](https://railway.app).
2. Conecta tu repo de GitHub.
3. Railway usa el `Dockerfile` incluido automáticamente.
4. Añade un volumen opcional para persistencia si configuras una DB.

### Nota sobre el bot de Telegram
El bot (`main.py`) no se despliega con la web. Si quieres ambos, despliega también
`main.py` como worker o usa la web localmente. La web es independiente.

---

## 🧪 Ejecutar localmente

Requisito: Python 3.11+.

```bash
pip install -r requirements.txt
python run.py
```

Abre `http://localhost:8000` en tu navegador.

---

## 📁 Estructura

```
├── web/                   # Aplicación web
│   ├── app.py             # Backend FastAPI (endpoints REST)
│   ├── preselected_data.py# Stats realistas precargadas por equipo
│   └── static/            # Frontend (HTML/CSS/JS)
├── catalog.py            # Catálogo de ligas y equipos por región
├── analyzers/            # Modelo predictivo (Poisson, H2H, value)
├── predictors/           # Motor de predicción y recomendaciones
├── collectors/           # Clientes de APIs de datos
├── bot/                  # Bot de Telegram (+)
├── storage/              # Persistencia SQLite
├── run.py                # Arranque local
├── Dockerfile            # Para Railway
├── Procfile / render.yaml# Para Render
└── requirements.txt      # Dependencias
```

---

## ⚙️ Actualizar datos con API-Football (opcional)

Por defecto la app usa **stats preseleccionadas** (no consume la API). Para
conectar datos reales:

1. Crea una cuenta gratis en [api-football.com](https://www.api-football.com) (100 requests/día).
2. Añade tu key al entorno (Render: *Environment* → `API_FOOTBALL_KEY`).
3. Reinicia el servicio. El botón "Actualizar datos" usará la API respetando el límite diario.

---

## ⚠️ Aviso legal

Las recomendaciones son de naturaleza **estadística** y **no garantizan
resultados**. Las apuestas deportivas implican riesgo económico. Juega
responsablemente.

---

## 📋 Endpoints API

| Método | Ruta | Descripción |
|---|---|---|
| GET | `/` | Frontend |
| GET | `/api/regiones` | Regiones disponibles |
| GET | `/api/ligas/{region}` | Ligas de una región |
| GET | `/api/equipos/{liga}` | Equipos y stats de una liga |
| GET | `/api/recomendaciones/{liga}/{equipo}` | Recomendaciones de un equipo |
| GET | `/api/equipo/{liga}/{equipo}` | Stats de un equipo |
| POST | `/api/actualizar/{liga}` | Actualizar datos (requiere API key) |