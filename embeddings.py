import openai
import os
import numpy as np
from dotenv import load_dotenv

load_dotenv()

class EmbeddingService:
    def __init__(self, api_key: str = None):
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        self.client = openai.OpenAI(api_key=self.api_key)

    def get_embedding(self, text: str, model: str = "text-embedding-ada-002"):
        response = self.client.embeddings.create(
            input=text,
            model=model
        )
        return response.data[0].embedding

    @staticmethod
    def cosine_similarity(a, b):
        a = np.array(a)
        b = np.array(b)
        return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))
