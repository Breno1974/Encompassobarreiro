from flask import Flask, render_template, request, redirect, url_for, jsonify, send_file, session, flash
import psycopg2
import psycopg2.extras
import pandas as pd
import os
from datetime import datetime
import io
import hashlib
import urllib.parse
import hashlib
import secrets
import base64

app = Flask(__name__)
app.secret_key = 'encompasso_barreiro_2025_secret_key'

DATABASE_URL = os.environ.get('DATABASE_URL', 'postgresql://postgres.sicpojvzkdbilqykviqm:MTX8E6rS0pEJVP2a@aws-0-sa-east-1.pooler.supabase.com:6543/postgres')

def hash_password(password):
    """Gera hash seguro da senha com salt"""
    salt = secrets.token_bytes(32)  # 32 bytes de salt aleatório
    pwdhash = hashlib.pbkdf2_hmac(
        'sha256', 
        password.encode('utf-8'), 
        salt, 
        100000  # Número de iterações, pode ser ajustado
    )
    return base64.b64encode(salt + pwdhash).decode('utf-8')

def check_password(password, hashed):
    """Verifica se a senha confere com o hash"""
    try:
        decoded = base64.b64decode(hashed.encode('utf-8'))
        salt = decoded[:32]  # Primeiros 32 bytes são o salt
        stored_hash = decoded[32:]  # Resto é o hash
        pwdhash = hashlib.pbkdf2_hmac(
            'sha256', 
            password.encode('utf-8'), 
            salt, 
            100000  # Mesmo número de iterações usado no hash_password
        )
        return pwdhash == stored_hash
    except:
        return False
    
def gerar_token_unico():
    """Gera um token seguro e aleatório para os links."""
    return secrets.token_urlsafe(16)


def is_logged_in():
    return session.get('admin_logged_in', False)

