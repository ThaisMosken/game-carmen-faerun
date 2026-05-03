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


def get_valid_session(db, session_id):
    """Verifica se a sessão existe e retorna os dados."""
    if not session_id:
        return None, None

    session_ref = db.collection("sessions").document(session_id)
    session_doc = session_ref.get()

    if not session_doc.exists:
        return None, None

    return session_ref, session_doc.to_dict()


@https_fn.on_request()
def start_game(req: https_fn.Request) -> https_fn.Response:
    cors_headers, is_options = handle_cors(req)
    if is_options:
        return cors_headers

    db = firestore.client()
    try:
        criminals = [d.to_dict() for d in db.collection("criminals").stream()]
        cities = [d.to_dict() for d in db.collection("cities").stream()]
        venues = [d.to_dict() for d in db.collection("venues").stream()]

        criminal = random.choice(criminals)
        trail_cities = random.sample(cities, 6)
        trail_ids = [c["id"] for c in trail_cities]
        first_city_venues = [v["id"] for v in random.sample(venues, 3)]
        non_trail_cities = [c["id"] for c in cities if c["id"] not in trail_ids]
        initial_distractors = random.sample(non_trail_cities, min(4, len(non_trail_cities)))

        session_ref = db.collection("sessions").document()
        session_data = {
            "criminal_id": criminal["id"],
            "trail": trail_ids,
            "current_step": 0,
            "current_location": trail_ids[0],
            "start_time": firestore.SERVER_TIMESTAMP,
            "venues_per_city": {
                trail_ids[0]: first_city_venues
            },
            "used_curiosities_per_city": {},
            "distractors_per_city": {
                trail_ids[0]: initial_distractors
            },
        }
        session_ref.set(session_data)

        return https_fn.Response(
            json.dumps({
                "sessionId": session_ref.id,
                "firstCityId": trail_ids[0],
                "venues": first_city_venues,
                "travelOptions": _build_travel_options(
                    trail_ids=trail_ids,
                    current_step=0,
                    current_location=trail_ids[0], # Adicionado aqui
                    history=[trail_ids[0]],
                    distractors=initial_distractors,
                )
            }),
            mimetype="application/json",
            headers=cors_headers
        )
    except Exception as e:
        return https_fn.Response(json.dumps({"error": str(e)}), status=500, headers=cors_headers)


def _build_travel_options(trail_ids, current_step, current_location, history, distractors):
    """
    Monta a lista de até 5 opções de viagem da mesma forma que o frontend original fazia:
    - Cidade anterior (para voltar), se existir no histórico
    - Próxima cidade correta da trilha, se existir
    - Cidades distratoras fixas (fora da trilha)
    Embaralha o resultado final.
    """
    options = set()

    if len(history) > 1:
        options.add(history[-2])

    if current_location == trail_ids[current_step]:
        if current_step < len(trail_ids) - 1:
            options.add(trail_ids[current_step + 1])

    for d in distractors:
        options.add(d)

    result = list(options)[:5]
    random.shuffle(result)
    return result


