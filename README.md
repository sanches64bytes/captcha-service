# Visão Geral

Este projeto disponibiliza uma API para resolução de CAPTCHAs.

> **Estado atual:** a primeira etapa implementa criação e consulta de tarefas,
> Redis/cache, Celery, autenticação por API key e controle de threads por usuário.
> Consulte
> [`docs/TASK_API.md`](docs/TASK_API.md) para detalhes internos ou o
> [`guia de integração do cliente`](docs/CLIENT_GUIDE.md) para consumir a API.

Cada usuário possui uma **chave de API**, utilizada para autenticar suas requisições e acessar os recursos disponíveis.

## Início rápido

Requisitos: Python 3.14 ou superior, Redis e `uv`.

```bash
uv sync --dev
cp .env.example .env
# edite .env e substitua os placeholders; depois carregue-o no shell
set -a
source .env
set +a
uv run python manage.py migrate
uv run python manage.py check
```

Configure `CAPTCHAAI_API_KEY` e `DJANGO_SECRET_KEY` no `.env`. Em seguida,
inicie a API e um worker Celery em terminais separados:

```bash
uv run python manage.py runserver
uv run celery -A conf worker --loglevel=INFO
```

O Redis deve estar disponível nas URLs definidas por `REDIS_URL`, `CACHE_URL` e
`CELERY_RESULT_BACKEND`. Para criar uma chave de acesso localmente, crie um
superusuário e utilize o Django Admin:

```bash
uv run python manage.py createsuperuser
```

Depois, cadastre uma `Chave` em `/admin/`, defina `max_threads` e use o valor de
`api_key` no cabeçalho `X-API-Key`. O guia completo para clientes está em
[`docs/CLIENT_GUIDE.md`](docs/CLIENT_GUIDE.md).

A principal funcionalidade consiste em receber uma solicitação de resolução de CAPTCHA, adicioná-la a uma fila de processamento e retornar imediatamente um identificador único da tarefa, chamado `task_id`.

O sistema também implementa controle de concorrência por usuário, baseado em **threads de execução disponíveis**, garantindo limitação justa de uso e escalabilidade do processamento.

O fluxo geral é:

```text
Cliente
  │
  │ Envia CAPTCHA
  ▼
API
  │
  │ Cria tarefa (respeitando limite de threads do usuário)
  ▼
Celery
  │
  │ Envia para processamento
  ▼
CaptchaAI (Thread Pool)
  │
  │ Processa em paralelo conforme threads disponíveis
  ▼
Cache
  │
  │ Armazena temporariamente o resultado
  ▼
Cliente consulta usando task_id
```

---

## Fluxo de funcionamento

1. O usuário envia um CAPTCHA para a API utilizando sua chave de autenticação.
2. A API valida a requisição e verifica a quantidade de **threads disponíveis para aquele usuário**.
3. Se o usuário ainda possuir threads livres, a tarefa é criada e adicionada à fila de processamento.
4. Um `task_id` é retornado imediatamente ao usuário.
5. O processamento ocorre de forma assíncrona utilizando **Celery**.
6. O worker encaminha a tarefa para o **CaptchaAI**, que executa a resolução utilizando seu sistema de threads.
7. Enquanto a tarefa estiver em processamento, o usuário pode consultar seu status utilizando o `task_id`.
8. Quando a resolução for concluída, o resultado fica disponível para consulta.
9. Após **30 minutos**, os dados da tarefa são automaticamente removidos do cache.

---

## Controle de concorrência por threads (usuário)

Cada usuário possui um limite de **threads simultâneas**, que define quantas tarefas ele pode executar ao mesmo tempo.

Exemplo:

* Usuário A possui **2 threads**
* Ele pode ter no máximo **2 tarefas em execução simultânea**
* Enquanto as 2 threads estiverem ocupadas, uma nova requisição será **negada**

### Comportamento do sistema

* Se o usuário ainda tiver threads disponíveis:

  * A tarefa é aceita imediatamente
  * O contador de threads é decrementado

* Se o usuário atingir o limite:

  * A nova requisição é **negada**
  * Nenhuma tarefa é criada ou adicionada a uma fila de espera
  * O cliente pode enviar outra requisição depois que uma thread for liberada

* Quando uma tarefa finaliza:

  * A thread é liberada automaticamente
  * Uma nova requisição do usuário pode ser aceita

Esse mecanismo garante:

* controle de uso por cliente
* prevenção de sobrecarga individual
* distribuição justa de recursos
* previsibilidade de performance

---

## Armazenamento das tarefas

As tarefas de resolução não são armazenadas permanentemente no banco de dados.

Informações como:

```text
task_id
status
resultado
erros
metadados temporários
```

são armazenadas exclusivamente em um sistema de **cache**, como Redis.

Cada tarefa possui um tempo de expiração (`TTL`) de aproximadamente:

