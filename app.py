import sys

if sys.platform != "win32":
    try:
        from gevent import monkey
        monkey.patch_all()
    except ImportError:
        print("Gevent não instalado!")

from flask import Flask, request, session, jsonify
from flask_socketio import SocketIO, emit
from google import genai
from google.genai import types
from dotenv import load_dotenv
from uuid import uuid4
import os

# Carrega as variáveis ocultas do arquivo .env (como a chave da API do Gemini)
load_dotenv()

# Define qual versão da IA vamos usar. O modelo "flash" é rápido e ideal para chatbots.
MODELO = "gemini-3.1-flash-lite"

# Aqui definimos o "Prompt de Sistema". É a personalidade e as regras que o bot deve seguir.
instrucoes = """
# PERSONA
Você é o **Sócio de Valor**, um parceiro chamado clayver de investimentos experiente e pragmático, moldado pela filosofia de Warren Buffett e Charlie Munger. Você me trata como um amigo próximo com quem divide ideias de alocação. Vai direto ao ponto: fala **como, onde e por quê** investir, com respostas curtas, claras e acionáveis. Seu estilo é o de um confidente que fala na mesa do bar, não em uma sala de aula.

# COMPORTAMENTO
- Respostas curtas e diretas, sem enrolação. Se eu perguntar “onde invisto agora?”, você responde com um ativo ou classe de ativo concreta, seguida de um “porquê” de uma frase.
- Sugere alocações reais (ex.: “Tesouro IPCA+ 2029”, “ETFs como IVVB11 ou BOVA11”, “ações perenes como empresas de energia elétrica com bons dividendos”), sempre inspiradas em negócios previsíveis, com vantagens duráveis e gestão competente.
- Se não houver uma boa oportunidade na sua visão, você dirá “prefiro ficar líquido aguardando uma pechincha, como Buffett faria”.
- Sempre justifica a sugestão com um fundamento de valor (margem de segurança, moat, lucros consistentes, baixo custo etc.), mas em poucas palavras.
- Quando o cenário exigir cautela, você será pessimista do jeito Munger: “mercado caro, não faça besteira”.

# FILOSOFIA POR TRÁS DAS SUGESTÕES
- Negócios simples e dominantes (moats largos), com lucros previsíveis.
- Preço importa: só sugira algo se estiver razoável ou barato historicamente.
- Prefira o tédio rentável: empresas de consumo básico, energia, seguros, índices.
- Odeie dívidas excessivas e modismos.
- O horizonte é “para sempre”, então foque no que você aguentaria carregar por 10 anos sem vender.
- Em momentos de pânico, indique compras agressivas; em euforia, recomende cautela.

# TOM E ESTILO DE RESPOSTA
- Frases curtas, quase telegráficas, mas com personalidade.
- Exemplo de interação:
  **Eu:** “Tenho R$10 mil, onde coloco?”
  **Sócio:** “IVVB11. Simples, barato, 500 maiores empresas dos EUA. Esqueça e vá viver. Só não mexa nos próximos 5 anos.”
- Se eu pedir uma ação específica, você pode sugerir um setor ou tipo de empresa, com o porquê. Ex.: “Copel ou Engie. Energia previsível, dividendos gordos. Mas só se o preço estiver abaixo de 5x EV/Ebitda.”
- Nunca use mais de 5 linhas se não for extremamente necessário. Vá direto ao ponto.

# LIMITES CRÍTICOS
1. **DISCLAIMER OBRIGATÓRIO NO INÍCIO DA CONVERSA:** “Sou um parceiro de ideias, não consultor certificado. O que digo são reflexões de um amigo – decisão final e riscos são seus.”
2. **Sem previsões de curto prazo:** Se eu perguntar “a bolsa vai cair amanhã?”, responda apenas “Não sei, mas se empresas boas ficarem baratas, compro mais”.
3. **Nada de day trade, opções, cripto ou alavancagem.** Você despreza essas coisas e não as sugere.
4. **Não peça nem comente dados financeiros pessoais.** Fale de forma genérica, sempre.
5. **Quando o risco for alto, alerte:** “Lembre-se: investimento tem risco. O que eu falo é o que eu faria, não o que você deve fazer.”

# EXEMPLOS REAIS DE RESPOSTAS
- “Renda fixa agora? Tesouro IPCA+ 2035. Juro real de 6% ao ano, durma tranquilo.”
- “Ação pra buy and hold? WEG, mas só se o P/L estiver abaixo de 30. Fora isso, espere.”
- “Quero dolarizar. IVVB11 ou Berkshire B. Warren cuida do seu dinheiro melhor que você.”
- “Fundo imobiliário? Só tijolo e bem localizado. HGLG11. Gestão boa, imóveis logísticos.”

Seja meu parceiro de alocação: direto, sem medo de dar nomes, mas sempre com o pé no chão do value investing.
"""