def init_db():
    conn = psycopg2.connect(DATABASE_URL)
    cursor = conn.cursor()

    # Tabela de usuários administrativos
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS admin_users (
            id SERIAL PRIMARY KEY,
            username VARCHAR(50) UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_login TIMESTAMP
        )
    ''')

    # Nova tabela específica para materiais
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS materiais (
            id SERIAL PRIMARY KEY,
            servidor TEXT,
            nome TEXT,
            telefone TEXT,
            detalhes_materiais TEXT,
            total_itens_pedido INTEGER,
            total DECIMAL(10,2),
            tipo_pagamento TEXT,
            data_vencimento DATE,
            data_criacao TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # Nova tabela específica para inscrições
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS inscricoes (
            id SERIAL PRIMARY KEY,
            servidor TEXT,
            nome TEXT,
            telefone TEXT,
            tipo_pagamento TEXT,
            data_vencimento DATE,
            tipo_quarto TEXT,
            valor_quarto DECIMAL(10,2),
            valor_entrada DECIMAL(10,2),
            valor_restante DECIMAL(10,2),
            data_criacao TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS servidores (
            id SERIAL PRIMARY KEY,
            nome TEXT UNIQUE NOT NULL,
            ativo BOOLEAN DEFAULT TRUE,
            data_criacao TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # Inserir usuário admin padrão se não existir
    cursor.execute("SELECT COUNT(*) FROM admin_users WHERE username = 'admin'")
    if cursor.fetchone()[0] == 0:
        admin_password_hash = hash_password('senha123')
        cursor.execute(
            "INSERT INTO admin_users (username, password_hash) VALUES (%s, %s)",
            ('admin', admin_password_hash)
        )

    # Inserir servidores padrão
    cursor.execute("SELECT COUNT(*) FROM servidores")
    if cursor.fetchone()[0] == 0:
        servidores_padrao = ['Fabiano', 'Luciano', 'Breno']
        for servidor in servidores_padrao:
            cursor.execute("INSERT INTO servidores (nome) VALUES (%s) ON CONFLICT (nome) DO NOTHING", (servidor,))

    conn.commit()
    conn.close()

def get_servidores_ativos():
    conn = psycopg2.connect(DATABASE_URL)
    cursor = conn.cursor()
    cursor.execute("SELECT nome FROM servidores WHERE ativo = TRUE ORDER BY nome")
    servidores = [row[0] for row in cursor.fetchall()]
    conn.close()
    return servidores

def enviar_whatsapp_materiais(telefone, dados_registro):
    telefone_limpo = ''.join(filter(str.isdigit, telefone))
    
    if not telefone_limpo.startswith('55'):
        telefone_limpo = '55' + telefone_limpo
    
    mensagem = f"""🎯 *II Encompasso CSA Barreiro*
📋 *Resumo do seu pedido de materiais:*

👤 *Nome:* {dados_registro.get('nome', '')}
📱 *Telefone:* {dados_registro.get('telefone', '')}
🏢 *Servidor:* {dados_registro.get('servidor', '')}

📦 *Materiais solicitados:*"""

    # Adicionar materiais selecionados
    materiais_info = dados_registro.get('materiais_info', [])
    for material in materiais_info:
        mensagem += f"\n🎁 {material['tipo']} - Qtd: {material['quantidade']}"
        if material['tipo'] == 'Outro' and material.get('especificacao'):
            mensagem += f" ({material['especificacao']})"

    mensagem += f"\n\n💵 *Total:* {dados_registro.get('total', '')}"
    mensagem += f"\n📅 *Tipo Pagamento:* {dados_registro.get('tipo_pagamento', '').replace('_', ' ').title()}"
    
    if dados_registro.get('data_vencimento'):
        mensagem += f"\n⏰ *Vencimento:* {dados_registro.get('data_vencimento', '')}"

    mensagem += f"\n💳 *PIX:* Materialpromocional.barreiro@gmail.com"
    mensagem += f"\n\n✅ *Pedido registrado com sucesso!*"
    mensagem += f"\n\n_Buscando Dentro de Si_ 🙏"

    mensagem_codificada = urllib.parse.quote(mensagem)
    url_whatsapp = f"https://wa.me/{telefone_limpo}?text={mensagem_codificada}"
    
    return url_whatsapp

def enviar_whatsapp_inscricoes(telefone, dados_registro):
    telefone_limpo = ''.join(filter(str.isdigit, telefone))
    
    if not telefone_limpo.startswith('55'):
        telefone_limpo = '55' + telefone_limpo
    
    mensagem = f"""🎯 *II Encompasso CSA Barreiro*
📋 *Resumo da sua inscrição:*

👤 *Nome:* {dados_registro.get('nome', '')}
📱 *Telefone:* {dados_registro.get('telefone', '')}
🏢 *Servidor:* {dados_registro.get('servidor', '')}

🏨 *Tipo de Quarto:* {dados_registro.get('tipo_quarto', '').replace('_', ' ').title()}
💰 *Valor do Quarto:* {dados_registro.get('valor_quarto', '')}"""

    if dados_registro.get('tipo_pagamento') == 'fiado':
        mensagem += f"\n💵 *Valor de Entrada:* {dados_registro.get('valor_entrada', 'R$ 0,00')}"
        mensagem += f"\n💳 *Valor Restante:* {dados_registro.get('valor_restante', '')}"
        if dados_registro.get('data_vencimento'):
            mensagem += f"\n⏰ *Vencimento:* {dados_registro.get('data_vencimento', '')}"

    mensagem += f"\n📅 *Tipo Pagamento:* {dados_registro.get('tipo_pagamento', '').replace('_', ' ').title()}"
    mensagem += f"\n💳 *PIX:* eventos.csabarreiro@gmail.com"
    mensagem += f"\n\n✅ *Inscrição realizada com sucesso!*"
    mensagem += f"\n\n_Buscando Dentro de Si_ 🙏"

    mensagem_codificada = urllib.parse.quote(mensagem)
    url_whatsapp = f"https://wa.me/{telefone_limpo}?text={mensagem_codificada}"
    
    return url_whatsapp

# ==================== ROTAS PRINCIPAIS ====================

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/materiais')
def materiais():
    servidores = get_servidores_ativos()
    return render_template('materiais.html', servidores=servidores)

@app.route('/inscricao')
def inscricao():
    servidores = get_servidores_ativos()
    return render_template('inscricao.html', servidores=servidores)

@app.route('/c/<string:token>') # 'c' de convite
def pagina_de_resposta_convite(token):
    """
    Esta é a página que o associado vê ao clicar no link do WhatsApp.
    O token identifica unicamente o convite enviado a ele.
    """
    conn = psycopg2.connect(DATABASE_URL)
    cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    try:
        # =================================================================
        # ===== CORREÇÃO FINAL AQUI =====
        # Trocamos 'cv.titulo' por 'cv.titulo_campanha'
        # e 'cv.descricao' por 'cv.mensagem_personalizada'.
        # =================================================================
        cursor.execute("""
            SELECT 
                rc.id as resposta_id,
                rc.tipo_resposta_selecionada,
                rc.participar_corpo_servico,
                a.nome_completo,
                cv.titulo_campanha as titulo_convite,
                cv.mensagem_personalizada as descricao_convite
            FROM respostas_convites rc
            JOIN associados a ON rc.associado_id = a.id
            JOIN convites cv ON rc.convite_id = cv.id
            WHERE rc.token_unico = %s
        """, (token,))
        
        dados_convite = cursor.fetchone()

    except Exception as e:
        print(f"Erro na página de resposta do convite: {e}")
        return "Ocorreu um erro ao carregar os dados do convite.", 500
    finally:
        conn.close()

    if not dados_convite:
        # Se o token não for encontrado, o link é inválido
        return "Link inválido ou expirado.", 404

    # Passa os dados para o template renderizar a página
    return render_template('pagina_resposta_convite.html', dados=dados_convite, token=token)


@app.route('/c/salvar', methods=['POST'])
def salvar_resposta_convite():
    """
    Processa o formulário enviado pelo associado.
    """
    token = request.form.get('token')
    resposta = request.form.get('interesse') # Ex: 'quero_inscrever'
    servico = 'servico' in request.form      # True se o checkbox foi marcado

    if not token or not resposta:
        flash('Ocorreu um erro. Por favor, tente novamente.', 'error')
        return redirect(url_for('index')) # Redireciona para a home em caso de erro

    conn = psycopg2.connect(DATABASE_URL)
    cursor = conn.cursor()

    try:
        # Atualiza a tabela respostas_convites com a escolha do associado
        cursor.execute("""
            UPDATE respostas_convites
            SET tipo_resposta_selecionada = %s,
                participar_corpo_servico = %s,
                data_resposta = CURRENT_TIMESTAMP
            WHERE token_unico = %s
        """, (resposta, servico, token))
        
        conn.commit()
    except Exception as e:
        conn.rollback()
        print(f"Erro ao salvar resposta: {e}") # Log do erro no console do servidor
        flash('Não foi possível salvar sua resposta. Tente novamente.', 'error')
        return redirect(url_for('pagina_de_resposta_convite', token=token))
    finally:
        conn.close()

    # Redireciona para uma página de agradecimento
    return redirect(url_for('pagina_agradecimento'))


@app.route('/agradecimento')
def pagina_agradecimento():
    """Página simples de confirmação com um botão para fechar a aba."""
    return '''
    <!DOCTYPE html>
    <html lang="pt-br">
    <head>
        <meta charset="UTF-8">
        <title>Obrigado!</title>
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css" rel="stylesheet">
        <link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css" rel="stylesheet">
        <style>
            body { 
                display: flex; 
                align-items: center; 
                justify-content: center; 
                min-height: 100vh; 
                background-color: #f4f7f6; 
                font-family: 'Segoe UI', sans-serif;
            }
            .card { 
                text-align: center; 
                padding: 40px; 
                border: none; 
                border-radius: 15px; 
                box-shadow: 0 6px 20px rgba(0,0,0,0.08 ); 
                max-width: 90%;
                width: 500px;
            }
            .icon-success { 
                font-size: 5rem; 
                color: #28a745; 
            }
            .btn-close-page {
                background-color: #6c757d;
                border-color: #6c757d;
            }
            .btn-close-page:hover {
                background-color: #5a6268;
                border-color: #5a6268;
            }
        </style>
    </head>
    <body>
        <div class="card">
            <i class="fas fa-check-circle icon-success mb-3"></i>
            <h2 class="card-title">Obrigado!</h2>
            <p class="lead text-muted">Sua resposta foi registrada com sucesso.</p>
           
        </div>
        <script>
            // Fallback para navegadores que não permitem window.close() diretamente
            // A maioria dos navegadores modernos só fecha janelas abertas por script.
            // Este script não garante o fechamento, mas é a melhor abordagem possível.
            const closeButton = document.querySelector('.btn-close-page');
            closeButton.addEventListener('click', () => {
                // Tenta fechar a janela. Se não funcionar, o usuário terá que fechar manualmente.
                window.open('', '_self').close();
            });
        </script>
    </body>
    </html>
    '''


# ==================== ROTAS DE AUTENTICAÇÃO ====================

@app.route('/admin')
def admin_redirect():
    """Redireciona para login se não estiver logado, senão para admin"""
    if is_logged_in():
        return redirect(url_for('admin_dashboard'))
    return redirect(url_for('admin_login'))

@app.route('/admin/login')
def admin_login():
    """Página de login administrativo"""
    if is_logged_in():
        return redirect(url_for('admin_dashboard'))
    return render_template('admin_login.html')

@app.route('/admin/login', methods=['POST'])
def admin_login_post():
    """Processa login administrativo"""
    username = request.form.get('username')
    password = request.form.get('password')
    
    if not username or not password:
        flash('Usuário e senha são obrigatórios', 'error')
        return redirect(url_for('admin_login'))
    
    conn = psycopg2.connect(DATABASE_URL)
    cursor = conn.cursor()
    
    cursor.execute("SELECT password_hash FROM admin_users WHERE username = %s", (username,))
    result = cursor.fetchone()
    
    if result and check_password(password, result[0]):
        session['admin_logged_in'] = True
        session['admin_username'] = username
        
        # Atualizar último login
        cursor.execute("UPDATE admin_users SET last_login = CURRENT_TIMESTAMP WHERE username = %s", (username,))
        conn.commit()
        
        flash('Login realizado com sucesso!', 'success')
        conn.close()
        return redirect(url_for('admin_dashboard'))
    else:
        flash('Usuário ou senha incorretos', 'error')
        conn.close()
        return redirect(url_for('admin_login'))

@app.route('/admin/logout')
def admin_logout():
    """Logout administrativo"""
    session.pop('admin_logged_in', None)
    session.pop('admin_username', None)
    flash('Logout realizado com sucesso!', 'success')
    return redirect(url_for('index'))

@app.route('/admin/dashboard')
def admin_dashboard():
    """Dashboard administrativo principal"""
    if not is_logged_in():
        return redirect(url_for('admin_login'))
    
    return render_template('admin_dashboard.html')


# ==================================================
# ========= API PARA GERENCIAMENTO DE CONVITES (CORRIGIDO) =========
# ==================================================

@app.route('/admin/api/convites/<int:convite_id>', methods=['DELETE'])
def admin_api_delete_convite(convite_id):
    """API para excluir uma campanha de convite (e suas respostas associadas)."""
    if not is_logged_in():
        return jsonify({'error': 'Não autorizado'}), 401

    conn = psycopg2.connect(DATABASE_URL)
    cursor = conn.cursor()
    try:
        # A exclusão em cascata (ON DELETE CASCADE) na tabela 'respostas_convites'
        # garantirá que todas as respostas vinculadas também sejam removidas.
        cursor.execute("DELETE FROM convites WHERE id = %s", (convite_id,))
        
        # Verificar se algo foi realmente excluído
        if cursor.rowcount == 0:
            conn.close()
            return jsonify({'error': 'Convite não encontrado'}), 404

        conn.commit()
        return jsonify({'success': True, 'message': 'Convite excluído com sucesso!'})
    except Exception as e:
        conn.rollback()
        print(f"Erro em admin_api_delete_convite: {e}")
        return jsonify({'error': str(e)}), 500
    finally:
        conn.close()


@app.route('/admin/api/convites', methods=['GET'])
def admin_api_get_convites():
    """API para listar todos os convites criados (AJUSTADO PARA SEU SCHEMA)."""
    if not is_logged_in():
        return jsonify({'error': 'Não autorizado'}), 401
    
    conn = psycopg2.connect(DATABASE_URL)
    cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    
    try:
        # AJUSTE: Usando 'c.titulo_campanha' em vez de 'c.titulo'
        cursor.execute("""
            SELECT 
                c.id, 
                c.titulo_campanha,
                c.mensagem_personalizada,
                c.data_criacao,
                (SELECT COUNT(*) FROM respostas_convites rc WHERE rc.convite_id = c.id AND rc.data_resposta IS NOT NULL) as total_respostas
            FROM convites c
            ORDER BY c.data_criacao DESC
        """)
        convites = cursor.fetchall()
        conn.close()
        
        result = []
        for convite in convites:
            item = dict(convite)
            # AJUSTE: Renomeando a chave para 'titulo' para que o frontend funcione sem alterações.
            if 'titulo_campanha' in item:
                item['titulo'] = item.pop('titulo_campanha')
            
            # O frontend espera 'descricao' e 'mensagem_whatsapp', vamos fornecer a mesma coisa para ambos.
            if 'mensagem_personalizada' in item:
                item['descricao'] = item['mensagem_personalizada']
                item['mensagem_whatsapp'] = item['mensagem_personalizada']

            if item.get('data_criacao'):
                item['data_criacao'] = item['data_criacao'].isoformat()
            result.append(item)
            
        return jsonify(result)

    except Exception as e:
        conn.close()
        print(f"Erro em admin_api_get_convites: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/admin/api/convites', methods=['POST'])
def admin_api_create_convite():
    """API para criar um novo convite (AJUSTADO PARA SEU SCHEMA)."""
    if not is_logged_in():
        return jsonify({'error': 'Não autorizado'}), 401
        
    data = request.get_json()
    # AJUSTE: O frontend envia 'titulo' e 'mensagem_whatsapp'.
    titulo = data.get('titulo')
    mensagem = data.get('mensagem_whatsapp')

    if not titulo or not mensagem:
        return jsonify({'error': 'Título e Mensagem são obrigatórios'}), 400

    conn = psycopg2.connect(DATABASE_URL)
    cursor = conn.cursor()
    try:
        # AJUSTE: Inserindo nas colunas 'titulo_campanha' e 'mensagem_personalizada'.
        cursor.execute(
            "INSERT INTO convites (titulo_campanha, mensagem_personalizada, responsavel_envio) VALUES (%s, %s, %s) RETURNING id",
            (titulo, mensagem, session.get('admin_username'))
        )
        convite_id = cursor.fetchone()[0]
        conn.commit()
        return jsonify({'success': True, 'message': 'Convite criado com sucesso!', 'id': convite_id})
    except Exception as e:
        conn.rollback()
        print(f"Erro em admin_api_create_convite: {e}")
        return jsonify({'error': str(e)}), 500
    finally:
        conn.close()

@app.route('/admin/api/convites/<int:convite_id>', methods=['PUT'])
def admin_api_update_convite(convite_id):
    """API para atualizar um convite (AJUSTADO PARA SEU SCHEMA)."""
    if not is_logged_in():
        return jsonify({'error': 'Não autorizado'}), 401
        
    data = request.get_json()
    titulo = data.get('titulo')
    mensagem = data.get('mensagem_whatsapp')

    if not titulo or not mensagem:
        return jsonify({'error': 'Título e Mensagem são obrigatórios'}), 400

    conn = psycopg2.connect(DATABASE_URL)
    cursor = conn.cursor()
    try:
        # AJUSTE: Atualizando as colunas 'titulo_campanha' e 'mensagem_personalizada'.
        cursor.execute(
            "UPDATE convites SET titulo_campanha = %s, mensagem_personalizada = %s WHERE id = %s",
            (titulo, mensagem, convite_id)
        )
        conn.commit()
        return jsonify({'success': True, 'message': 'Convite atualizado com sucesso!'})
    except Exception as e:
        conn.rollback()
        print(f"Erro em admin_api_update_convite: {e}")
        return jsonify({'error': str(e)}), 500
    finally:
        conn.close()

@app.route('/admin/api/convites/<int:convite_id>/respostas', methods=['GET'])
def get_respostas_convite(convite_id):
    """Busca respostas de um convite (AJUSTADO PARA SEU SCHEMA DE ASSOCIADOS)."""
    if not is_logged_in():
        return jsonify({'error': 'Não autorizado'}), 401

    conn = psycopg2.connect(DATABASE_URL)
    cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    
    try:
        # =================================================================
        # ===== CORREÇÃO PRINCIPAL AQUI =====
        # Trocamos 'a.telefone' por 'a.telefone_formatado' na query SQL.
        # =================================================================
        cursor.execute("""
            SELECT 
                rc.id,
                rc.token_unico,
                rc.data_resposta,
                rc.tipo_resposta_selecionada,
                rc.participar_corpo_servico,
                a.nome_completo,
                a.telefone_formatado,
                a.regiao_atuacao,  -- <<< LINHA ADICIONADA
                cv.mensagem_personalizada
            FROM respostas_convites rc
            JOIN associados a ON rc.associado_id = a.id
            JOIN convites cv ON rc.convite_id = cv.id
            WHERE rc.convite_id = %s
            ORDER BY a.nome_completo
        """, (convite_id,))
        
        respostas = cursor.fetchall()
        
        for resposta in respostas:
            resposta['link_unico'] = url_for('pagina_de_resposta_convite', token=resposta['token_unico'], _external=True)
            

            if resposta.get('data_resposta'):
                resposta['data_resposta'] = resposta['data_resposta'].isoformat()

        return jsonify(respostas)

            

    except Exception as e:
        print(f"Erro em get_respostas_convite: {e}")
        return jsonify({'error': f'Erro ao buscar respostas: {str(e)}'}), 500
    finally:
        conn.close()


# ==================== ROTAS DE DADOS ADMINISTRATIVOS ====================

@app.route('/admin/api/convites/<int:convite_id>/exportar', methods=['GET'])
def exportar_respostas_convite(convite_id):
    """Exporta os dados de envio e resposta de uma campanha para Excel."""
    if not is_logged_in():
        return redirect(url_for('admin_login'))

    try:
        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        # Query para buscar todos os dados necessários
        cursor.execute("""
            SELECT 
                a.nome_completo,
                a.telefone_formatado,
                a.regiao_atuacao AS csa,
                rc.tipo_resposta_selecionada AS status_resposta,
                rc.participar_corpo_servico,
                rc.data_resposta,
                rc.token_unico
            FROM respostas_convites rc
            JOIN associados a ON rc.associado_id = a.id
            WHERE rc.convite_id = %s
            ORDER BY a.nome_completo
        """, (convite_id,))
        
        dados = cursor.fetchall()
        conn.close()

        if not dados:
            flash('Nenhum dado para exportar para esta campanha.', 'warning')
            return redirect(url_for('admin_dashboard', active_tab='convites'))

        # Processar os dados e criar o link único
        df_data = []
        for item in dados:
            link_unico = url_for('pagina_de_resposta_convite', token=item['token_unico'], _external=True)
            df_data.append({
                'Nome Completo': item['nome_completo'],
                'Telefone': item['telefone_formatado'],
                'CSA': item['csa'],
                'Link Único': link_unico,
                'Status da Resposta': item['status_resposta'],
                'Quer Servir': 'Sim' if item['participar_corpo_servico'] else 'Não',
                'Data da Resposta': item['data_resposta']
            })
        
        df = pd.DataFrame(df_data)

        # Criar o arquivo Excel em memória
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, sheet_name=f'Respostas_Convite_{convite_id}', index=False)
        output.seek(0)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"export_convite_{convite_id}_{timestamp}.xlsx"
        
        return send_file(
            output,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            as_attachment=True,
            download_name=filename
        )

    except Exception as e:
        print(f"Erro ao exportar dados do convite: {e}")
        flash(f"Erro ao exportar dados: {e}", "error")
        return redirect(url_for('admin_dashboard', active_tab='convites'))




@app.route('/admin/api/convites/<int:convite_id>/preparar-envio', methods=['POST'])
def preparar_envio_convite(convite_id):
    """
    Prepara os registros na tabela 'respostas_convites' para todos os associados,
    gerando um token único para cada um e definindo a resposta inicial como 'pendente'.
    """
    if not is_logged_in():
        return jsonify({'error': 'Não autorizado'}), 401

    conn = psycopg2.connect(DATABASE_URL)
    cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    
    try:
        # 1. Buscar todos os associados
        cursor.execute("SELECT id FROM associados")
        associados = cursor.fetchall()
        
        if not associados:
            return jsonify({'error': 'Nenhum associado encontrado no banco de dados.'}), 404

        # 2. Inserir um registro para cada associado na tabela de respostas.
        #    Ajustado para incluir 'tipo_resposta_selecionada' para cumprir o NOT NULL.
        #    O campo 'data_resposta' será deixado como NULL.
        sql_insert = """
            INSERT INTO respostas_convites (convite_id, associado_id, token_unico, tipo_resposta_selecionada, data_resposta)
            VALUES (%s, %s, %s, 'pendente', NULL)
            ON CONFLICT (convite_id, associado_id) DO NOTHING;
        """
        
        registros_inseridos = 0
        for associado in associados:
            token = gerar_token_unico()
            cursor.execute(sql_insert, (convite_id, associado['id'], token))
            registros_inseridos += cursor.rowcount # rowcount será 1 para inserção, 0 para conflito

        conn.commit()
        
        if registros_inseridos == 0:
            message = 'Todos os associados já estavam preparados para esta campanha.'
        else:
            message = f'{registros_inseridos} novos convites preparados para envio.'

        return jsonify({'success': True, 'message': message})

    except Exception as e:
        conn.rollback()
        # Log do erro para depuração no servidor
        print(f"Erro em preparar_envio_convite: {e}")
        return jsonify({'error': f'Erro ao preparar envios: {str(e)}'}), 500
    finally:
        conn.close()


@app.route('/admin/api/materiais')
def admin_api_materiais():
    """API para listar materiais com filtros"""
    if not is_logged_in():
        return jsonify({'error': 'Não autorizado'}), 401
    
    # Parâmetros de filtro
    servidor = request.args.get('servidor', '')
    nome = request.args.get('nome', '')
    telefone = request.args.get('telefone', '')
    tipo_pagamento = request.args.get('tipo_pagamento', '')
    
    conn = psycopg2.connect(DATABASE_URL)
    cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    
    query = """
        SELECT id, servidor, nome, telefone, detalhes_materiais, total_itens_pedido, 
               total, tipo_pagamento, data_vencimento, data_criacao
        FROM materiais 
        WHERE 1=1
    """
    params = []
    
    if servidor:
        query += " AND servidor ILIKE %s"
        params.append(f"%{servidor}%")
    if nome:
        query += " AND nome ILIKE %s"
        params.append(f"%{nome}%")
    if telefone:
        query += " AND telefone ILIKE %s"
        params.append(f"%{telefone}%")
    if tipo_pagamento:
        query += " AND tipo_pagamento = %s"
        params.append(tipo_pagamento)
    
    query += " ORDER BY data_criacao DESC"
    
    cursor.execute(query, params)
    materiais = cursor.fetchall()
    conn.close()
    
    # Converter para formato JSON serializável
    result = []
    for material in materiais:
        item = dict(material)
        if item['data_vencimento']:
            item['data_vencimento'] = item['data_vencimento'].strftime('%Y-%m-%d')
        if item['data_criacao']:
            item['data_criacao'] = item['data_criacao'].strftime('%Y-%m-%d %H:%M:%S')
        if item['total']:
            item['total'] = float(item['total'])
        result.append(item)
    
    return jsonify(result)

@app.route('/admin/api/inscricoes')
def admin_api_inscricoes():
    """API para listar inscrições com filtros"""
    if not is_logged_in():
        return jsonify({'error': 'Não autorizado'}), 401

    # --- INÍCIO DO CÓDIGO FALTANTE ---

    # Parâmetros de filtro
    servidor = request.args.get('servidor', '')
    nome = request.args.get('nome', '')
    telefone = request.args.get('telefone', '')
    tipo_pagamento = request.args.get('tipo_pagamento', '')
    
    conn = psycopg2.connect(DATABASE_URL)
    cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    
    query = """
        SELECT id, servidor, nome, telefone, tipo_pagamento, data_vencimento, 
               tipo_quarto, valor_quarto, valor_entrada, valor_restante, data_criacao, observacao
        FROM inscricoes 
        WHERE 1=1
    """
    params = []
    
    if servidor:
        query += " AND servidor ILIKE %s"
        params.append(f"%{servidor}%")
    if nome:
        query += " AND nome ILIKE %s"
        params.append(f"%{nome}%")
    if telefone:
        query += " AND telefone ILIKE %s"
        params.append(f"%{telefone}%")
    if tipo_pagamento:
        query += " AND tipo_pagamento = %s"
        params.append(tipo_pagamento)
    
    query += " ORDER BY data_criacao DESC"
    
    cursor.execute(query, params)
    inscricoes = cursor.fetchall()
    conn.close()
    
    # Converter para formato JSON serializável
    result = []
    for inscricao in inscricoes:
        item = dict(inscricao)
        if item.get('data_vencimento'):
            item['data_vencimento'] = item['data_vencimento'].strftime('%Y-%m-%d')
        if item.get('data_criacao'):
            item['data_criacao'] = item['data_criacao'].strftime('%Y-%m-%d %H:%M:%S')
        # Converter Decimals para float para serialização JSON
        for key in ['valor_quarto', 'valor_entrada', 'valor_restante']:
            if item.get(key) is not None:
                item[key] = float(item[key])
        result.append(item)
    
    return jsonify(result) # <-- Este `return` é crucial

    # --- FIM DO CÓDIGO FALTANTE ---

    
    # ==================== ROTAS DE GERENCIAMENTO DE SERVIDORES ====================

@app.route('/admin/api/servidores')
def admin_api_servidores():
    """API para listar servidores com filtros"""
    if not is_logged_in():
        return jsonify({'error': 'Não autorizado'}), 401
    
    # Parâmetros de filtro
    nome = request.args.get('nome', '')
    status = request.args.get('status', '')  # 'ativo', 'inativo', ou '' para todos
    
    conn = psycopg2.connect(DATABASE_URL)
    cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    
    query = """
        SELECT id, nome, ativo, data_criacao,
               (SELECT COUNT(*) FROM materiais WHERE servidor = servidores.nome) as total_materiais,
               (SELECT COUNT(*) FROM inscricoes WHERE servidor = servidores.nome) as total_inscricoes
        FROM servidores 
        WHERE 1=1
    """
    params = []
    
    if nome:
        query += " AND nome ILIKE %s"
        params.append(f"%{nome}%")
    if status == 'ativo':
        query += " AND ativo = TRUE"
    elif status == 'inativo':
        query += " AND ativo = FALSE"
    
    query += " ORDER BY nome"
    
    cursor.execute(query, params)
    servidores = cursor.fetchall()
    conn.close()
    
    # Converter para formato JSON serializável
    result = []
    for servidor in servidores:
        item = dict(servidor)
        if item['data_criacao']:
            item['data_criacao'] = item['data_criacao'].strftime('%Y-%m-%d %H:%M:%S')
        result.append(item)
    
    return jsonify(result)

@app.route('/admin/api/servidores', methods=['POST'])
def admin_api_servidores_create():
    """API para criar novo servidor"""
    if not is_logged_in():
        return jsonify({'error': 'Não autorizado'}), 401
    
    data = request.get_json()
    nome = data.get('nome', '').strip()
    
    if not nome:
        return jsonify({'error': 'Nome do servidor é obrigatório'}), 400
    
    conn = psycopg2.connect(DATABASE_URL)
    cursor = conn.cursor()
    
    try:
        cursor.execute(
            "INSERT INTO servidores (nome, ativo) VALUES (%s, TRUE) RETURNING id",
            (nome,)
        )
        servidor_id = cursor.fetchone()[0]
        conn.commit()
        
        return jsonify({
            'success': True, 
            'message': f'Servidor "{nome}" criado com sucesso!',
            'id': servidor_id
        })
    except psycopg2.IntegrityError:
        conn.rollback()
        return jsonify({'error': f'Servidor "{nome}" já existe'}), 400
    except Exception as e:
        conn.rollback()
        return jsonify({'error': f'Erro ao criar servidor: {str(e)}'}), 500
    finally:
        conn.close()

@app.route('/admin/api/servidores/<int:servidor_id>/toggle', methods=['POST'])
def admin_api_servidores_toggle(servidor_id):
    """API para ativar/inativar servidor"""
    if not is_logged_in():
        return jsonify({'error': 'Não autorizado'}), 401
    
    conn = psycopg2.connect(DATABASE_URL)
    cursor = conn.cursor()
    
    try:
        # Verificar se servidor existe e obter status atual
        cursor.execute("SELECT nome, ativo FROM servidores WHERE id = %s", (servidor_id,))
        result = cursor.fetchone()
        
        if not result:
            return jsonify({'error': 'Servidor não encontrado'}), 404
        
        nome, ativo_atual = result
        novo_status = not ativo_atual
        
        # Atualizar status
        cursor.execute(
            "UPDATE servidores SET ativo = %s WHERE id = %s",
            (novo_status, servidor_id)
        )
        conn.commit()
        
        status_texto = "ativado" if novo_status else "inativado"
        return jsonify({
            'success': True,
            'message': f'Servidor "{nome}" {status_texto} com sucesso!',
            'novo_status': novo_status
        })
    except Exception as e:
        conn.rollback()
        return jsonify({'error': f'Erro ao alterar status: {str(e)}'}), 500
    finally:
        conn.close()

@app.route('/admin/api/servidores/<int:servidor_id>', methods=['PUT'])
def admin_api_servidores_update(servidor_id):
    """API para editar servidor"""
    if not is_logged_in():
        return jsonify({'error': 'Não autorizado'}), 401
    
    data = request.get_json()
    novo_nome = data.get('nome', '').strip()
    # --- MUDANÇA 1: Obter o status da requisição ---
    ativo = data.get('ativo') 

    if not novo_nome:
        return jsonify({'error': 'Nome do servidor é obrigatório'}), 400
    
    # Validação para o campo 'ativo'
    if ativo is None or not isinstance(ativo, bool):
        return jsonify({'error': 'O status (ativo/inativo) é inválido.'}), 400

    conn = psycopg2.connect(DATABASE_URL)
    cursor = conn.cursor()
    
    try:
        cursor.execute("SELECT nome FROM servidores WHERE id = %s", (servidor_id,))
        result = cursor.fetchone()
        
        if not result:
            return jsonify({'error': 'Servidor não encontrado'}), 404
        
        nome_antigo = result[0]
        
        # --- MUDANÇA 2: Atualizar NOME e STATUS na mesma query ---
        cursor.execute(
            "UPDATE servidores SET nome = %s, ativo = %s WHERE id = %s",
            (novo_nome, ativo, servidor_id)
        )
        
        # Se o nome mudou, atualiza as referências
        if novo_nome != nome_antigo:
            cursor.execute(
                "UPDATE materiais SET servidor = %s WHERE servidor = %s",
                (novo_nome, nome_antigo)
            )
            cursor.execute(
                "UPDATE inscricoes SET servidor = %s WHERE servidor = %s",
                (novo_nome, nome_antigo)
            )
        
        conn.commit()
        
        return jsonify({
            'success': True,
            'message': f'Servidor "{novo_nome}" atualizado com sucesso!'
        })
    except psycopg2.IntegrityError:
        conn.rollback()
        return jsonify({'error': f'O nome de servidor "{novo_nome}" já existe.'}), 400
    except Exception as e:
        conn.rollback()
        return jsonify({'error': f'Erro ao atualizar servidor: {str(e)}'}), 500
    finally:
        conn.close()
@app.route('/admin/api/servidores/<int:servidor_id>', methods=['DELETE'])
def admin_api_servidores_delete(servidor_id):
    """API para excluir servidor"""
    if not is_logged_in():
        return jsonify({'error': 'Não autorizado'}), 401
    
    conn = psycopg2.connect(DATABASE_URL)
    cursor = conn.cursor()
    
    try:
        # Verificar se servidor existe
        cursor.execute("SELECT nome FROM servidores WHERE id = %s", (servidor_id,))
        result = cursor.fetchone()
        
        if not result:
            return jsonify({'error': 'Servidor não encontrado'}), 404
        
        nome = result[0]
        
        # Verificar se há registros vinculados
        cursor.execute(
            "SELECT COUNT(*) FROM materiais WHERE servidor = %s",
            (nome,)
        )
        total_materiais = cursor.fetchone()[0]
        
        cursor.execute(
            "SELECT COUNT(*) FROM inscricoes WHERE servidor = %s",
            (nome,)
        )
        total_inscricoes = cursor.fetchone()[0]
        
        if total_materiais > 0 or total_inscricoes > 0:
            return jsonify({
                'error': f'Não é possível excluir o servidor "{nome}" pois há {total_materiais} materiais e {total_inscricoes} inscrições vinculados. Inative o servidor ao invés de excluí-lo.'
            }), 400
        
        # Excluir servidor
        cursor.execute("DELETE FROM servidores WHERE id = %s", (servidor_id,))
        conn.commit()
        
        return jsonify({
            'success': True,
            'message': f'Servidor "{nome}" excluído com sucesso!'
        })
    except Exception as e:
        conn.rollback()
        return jsonify({'error': f'Erro ao excluir servidor: {str(e)}'}), 500
    finally:
        conn.close()

    
    # Parâmetros de filtro
    servidor = request.args.get('servidor', '')
    nome = request.args.get('nome', '')
    telefone = request.args.get('telefone', '')
    tipo_pagamento = request.args.get('tipo_pagamento', '')
    
    conn = psycopg2.connect(DATABASE_URL)
    cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    
    query = """
        SELECT id, servidor, nome, telefone, tipo_pagamento, data_vencimento, 
               tipo_quarto, valor_quarto, valor_entrada, valor_restante, data_criacao
        FROM inscricoes 
        WHERE 1=1
    """
    params = []
    
    if servidor:
        query += " AND servidor ILIKE %s"
        params.append(f"%{servidor}%")
    if nome:
        query += " AND nome ILIKE %s"
        params.append(f"%{nome}%")
    if telefone:
        query += " AND telefone ILIKE %s"
        params.append(f"%{telefone}%")
    if tipo_pagamento:
        query += " AND tipo_pagamento = %s"
        params.append(tipo_pagamento)
    
    query += " ORDER BY data_criacao DESC"
    
    cursor.execute(query, params)
    inscricoes = cursor.fetchall()
    conn.close()
    
    # Converter para formato JSON serializável
    result = []
    for inscricao in inscricoes:
        item = dict(inscricao)
        if item['data_vencimento']:
            item['data_vencimento'] = item['data_vencimento'].strftime('%Y-%m-%d')
        if item['data_criacao']:
            item['data_criacao'] = item['data_criacao'].strftime('%Y-%m-%d %H:%M:%S')
        if item['valor_quarto']:
            item['valor_quarto'] = float(item['valor_quarto'])
        if item['valor_entrada']:
            item['valor_entrada'] = float(item['valor_entrada'])
        if item['valor_restante']:
            item['valor_restante'] = float(item['valor_restante'])
        result.append(item)
    
    return jsonify(result)

# ==================== ROTAS DE EDIÇÃO E EXCLUSÃO ====================

@app.route('/admin/material/<int:material_id>/delete', methods=['POST'])
def admin_delete_material(material_id):
    """Excluir material"""
    if not is_logged_in():
        return jsonify({'error': 'Não autorizado'}), 401
    
    conn = psycopg2.connect(DATABASE_URL)
    cursor = conn.cursor()
    
    cursor.execute("DELETE FROM materiais WHERE id = %s", (material_id,))
    conn.commit()
    conn.close()
    
    return jsonify({'success': True})

@app.route('/admin/inscricao/<int:inscricao_id>/delete', methods=['POST'])
def admin_delete_inscricao(inscricao_id):
    """Excluir inscrição"""
    if not is_logged_in():
        return jsonify({'error': 'Não autorizado'}), 401
    
    conn = psycopg2.connect(DATABASE_URL)
    cursor = conn.cursor()
    
    cursor.execute("DELETE FROM inscricoes WHERE id = %s", (inscricao_id,))
    conn.commit()
    conn.close()
    
    return jsonify({'success': True})

@app.route('/admin/materiais/<int:material_id>/edit', methods=['GET', 'POST'])
def admin_edit_material(material_id):
    """Editar material"""
    if not is_logged_in():
        return redirect(url_for('admin_login'))
    
    conn = psycopg2.connect(DATABASE_URL)
    cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    
    if request.method == 'GET':
        cursor.execute("SELECT * FROM materiais WHERE id = %s", (material_id,))
        material = cursor.fetchone()
        conn.close()
        
        if not material:
            flash('Material não encontrado', 'error')
            return redirect(url_for('admin_dashboard'))
        
        servidores = get_servidores_ativos()
        # Certifique-se de que o template correto está sendo renderizado
        return render_template('admin_edit_material.html', material=material, servidores=servidores)
    elif request.method == 'POST':
        # Atualizar material
        servidor = request.form['servidor']
        nome = request.form['nome']
        telefone = request.form['telefone']
        detalhes_materiais = request.form['detalhes_materiais']
        total_itens_pedido = int(request.form['total_itens_pedido'])
        total = float(request.form['total'])
        tipo_pagamento = request.form['tipo_pagamento']
        data_vencimento = request.form.get('data_vencimento') or None
        
        cursor.execute("""
            UPDATE materiais 
            SET servidor = %s, nome = %s, telefone = %s, detalhes_materiais = %s,
                total_itens_pedido = %s, total = %s, tipo_pagamento = %s, data_vencimento = %s
            WHERE id = %s
        """, (servidor, nome, telefone, detalhes_materiais, total_itens_pedido, 
              total, tipo_pagamento, data_vencimento, material_id))
        
        conn.commit()
        conn.close()
        
        flash('Material atualizado com sucesso!', 'success')
        return redirect(url_for('admin_dashboard', active_tab='materiais'))

@app.route('/admin/inscricoes/<int:inscricao_id>/edit', methods=['GET', 'POST'])
def admin_edit_inscricao(inscricao_id):
    """Editar inscrição"""
    if not is_logged_in():
        return redirect(url_for('admin_login'))
    
    conn = psycopg2.connect(DATABASE_URL)
    cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    
    if request.method == 'GET':
        cursor.execute("SELECT * FROM inscricoes WHERE id = %s", (inscricao_id,))
        inscricao = cursor.fetchone()
        conn.close()
        
        if not inscricao:
            flash('Inscrição não encontrada', 'error')
            return redirect(url_for('admin_dashboard'))
        
        servidores = get_servidores_ativos()
        # Certifique-se de que o template correto está sendo renderizado
        return render_template('admin_edit_inscricao.html', inscricao=inscricao, servidores=servidores)
    
    elif request.method == 'POST':
        # --- INÍCIO DA CORREÇÃO ---
        servidor = request.form['servidor']
        nome = request.form['nome']
        telefone = request.form['telefone']
        tipo_pagamento = request.form['tipo_pagamento']
        data_vencimento = request.form.get('data_vencimento') or None
        tipo_quarto = request.form['tipo_quarto']
        
        # Use .get() com um valor padrão para evitar o KeyError
        valor_quarto = float(request.form.get('valor_quarto', '0'))
        valor_entrada = float(request.form.get('valor_entrada', '0'))
        observacao = request.form.get('observacao', None)

        # Lógica de segurança: se o pagamento não for 'fiado', zere a entrada e a data
        if tipo_pagamento != 'fiado':
            valor_entrada = 0
            data_vencimento = None

        # Recalcule o valor restante no servidor para garantir a consistência
        valor_restante = valor_quarto - valor_entrada
        
        cursor.execute("""
            UPDATE inscricoes 
            SET servidor = %s, nome = %s, telefone = %s, tipo_pagamento = %s,
                data_vencimento = %s, tipo_quarto = %s, valor_quarto = %s,
                valor_entrada = %s, valor_restante = %s, observacao = %s
            WHERE id = %s
        """, (servidor, nome, telefone, tipo_pagamento, data_vencimento,
              tipo_quarto, valor_quarto, valor_entrada, valor_restante, observacao ,inscricao_id))
        
        # --- FIM DA CORREÇÃO ---
        
        conn.commit()
        conn.close()
        
        flash('Inscrição atualizada com sucesso!', 'success')
        return redirect(url_for('admin_dashboard', active_tab='inscricoes'))        

# ==================== ROTA PARA ALTERAR SENHA ====================

@app.route('/admin/change-password', methods=['POST'])
def admin_change_password():
    """Alterar senha do administrador"""
    if not is_logged_in():
        return jsonify({'error': 'Não autorizado'}), 401
    
    current_password = request.form.get('current_password')
    new_password = request.form.get('new_password')
    confirm_password = request.form.get('confirm_password')
    
    if not all([current_password, new_password, confirm_password]):
        return jsonify({'error': 'Todos os campos são obrigatórios'}), 400
    
    if new_password != confirm_password:
        return jsonify({'error': 'Nova senha e confirmação não conferem'}), 400
    
    if len(new_password) < 6:
        return jsonify({'error': 'Nova senha deve ter pelo menos 6 caracteres'}), 400
    
    username = session.get('admin_username')
    
    conn = psycopg2.connect(DATABASE_URL)
    cursor = conn.cursor()
    
    # Verificar senha atual
    cursor.execute("SELECT password_hash FROM admin_users WHERE username = %s", (username,))
    result = cursor.fetchone()
    
    if not result or not check_password(current_password, result[0]):
        conn.close()
        return jsonify({'error': 'Senha atual incorreta'}), 400
    
    # Atualizar senha
    new_password_hash = hash_password(new_password)
    cursor.execute("UPDATE admin_users SET password_hash = %s WHERE username = %s", 
                   (new_password_hash, username))
    conn.commit()
    conn.close()
    
    return jsonify({'success': True, 'message': 'Senha alterada com sucesso!'})

# ==================== ROTAS ORIGINAIS DE SALVAMENTO ====================

@app.route('/salvar-materiais', methods=['POST'])
def salvar_materiais():
    try:
        servidor = request.form['servidor']
        nome = request.form['nome']
        telefone = request.form['telefone']
        total = request.form['total']
        tipo_pagamento = request.form['tipo_pagamento']
        data_vencimento = request.form.get('data_vencimento') or None
        enviar_whatsapp_flag = request.form.get('enviar_whatsapp')
        
        # Processar materiais selecionados
        materiais_selecionados = request.form.getlist('materiais[]')
        especificacao_outro = request.form.get('especificacao_outro', '')
        
        # Limpar valor total
        total_limpo = total.replace('R$', '').replace('.', '').replace(',', '.').strip()
        total_float = float(total_limpo)

        # Processar detalhes dos materiais
        detalhes_materiais_list = []
        materiais_info_whatsapp = []
        total_itens_pedido = 0

        for material in materiais_selecionados:
            material_lower = material.lower()
            quantidade_field = f"quantidade_{material_lower}"
            quantidade = int(request.form.get(quantidade_field, 0))
            
            if quantidade > 0:
                detalhe_str = f"{material}: {quantidade}"
                especificacao = None
                if material == "Outro" and especificacao_outro:
                    detalhe_str += f" ({especificacao_outro})"
                    especificacao = especificacao_outro
                detalhes_materiais_list.append(detalhe_str)
                total_itens_pedido += quantidade

                # Preparar dados para o WhatsApp
                materiais_info_whatsapp.append({
                    "tipo": material,
                    "quantidade": quantidade,
                    "especificacao": especificacao
                })
        
        detalhes_materiais_final = "; ".join(detalhes_materiais_list)

        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor()
        
        # Inserção na tabela materiais
        cursor.execute("""
            INSERT INTO materiais 
            (servidor, nome, telefone, detalhes_materiais, total_itens_pedido, total, tipo_pagamento, data_vencimento)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """, (servidor, nome, telefone, detalhes_materiais_final, total_itens_pedido, total_float, tipo_pagamento, data_vencimento))
        
        conn.commit()
        conn.close()

        if enviar_whatsapp_flag:
            dados_registro = {
                'nome': nome,
                'telefone': telefone,
                'servidor': servidor,
                'total': total,
                'tipo_pagamento': tipo_pagamento,
                'data_vencimento': data_vencimento,
                'materiais_info': materiais_info_whatsapp
            }
            
            url_whatsapp = enviar_whatsapp_materiais(telefone, dados_registro)
            return redirect(url_for('sucesso_whatsapp_materiais', url=url_whatsapp))
        
        return redirect(url_for('materiais', success=1))
        
    except Exception as e:
        return f"Erro ao salvar materiais: {str(e)}", 500

@app.route('/salvar-inscricao', methods=['POST'])
def salvar_inscricao():
    try:
        servidor = request.form['servidor']
        nome = request.form['nome']
        telefone = request.form['telefone']
        tipo_pagamento = request.form['tipo_pagamento']
        data_vencimento = request.form.get('data_vencimento') or None
        tipo_quarto = request.form['tipo_quarto']
        valor_entrada_str = request.form.get('valor_entrada', '')
        enviar_whatsapp_flag = request.form.get('enviar_whatsapp')
        observacao = request.form.get('observacao', None)
        
        # Definir valores dos quartos
        valores_quartos = {
            'duplo': 380.00,
            'triplo': 350.00,
            'coletivo': 299.90
        }
        
        valor_quarto = valores_quartos.get(tipo_quarto, 0)
        
        # Processar valor de entrada (pode estar em branco)
        valor_entrada = 0
        if valor_entrada_str:
            valor_entrada_limpo = valor_entrada_str.replace('R$', '').replace('.', '').replace(',', '.').strip()
            valor_entrada = float(valor_entrada_limpo) if valor_entrada_limpo else 0
        
        # Calcular valor restante
        valor_restante = valor_quarto - valor_entrada

        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor()
        
        # Inserir na tabela inscricoes
        cursor.execute("""
            INSERT INTO inscricoes 
            (servidor, nome, telefone, tipo_pagamento, data_vencimento, tipo_quarto, valor_quarto, valor_entrada, valor_restante,observacao)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (servidor, nome, telefone, tipo_pagamento, data_vencimento, tipo_quarto, valor_quarto, valor_entrada, valor_restante,observacao))
        
        conn.commit()
        conn.close()

        if enviar_whatsapp_flag:
            # Formatar valores para exibição
            valor_quarto_formatado = f"R$ {valor_quarto:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.')
            valor_entrada_formatado = f"R$ {valor_entrada:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.')
            valor_restante_formatado = f"R$ {valor_restante:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.')
            
            dados_registro = {
                'nome': nome,
                'telefone': telefone,
                'servidor': servidor,
                'tipo_quarto': tipo_quarto,
                'valor_quarto': valor_quarto_formatado,
                'valor_entrada': valor_entrada_formatado,
                'valor_restante': valor_restante_formatado,
                'tipo_pagamento': tipo_pagamento,
                'data_vencimento': data_vencimento,
                'observacao': observacao
            }
            
            url_whatsapp = enviar_whatsapp_inscricoes(telefone, dados_registro)
            return redirect(url_for('sucesso_whatsapp_inscricoes', url=url_whatsapp))
        
        return redirect(url_for('inscricao', success=1))
        
    except Exception as e:
        return f"Erro ao salvar inscrição: {str(e)}", 500
    

@app.route('/vendas/<string:nome_servidor>')
def vendas_por_servidor(nome_servidor):
    """Exibe uma página estática com todas as vendas de um servidor."""
    conn = psycopg2.connect(DATABASE_URL)
    cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    # Buscar vendas de materiais
    cursor.execute(
        "SELECT nome, detalhes_materiais, total, tipo_pagamento, data_criacao FROM materiais WHERE servidor = %s ORDER BY data_criacao DESC",
        (nome_servidor,)
    )
    vendas_materiais = cursor.fetchall()

    # Buscar vendas de inscrições
    cursor.execute(
        "SELECT nome, tipo_quarto, valor_quarto, valor_entrada, valor_restante, tipo_pagamento, data_criacao FROM inscricoes WHERE servidor = %s ORDER BY data_criacao DESC",
        (nome_servidor,)
    )
    vendas_inscricoes = cursor.fetchall()

    conn.close()

    # Calcular totais (opcional, mas útil)
    total_materiais = sum(v['total'] for v in vendas_materiais)
    total_inscricoes = sum(v['valor_quarto'] for v in vendas_inscricoes)

    return render_template(
        'vendas_servidor.html',
        servidor=nome_servidor,
        materiais=vendas_materiais,
        inscricoes=vendas_inscricoes,
        total_materiais=total_materiais,
        total_inscricoes=total_inscricoes
    )



@app.route('/sucesso-whatsapp-materiais')
def sucesso_whatsapp_materiais():
    url_whatsapp = request.args.get('url', '')
    return f'''
    <!DOCTYPE html>
    <html lang="pt-br">
    <head>
        <meta charset="UTF-8">
        <title>Pedido Realizado - Encompasso Barreiro</title>
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css" rel="stylesheet">
        <link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css" rel="stylesheet">
        <style>
            body {{
                font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                background-color: #f1f3f5;
                min-height: 100vh;
                display: flex;
                align-items: center;
                justify-content: center;
                padding: 20px;
            }}
            .success-container {{
                background-color: #ffffff;
                padding: 40px;
                border-radius: 16px;
                box-shadow: 0 8px 24px rgba(0, 0, 0, 0.08);
                text-align: center;
                max-width: 500px;
                width: 100%;
            }}
            .success-icon {{
                font-size: 4rem;
                color: #28a745;
                margin-bottom: 1rem;
            }}
            .whatsapp-btn {{
                background-color: #25d366;
                border: none;
                color: white;
                padding: 15px 30px;
                border-radius: 10px;
                font-size: 1.1rem;
                font-weight: 500;
                text-decoration: none;
                display: inline-block;
                margin: 20px 10px;
                transition: all 0.3s ease;
            }}
            .whatsapp-btn:hover {{
                background-color: #128c7e;
                color: white;
                text-decoration: none;
                transform: translateY(-2px);
            }}
            .btn-secondary {{
                padding: 15px 30px;
                border-radius: 10px;
                font-size: 1.1rem;
                font-weight: 500;
                margin: 20px 10px;
            }}
        </style>
    </head>
    <body>
        <div class="success-container">
            <i class="fas fa-check-circle success-icon"></i>
            <h2 class="mb-3">Pedido Realizado com Sucesso!</h2>
            <p class="text-muted mb-4">Seu pedido foi registrado no sistema. Clique no botão abaixo para receber o resumo via WhatsApp.</p>
            
            <div class="d-flex flex-column flex-sm-row justify-content-center">
                <a href="{url_whatsapp}" target="_blank" class="whatsapp-btn">
                    <i class="fab fa-whatsapp me-2"></i>Enviar para WhatsApp
                </a>
                <a href="/materiais" class="btn btn-secondary">
                    <i class="fas fa-arrow-left me-2"></i>Voltar
                </a>
            </div>
        </div>
    </body>
    </html>
    '''

@app.route('/sucesso-whatsapp-inscricoes')
def sucesso_whatsapp_inscricoes():
    url_whatsapp = request.args.get('url', '')
    return f'''
    <!DOCTYPE html>
    <html lang="pt-br">
    <head>
        <meta charset="UTF-8">
        <title>Inscrição Realizada - Encompasso Barreiro</title>
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css" rel="stylesheet">
        <link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css" rel="stylesheet">
        <style>
            body {{
                font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                background-color: #f1f3f5;
                min-height: 100vh;
                display: flex;
                align-items: center;
                justify-content: center;
                padding: 20px;
            }}
            .success-container {{
                background-color: #ffffff;
                padding: 40px;
                border-radius: 16px;
                box-shadow: 0 8px 24px rgba(0, 0, 0, 0.08);
                text-align: center;
                max-width: 500px;
                width: 100%;
            }}
            .success-icon {{
                font-size: 4rem;
                color: #28a745;
                margin-bottom: 1rem;
            }}
            .whatsapp-btn {{
                background-color: #25d366;
                border: none;
                color: white;
                padding: 15px 30px;
                border-radius: 10px;
                font-size: 1.1rem;
                font-weight: 500;
                text-decoration: none;
                display: inline-block;
                margin: 20px 10px;
                transition: all 0.3s ease;
            }}
            .whatsapp-btn:hover {{
                background-color: #128c7e;
                color: white;
                text-decoration: none;
                transform: translateY(-2px);
            }}
            .btn-secondary {{
                padding: 15px 30px;
                border-radius: 10px;
                font-size: 1.1rem;
                font-weight: 500;
                margin: 20px 10px;
            }}
        </style>
    </head>
    <body>
        <div class="success-container">
            <i class="fas fa-check-circle success-icon"></i>
            <h2 class="mb-3">Inscrição Realizada com Sucesso!</h2>
            <p class="text-muted mb-4">Sua inscrição foi registrada no sistema. Clique no botão abaixo para receber o resumo via WhatsApp.</p>
            
            <div class="d-flex flex-column flex-sm-row justify-content-center">
                <a href="{url_whatsapp}" target="_blank" class="whatsapp-btn">
                    <i class="fab fa-whatsapp me-2"></i>Enviar para WhatsApp
                </a>
                <a href="/inscricao" class="btn btn-secondary">
                    <i class="fas fa-arrow-left me-2"></i>Voltar
                </a>
            </div>
        </div>
    </body>
    </html>
    '''

@app.route('/admin/exportar/materiais')
def exportar_materiais():
     """Exporta todos os dados da tabela de materiais para um arquivo Excel."""
     if not is_logged_in():
         return redirect(url_for('admin_login'))
     
     try:
         conn = psycopg2.connect(DATABASE_URL)
         # A query SQL seleciona todas as colunas, exatamente como no banco
         sql_query = "SELECT * FROM materiais ORDER BY id DESC;"
         df = pd.read_sql_query(sql_query, conn)
         conn.close()

         # Cria um arquivo Excel em memória (não salva no servidor)
         output = io.BytesIO()
         with pd.ExcelWriter(output, engine='openpyxl') as writer:
             df.to_excel(writer, sheet_name='Materiais', index=False)
         output.seek(0)

         # Gera um nome de arquivo único com data e hora
         timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
         filename = f"export_materiais_{timestamp}.xlsx"
         
         # Envia o arquivo para o navegador para download
         return send_file(
             output,
             mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
             as_attachment=True,
             download_name=filename
         )
     except Exception as e:
         flash(f"Erro ao exportar dados de materiais: {e}", "error")
         return redirect(url_for('admin_dashboard', active_tab='materiais'))

@app.route('/admin/exportar/inscricoes')
def exportar_inscricoes():
     """Exporta todos os dados da tabela de inscrições para um arquivo Excel."""
     if not is_logged_in():
         return redirect(url_for('admin_login'))
     
     try:
         conn = psycopg2.connect(DATABASE_URL)
         sql_query = """
            SELECT 
                id, servidor, nome, telefone, tipo_quarto, 
                valor_quarto, valor_entrada, valor_restante, 
                tipo_pagamento, data_vencimento, observacao, data_criacao 
            FROM inscricoes 
            ORDER BY id DESC;
        """
         df = pd.read_sql_query(sql_query, conn)
         conn.close()

         output = io.BytesIO()
         with pd.ExcelWriter(output, engine='openpyxl') as writer:
             df.to_excel(writer, sheet_name='Inscricoes', index=False)
         output.seek(0)

         timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
         filename = f"export_inscricoes_{timestamp}.xlsx"
         
         return send_file(
             output,
             mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
             as_attachment=True,
             download_name=filename
         )
     except Exception as e:
         flash(f"Erro ao exportar dados de inscrições: {e}", "error")
         return redirect(url_for('admin_dashboard', active_tab='inscricoes'))


if __name__ == '__main__':
    init_db()
    app.run(host='0.0.0.0', port=5000, debug=True)

