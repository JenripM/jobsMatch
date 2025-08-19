#!/bin/bash
# Script de build para Render que soluciona el problema de grpcio

echo "🔧 Configurando variables de entorno para grpcio..."
export GRPC_BUILD_WITH_BORING_SSL_ASM=""
export GRPC_PYTHON_BUILD_SYSTEM_RE2=true
export GRPC_PYTHON_BUILD_SYSTEM_OPENSSL=true
export GRPC_PYTHON_BUILD_SYSTEM_ZLIB=true

echo "📦 Instalando wheel primero..."
pip install wheel

echo "📦 Instalando dependencias..."
pip install -r requirements.txt

echo "✅ Build completado exitosamente"
