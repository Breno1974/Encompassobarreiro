#!/bin/bash
set -e

# A URL precisa ser a da sua aplicação. Verifique no painel do Render se está correta.
# A rota /api/profiles era do projeto Next.js. Para o projeto Python, precisamos de uma rota válida.
# Vamos assumir que você tem uma rota principal que faz alguma consulta.
# Se sua app Python não tiver uma rota de API, podemos usar a rota principal ('/').

APP_URL="https://encompassobarreiro.onrender.com" 

echo "Iniciando ping no $APP_URL para manter o Supabase ativo..."
curl -sS --fail "$APP_URL" > /dev/null
echo "Ping concluído com sucesso."
