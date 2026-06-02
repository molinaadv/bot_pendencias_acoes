from fastapi import FastAPI, Request, HTTPException
from supabase import create_client
from datetime import datetime
import os
import json
import requests

app = FastAPI()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
API_SECRET = os.getenv("API_SECRET", "")

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

TABELA_PENDENCIAS = "pendencias_acoes"
TABELA_SESSOES = "chat_sessions_acoes"
TABELA_HISTORICO = "historico_pendencias"


def gerar_protocolo():
    return "PA-" + datetime.now().strftime("%Y%m%d%H%M%S")


def resposta_chat(texto):
    return {
        "hostAppDataAction": {
            "chatDataAction": {
                "createMessageAction": {
                    "message": {"text": texto}
                }
            }
        }
    }


def extrair_texto(event):
    texto = (
        event.get("argumentText")
        or event.get("message", {}).get("argumentText")
        or event.get("message", {}).get("text")
        or event.get("messagePayload", {}).get("argumentText")
        or event.get("messagePayload", {}).get("message", {}).get("argumentText")
        or event.get("messagePayload", {}).get("message", {}).get("text")
        or event.get("chat", {}).get("messagePayload", {}).get("argumentText")
        or event.get("chat", {}).get("messagePayload", {}).get("message", {}).get("argumentText")
        or event.get("chat", {}).get("messagePayload", {}).get("message", {}).get("text")
        or event.get("chat", {}).get("messagePayload", {}).get("message", {}).get("formattedText")
        or ""
    )
    return str(texto).strip()


def dados_usuario(event):
    user = (
        event.get("user")
        or event.get("chat", {}).get("user")
        or event.get("message", {}).get("sender")
        or event.get("messagePayload", {}).get("message", {}).get("sender")
        or event.get("chat", {}).get("messagePayload", {}).get("message", {}).get("sender")
        or {}
    )

    nome = user.get("displayName") or user.get("name") or "Usuário Google Chat"
    email = user.get("email") or ""
    google_user_id = user.get("name") or user.get("email") or nome

    return nome, email, google_user_id


def dados_chat(event):
    payload = event.get("chat", {}).get("messagePayload", {}) or event.get("messagePayload", {})
    space = payload.get("space", {}) or payload.get("message", {}).get("space", {})
    message = payload.get("message", {})

    chat_space_name = space.get("name", "")
    chat_thread_name = message.get("thread", {}).get("name", "")

    return chat_space_name, chat_thread_name


def enviar_mensagem_google_chat(space_name, texto):
    """
    Envio ativo para Google Chat.
    Para funcionar, precisa configurar depois a autenticação da Google Chat API.
    Por enquanto, se não houver token, apenas registra no log e não quebra.
    """
    token = os.getenv("GOOGLE_CHAT_BEARER_TOKEN", "")

    if not token:
        print("GOOGLE_CHAT_BEARER_TOKEN não configurado. Mensagem não enviada automaticamente.")
        print(texto)
        return False

    url = f"https://chat.googleapis.com/v1/{space_name}/messages"

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }

    payload = {"text": texto}

    resp = requests.post(url, headers=headers, json=payload, timeout=15)

    print("RESPOSTA GOOGLE CHAT:")
    print(resp.status_code)
    print(resp.text)

    return resp.status_code in [200, 201]


@app.get("/")
async def home():
    return {"status": "online", "app": "Pendências Ações"}


