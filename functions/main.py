from firebase_functions import https_fn
from firebase_admin import initialize_app, firestore
import random
import json

initialize_app()

def handle_cors(req: https_fn.Request):
    """Função utilitária para tratar o CORS de todas as rotas."""
    if req.method == "OPTIONS":
        headers = {
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "POST, GET, OPTIONS",
            "Access-Control-Allow-Headers": "Content-Type",
            "Access-Control-Max-Age": "3600",
        }
        return https_fn.Response("", status=204, headers=headers), True
    return {"Access-Control-Allow-Origin": "*"}, False

@https_fn.on_request()
def start_game(req: https_fn.Request) -> https_fn.Response:
    cors_headers, is_options = handle_cors(req)
    if is_options: return cors_headers

    db = firestore.client()
    try:
        criminals = [d.to_dict() for d in db.collection("criminals").stream()]
        cities = [d.to_dict() for d in db.collection("cities").stream()]
        venues = [d.to_dict() for d in db.collection("venues").stream()]

        criminal = random.choice(criminals)
        trail_cities = random.sample(cities, 6)
        trail_ids = [c["id"] for c in trail_cities]
        
        # Sorteia 3 locais para a cidade inicial
        first_city_venues = [v["id"] for v in random.sample(venues, 3)]

        session_ref = db.collection("sessions").document()
        session_data = {
            "criminal_id": criminal["id"],
            "trail": trail_ids,
            "current_step": 0,
            "current_location": trail_ids[0], # Registra a posição física do jogador
            "start_time": firestore.SERVER_TIMESTAMP,
            "venues_per_city": {
                trail_ids[0]: first_city_venues
            }
        }
        session_ref.set(session_data)

        return https_fn.Response(
            json.dumps({
                "sessionId": session_ref.id,
                "firstCityId": trail_ids[0],
                "venues": first_city_venues
            }),
            mimetype="application/json",
            headers=cors_headers
        )
    except Exception as e:
        return https_fn.Response(json.dumps({"error": str(e)}), status=500, headers=cors_headers)

@https_fn.on_request()
def investigate(req: https_fn.Request) -> https_fn.Response:
    cors_headers, is_options = handle_cors(req)
    if is_options: return cors_headers

    db = firestore.client()
    try:
        data = req.get_json()
        session_id = data.get("sessionId")
        venue_id = data.get("venueId")

        session_ref = db.collection("sessions").document(session_id)
        session = session_ref.get().to_dict()

        current_step = session["current_step"]
        trail = session["trail"]
        criminal_id = session["criminal_id"]
        current_location = session.get("current_location")

        if current_location != trail[current_step]:
            clues_wrong_track = [
                "As ruas estão calmas, ninguém suspeito passou por aqui.",
                "Não vi ninguém com essa descrição. Você deve ter se perdido no caminho.",
                "Acho que você está procurando no lugar errado, forasteiro."
            ]
            return https_fn.Response(
                json.dumps({"clue": random.choice(clues_wrong_track)}),
                mimetype="application/json",
                headers=cors_headers
            )

        criminal = db.collection("criminals").document(criminal_id).get().to_dict()
        
        gender_prefix = "Uma mulher" if criminal.get('gender') == 'F' else "Um homem"
        traits = [
            f"{gender_prefix} que você procura esteve aqui e",
            f"Vi uma pessoa de cabelo {criminal.get('hair')} que",
            f"Vi alguém com {criminal.get('feature')} que",
            f"Havia por aqui um viajante que costumava jogar {criminal.get('hobby')} e que",
            f"Alguém assim chegou {criminal.get('vehicle')} e",
            f"Uma pessoa assim estava comentando sobre gostar de {criminal.get('cuisine')} e"
        ]
        criminal_clue = random.choice(traits)

        if current_step + 1 < len(trail):
            next_city_id = trail[current_step + 1]
            next_city = db.collection("cities").document(next_city_id).get().to_dict()
            curiosities = list(next_city.get('curiosities', {}).values())
            lead = random.choice(curiosities) if curiosities else "um local desconhecido"

        dialogue_templates = {
            "biblioteca": [
                f"(O bibliotecário ajeita os óculos) {criminal_clue} requisitou pergaminhos raros que descreviam {lead}.",
                f"(O bibliotecário consulta um registro) Tivemos um visitante interessado em histórias sobre {lead}."
            ],
            "cartografo": [
                f"(O cartógrafo limpa a tinta dos dedos) {criminal_clue} queria um mapa sobre {lead}.",
                f"(O cartógrafo limpa a tinta dos dedos) Um curioso esteve aqui olhando mapas sobre {lead}."
            ],
            "centro_cultural": [
                f"(O guia local aponta para um mural) {criminal_clue} passou um longo tempo estudando a representação sobre {lead}.",
                f"(O guia local consulta um folheto) Tivemos um visitante procurando por apresentações sobre {lead}."
            ],
            "estalagem": [
                f"(O estalajadeiro entrega uma chave) {criminal_clue} alugou um quarto, mas passou a noite escrevendo sobre {lead}.",
                f"(O estalajadeiro limpa uma caneca) Alguém com essa descrição saiu cedo, resmungando algo sobre {lead}."
            ],
            "estaleiro": [
                f"(O mestre do cais observa as amarras) {criminal_clue} tentou fretar um barco que carregava alguns contêineres com {lead}.",
                f"(O mestre do cais aponta para a água) O sujeito partiu no último barco após fazer perguntas sobre {lead}."
            ],
            "museu": [
                f"(O curador ajeita uma vitrine) {criminal_clue} demonstrou um interesse acadêmico incomum na exposição sobre {lead}.",
                f"(O curador consulta o catálogo) Lembro-me de um visitante que passou horas examinando artefatos sobre {lead}."
            ],
            "oficina_gemas": [
                f"(O mestre joalheiro analisa uma pedra) {criminal_clue} trouxe uma joia para avaliar, alegando precisar de fundos para viajar para {lead}.",
                f"(O mestre joalheiro guarda as ferramentas) Um cliente com essas características esteve aqui perguntando sobre {lead}."
            ],
            "patio_carrocas": [
                f"(O mestre de carga confere uma lista) {criminal_clue} comprou mantimentos para uma viagem, mencionando algo sobre {lead}.",
                f"(O mestre de carga olha o horizonte) Alguém com essas características partiu após questionar sobre {lead}."
            ],
            "patio_treinamento": [
                f"(O mestre d'armas golpeia o boneco) {criminal_clue} observou os treinos e perguntou sobre as táticas de combate de {lead}.",
                f"(O mestre d'armas limpa o suor) Alguém perguntou se nossas lâminas seriam eficazes contra {lead}."
            ],
            "santuario": [
                f"(O sacerdote acende uma vela) {criminal_clue} fez uma oferta aos deuses pedindo proteção e perguntou sobre {lead}.",
                f"(O sacerdote fecha o livro de preces) Tivemos um fiel angustiado que buscava orientação divina sobre {lead}."
            ],
            "taverna": [
                f"(O taverneiro limpa o balcão) {criminal_clue} esteve aqui e não parava de perguntar sobre {lead}.",
                f"(O taverneiro aponta para uma mesa vazia) Aquele sujeito de quem você falou? Ele passou a noite pesquisando sobre {lead}."
            ],
            "torre_alta_magia": [
                f"(O arcanista consulta uma esfera) {criminal_clue} contratou um feitiço para recontar sobre {lead}.",
                f"(O arcanista ajusta as vestes) Um visitante assim passou por aqui e quase esqueceu um pergaminho sobre {lead}."
            ],
            "default": [
                f"(O {venue_doc.get('role', 'encarregado')} olha para você) {criminal_clue} demonstrou um interesse incomum sobre {lead}.",
                f"(O {venue_doc.get('role', 'encarregado')} faz uma pausa) Me lembro de alguém perguntando sobre o relato de que {lead}."
            ]
        }

        else:
            templates = dialogue_templates.get(venue_id, dialogue_templates["default"])
            final_clue = random.choice(templates)[cite: 1]

        return https_fn.Response(
            json.dumps({"clue": final_clue}),
            mimetype="application/json",
            headers=cors_headers
        )
    except Exception as e:
        return https_fn.Response(json.dumps({"error": str(e)}), status=500, headers=cors_headers)

