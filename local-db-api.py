from fastapi import FastAPI
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware
import tensorflow as tf
import tensorflow_hub as hub
import tensorflow_text
import pandas as pd
import numpy as np
import json

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=['*'],
    allow_credentials=True,
    allow_methods=['*'],
    allow_headers=['*'],
)

# embeddings model
model_url = 'https://tfhub.dev/google/universal-sentence-encoder-multilingual/3'
encoder = hub.KerasLayer(model_url, trainable=False)

# excel data
df = pd.read_excel('output.xlsx')
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

    batch_size = 4
    num_iter = len(df) // batch_size
    db = np.empty(shape=(df.shape[0], 512), dtype=np.float32)

    for i in range(num_iter):
        start_index = i * batch_size
        end_index = start_index + batch_size
        batch = df.iloc[start_index:end_index]

        embeddings = encoder(batch['PFSA'].to_list())
        db[start_index:end_index] = embeddings.numpy()
        print(f'{i} out of {num_iter}')
        break

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
    query_embedding = encoder(query.query)
    query_tensor = tf.constant(query_embedding, dtype=tf.float32)
    query_norm = tf.nn.l2_normalize(query_tensor, axis=1)

    similarities = tf.linalg.matmul(query_norm, tf.transpose(database['embeds']))
    top_indices = tf.argsort(tf.reshape(similarities, [-1]), direction='DESCENDING')[:10]

    return json.dumps(top_indices.numpy().tolist())


@app.get('/', tags=['info'])
def ping():
    return {'message': 'Hey there!'}
