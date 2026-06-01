from fastapi import FastAPI, Request
from supabase import create_client
from datetime import datetime
import os

app = FastAPI()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)


def protocolo():
    return "MAR-" + datetime.now().strftime("%Y%m%d%H%M%S")


def get_user(event):
    user = event.get("user", {})
    return user.get("name") or user.get("email") or user.get("displayName") or "usuario_google_chat"


def resposta(texto):
    return {"text": texto}

@app.post("/google-chat-marcos")
async def google_chat_marcos(request: Request):
    event = await request.json()
    texto = (event.get("message", {}).get("text") or "").strip()
    user_id = get_user(event)

    if not texto:
        return resposta("Digite: abrir pendência")

    session_resp = supabase.table("chat_sessions_marcos").select("*").eq("user_id", user_id).execute()
    sess = session_resp.data[0] if session_resp.data else None

    if texto.lower() in ["abrir", "abrir pendência", "abrir pendencia", "nova", "nova pendência", "nova pendencia"]:
        if sess:
            supabase.table("chat_sessions_marcos").delete().eq("user_id", user_id).execute()
        supabase.table("chat_sessions_marcos").insert({"user_id": user_id, "etapa": "nome", "dados": {}}).execute()
        return resposta("Vamos abrir uma pendência para o Marcos.\n\nInforme seu nome:")

    if not sess:
        return resposta("Para abrir uma pendência, digite: abrir pendência")

    etapa = sess.get("etapa")
    dados = sess.get("dados") or {}

    if etapa == "nome":
        dados["nome_solicitante"] = texto
        supabase.table("chat_sessions_marcos").update({"etapa": "cidade", "dados": dados}).eq("user_id", user_id).execute()
        return resposta("Informe a cidade:")

    if etapa == "cidade":
        dados["cidade"] = texto
        supabase.table("chat_sessions_marcos").update({"etapa": "comunidade", "dados": dados}).eq("user_id", user_id).execute()
        return resposta("Informe a comunidade:")

    if etapa == "comunidade":
        dados["comunidade"] = texto
        supabase.table("chat_sessions_marcos").update({"etapa": "descricao", "dados": dados}).eq("user_id", user_id).execute()
        return resposta("Descreva a pendência:")

    if etapa == "descricao":
        prot = protocolo()
        pendencia = {
            "protocolo": prot,
            "nome_solicitante": dados.get("nome_solicitante", ""),
            "cidade": dados.get("cidade", ""),
            "comunidade": dados.get("comunidade", ""),
            "descricao": texto,
            "status": "Aberta",
            "responsavel": "Marcos",
        }
        supabase.table("pendencias_marcos").insert(pendencia).execute()
        supabase.table("chat_sessions_marcos").delete().eq("user_id", user_id).execute()
        return resposta(f"Pendência aberta com sucesso.\n\nProtocolo: {prot}\nResponsável: Marcos\nStatus: Aberta")

    return resposta("Digite: abrir pendência")