@https_fn.on_request()
def travel(req: https_fn.Request) -> https_fn.Response:
    cors_headers, is_options = handle_cors(req)
    if is_options: return cors_headers

    db = firestore.client()
    try:
        data = req.get_json()
        session_id = data.get("sessionId")
        target_city_id = data.get("targetCityId")

        session_ref = db.collection("sessions").document(session_id)
        session = session_ref.get().to_dict()

        current_step = session["current_step"]
        trail = session["trail"]
        venues_per_city = session.get("venues_per_city", {})

        # Valida se o jogador avançou na trilha correta
        if current_step + 1 < len(trail) and target_city_id == trail[current_step + 1]:
            current_step += 1

        # Gera novos locais para explorar se a cidade for nova na sessão
        if target_city_id not in venues_per_city:
            all_venues = [d.to_dict()["id"] for d in db.collection("venues").stream()]
            venues_per_city[target_city_id] = random.sample(all_venues, min(3, len(all_venues)))

        session_ref.update({
            "current_location": target_city_id,
            "current_step": current_step,
            "venues_per_city": venues_per_city
        })

        return https_fn.Response(
            json.dumps({
                "cityId": target_city_id,
                "venues": venues_per_city[target_city_id]
            }),
            mimetype="application/json",
            headers=cors_headers
        )
    except Exception as e:
        return https_fn.Response(json.dumps({"error": str(e)}), status=500, headers=cors_headers)

@https_fn.on_request()
def arrest(req: https_fn.Request) -> https_fn.Response:
    cors_headers, is_options = handle_cors(req)
    if is_options: return cors_headers

    db = firestore.client()
    try:
        data = req.get_json()
        session_id = data.get("sessionId")
        warrant_id = data.get("warrantId")

        session_ref = db.collection("sessions").document(session_id)
        session = session_ref.get().to_dict()

        status = "won" if warrant_id == session["criminal_id"] else "wrong_warrant"

        return https_fn.Response(
            json.dumps({"status": status}),
            mimetype="application/json",
            headers=cors_headers
        )
    except Exception as e:
        return https_fn.Response(json.dumps({"error": str(e)}), status=500, headers=cors_headers)