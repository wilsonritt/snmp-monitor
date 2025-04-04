# SNMP Monitor

Monitoramento em tempo real de tráfego de interfaces via SNMP (usando Streamlit + easysnmp)

## Como usar

1. Construa a imagem:

```bash
docker build -t snmp-monitor .
```

2. Rode o container:

```bash
docker run -it --rm -p 8501:8501 snmp-monitor
```

3. Acesse no navegador:

http://localhost:8501
