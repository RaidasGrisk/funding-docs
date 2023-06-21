"""
Other models to consider
https://huggingface.co/EMBEDDIA/litlat-bert

read data from google sheets:
https://towardsdatascience.com/read-data-from-google-sheets-into-pandas-without-the-google-sheets-api-5c468536550

Pinecone:
https://docs.pinecone.io/docs/semantic-text-search
"""


import pandas as pd
import tensorflow_hub as hub
import tensorflow_text
import numpy as np
import pinecone
import os
from dotenv import load_dotenv

# init pinecone connection
load_dotenv()
PINECONE_API_KEY = os.environ.get('PINECONE_API_KEY')
PINECONE_ENV = os.environ.get('PINECONE_ENV')

pinecone.init(
    api_key=PINECONE_API_KEY,
    environment=PINECONE_ENV
)

# init db index
index_name = 'semantic-search'
# pinecone.delete_index(index_name)
if index_name not in pinecone.list_indexes():
    pinecone.create_index(
        name=index_name,
        dimension=512,
        metric='cosine'
    )

index = pinecone.Index(index_name)

# read the data
df = pd.read_excel('output.xlsx')
df = df.replace(np.nan, None)
documents = df.to_dict(orient='records')
documents = [doc for doc in documents]

# embed the docs
model_url = 'https://tfhub.dev/google/universal-sentence-encoder-multilingual/3'
encoder = hub.KerasLayer(model_url, trainable=False)
for doc in documents:
    if doc['PFSA'] and doc['IS_PFSA']:
        embeddings = encoder(doc['doc'])
        doc['vector'] = embeddings

# upsert the data
for doc in documents:
    if doc['PFSA'] and doc['IS_PFSA']:
        # TODO:
        #  - same id has multiple files/vectors. Deal with it.
        #  - what do we want to store in the db? Full doc text - no.
        #  - frontend will fetch text data from elsewhere and match with db id.
        index.upsert([
            (doc['id'], doc['vector'].numpy().tolist())
        ])
        print(doc['id'])

index.describe_index_stats()

# making queries
query = 'this is the query text'
embeddings = encoder(query)
results = index.query(embeddings.numpy().tolist(), top_k=5, include_metadata=True)
print(results)
