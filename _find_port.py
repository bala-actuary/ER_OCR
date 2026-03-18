"""Find a free port in range 7000-7009. Used by start.bat."""
import socket, sys

for p in range(7000, 7010):
    s = socket.socket()
    try:
        s.bind(('127.0.0.1', p))
        s.close()
        print(p)
        sys.exit(0)
    except OSError:
        pass

print(7000)
