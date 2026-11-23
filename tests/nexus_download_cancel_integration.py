"""Stop a real verified aria process serving harmless temporary local data."""
import http.server
import tempfile
import threading
import time
from pathlib import Path
from nexus_repacks.downloads import Download, parse_progress


class Fixture(http.server.BaseHTTPRequestHandler):
    def log_message(self,*args): pass
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-Length',str(64*1024**2))
        self.send_header('Content-Type','application/octet-stream')
        self.end_headers()
        try:
            for _ in range(1024):
                self.wfile.write(b'Harmless local test data. '.ljust(65536,b'.'))
                self.wfile.flush()
                time.sleep(.01)
        except (BrokenPipeError,ConnectionResetError,ConnectionAbortedError):
            pass


def main():
    server=http.server.ThreadingHTTPServer(('127.0.0.1',0),Fixture)
    threading.Thread(target=server.serve_forever,daemon=True).start()
    try:
        with tempfile.TemporaryDirectory() as tmp:
            progress=threading.Event()
            def log(line):
                p=parse_progress(line)
                if p.get('ratio',0):
                    progress.set()
            job=Download(f'http://127.0.0.1:{server.server_port}/fixture.bin',Path(tmp)/'payload',log)
            worker=threading.Thread(target=job.run,daemon=True)
            worker.start()
            try:
                assert progress.wait(10),'No live progress received'
            finally:
                job.cancel()
                worker.join(10)
            assert not worker.is_alive(),'aria failed to stop'
            assert job.process.poll() is not None
            assert job.cancelled
            assert (Path(tmp)/'payload'/'fixture.bin').stat().st_size>0,'Partial payload not preserved'
            print('PASS: live progress received; real aria stopped; partial file preserved; user downloads untouched')
    finally:
        server.shutdown()


if __name__=='__main__':
    main()