@https_fn.on_request()
def investigate(req: https_fn.Request) -> https_fn.Response:
    cors_headers, is_options = handle_cors(req)
    if is_options:
        return cors_headers

    db = firestore.client()
    try:
        data = req.get_json()
        session_id = data.get("sessionId")
        session_ref, session = get_valid_session(db, session_id)

        if not session:
            return https_fn.Response(
                json.dumps({"error": "Sessão não encontrada ou expirada."}),
                status=404,
                mimetype="application/json",
                headers=cors_headers
            )

        venue_id = data.get("venueId")
        current_step = session["current_step"]
        trail = session["trail"]
        criminal_id = session["criminal_id"]
        current_location = session.get("current_location")

        if current_location != trail[current_step]:
            clues_wrong_track = [
                "As ruas estão calmas, ninguém suspeito passou por aqui.",
                "Não vi ninguém com essa descrição. Você deve ter se perdido no caminho.",
                "Acho que você está procurando no lugar errado, forasteiro.",
            ]
            return https_fn.Response(
                json.dumps({"clue": random.choice(clues_wrong_track), "captured": False}),
                mimetype="application/json",
                headers=cors_headers
            )

        criminal = db.collection("criminals").document(criminal_id).get().to_dict()

        if current_step == len(trail) - 1:
            used_in_final = session.get("used_curiosities_per_city", {}).get(trail[current_step], [])
            attempts_in_city = len(used_in_final)

            if attempts_in_city == 0:
                capture_probability = 0.8
            elif attempts_in_city == 1:
                capture_probability = 0.6
            else:
                capture_probability = 1.0

            used_in_final_updated = used_in_final + [venue_id]
            session_ref.update({
                f"used_curiosities_per_city.{trail[current_step]}": used_in_final_updated
            })

            captured = random.random() < capture_probability

            return https_fn.Response(
                json.dumps({
                    "clue": "O suspeito foi visto por aqui há poucos minutos!",
                    "captured": captured
                }),
                mimetype="application/json",
                headers=cors_headers
            )

        next_city_id = trail[current_step + 1]
        next_city = db.collection("cities").document(next_city_id).get().to_dict()
        curiosities_map = next_city.get("curiosities", {})
        all_curiosity_values = list(curiosities_map.values())

        used_curiosities = session.get("used_curiosities_per_city", {}).get(current_location, [])
        available_curiosities = [c for c in all_curiosity_values if c not in used_curiosities]

        if not available_curiosities:
            available_curiosities = all_curiosity_values

        lead = random.choice(available_curiosities)

        updated_used = used_curiosities + [lead]
        session_ref.update({
            f"used_curiosities_per_city.{current_location}": updated_used
        })

        add_clue = random.random() < 0.5

        gender_prefix = "A mulher" if criminal.get("gender") == "F" else "O homem"
        traits = [
            f"{gender_prefix} que você procura esteve aqui e",
            f"Vi uma pessoa de cabelo {criminal.get('hair')} que",
            f"Vi alguém com {criminal.get('feature')} que",
            f"Havia por aqui um viajante que costumava jogar {criminal.get('hobby')} e que",
            f"Alguém assim chegou {criminal.get('vehicle')} e",
            f"Uma pessoa assim estava comentando sobre gostar de {criminal.get('cuisine')} e",
        ]

        criminal_clue = random.choice(traits) + " " if add_clue else " Um viajante "
        lead_lower = lead[0].lower() + lead[1:]

        venue_doc = db.collection("venues").document(venue_id).get()
        venue_data = venue_doc.to_dict() if venue_doc.exists else {}
        role = venue_data.get("role", "encarregado")

        dialogue_templates = {
            "biblioteca": [
                f"(O bibliotecário ajeita os óculos) {criminal_clue}requisitou pergaminhos raros que descreviam {lead_lower}.",
                f"(O bibliotecário consulta um registro) Tivemos um visitante interessado em histórias sobre {lead_lower}.",
            ],
            "cartografo": [
                f"(O cartógrafo limpa a tinta dos dedos) {criminal_clue}queria um mapa de {lead_lower}.",
                f"(O cartógrafo limpa a tinta dos dedos) Um curioso esteve aqui olhando mapas de {lead_lower}.",
            ],
            "centro_cultural": [
                f"(O guia local aponta para um mural) {criminal_clue}passou um longo tempo estudando a representação sobre {lead_lower}.",
                f"(O guia local consulta um folheto) Tivemos um visitante procurando por apresentações sobre {lead_lower}.",
            ],
            "estalagem": [
                f"(O estalajadeiro entrega uma chave) {criminal_clue}alugou um quarto, mas passou a noite escrevendo sobre {lead_lower}.",
                f"(O estalajadeiro limpa uma caneca) Alguém com essa descrição saiu cedo, resmungando algo sobre {lead_lower}.",
            ],
            "estaleiro": [
                f"(O mestre do cais observa as amarras) {criminal_clue}tentou fretar um barco que carregava alguns contêineres com {lead_lower}.",
                f"(O mestre do cais aponta para a água) O sujeito partiu no último barco após fazer perguntas sobre {lead_lower}.",
            ],
            "museu": [
                f"(O curador ajeita uma vitrine) {criminal_clue}demonstrou um interesse acadêmico incomum na exposição sobre {lead_lower}.",
                f"(O curador consulta o catálogo) Lembro-me de um visitante que passou horas examinando artefatos sobre {lead_lower}.",
            ],
            "oficina_gemas": [
                f"(O mestre joalheiro analisa uma pedra) {criminal_clue}trouxe uma joia para avaliar, alegando precisar de fundos para viajar para {lead_lower}.",
                f"(O mestre joalheiro guarda as ferramentas) Um cliente com essas características esteve aqui perguntando sobre {lead_lower}.",
            ],
            "patio_carrocas": [
                f"(O mestre de carga confere uma lista) {criminal_clue}comprou mantimentos para uma viagem, mencionando algo sobre {lead_lower}.",
                f"(O mestre de carga olha o horizonte) Alguém com essas características partiu após questionar sobre {lead_lower}.",
            ],
            "patio_treinamento": [
                f"(O mestre d'armas golpeia o boneco) {criminal_clue}observou os treinos e perguntou sobre as táticas de combate de {lead_lower}.",
                f"(O mestre d'armas limpa o suor) Alguém perguntou se nossas lâminas seriam eficazes contra {lead_lower}.",
            ],
            "santuario": [
                f"(O sacerdote acende uma vela) {criminal_clue}fez uma oferta aos deuses pedindo proteção e perguntou sobre {lead_lower}.",
                f"(O sacerdote fecha o livro de preces) Tivemos um fiel angustiado que buscava orientação divina sobre {lead_lower}.",
            ],
            "taverna": [
                f"(O taverneiro limpa o balcão) {criminal_clue}esteve aqui e não parava de perguntar sobre {lead_lower}.",
                f"(O taverneiro aponta para uma mesa vazia) Aquele sujeito de quem você falou? Ele passou a noite pesquisando sobre {lead_lower}.",
            ],
            "torre_alta_magia": [
                f"(O arcanista consulta uma esfera) {criminal_clue}contratou um feitiço para recontar sobre {lead_lower}.",
                f"(O arcanista ajusta as vestes) Um visitante assim passou por aqui e quase esqueceu um pergaminho sobre {lead_lower}.",
            ],
        }

        templates = dialogue_templates.get(venue_id, [
            f"(O {role} olha para você) {criminal_clue}demonstrou um interesse incomum sobre {lead_lower}.",
            f"(O {role} faz uma pausa) Me lembro de alguém perguntando sobre o relato de que {lead_lower}.",
        ])

        final_clue = random.choice(templates)

        return https_fn.Response(
            json.dumps({"clue": final_clue, "captured": False}),
            mimetype="application/json",
            headers=cors_headers
        )

    except Exception as e:
        return https_fn.Response(json.dumps({"error": str(e)}), status=500, headers=cors_headers)


