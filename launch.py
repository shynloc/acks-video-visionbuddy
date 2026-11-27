"""Open the local library from a previously downloaded ZIP."""
import sys
import threading
import webbrowser

from serve import make_server


def main():
    try:
        import PIL  # availability is checked before starting the gallery
    except ImportError:
        sys.exit("请先安装 Pillow，或使用已安装口播导演工作台的 Python 环境。参见 README。")
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
