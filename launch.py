"""Open the local library from a previously downloaded ZIP."""
import threading
import webbrowser

from serve import make_server


def main():
    with make_server("127.0.0.1", 0) as server:
        url = f"http://127.0.0.1:{server.server_port}"
        print(f"VisionBuddy 离线素材库 · {url}", flush=True)
        timer = threading.Timer(0.35, webbrowser.open, (url,))
        timer.daemon = True
        timer.start()
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