@https_fn.on_request()
def travel(req: https_fn.Request) -> https_fn.Response:
    cors_headers, is_options = handle_cors(req)
    if is_options:
        return cors_headers

    db = firestore.client()
    try:
        data = req.get_json()
        target_city_id = data.get("targetCityId")
        history = data.get("history", [target_city_id])

        session_id = data.get("sessionId")
        session_ref, session = get_valid_session(db, session_id)

        if not session:
            return https_fn.Response(
                json.dumps({"error": "Sessão não encontrada ou expirada."}),
                status=404,
                mimetype="application/json",
                headers=cors_headers
            )

        current_location_before = session.get("current_location")
        current_step = session["current_step"]
        trail = session["trail"]
        venues_per_city = session.get("venues_per_city", {})
        distractors_per_city = session.get("distractors_per_city", {})

        if (current_location_before == trail[current_step] and 
            current_step + 1 < len(trail) and 
            target_city_id == trail[current_step + 1]):
            current_step += 1

        if target_city_id not in venues_per_city:
            all_venues = [d.to_dict()["id"] for d in db.collection("venues").stream()]
            venues_per_city[target_city_id] = random.sample(all_venues, min(3, len(all_venues)))

        if target_city_id not in distractors_per_city:
            non_trail_cities = [
                c.to_dict()["id"]
                for c in db.collection("cities").stream()
                if c.to_dict()["id"] not in trail
            ]
            distractors_per_city[target_city_id] = random.sample(
                non_trail_cities, min(4, len(non_trail_cities))
            )

        session_ref.update({
            "current_location": target_city_id,
            "current_step": current_step,
            "venues_per_city": venues_per_city,
            "distractors_per_city": distractors_per_city,
        })

        travel_options = _build_travel_options(
            trail_ids=trail,
            current_step=current_step,
            current_location=target_city_id,
            history=history,
            distractors=distractors_per_city[target_city_id],
        )

        return https_fn.Response(
            json.dumps({
                "cityId": target_city_id,
                "venues": venues_per_city[target_city_id],
                "travelOptions": travel_options,
            }),
            mimetype="application/json",
            headers=cors_headers
        )

    except Exception as e:
        return https_fn.Response(json.dumps({"error": str(e)}), status=500, headers=cors_headers)


@https_fn.on_request()
def arrest(req: https_fn.Request) -> https_fn.Response:
    """
    Endpoint mantido para compatibilidade, mas na lógica correta a captura
    acontece dentro do endpoint /investigate (quando captured=True é retornado).
    Este endpoint valida apenas se o mandado emitido está correto,
    e pode ser usado como fallback ou verificação final.
    """
    cors_headers, is_options = handle_cors(req)
    if is_options:
        return cors_headers

    db = firestore.client()
    try:
        data = req.get_json()
        session_id = data.get("sessionId")
        session_ref, session = get_valid_session(db, session_id)

        if not session:
            return https_fn.Response(
                json.dumps({"error": "Sessão não encontrada ou expirada."}),
                status=404,
                mimetype="application/json",
                headers=cors_headers
            )

        warrant_id = data.get("warrantId")
        status = "won" if warrant_id == session["criminal_id"] else "wrong_warrant"

        return https_fn.Response(
            json.dumps({"status": status}),
            mimetype="application/json",
            headers=cors_headers
        )

    except Exception as e:
        return https_fn.Response(json.dumps({"error": str(e)}), status=500, headers=cors_headers)