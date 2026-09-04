# Despliegue en Oracle Cloud Always Free

**Gratis para siempre. Nunca se duerme. Sin límites de tiempo.**

## Requisitos previos

- Cuenta de GitHub (gratuita)
- Cuenta de Oracle Cloud (gratuita) → [cloud.oracle.com](https://cloud.oracle.com)
- SSH client (terminal en Mac/Linux, PowerShell o PuTTY en Windows)
- Tu API key de API-Football (ya la tienes configurada)

---

## Paso 1: Crear cuenta de Oracle Cloud (5 minutos)

1. Ve a [cloud.oracle.com](https://cloud.oracle.com)
2. Clic **"Start for Free"** o **"Sign Up"**
3. Completa: email, contraseña, país
4. Verificación telefónica (SMS o llamada)
5. Selecciona **"Home Region"**: el más cercano a tu país (ej: `Mexico City`, `São Paulo`, `Ashburn`)
6. Clic **"Start Free"**
7. En el dashboard, ve a **"Compute → Instances"**

---

## Paso 2: Crear la VM (5 minutos)

1. En el dashboard de Oracle Cloud, ve a **"Compute → Instances"**
2. Clic **"Create Instance"**
3. Configura:
   - **Name**: `agente-apuestas`
   - **Image**: Ubuntu 22.04 (o 20.04)
   - **Shape**: `VM.Standard.E4.Flex` (1 OCPU, 1 GB RAM) — **siempre gratuito**
   - **SSH Keys**: Sube tu clave pública SSH (o genera una con `ssh-keygen`)
   - **VCPUs**: 1
   - **Memory**: 1 GB
4. Clic **"Create"**
5. Espera ~2 minutos a que la VM esté "Running"
6. Copia la **IP pública** de la instancia

---

## Paso 3: Conectarse a la VM (2 minutos)

```bash
# En Mac/Linux/WSL:
ssh -i ~/.ssh/tu_llave_privada ubuntu@IP_PUBLICA

# En Windows con PuTTY:
# Host: IP_PUBLICA
# Username: ubuntu
# Auth: selecciona tu clave .ppk
```

---

## Paso 4: Subir el proyecto (5 minutos)

**Opción A — Git (recomendado):**

```bash
# 1. Sube el proyecto a GitHub primero:
cd ~/AGENTE\ DE\ APUESTAS\ DEPORTIVAS
git remote add origin https://github.com/TU_USUARIO/agente-apuestas.git
git push -u origin main

# 2. En la VM:
cd /home/ubuntu
git clone https://github.com/TU_USUARIO/agente-apuestas.git
cd agente-apuestas
```

**Opción B — SCP (si no usas Git):**

```bash
# Desde tu PC:
scp -r "C:\Users\david\Desktop\AGENTE DE APUESTAS DEPORTIVAS\*" ubuntu@IP_PUBLICA:/home/ubuntu/agente-apuestas/
```

---

## Paso 5: Ejecutar el script de instalación (3 minutos)

```bash
cd /home/ubuntu/agente-apuestas
chmod +x deploy/oracle-cloud/setup.sh
bash deploy/oracle-cloud/setup.sh
```

El script te preguntará tu API_FOOTBALL_KEY. Pégala cuando te lo pida.

---

## Paso 6: Verificar

```bash
# Ver IP pública de tu VM:
curl ifconfig.me

# Verificar que la app responde:
curl http://localhost:8000/api/regiones

# Ver logs:
sudo journalctl -u agente-apuestas -f
```

---

## Paso 7: Acceder desde tu navegador

Abre: `http://TU_IP_PUBLICA:8000`

¡Listo! Tu app de apuestas está corriendo 24/7 en Oracle Cloud.

---

## Gestionar el servicio

```bash
# Estado
sudo systemctl status agente-apuestas

# Reiniciar
sudo systemctl restart agente-apuestas

# Detener
sudo systemctl stop agente-apuestas

# Logs en tiempo real
sudo journalctl -u agente-apuestas -f

# Editar .env
nano /home/ubuntu/agente-apuestas/.env
```

---

## Actualizar el código

```bash
cd /home/ubuntu/agente-apuestas
git pull
sudo systemctl restart agente-apuestas
```

---

## Solución de problemas

| Problema | Solución |
|---|---|
| No puedo conectarme por SSH | Verificar que la IP pública es correcta y el firewall permite SSH (22) |
| La app no responde | Verificar firewall: `sudo ufw status` debe mostrar 22 y 8000 abiertos |
| Error de "API key not configured" | Editar `.env`: `sudo nano /home/ubuntu/agente-apuestas/.env` |
| "Permission denied" en setup.sh | Asegurarse de ejecutar `chmod +x deploy/oracle-cloud/setup.sh` |

---

## Costo real

| Concepto | Costo |
|---|---|
| Oracle Cloud Always Free VM | **$0 para siempre** |
| API-Football (plan gratuito) | **$0** |
| Dominio (opcional) | Puedes usar duckdns.org gratis |
| **Total** | **$0** |
