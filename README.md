# 🛡️ Juniper Backup Automation

![Python](https://img.shields.io/badge/Python-3.9-3776AB?style=for-the-badge&logo=python&logoColor=white)
![Docker](https://img.shields.io/badge/Docker-Ready-2496ED?style=for-the-badge&logo=docker&logoColor=white)
![Juniper](https://img.shields.io/badge/Juniper-Junos-803C94?style=for-the-badge&logo=junipernetworks&logoColor=white)
![Status](https://img.shields.io/badge/Status-Active-success?style=for-the-badge)

Este projeto automatiza o backup de configurações de roteadores Juniper de forma segura e eficiente, utilizando Docker e Python.

## ✨ Funcionalidades

- **🔒 Conexão Segura**: Utiliza SSH para conectar aos dispositivos.
- **📂 Organização Automática**: Salva backups com timestamp (`hostname_YYYYMMDD_HHMMSS.conf`).
- **🧹 Limpeza Automática**: Mantém apenas os últimos `N` backups (configurável), economizando espaço.
- **🐳 Containerizado**: Roda isolado em um container Docker, fácil de implantar.
- **⏰ Agendamento**: Executa automaticamente de hora em hora (configurável via Cron).

## 🚀 Como Usar

### 1. Pré-requisitos
- Docker e Docker Compose instalados.

### 2. Configuração
Crie um arquivo `.env` na raiz do projeto com suas configurações:

```bash
cp .env.example .env
```

Edite o arquivo `.env`:
```ini
# Lista de IPs ou Hostnames dos roteadores (separados por vírgula)
ROUTER_HOSTS=192.168.1.1,192.168.1.2

# Porta SSH (Padrão: 22, ou personalize se necessário)
PORT=22

# Credenciais de Acesso
JUNIPER_USERNAME=seu_usuario
JUNIPER_PASSWORD=sua_senha

# Configurações de Backup
BACKUP_DIR=/backups
MAX_BACKUPS=10
```

### 3. Executando
Para iniciar o serviço de backup automático (rodando em segundo plano):

```bash
docker compose up --build -d
```

O container irá iniciar e agendar o backup para rodar **a cada hora** (minuto 0).

### 4. Verificando Logs
Para ver se o backup está rodando ou identificar erros:

```bash
docker compose logs -f
```

### 5. Onde ficam os backups?
Os arquivos são salvos na pasta `backups/` dentro do diretório do projeto.

---

## ⚙️ Personalização Avançada

### Alterar Frequência (Cron)
Para mudar o agendamento, edite o arquivo `crontab`:

- **Padrão (Hora em hora):** `0 * * * *`
- **Todo dia às 03:00:** `0 3 * * *`
- **A cada 15 minutos:** `*/15 * * * *`

Após alterar, reinicie o container:
```bash
docker compose up --build -d
```
