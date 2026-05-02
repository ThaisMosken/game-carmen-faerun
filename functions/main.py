from firebase_functions import https_fn
from firebase_admin import initialize_app, firestore
import random
import json

initialize_app()

@https_fn.on_request()
def start_game(req: https_fn.Request) -> https_fn.Response:
    if req.method == "OPTIONS":
        headers = {
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "POST, GET, OPTIONS",
            "Access-Control-Allow-Headers": "Content-Type",
            "Access-Control-Max-Age": "3600",
        }
        return https_fn.Response("", status=204, headers=headers)

    headers = {"Access-Control-Allow-Origin": "*"}
    db = firestore.client()

    try:
        criminals = [d.to_dict() for d in db.collection("criminals").stream()]
        cities = [d.to_dict() for d in db.collection("cities").stream()]
        venues = [d.to_dict() for d in db.collection("venues").stream()]

        criminal = random.choice(criminals)
        trail_cities = random.sample(cities, 6)
        trail_ids = [c["id"] for c in trail_cities]

        session_ref = db.collection("sessions").document()
        session_data = {
            "criminal_id": criminal["id"],
            "trail": trail_ids,
            "current_step": 0,
            "start_time": firestore.SERVER_TIMESTAMP,
            "venues_per_city": {
                city_id: [v["id"] for v in random.sample(venues, 3)]
                for city_id in trail_ids
            }
        }
        session_ref.set(session_data)

        response_data = {
            "sessionId": session_ref.id,
            "firstCityId": trail_ids[0],
            "venues": session_data["venues_per_city"][trail_ids[0]]
        }

        return https_fn.Response(
            json.dumps(response_data),
            mimetype="application/json",
            headers=headers
        )

    except Exception as e:
        return https_fn.Response(
            json.dumps({"error": str(e)}),
            status=500,
            mimetype="application/json",
            headers=headers
        )