@app.post("/google-chat-pendencias-acoes")
async def google_chat_pendencias_acoes(request: Request):
    event = await request.json()

    print("===================================")
    print("EVENTO RECEBIDO GOOGLE CHAT")
    print(event)

    texto = extrair_texto(event)
    texto_lower = texto.lower()

    print("TEXTO EXTRAIDO:", texto)
    print("TEXTO LOWER:", texto_lower)

    nome_usuario, email_usuario, google_user_id = dados_usuario(event)
    chat_space_name, chat_thread_name = dados_chat(event)

    try:
        session_resp = (
            supabase.table(TABELA_SESSOES)
            .select("*")
            .eq("user_id", google_user_id)
            .execute()
        )
        sessao = session_resp.data[0] if session_resp.data else None

    except Exception as e:
        print("ERRO AO CONSULTAR SESSAO:", e)
        return resposta_chat("⚠️ Não consegui consultar a sessão no banco de dados.")

    if texto_lower in ["oi", "olá", "ola", "menu", "ajuda", "início", "inicio", "help"]:
        return resposta_chat(
            "📌 *Pendências Ações*\n\n"
            "*nova* - abrir uma nova pendência\n"
            "*listar* - listar pendências abertas\n"
            "*cancelar* - cancelar abertura em andamento"
        )

    if texto_lower in [
        "nova", "abrir", "abrir pendência", "abrir pendencia",
        "nova pendência", "nova pendencia", "pendência", "pendencia"
    ]:
        try:
            if sessao:
                supabase.table(TABELA_SESSOES).delete().eq("user_id", google_user_id).execute()

            supabase.table(TABELA_SESSOES).insert({
                "user_id": google_user_id,
                "etapa": "cidade",
                "dados": {
                    "solicitante": nome_usuario,
                    "email_solicitante": email_usuario,
                    "google_user_id": google_user_id,
                    "chat_space_name": chat_space_name,
                    "chat_thread_name": chat_thread_name
                }
            }).execute()

        except Exception as e:
            print("ERRO AO CRIAR SESSAO:", e)
            return resposta_chat("⚠️ Não consegui iniciar a abertura da pendência.")

        return resposta_chat(
            f"📋 *Nova Pendência - Ações*\n\n"
            f"Solicitante identificado:\n*{nome_usuario}*\n\n"
            f"Informe a *cidade*:"
        )

    if texto_lower in ["cancelar", "sair", "parar"]:
        if sessao:
            supabase.table(TABELA_SESSOES).delete().eq("user_id", google_user_id).execute()
        return resposta_chat("Operação cancelada.\n\nPara abrir outra pendência, digite *nova*.")

    if texto_lower in ["listar", "pendências", "pendencias", "abertas"]:
        pend_resp = (
            supabase.table(TABELA_PENDENCIAS)
            .select("protocolo,cidade,comunidade,status,descricao,criado_em")
            .in_("status", ["Aberta", "Em andamento", "Aguardando informação"])
            .order("criado_em", desc=True)
            .limit(10)
            .execute()
        )

        dados = pend_resp.data or []

        if not dados:
            return resposta_chat("Nenhuma pendência ativa encontrada.")

        linhas = ["📋 *Últimas pendências ativas*\n"]

        for item in dados:
            linhas.append(
                f"\n*{item.get('protocolo', '')}*\n"
                f"Cidade: {item.get('cidade', '')}\n"
                f"Comunidade: {item.get('comunidade', '')}\n"
                f"Status: {item.get('status', '')}\n"
                f"Descrição: {str(item.get('descricao', ''))[:80]}"
            )

        return resposta_chat("\n".join(linhas))

    if not sessao:
        return resposta_chat(
            "Não encontrei uma pendência em andamento.\n\n"
            "Digite *nova* para abrir uma pendência."
        )

    etapa = sessao.get("etapa")
    dados = sessao.get("dados") or {}

    if etapa == "cidade":
        dados["cidade"] = texto

        supabase.table(TABELA_SESSOES).update({
            "etapa": "comunidade",
            "dados": dados
        }).eq("user_id", google_user_id).execute()

        return resposta_chat("Informe a *comunidade*:")

    if etapa == "comunidade":
        dados["comunidade"] = texto

        supabase.table(TABELA_SESSOES).update({
            "etapa": "descricao",
            "dados": dados
        }).eq("user_id", google_user_id).execute()

        return resposta_chat("Descreva a *pendência*:")

    if etapa == "descricao":
        protocolo = gerar_protocolo()

        pendencia = {
            "protocolo": protocolo,
            "nome_solicitante": dados.get("solicitante", nome_usuario),
            "solicitante": dados.get("solicitante", nome_usuario),
            "email_solicitante": dados.get("email_solicitante", email_usuario),
            "google_user_id": dados.get("google_user_id", google_user_id),
            "chat_space_name": dados.get("chat_space_name", chat_space_name),
            "chat_thread_name": dados.get("chat_thread_name", chat_thread_name),
            "cidade": dados.get("cidade", ""),
            "comunidade": dados.get("comunidade", ""),
            "descricao": texto,
            "status": "Aberta",
            "responsavel": "Ações"
        }

        try:
            insert_resp = supabase.table(TABELA_PENDENCIAS).insert(pendencia).execute()
            pendencia_id = insert_resp.data[0].get("id") if insert_resp.data else None

            supabase.table(TABELA_HISTORICO).insert({
                "pendencia_id": pendencia_id,
                "protocolo": protocolo,
                "usuario": nome_usuario,
                "email_usuario": email_usuario,
                "status_anterior": "",
                "status_novo": "Aberta",
                "observacao": "Pendência criada pelo Google Chat"
            }).execute()

            supabase.table(TABELA_SESSOES).delete().eq("user_id", google_user_id).execute()

        except Exception as e:
            print("ERRO AO CRIAR PENDENCIA:", e)
            return resposta_chat("⚠️ Erro ao criar a pendência no banco de dados.")

        return resposta_chat(
            f"✅ *Pendência criada com sucesso!*\n\n"
            f"*Protocolo:* {protocolo}\n"
            f"*Cidade:* {dados.get('cidade', '')}\n"
            f"*Comunidade:* {dados.get('comunidade', '')}\n"
            f"*Status:* Aberta\n\n"
            f"A pendência já aparece no painel."
        )

    return resposta_chat("Não entendi.\n\nDigite *nova* para abrir uma pendência.")


