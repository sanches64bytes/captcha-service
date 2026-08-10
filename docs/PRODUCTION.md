# Operação em VPS ou EC2

Esta aplicação pode ser executada diretamente em uma máquina Linux, sem
containers. A arquitetura recomendada é:

```text
Cliente → Nginx/HTTPS → Gunicorn/Django → PostgreSQL
                                      ↘ Redis/cache
                                      ↘ Celery worker → CaptchaAI
```

## Requisitos do servidor

Recomendação para Ubuntu 24.04 LTS ou equivalente:

- Python 3.14 ou superior;
- `uv`;
- PostgreSQL 16 ou superior;
- Redis 7 ou superior;
- Nginx;
- Certbot para HTTPS;
- grupo de segurança/firewall permitindo somente SSH e HTTP/HTTPS.

Não exponha as portas 5432 e 6379 à internet. Elas devem aceitar conexões
somente de `127.0.0.1` ou da rede privada necessária.

## Usuário e código

Crie um usuário dedicado e instale o projeto em `/opt`:

```bash
sudo useradd --system --home /opt/captcha-api --shell /usr/sbin/nologin captcha-api
sudo mkdir -p /opt/captcha-api
sudo chown captcha-api:captcha-api /opt/captcha-api
sudo -u captcha-api git clone <URL_DO_REPOSITORIO> /opt/captcha-api
cd /opt/captcha-api
uv sync --no-dev
```

## PostgreSQL

Crie um banco e um usuário sem privilégios administrativos:

```bash
sudo -u postgres createuser --pwprompt captcha_api
sudo -u postgres createdb --owner=captcha_api captcha_api
```

## Redis

Configure uma senha no `/etc/redis/redis.conf`:

```text
bind 127.0.0.1 ::1
protected-mode yes
requirepass <senha-forte-do-redis>
appendonly yes
```

Depois reinicie o serviço:

```bash
sudo systemctl restart redis-server
sudo systemctl enable redis-server
```

## Variáveis de ambiente

```bash
sudo install -o root -g captcha-api -m 0640 .env.production.example /etc/captcha-api.env
sudoedit /etc/captcha-api.env
```

Configure pelo menos:

```env
DJANGO_SECRET_KEY=<valor-aleatorio-longo>
DJANGO_DEBUG=false
DJANGO_ALLOWED_HOSTS=api.seudominio.com
DJANGO_SECURE_SSL_REDIRECT=true
DJANGO_TRUST_PROXY=true
DJANGO_HSTS_SECONDS=31536000
DB_NAME=captcha_api
DB_USER=captcha_api
DB_PASSWORD=<senha-do-postgresql>
DB_HOST=127.0.0.1
DB_PORT=5432
REDIS_PASSWORD=<senha-do-redis>
REDIS_URL=redis://:<senha-do-redis>@127.0.0.1:6379/0
CACHE_URL=redis://:<senha-do-redis>@127.0.0.1:6379/2
CELERY_BROKER_URL=redis://:<senha-do-redis>@127.0.0.1:6379/0
CELERY_RESULT_BACKEND=redis://:<senha-do-redis>@127.0.0.1:6379/1
CAPTCHAAI_API_KEY=<chave-do-provider>
CELERY_LOGLEVEL=INFO
CELERY_CONCURRENCY=4
```

O arquivo deve permanecer fora do repositório e com permissões restritas.

## Migrations e arquivos estáticos

```bash
cd /opt/captcha-api
sudo -u captcha-api env $(sudo cat /etc/captcha-api.env | xargs) \
  /opt/captcha-api/.venv/bin/python manage.py migrate --noinput
sudo -u captcha-api env $(sudo cat /etc/captcha-api.env | xargs) \
  /opt/captcha-api/.venv/bin/python manage.py collectstatic --noinput
```

Para valores que contenham espaços ou caracteres especiais, prefira executar
essas operações com `systemd-run --property=EnvironmentFile=/etc/captcha-api.env`
ou exportar as variáveis em um shell seguro; o comando com `xargs` é apenas uma
forma simples para valores sem espaços.

Crie o administrador:

```bash
sudo -u captcha-api env $(sudo cat /etc/captcha-api.env | xargs) \
  /opt/captcha-api/.venv/bin/python manage.py createsuperuser
```

## Serviços systemd

Instale as unidades fornecidas:

```bash
sudo cp deploy/captcha-api.service /etc/systemd/system/
sudo cp deploy/captcha-worker.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now captcha-api captcha-worker
sudo systemctl status captcha-api captcha-worker
```

Os logs podem ser acompanhados com:

```bash
journalctl -u captcha-api -f
journalctl -u captcha-worker -f
```

## Nginx e HTTPS

Edite `deploy/nginx.conf`, substitua `api.example.com` pelo domínio real e
instale:

```bash
sudo cp deploy/nginx.conf /etc/nginx/sites-available/captcha-api
sudo ln -s /etc/nginx/sites-available/captcha-api /etc/nginx/sites-enabled/captcha-api
sudo nginx -t
sudo systemctl reload nginx
sudo certbot --nginx -d api.seudominio.com
```

O endpoint de saúde é `GET /health/` e não exige API key. Use-o no health check
do EC2 load balancer ou monitor externo. As rotas de tarefas continuam exigindo
`X-API-Key`.

## Deploy de novas versões

```bash
cd /opt/captcha-api
sudo -u captcha-api git fetch --all
sudo -u captcha-api git checkout <versao>
sudo -u captcha-api uv sync --no-dev
sudo systemctl stop captcha-worker captcha-api
sudo -u captcha-api /opt/captcha-api/.venv/bin/python manage.py migrate --noinput
sudo -u captcha-api /opt/captcha-api/.venv/bin/python manage.py collectstatic --noinput
sudo systemctl start captcha-api captcha-worker
```

Faça backup do PostgreSQL antes de migrations importantes. O Redis guarda estado
temporário, tarefas e contadores de threads; mantenha persistência para evitar
perdas durante reinícios, mas não o trate como substituto do backup do banco.

## Escala e observabilidade

Para aumentar o processamento, ajuste `CELERY_CONCURRENCY` e, em máquinas com
mais capacidade, use mais workers systemd ou instâncias EC2 separadas. O limite
de threads por chave é coordenado pelo Redis.

Monitore `/health/`, reinícios dos serviços, erros HTTP 5xx, tarefas `failed`,
timeouts do CaptchaAI, tamanho da fila Celery, memória do Redis e espaço do
PostgreSQL. Nunca registre API keys, tokens, imagens Base64 ou credenciais.
