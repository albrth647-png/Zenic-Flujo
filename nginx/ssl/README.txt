# Nginx SSL directory placeholder
# Fix Sprint 4 bug #61: docker-compose.yml monta ./nginx/ssl para TLS.
# En producción, colocar aquí:
#   - zenic-flujo.crt (certificado)
#   - zenic-flujo.key (clave privada)
# Generar self-signed para dev con:
#   openssl req -x509 -newkey rsa:2048 -nodes -days 365 \
#     -keyout zenic-flujo.key -out zenic-flujo.crt \
#     -subj "/CN=localhost"
