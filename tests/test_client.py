import socket

s = socket.socket()
address = '127.0.0.1'
port = 3000
try:
    s.connect((address, port))
    s.send(b"test")  # send anything
    answer = s.recv(1024)
    print(answer.decode('utf-8'))
except Exception as e:
    print(e)
finally:
    s.close()