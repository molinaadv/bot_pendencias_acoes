from fastapi import FastAPI, Request
from supabase import create_client
from datetime import datetime
import os

app = FastAPI()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

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
                    "message": {
                        "text": texto
                    }
                }
            }
        }
    }


def dados_usuario(event):
    user = event.get("chat", {}).get("user", {}) or event.get("user", {}) or {}

    nome = (
        user.get("displayName")
        or user.get("name")
        or "Usuário Google Chat"
    )

    email = user.get("email") or ""

    google_user_id = (
        user.get("name")
        or user.get("email")
        or nome
    )

    return nome, email, google_user_id


@app.get("/")
async def home():
    return {"status": "online", "app": "Pendências Ações"}


@app.post("/google-chat-pendencias-acoes")
async def google_chat_pendencias_acoes(request: Request):
    event = await request.json()

    print("EVENTO RECEBIDO GOOGLE CHAT")
    print(event)

    texto = (
        event.get("messagePayload", {})
        .get("message", {})
        .get("text")
        or event.get("message", {}).get("text")
        or ""
    ).strip()

    texto_lower = texto.lower()

    nome_usuario, email_usuario, google_user_id = dados_usuario(event)

    session_resp = (
        supabase
        .table(TABELA_SESSOES)
        .select("*")
        .eq("user_id", google_user_id)
        .execute()
    )

    sessao = session_resp.data[0] if session_resp.data else None

    if texto_lower in ["oi", "olá", "ola", "menu", "ajuda", "início", "inicio"]:
        return resposta_chat(
            "📌 *Pendências Ações*\n\n"
            "Comandos disponíveis:\n\n"
            "*nova* - abrir uma nova pendência\n"
            "*listar* - listar pendências abertas\n"
            "*cancelar* - cancelar abertura em andamento"
        )

    if texto_lower in [
        "nova",
        "abrir",
        "abrir pendência",
        "abrir pendencia",
        "nova pendência",
        "nova pendencia",
        "pendência",
        "pendencia"
    ]:
        if sessao:
            supabase.table(TABELA_SESSOES).delete().eq("user_id", google_user_id).execute()

        supabase.table(TABELA_SESSOES).insert({
            "user_id": google_user_id,
            "etapa": "cidade",
            "dados": {
                "solicitante": nome_usuario,
                "email_solicitante": email_usuario,
                "google_user_id": google_user_id
            }
        }).execute()

        return resposta_chat(
            f"📋 *Nova Pendência - Ações*\n\n"
            f"Solicitante identificado:\n"
            f"*{nome_usuario}*\n\n"
            f"Informe a *cidade*:"
        )

    if texto_lower in ["cancelar", "sair", "parar"]:
        if sessao:
            supabase.table(TABELA_SESSOES).delete().eq("user_id", google_user_id).execute()

        return resposta_chat(
            "Operação cancelada.\n\n"
            "Para abrir outra pendência, digite *nova*."
        )

    if texto_lower in ["listar", "pendências", "pendencias", "abertas"]:
        pend_resp = (
            supabase
            .table(TABELA_PENDENCIAS)
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
                f"Descrição: {item.get('descricao', '')[:80]}"
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
            "cidade": dados.get("cidade", ""),
            "comunidade": dados.get("comunidade", ""),
            "descricao": texto,
            "status": "Aberta",
            "responsavel": "Ações"
        }

        insert_resp = supabase.table(TABELA_PENDENCIAS).insert(pendencia).execute()

        pendencia_id = None
        if insert_resp.data:
            pendencia_id = insert_resp.data[0].get("id")

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

        return resposta_chat(
            f"✅ *Pendência criada com sucesso!*\n\n"
            f"*Protocolo:* {protocolo}\n"
            f"*Cidade:* {dados.get('cidade', '')}\n"
            f"*Comunidade:* {dados.get('comunidade', '')}\n"
            f"*Status:* Aberta\n\n"
            f"A pendência já aparece no painel."
        )

    return resposta_chat("Não entendi. Digite *nova* para abrir uma pendência.")
