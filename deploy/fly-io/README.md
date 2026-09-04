# Despliegue en Fly.io Free

**Gratis para siempre. Sin tarjeta de crédito. VM siempre activa.**

---

## Paso 1: Instalar Fly CLI (2 minutos)

**Windows (PowerShell):**
```powershell
iwr https://fly.io/install.ps1 -useb | iex
```

**Mac/Linux:**
```bash
curl -L https://fly.io/install.sh | sh
```

Después de instalar, reinicia la terminal y verifica:
```bash
fly version
```

---

## Paso 2: Crear cuenta de Fly.io (2 minutos)

```bash
fly auth signup
```

Se abrirá el navegador. Crea cuenta con:
- Email
- Contraseña
- **NO pide tarjeta de crédito**

---

## Paso 3: Preparar el proyecto (5 minutos)

En tu PC, en la carpeta del proyecto:

```bash
cd "C:\Users\david\Desktop\AGENTE DE APUESTAS DEPORTIVAS"
```

Si aún no tienes el `.env` con tu API key, créalo:
```
API_FOOTBALL_KEY=aa60ccff49a0ae41375c0cb6246e317d
```

---

## Paso 4: Lanzar a Fly.io (3 minutos)

```bash
fly launch
```

Fly.io detectará el `fly.toml` y el `Dockerfile`. Sigue las preguntas:
- **App name**: `agente-apuestas` (o deja el default)
- **Region**: selecciona la más cercana (ej: `sjc` para Latinoamérica)
- **Overwrite existing?**: Sí

Esto creará la app y desplegará la primera versión.

---

## Paso 5: Configurar variables de entorno

```bash
fly secrets set API_FOOTBALL_KEY=aa60ccff49a0ae41375c0cb6246e317d
```

---

## Paso 6: Verificar

```bash
# Ver estado
fly status

# Ver logs
fly logs

# Abrir en navegador
fly open
```

Obtendrás una URL tipo: `https://agente-apuestas.fly.dev`

---

## Gestionar la app

```bash
# Ver estado
fly status

# Reiniciar
fly restart

# Ver logs en tiempo real
fly logs

# Actualizar código (después de cambios)
fly deploy

# Ver IP pública
fly ips list
```

---

## Actualizar el código

Después de hacer cambios en tu PC:

```bash
cd "C:\Users\david\Desktop\AGENTE DE APUESTAS DEPORTIVAS"
git add -A
git commit -m "Actualización"
fly deploy
```

---

## Solución de problemas

| Problema | Solución |
|---|---|
| `fly: command not found` | Reiniciar la terminal después de instalar |
| `Error: no app found` | Ejecutar `fly launch` primero |
| `Error: secret not set` | Ejecutar `fly secrets set API_FOOTBALL_KEY=...` |
| `502 Bad Gateway` | Verificar logs: `fly logs` |
| `App sleeping` | Verificar `fly status`, shouldn't happen on free tier |

---

## Costo real

| Concepto | Costo |
|---|---|
| Fly.io Free tier | **$0 para siempre** |
| VM compartida (256MB RAM) | **$0** |
| API-Football (plan gratuito) | **$0** |
| **Total** | **$0** |

---

## Límites del plan free

- 3 VMs compartidas (256MB RAM cada una)
- 160GB de transferencia de datos/mes
- Sin tarjeta de crédito
- VM siempre activa (no se duerme)
