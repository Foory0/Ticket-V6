from flask import Flask
from threading import Thread
from waitress import serve

app = Flask('')

@app.route('/')
def home():
    return "البوت يعمل!"

def run():
    serve(app, host='0.0.0.0', port=8080)

def keep_alive():
    t = Thread(target=run)
    t.start() 