@app.post("/notificar-conclusao")
async def notificar_conclusao(request: Request):
    api_key = request.headers.get("X-API-KEY")

    if not API_SECRET or api_key != API_SECRET:
        raise HTTPException(status_code=401, detail="Não autorizado")

    body = await request.json()

    protocolo = body.get("protocolo")
    concluido_por = body.get("concluido_por", "")
    email_concluido_por = body.get("email_concluido_por", "")
    observacao = body.get("observacao", "")

    if not protocolo:
        raise HTTPException(status_code=400, detail="Protocolo obrigatório")

    res = (
        supabase.table(TABELA_PENDENCIAS)
        .select("*")
        .eq("protocolo", protocolo)
        .limit(1)
        .execute()
    )

    if not res.data:
        raise HTTPException(status_code=404, detail="Pendência não encontrada")

    pendencia = res.data[0]
    pendencia_id = pendencia.get("id")

    supabase.table(TABELA_PENDENCIAS).update({
        "status": "Concluída",
        "concluido_em": datetime.utcnow().isoformat(),
        "concluido_por": concluido_por,
        "email_concluido_por": email_concluido_por,
        "observacao_retorno": observacao
    }).eq("protocolo", protocolo).execute()

    supabase.table(TABELA_HISTORICO).insert({
        "pendencia_id": pendencia_id,
        "protocolo": protocolo,
        "usuario": concluido_por,
        "email_usuario": email_concluido_por,
        "status_anterior": pendencia.get("status", ""),
        "status_novo": "Concluída",
        "observacao": observacao or "Pendência concluída pelo painel"
    }).execute()

    mensagem = (
        f"✅ *Sua pendência foi concluída!*\n\n"
        f"*Protocolo:* {protocolo}\n"
        f"*Cidade:* {pendencia.get('cidade', '')}\n"
        f"*Comunidade:* {pendencia.get('comunidade', '')}\n"
        f"*Descrição:* {pendencia.get('descricao', '')}\n\n"
        f"*Concluída por:* {concluido_por or 'Equipe Ações'}\n"
    )

    if observacao:
        mensagem += f"\n*Observação:*\n{observacao}\n"

    chat_space_name = pendencia.get("chat_space_name")

    enviado = False

    if chat_space_name:
        enviado = enviar_mensagem_google_chat(chat_space_name, mensagem)

    return {
        "ok": True,
        "protocolo": protocolo,
        "status": "Concluída",
        "mensagem_tentou_enviar": bool(chat_space_name),
        "mensagem_enviada": enviado
    }
