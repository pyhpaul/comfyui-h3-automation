"""Tiny keep-alive probe executed in the Colab VM by the keeper."""
import socket

print("H3_KEEPALIVE_OK", socket.gethostname())
