#!/bin/bash
# Radar Imóveis Pro - Script de Deploy
cd /var/www/radarimoveispro

echo "🔄 Puxando alterações do GitHub..."
git pull origin main

echo "📦 Instalando dependências novas (se houver)..."
source venv/bin/activate
pip install -r requirements.txt -q

echo "⚙️ Ajustando permissões..."
chown -R radar:radar .
chmod 640 .env

echo "🔄 Reiniciando serviço..."
systemctl restart radar

echo "✅ Deploy concluído!"