```text
30 minutos
```

Após esse período, tanto a tarefa quanto seu resultado são automaticamente removidos.

---

## Processamento assíncrono

O processamento das solicitações é realizado utilizando **Celery**.

A API não aguarda a resolução do CAPTCHA para responder ao cliente.

Exemplo de requisição:

```http
POST /api/v1/tasks/
```

Resposta imediata:

```json
{
  "task_id": "4dd69e6c-781b-49ba-b59d-f3201507121f",
  "status": "processing"
}
```

Enquanto isso, o Celery processa a tarefa em segundo plano.

Consulta de status:

```http
GET /api/v1/tasks/4dd69e6c-781b-49ba-b59d-f3201507121f/
```

Em processamento:

```json
{
  "task_id": "4dd69e6c-781b-49ba-b59d-f3201507121f",
  "status": "processing"
}
```

Concluído:

```json
{
  "task_id": "4dd69e6c-781b-49ba-b59d-f3201507121f",
  "status": "completed",
  "result": {
    "solution": "..."
  }
}
```

---

## Integração com CaptchaAI

A resolução dos CAPTCHAs é realizada através da integração com o **CaptchaAI**.

A aplicação atua como uma camada intermediária entre o usuário e o serviço de resolução:

```text
Usuário
   ↓
Nossa API
   ↓
Celery
   ↓
CaptchaAI (Thread Pool)
   ↓
Nossa API
   ↓
Usuário
```

A API é responsável por:

* autenticação dos usuários
* controle de concorrência por threads
* criação e gerenciamento de tarefas
* filas de processamento
* tratamento de erros
* consulta de status
* normalização de respostas
* expiração automática de dados

---

## Integração com Threads do CaptchaAI

O CaptchaAI utiliza um sistema interno de **threads de execução**, permitindo processamento paralelo de CAPTCHAs.

Quanto maior o número de threads disponíveis no CaptchaAI, maior será a capacidade de processamento simultâneo de tarefas.

### Funcionamento das threads

* Cada thread representa uma unidade independente de execução
* As tarefas são distribuídas dinamicamente entre threads disponíveis
* Múltiplos CAPTCHAs podem ser processados ao mesmo tempo
* O sistema evita bloqueios entre execuções

### Escalabilidade

* Aumentar o número de threads no CaptchaAI aumenta diretamente a capacidade de processamento
* O sistema pode escalar horizontalmente com mais workers e threads
* A performance total depende da combinação entre:

  * threads do CaptchaAI
  * workers do Celery
  * limite de concorrência por usuário

### Fluxo com threads

```text
Celery Worker
   │
   │ envia tarefa
   ▼
CaptchaAI Thread Pool
   │
   ├── Thread 1 → execução
   ├── Thread 2 → execução
   ├── Thread 3 → execução
   │
   ▼
Resultado consolidado
   │
   ▼
Cache
```

---

## Estados de uma tarefa

Uma tarefa pode possuir os seguintes estados:

```text
PENDING
PROCESSING
COMPLETED
FAILED
```

### `PENDING`

A tarefa foi criada com uma thread disponível e está aguardando o início da execução. Requisições recebidas quando o limite de threads já foi atingido são negadas e, portanto, não recebem esse estado.

### `PROCESSING`

A tarefa está sendo executada por um worker e/ou thread do CaptchaAI.

### `COMPLETED`

A tarefa foi concluída com sucesso e o resultado está disponível.

### `FAILED`

Ocorreu um erro durante o processamento.

---

## Arquitetura

A arquitetura inicial é composta por:

```text
Client
  │
  ▼
API
  │
  ├── Autenticação por API Key
  ├── Controle de threads por usuário
  ├── Validação de requisição
  ├── Criação de task_id
  │
  ▼
Redis / Cache
  │
  │ estado da tarefa + controle de concorrência
  ▼
Celery
  │
  ▼
CaptchaAI (Thread Pool)
```

---

## Principais componentes

* **API:** interface principal de entrada das requisições
* **API Key:** autenticação e identificação de usuários
* **Controle de Threads:** limita concorrência por usuário
* **Celery:** processamento assíncrono das tarefas
* **Redis:** broker e armazenamento temporário
* **CaptchaAI:** serviço de resolução com execução paralela por threads
* **Cache:** armazenamento temporário de estado e resultados

---

## Objetivo

O objetivo do projeto é fornecer uma camada de abstração sobre o CaptchaAI, oferecendo uma API própria, simples e padronizada para gerenciamento de tarefas de resolução de CAPTCHA em ambientes autorizados.

A API centraliza:

* controle de concorrência por usuário
* gerenciamento de threads
* filas de execução
* processamento assíncrono
* integração com CaptchaAI
* expiração automática de tarefas

Assim, o cliente não precisa lidar diretamente com a complexidade do CaptchaAI, utilizando apenas uma interface unificada e controlada.
