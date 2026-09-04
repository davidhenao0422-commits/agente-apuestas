#!/bin/bash
# ============================================================
# Script de despliegue para Oracle Cloud Always Free
# Ejecutar en la VM después de conectarse por SSH
# ============================================================
set -e

echo "================================================"
echo "  Agente de Apuestas Deportivas - Oracle Cloud"
echo "  Instalación automática"
echo "================================================"

# 1. Actualizar sistema
echo "[1/7] Actualizando sistema..."
sudo apt update -y
sudo apt upgrade -y

# 2. Instalar dependencias
echo "[2/7] Instalando Python y dependencias..."
sudo apt install -y python3 python3-pip python3-venv git

# 3. Clonar el proyecto
echo "[3/7] Clonando proyecto..."
cd /home/ubuntu
if [ ! -d "agente-apuestas" ]; then
    git clone https://github.com/TU_USUARIO/agente-apuestas.git
    # IMPORTANTE: Cambia TU_USUARIO por tu usuario de GitHub
else
    cd agente-apuestas && git pull
fi

cd agente-apuestas

# 4. Crear entorno virtual e instalar dependencias
echo "[4/7] Instalando dependencias Python..."
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

# 5. Configurar variables de entorno
echo "[5/7] Configurando variables de entorno..."
if [ ! -f .env ]; then
    cp .env.example .env
    echo ""
    echo "================================================"
    echo "  IMPORTANTE: Edita el archivo .env para agregar"
    echo "  tu API_FOOTBALL_KEY"
    echo ""
    echo "  nano /home/ubuntu/agente-apuestas/.env"
    echo "================================================"
    echo ""
    echo "Si ya tienes tu API key, pégala ahora:"
    read -p "API_FOOTBALL_KEY (dejar vacío para configurar después): " API_KEY
    if [ -n "$API_KEY" ]; then
        echo "API_FOOTBALL_KEY=$API_KEY" > .env
        echo "¡API key configurada!"
    fi
fi

# 6. Configurar systemd service (para que inicie automáticamente)
echo "[6/7] Configurando servicio systemd..."
sudo tee /etc/systemd/system/agente-apuestas.service > /dev/null << EOF
[Unit]
Description=Agente de Apuestas Deportivas
After=network.target

[Service]
User=ubuntu
WorkingDirectory=/home/ubuntu/agente-apuestas
ExecStart=/home/ubuntu/agente-apuestas/venv/bin/uvicorn web.app:app --host 0.0.0.0 --port 8000
Restart=always
RestartSec=10
Environment=PATH=/home/ubuntu/agente-apuestas/venv/bin

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable agente-apuestas
sudo systemctl start agente-apuestas

# 7. Configurar firewall
echo "[7/7] Configurando firewall..."
sudo ufw allow 22/tcp   # SSH
sudo ufw allow 8000/tcp # App web
sudo ufw --force enable

echo ""
echo "================================================"
echo "  ¡INSTALACIÓN COMPLETADA!"
echo ""
echo "  La app está corriendo en: http://TU_IP_PUBLICA:8000"
echo ""
echo "  Para ver tu IP pública:"
echo "    curl ifconfig.me"
echo ""
echo "  Para ver el estado del servicio:"
echo "    sudo systemctl status agente-apuestas"
echo ""
echo "  Para ver los logs:"
echo "    sudo journalctl -u agente-apuestas -f"
echo ""
echo "  Para reiniciar:"
echo "    sudo systemctl restart agente-apuestas"
echo ""
echo "  Para detener:"
echo "    sudo systemctl stop agente-apuestas"
echo "================================================"
