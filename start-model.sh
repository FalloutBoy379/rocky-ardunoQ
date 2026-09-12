#!/bin/sh
# Run on the UNO Q. Keep this terminal open while chatting.
exec env OLLAMA_NO_CLOUD=1 OLLAMA_HOST=127.0.0.1:11434 OLLAMA_CONTEXT_LENGTH=2048 /home/arduino/rocky-runtime/bin/ollama serve
