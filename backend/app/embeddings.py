from typing import List
from openai import OpenAI
import os
import streamlit as st


##############################################################################
# Update later for open source models
##############################################################################
@st.cache_resource
def get_openai_client():
    return OpenAI(api_key=st.secrets["OPENAI_API_KEY"])

_client = get_openai_client()

EMBEDDING_MODEL = "text-embedding-3-small"


def embed_texts(texts: List[str]) -> List[List[float]]:
    # OpenAI expects a list of inputs
    resp = _client.embeddings.create(
        model=EMBEDDING_MODEL,
        input=texts,
    )
    return [d.embedding for d in resp.data]
