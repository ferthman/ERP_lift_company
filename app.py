import os

from liftcrm import create_app

app = create_app()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    debug = os.environ.get("DEBUG", "false").lower() in {"1", "true", "yes"}
    app.run(host=os.environ.get("HOST", "127.0.0.1"), port=port, debug=debug)