# Inicializa a conexão com a inteligência artificial do Google usando a chave da API
client = genai.Client(api_key=os.getenv("GENAI_KEY"))

# Cria o nosso aplicativo web principal (o servidor)
app = Flask(__name__)

# A 'secret_key' funciona como uma senha interna do servidor para proteger 
# e criptografar os dados da sessão (as "lembranças" de quem é quem).
app.secret_key = "ch@tb07"

# Adiciona a funcionalidade de WebSockets (comunicação em tempo real) ao nosso app.
# O 'cors_allowed_origins="*"' é crucial: ele permite que o nosso front-end (HTML/JS) 
# consiga se conectar com esse back-end, mesmo que estejam em arquivos ou portas diferentes.
socketio = SocketIO(app, cors_allowed_origins="*")

# Dicionário que funciona como a "memória temporária" do servidor. 
# Ele guarda a conversa de cada aluno separadamente usando um ID único.
active_chats = {}

def get_user_chat():
    """
    Função principal de gerenciamento de usuários.
    Ela verifica quem está mandando a mensagem e recupera a conversa correta,
    garantindo que o bot não misture o chat do Aluno A com o do Aluno B.
    """
    
    # Passo 1: Se o usuário é novo (não tem um 'session_id'), criamos um ID único para ele.
    # Usamos o 'uuid4' para gerar um código aleatório impossível de repetir.
    if 'session_id' not in session:
        session['session_id'] = str(uuid4())
        print(f"Nova sessão Flask criada: {session['session_id']}")

    session_id = session['session_id']

    # Passo 2: Se o usuário já tem um ID, mas ainda não tem uma conversa aberta com o Gemini...
    if session_id not in active_chats:
        print(f"Criando novo chat Gemini para session_id: {session_id}")
        try:
            # ...nós criamos uma nova conversa e passamos as instruções (personalidade).
            chat_session = client.chats.create(
                model=MODELO,
                config=types.GenerateContentConfig(system_instruction=instrucoes)
            )
            # Guardamos essa conversa no nosso dicionário (memória).
            active_chats[session_id] = chat_session
            print(f"Novo chat Gemini criado e armazenado para {session_id}")
        except Exception as e:
            app.logger.error(f"Erro ao criar chat Gemini para {session_id}: {e}", exc_info=True)
            raise  # Se der erro aqui, repassa para o sistema avisar que falhou
    
    # Passo 3: Segurança extra. Se o servidor reiniciou (apagou a variável active_chats), 
    # mas o usuário ainda estava no navegador com o mesmo ID, nós recriamos a conexão dele.
    if session_id in active_chats and active_chats[session_id] is None:
        print(f"Recriando chat Gemini para session_id existente (estava None): {session_id}")
        try:
            chat_session = client.chats.create(
                model=MODELO,
                config=types.GenerateContentConfig(system_instruction=instrucoes)
            )
            active_chats[session_id] = chat_session
        except Exception as e:
            app.logger.error(f"Erro ao recriar chat Gemini para {session_id}: {e}", exc_info=True)
            raise

    # Retorna o histórico de mensagens exato daquele usuário.
    return active_chats[session_id]

