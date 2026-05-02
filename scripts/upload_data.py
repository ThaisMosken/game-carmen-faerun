import firebase_admin
from firebase_admin import credentials, firestore
import json
import os

cred = credentials.Certificate("secrets/service-account.json")
firebase_admin.initialize_app(cred)
db = firestore.client()

def upload_collection(collection_name, file_path):
    """Lê um arquivo JSON e faz o upload para uma coleção no Firestore."""
    if not os.path.exists(file_path):
        print(f"Erro: Arquivo {file_path} não encontrado.")
        return

    with open(file_path, 'r', encoding='utf-8') as f:
        data_list = json.load(f)

    batch = db.batch()
    for item in data_list:
        doc_id = item.get('id')
        if not doc_id:
            print(f"Aviso: Item sem ID ignorado em {collection_name}")
            continue
        
        doc_ref = db.collection(collection_name).document(doc_id)
        batch.set(doc_ref, item)
    
    batch.commit()
    print(f"Sucesso: Coleção '{collection_name}' atualizada com {len(data_list)} registros.")

if __name__ == "__main__":
    upload_collection("cities", "data/cities.json")
    upload_collection("criminals", "data/criminals.json")
    upload_collection("venues", "data/venues.json")