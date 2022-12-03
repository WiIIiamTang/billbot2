from flask import Flask, abort

app = Flask(__name__)


@app.route("/")
def bad_home():
    # Return a forbidden error
    abort(403)


@app.route("/ack/health")
def health():
    # return 200 OK response
    return "OK", 200
