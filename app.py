from flask import Flask

app = Flask(__name__)

@app.route("/")
def home():
    return """
    <h1>🔥 Live Stream</h1>
    <p>Yaha tera stream chalega</p>
    <video width="400" controls autoplay>
        <source src="https://example.com/video.mp4" type="video/mp4">
    </video>
    """

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
