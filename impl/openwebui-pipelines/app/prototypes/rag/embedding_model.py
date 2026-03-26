from sentence_transformers import SentenceTransformer

MODEL_NAME = 'BAAI/bge-small-en-v1.5'

def get_model(model_path):
    try:
        # 1. Try to load from local cache folder ONLY
        print(f"Checking for cached model at {model_path}...")
        return SentenceTransformer(MODEL_NAME, cache_folder=model_path, local_files_only=True)
    except (OSError, Exception):
        # 2. If it fails, download it
        print("Model not found locally. Downloading from Hugging Face...")
        return SentenceTransformer(MODEL_NAME, cache_folder=model_path, local_files_only=False)