# Rota simples para verificar se o servidor está rodando.
# Ao acessar o localhost no navegador, o aluno verá este aviso em formato JSON.
@app.route('/')
def root():
    return jsonify({
        "api-websocket": "chatbot",
        "status": "ok"
    })


# ------------------------------------------------------------------
# EVENTOS SOCKET.IO (Onde a mágica do tempo real acontece)
# ------------------------------------------------------------------

@socketio.on('connect')
def handle_connect():
    """
    EVENTO: Disparado no momento exato em que o Front-end (navegador) se conecta ao servidor.
    """
    print(f"Cliente conectado: {request.sid}")
    
    try:
        # Tenta criar a pasta do usuário assim que ele entra
        get_user_chat()
        user_session_id = session.get('session_id', 'N/A')
        print(f"Sessão Flask para {request.sid} usa session_id: {user_session_id}")
        
        # O comando 'emit' serve para enviar um pacote de dados do servidor PARA o front-end.
        emit('status_conexao', {'data': 'Conectado com sucesso!', 'session_id': user_session_id})
    except Exception as e:
        app.logger.error(f"Erro durante o evento connect para {request.sid}: {e}", exc_info=True)
        emit('erro', {'erro': 'Falha ao inicializar a sessão de chat no servidor.'})


@socketio.on('enviar_mensagem')
def handle_enviar_mensagem(data):
    """
    EVENTO: O Front-end mandou uma mensagem (ex: o usuário clicou em 'Enviar' no chat).
    A variável 'data' traz os dados enviados pelo HTML (o texto que o usuário digitou).
    """
    try:
        # Pega o texto de dentro do dicionário enviado pelo JS
        mensagem_usuario = data.get("mensagem")
        app.logger.info(f"Mensagem recebida de {session.get('session_id', request.sid)}: {mensagem_usuario}")

        # Validação básica: não deixa enviar mensagens vazias
        if not mensagem_usuario:
            emit('erro', {"erro": "Mensagem não pode ser vazia."})
            return

        # Puxa o histórico de conversa desse aluno específico
        user_chat = get_user_chat()
        if user_chat is None:
            emit('erro', {"erro": "Sessão de chat não pôde ser estabelecida."})
            return

        # ==========================================
        # COMUNICAÇÃO COM O GOOGLE GEMINI
        # ==========================================
        # Aqui o nosso servidor repassa a pergunta para a IA do Google...
        resposta_gemini = user_chat.send_message(mensagem_usuario)

        # ... e aqui extraímos apenas o texto da resposta que o Gemini devolveu.
        # (O 'if/else' garante que vamos achar o texto independente de como a API estruturar a resposta)
        resposta_texto = (
            resposta_gemini.text
            if hasattr(resposta_gemini, 'text')
            else resposta_gemini.candidates[0].content.parts[0].text
        )
        
        # O servidor usa o 'emit' para devolver a resposta final do bot lá para a tela do Front-end.
        emit('nova_mensagem', {"remetente": "bot", "texto": resposta_texto, "session_id": session.get('session_id')})
        app.logger.info(f"Resposta enviada para {session.get('session_id', request.sid)}: {resposta_texto}")

    except Exception as e:
        app.logger.error(f"Erro ao processar 'enviar_mensagem' para {session.get('session_id', request.sid)}: {e}", exc_info=True)
        # Se algo quebrar (ex: falha de internet), avisamos o front-end educadamente.
        emit('erro', {"erro": f"Ocorreu um erro no servidor: {str(e)}"})


@socketio.on('disconnect')
def handle_disconnect():
    """
    EVENTO: Disparado quando o usuário fecha a aba do navegador ou perde a conexão.
    """
    print(f"Cliente desconectado: {request.sid}, session_id: {session.get('session_id', 'N/A')}")


# Inicia o servidor local. A porta padrão do Flask costuma ser a 5000.
if __name__ == "__main__":
    socketio.run(app)
