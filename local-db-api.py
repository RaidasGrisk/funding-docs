from fastapi import FastAPI
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware
import tensorflow as tf
import tensorflow_hub as hub
import tensorflow_text
import pandas as pd
import numpy as np
import json
import re

from transformers import CanineTokenizer, CanineModel
from transformers import AutoConfig

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=['*'],
    allow_credentials=True,
    allow_methods=['*'],
    allow_headers=['*'],
)

# embeddings model
# model_url = 'https://tfhub.dev/google/universal-sentence-encoder-multilingual/3'
# encoder = hub.KerasLayer(model_url, trainable=False)

# model objects
model_name = 'google/canine-s'
config = AutoConfig.from_pretrained(model_name)
max_length = config.max_position_embeddings

model = CanineModel.from_pretrained(model_name)
tokenizer = CanineTokenizer.from_pretrained(model_name)

# excel data
# df = pd.read_excel('output.xlsx')
df = pd.read_parquet('output.parquet')
df['id_'] = df.groupby('id').cumcount().apply(lambda x: f'{x+1}') + ' | ' + df['id']
df = df[df['IS_PFSA_BETTER'] == True]

# init local db
# TODO: put all this into google drive
#  - put embeddings to csv
#  - put whole dataset into csv
#  - fetch it on frontend
database = {}


@app.on_event('startup')
async def startup():

    # TODO: slice texts into 2024 words or similar and create db_indices

    batch_size = 4
    num_iter = len(df) // batch_size
    db = np.empty(shape=(df.shape[0], 768), dtype=np.float32)

    # clean the text input
    texts = df['PFSA'].to_list()
    texts = [text.replace('\n', ' ').replace('\t', ' ').replace(u'\xa0', '') for text in texts]

    for i in range(num_iter):
        start_index = i * batch_size
        end_index = start_index + batch_size
        batch = texts[start_index:end_index]

        encoding = tokenizer(batch, padding="longest", truncation=True, return_tensors="pt")
        outputs = model(**encoding)
        embeddings = outputs.pooler_output.detach()

        db[start_index:end_index] = embeddings.numpy()
        print(f'{i} out of {num_iter}')

    # convert to proper tensorflow objects so that no need to deal with it later
    db = tf.Variable(initial_value=db, trainable=False)
    database['embeds'] = tf.nn.l2_normalize(db, axis=1)


@app.on_event('shutdown')
async def shutdown():
    print('shutting down')


class Query(BaseModel):
    query: str


@app.post('/search')
def search(query: Query):

    encoding = tokenizer([query.query], padding="longest", truncation=True, return_tensors="pt")
    query_embedding = model(**encoding).pooler_output.detach().numpy()

    query_tensor = tf.constant(query_embedding, dtype=tf.float32)
    query_norm = tf.nn.l2_normalize(query_tensor, axis=1)

    similarities = tf.linalg.matmul(query_norm, tf.transpose(database['embeds']))
    top_indices = tf.argsort(similarities, direction='DESCENDING')[0]
    top_similarities = tf.gather(similarities[0], top_indices)

    return json.dumps({
        'indices': top_indices.numpy().tolist(),
        'similarities': top_similarities.numpy().tolist(),
    })


@app.get('/', tags=['info'])
def ping():
    return {'message': 'Hey there!'}
